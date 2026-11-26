"""
Problem reports sent on their own (off by default; Settings → Problem reports).

When screen reading misses something it should see (a mini map title that names no map, the HUD's
EXP not read, the HUD or the mini map lost while you play, a read that hit an error), Companion
keeps what's needed to fix it: the game's picture at full size, what the reader saw in it and in
the reads before, the game area's size and UI scale, the screen, Companion's version and settings,
and the log's last lines. It goes to the group's report server (reports.json, built in like
discord.json), which files it in a private GitHub repository. Nothing goes anywhere while the
setting is off, and never anything from Discord.

  - Not a flood: each problem (its kind and what was misread, e.g. the title text) is sent at most
    once an hour, and at most DAY_CAP reports a day.
  - Nothing lost: a report is written to data/report_outbox/ first and stays there until the
    server answers 2xx; at most OUTBOX_MAX wait, the oldest go first, none older than a week.
  - Small enough to send: the server takes up to about 4 MB, so the picture is PNG when it fits,
    else JPEG with the area that matters kept as PNG beside it.

Watch.see(frame, seen, ...) is fed every full read and decides; Reports does the keeping and sending.
"""
import base64
import io
import json
import platform
import re
import shutil
import threading
import time
import traceback
import uuid
from pathlib import Path

from paths import APP_DIR, DATA_DIR, RES_DIR, load_json, save_json

OUTBOX = DATA_DIR / "report_outbox"
STATE = DATA_DIR / "reports_state.json"
COOLDOWN = 3600.0      # the same problem is sent again only after an hour
DAY_CAP = 25           # reports a day, whatever happens
OUTBOX_MAX = 40
OUTBOX_DAYS = 7
MAX_BYTES = 3_000_000  # the files' size before base64 (x 4/3): under the server's 4.5 MB
TIMEOUT = 30
SEND_EVERY = 20.0
BACKOFF_MAX = 1800.0
HISTORY = 15           # earlier reads' gist kept for a report
LOG_LINES = 80
PERSONAL = ("discord_id", "discord_name")

# how many full reads in a row before it counts
MAP_MISSED_READS = 3   # the title read, but names no map
EXP_MISSED_READS = 5   # the HUD found, its EXP not read
LOST_READS = 10        # the HUD or the mini map seen lately, now gone
LOST_RECENT = 600.0    # ...where "lately" is this many seconds
NEAR_MIN = 60          # a misread title is keyed by the closest map name when it's at least this close


def load_reports_config():
    """{"url", "key"} from reports.json bundled in the build (or next to the source), or None."""
    for folder in (RES_DIR, APP_DIR):
        cfg = load_json(folder / "reports.json", None)
        if isinstance(cfg, dict) and str(cfg.get("url", "")).startswith("https://") and cfg.get("key"):
            return {"url": cfg["url"], "key": str(cfg["key"])}
    return None


def slug(text, n=40):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:n] or "x"


def gist(seen):
    """What one read saw, in short: enough to follow how reads went before a problem."""
    seen = seen or {}
    hud = seen.get("hud") or {}
    m = seen.get("map") or {}
    return {"windows": sorted((seen.get("windows") or {}).keys()), "scale": seen.get("scale"),
            "level": hud.get("level"), "exp": hud.get("exp"), "exp_pct": hud.get("exp_pct"),
            "map": m.get("name"), "street": m.get("street"), "map_missed": seen.get("map_missed"),
            "error": seen.get("error")}


def jsonable(v, depth=0):
    """seen, made safe for JSON: no pictures, nothing endless."""
    if depth > 6:
        return None
    if isinstance(v, dict):
        return {str(k): jsonable(x, depth + 1) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [jsonable(x, depth + 1) for x in list(v)[:200]]
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if hasattr(v, "item"):          # numpy's numbers
        try:
            return jsonable(v.item(), depth + 1)
        except Exception:
            pass
    return repr(v)[:200]


def encode(frame, regions=(), budget=MAX_BYTES):
    """{name: bytes}: the frame as PNG if it fits the budget, else as JPEG with each region
    (l, t, r, b in pixels) kept as a PNG crop beside it."""
    buf = io.BytesIO()
    frame.convert("RGB").save(buf, "PNG", optimize=False, compress_level=6)
    if buf.tell() <= budget:
        return {"frame.png": buf.getvalue()}
    out = {}
    for i, (l, t, r, b) in enumerate(regions):
        l, t = max(0, int(l)), max(0, int(t))
        r, b = min(frame.width, int(r)), min(frame.height, int(b))
        if r - l > 4 and b - t > 4:
            c = io.BytesIO()
            frame.crop((l, t, r, b)).convert("RGB").save(c, "PNG")
            out[f"crop{i + 1}_{l}_{t}.png"] = c.getvalue()
    left = budget - sum(len(x) for x in out.values())
    for q in (92, 85, 75, 60):
        j = io.BytesIO()
        frame.convert("RGB").save(j, "JPEG", quality=q)
        if j.tell() <= left:
            out["frame.jpg"] = j.getvalue()
            break
    return out


class Reports:
    """Keeps reports on disk and sends them. enabled(): the setting. post(url, json=, headers=,
    timeout=): requests.post, or a stand-in in tests."""

    def __init__(self, enabled, setup=None, post=None, outbox=OUTBOX, state_path=STATE, clock=time.time, get=None):
        self.enabled = enabled
        self.setup = setup
        self.post = post
        self.get = get              # requests.get: asks the server whether it still wants this problem's pictures
        self.outbox = Path(outbox)
        self.state_path = Path(state_path)
        self.clock = clock
        self.lock = threading.RLock()
        st = load_json(self.state_path, {}) or {}
        self.install = st.get("install") or uuid.uuid4().hex[:12]
        self.last = st.get("last", {})            # problem key -> when it was last kept
        self.day = st.get("day", {"date": "", "count": 0})
        self.sent = int(st.get("sent", 0))
        self.error = ""
        self.next_at = 0.0
        self.wait = SEND_EVERY
        self._save_state()

    # ------------------------------------------------------------ keeping
    def _save_state(self):
        try:
            save_json(self.state_path, {"install": self.install, "last": self.last, "day": self.day, "sent": self.sent})
        except OSError:
            pass

    def ready(self):
        return bool(self.setup) and bool(self.enabled())

    def may_keep(self, key):
        """Whether a report for this problem may be kept now (setting on, not sent lately, under the day's cap)."""
        if not self.ready():
            return False
        now = self.clock()
        today = time.strftime("%Y-%m-%d", time.localtime(now))
        with self.lock:
            if self.day.get("date") != today:
                self.day = {"date": today, "count": 0}
            if self.day["count"] >= DAY_CAP:
                return False
            return now - self.last.get(key, -1e18) >= COOLDOWN

    def keep(self, kind, key, meta, frame=None, regions=(), extra_frames=None):
        """Write a report to the outbox. extra_frames: {name: picture} sent as JPEG (e.g. the last
        frame where the same thing did read). Returns the report's folder, or None."""
        if not self.may_keep(key):
            return None
        now = self.clock()
        rid = f"{time.strftime('%Y%m%d-%H%M%S', time.localtime(now))}-{kind}-{uuid.uuid4().hex[:6]}"
        files = {}
        try:
            if frame is not None:
                files.update(encode(frame, regions))
            room = MAX_BYTES - sum(len(v) for v in files.values())
            for name, img in (extra_frames or {}).items():
                j = io.BytesIO()
                img.convert("RGB").save(j, "JPEG", quality=80)
                if j.tell() <= room:
                    files[f"{name}.jpg"] = j.getvalue()
                    room -= j.tell()
        except Exception as e:      # a picture that won't encode: the report still goes, without it
            meta = {**meta, "picture_error": repr(e)}
        meta = {**meta, "id": rid, "kind": kind, "key": key, "install": self.install,
                "made": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)), "files": sorted(files)}
        folder = self.outbox / rid
        try:
            folder.mkdir(parents=True, exist_ok=True)
            for name, data in files.items():
                (folder / name).write_bytes(data)
            (folder / "report.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False, default=str),
                                                encoding="utf-8")
        except OSError:
            shutil.rmtree(folder, ignore_errors=True)
            return None
        with self.lock:
            self.last[key] = now
            self.last = {k: t for k, t in self.last.items() if now - t < COOLDOWN * 24}
            self.day["count"] = self.day.get("count", 0) + 1
            self._save_state()
        self._trim()
        return folder

    def waiting(self):
        if not self.outbox.is_dir():
            return []
        return sorted(p for p in self.outbox.iterdir() if p.is_dir() and (p / "report.json").exists())

    def pending(self):
        return len(self.waiting())

    def _trim(self):
        now = time.time()         # files' times are the real clock's
        ws = self.waiting()
        for p in ws[:max(0, len(ws) - OUTBOX_MAX)]:
            shutil.rmtree(p, ignore_errors=True)
        for p in self.waiting():
            try:
                if now - p.stat().st_mtime > OUTBOX_DAYS * 86400:
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass

    # ------------------------------------------------------------ sending
    def payload(self, folder):
        meta = json.loads((folder / "report.json").read_text(encoding="utf-8"))
        files = {p.name: base64.b64encode(p.read_bytes()).decode("ascii")
                 for p in sorted(folder.iterdir()) if p.is_file() and p.name != "report.json"}
        return {"report": meta, "files": files}

    def wants_files(self, meta):
        """Whether the server still wants pictures of this problem: it keeps a few of each (and a few
        more for a screen size it hasn't seen it at, or once it's back after being fixed), and only
        counts the rest. When it can't be asked, the pictures go: the server drops them if unwanted."""
        if self.get is None:
            return True
        size = meta.get("frame_size") or []
        try:
            r = self.get(self.setup["url"], params={"key": meta.get("key", ""), "version": meta.get("version", ""),
                                                    "size": "x".join(map(str, size))},
                         headers={"X-Companion-Key": self.setup["key"]}, timeout=TIMEOUT)
            if getattr(r, "status_code", 0) == 200:
                return bool(r.json().get("want_files", True))
        except Exception:
            pass
        return True

    def send_one(self):
        """Send the oldest waiting report. True if one went. A problem the server already has enough
        pictures of goes without them: it only adds one to its count."""
        if not self.ready() or self.post is None:
            return False
        ws = self.waiting()
        if not ws:
            return False
        folder = ws[0]
        try:
            body = self.payload(folder)
            if body["files"] and not self.wants_files(body["report"]):
                body = {"report": {**body["report"], "files": [], "count_only": True}, "files": {}}
        except (OSError, ValueError):
            shutil.rmtree(folder, ignore_errors=True)       # a broken report can't ever go
            return False
        try:
            r = self.post(self.setup["url"], json=body, headers={"X-Companion-Key": self.setup["key"]}, timeout=TIMEOUT)
        except Exception as e:
            self.error = f"Couldn't reach the report server: {type(e).__name__}"
            return False
        code = getattr(r, "status_code", 0)
        if 200 <= code < 300:
            shutil.rmtree(folder, ignore_errors=True)
            with self.lock:
                self.sent += 1
                self._save_state()
            self.error = ""
            return True
        if code in (400, 413, 422):         # this one will never be taken: drop it, go on
            shutil.rmtree(folder, ignore_errors=True)
            self.error = f"The report server refused a report ({code})"
            return False
        self.error = "This build's report key isn't accepted" if code in (401, 403) else f"The report server answered {code}"
        return False

    def pump(self):
        """One step of the sending loop, at most every SEND_EVERY seconds; backs off while it fails."""
        now = self.clock()
        if now < self.next_at:
            return
        if self.send_one():
            self.wait = SEND_EVERY
            self.next_at = now + 1.0         # the next one soon
        elif self.error and self.pending():
            self.wait = min(BACKOFF_MAX, self.wait * 2)
            self.next_at = now + self.wait
        else:
            self.next_at = now + SEND_EVERY

    def start(self):
        def run():
            while True:
                try:
                    self.pump()
                except Exception:
                    pass
                time.sleep(1.0)
        threading.Thread(target=run, daemon=True, name="reports").start()

    def status(self):
        return {"setup": bool(self.setup), "pending": self.pending(), "sent": self.sent, "error": self.error,
                "today": self.day.get("count", 0) if self.day.get("date") == time.strftime("%Y-%m-%d") else 0}


class Watch:
    """Looks at every full read for what should have read and didn't, and keeps a report for it.
    context(): the rest of what a report tells (version, settings, map, profile, game window)."""

    def __init__(self, reports, context=None, clock=time.time, near=None):
        self.reports = reports
        self.near = near           # near(text) -> (the map name closest to a misread title, score), or None
        self.context = context or (lambda: {})
        self.clock = clock
        self.history = []          # the last reads, in short (gist), with when
        self.runs = {}             # condition -> full reads in a row it held
        self.seen_at = {}          # "hud" / "map" -> when it last read
        self.last_ok = None        # the last frame where the HUD's EXP and the map both read
        self.extra = {}            # the reader's own state at this read (title picture scores, ...)

    def _meta(self, kind, seen, frame, why):
        meta = {"why": why, "seen": jsonable(seen), "history": self.history[:-1],
                "frame_size": [frame.width, frame.height] if frame is not None else None,
                "runs": dict(self.runs), "reader": jsonable(self.extra), "log": _log_tail(),
                "system": {"platform": platform.platform(), "python": platform.python_version()}}
        try:
            meta.update(jsonable(self.context()))
        except Exception as e:
            meta["context_error"] = repr(e)
        return meta

    def _run(self, name, holds):
        self.runs[name] = self.runs.get(name, 0) + 1 if holds else 0
        return self.runs[name]

    def report(self, kind, key, frame, seen, why, regions=(), with_last_ok=False):
        if not self.reports.may_keep(key):
            return None
        extra = {"last_ok": self.last_ok} if with_last_ok and self.last_ok is not None else None
        return self.reports.keep(kind, key, self._meta(kind, seen, frame, why), frame, regions, extra)

    def see(self, frame, seen, map_box=None, extra=None):
        """A full read. map_box: where the mini map's title was last found (l, t, r, b), if known.
        extra: the reader's own state, told in a report."""
        if not self.reports.ready() or not seen or seen.get("quick") or seen.get("error"):
            return []
        self.extra = extra or {}
        now = self.clock()
        self.history = (self.history + [{"t": round(now, 1), **gist(seen)}])[-HISTORY:]
        hud = seen.get("hud")
        size = f"{frame.width}x{frame.height}"
        s = seen.get("scale")
        if hud:
            self.seen_at["hud"] = now
        if seen.get("map"):
            self.seen_at["map"] = now
        if hud and hud.get("exp") is not None and seen.get("map"):
            self.last_ok = frame
        W, H = frame.width, frame.height
        hud_area = [(0, int(H * 0.88), W, H)]
        map_area = [map_box] if map_box else [(0, 0, int(W * 0.4), int(H * 0.35))]
        kept = []

        missed = seen.get("map_missed")
        if self._run("map_missed", bool(missed) and not seen.get("map")) >= MAP_MISSED_READS:
            # one map misread a different way each time ("Hennes Huntng", "Henes Hunting") is one
            # problem: keyed by the map it's closest to, when that's clear enough
            near = None
            try:
                near = self.near(missed) if self.near else None
            except Exception:
                pass
            name = near[0] if near and near[1] >= NEAR_MIN else None
            seen = {**seen, "nearest_map": list(near) if near else None}
            kept.append(self.report("map_missed", f"map_missed:{slug(name or missed)}", frame, seen,
                                    f"The mini map's title read as {missed!r}, which names no map"
                                    + (f" (closest: {name})" if name else ""), map_area, True))
        if self._run("exp_missed", bool(hud) and hud.get("exp") is None) >= EXP_MISSED_READS:
            kept.append(self.report("exp_missed", f"exp_missed:{size}:{s}", frame, seen,
                                    "The HUD was found but its EXP didn't read", hud_area, True))
        recent = lambda k: now - self.seen_at.get(k, -1e18) < LOST_RECENT
        if self._run("hud_lost", not hud and recent("hud")) >= LOST_READS:
            kept.append(self.report("hud_lost", f"hud_lost:{size}:{s}", frame, seen,
                                    "The HUD read a little while ago and not since", hud_area, True))
        if self._run("map_lost", bool(hud) and not seen.get("map") and not missed and recent("map")) >= LOST_READS:
            kept.append(self.report("map_lost", f"map_lost:{size}:{s}", frame, seen,
                                    "The mini map read a little while ago and not since (closed, or lost?)", map_area, True))
        for k in [k for k in self.runs if self.runs[k] >= LOST_READS * 3]:
            self.runs[k] = 0          # long over: let it count again (the hour between still holds)
        return [k for k in kept if k]

    def error(self, frame, exc):
        """A read that hit an error: its traceback and its picture."""
        if not self.reports.ready():
            return None
        tb = traceback.extract_tb(exc.__traceback__)
        where = f"{Path(tb[-1].filename).stem}:{tb[-1].lineno}" if tb else "?"
        key = f"error:{type(exc).__name__}:{where}"
        meta_seen = {"traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))}
        return self.report("error", key, frame, meta_seen, f"A read hit {type(exc).__name__}: {exc}")

    def shop_unread(self, frame, seen):
        return self.report("shop_unread", f"shop_unread:{frame.width}x{frame.height}", frame, seen,
                           "A player shop was found but none of its items read")


def _log_tail():
    try:
        import applog
        return applog.tail(LOG_LINES)
    except Exception:
        return []
