"""
Companion for MapleStory Classic World.

  Companion.exe  (or: python companion.py)

Opens Companion's own window (closing it quits) and a dashboard in your browser on this PC
(localhost only).
Out of the box it only uses public game data and prices: it doesn't touch the game or your screen.
Screen reading and on-game drawing are optional and switched on in the Settings tab.

  --report     prices you've seen yourself, per item (needs screen reading)
  --refresh    re-download game data now
  --no-browser don't open the dashboard automatically
  --second-copy start even while Companion is already running (a new build's smoke test)
"""
import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent / "app"))   # the app's modules

import os

# The matrix library's own threads, before numpy loads: one. Its many threads fight over the cores and
# took 29 s, every core full (the PC stuck), for a sum one thread does in 0.6 s (2026-11-17, full
# screen's width check); the screen reading's sums are all small.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import json
import queue
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import cozy
import discord_link
from reader import CORNER_READ, MIN_HEIGHT
from gamedata import JOBS, GameData, portal_meta

import applog
import autoreport
import paths
from paths import APP_DIR, CACHE_DIR, DATA_DIR, LOGS_DIR, RES_DIR, load_json, save_json
from version import VERSION

HERE = APP_DIR
PROFILE = DATA_DIR / "profile.json"
PORT = 8765

DEFAULT_PROFILE = {"job": "Beginner", "level": 10, "mesos": 80000, "acc": None, "skill_plan": {},
                   "current_map": None, "quests_done": [], "island": None,
                   # filled in by screen reading: what the game itself shows
                   "name": None, "skills_now": {}, "sp": None, "quests_active": []}


def load_profile():
    p = dict(DEFAULT_PROFILE)
    p.update(load_json(PROFILE, {}))
    return p


def save_profile(state):
    state["profile"]["rev"] = state["profile"].get("rev", 0) + 1   # lets the dashboard notice changes
    save_json(PROFILE, state["profile"])


def on_island(data, prof):
    return data.on_maple_island(int(prof["level"]), prof.get("current_map"), prof.get("island"))


def plan(data, prof, start, goal, came_from=None, taxi=None):
    """A route for state["nav"]: {"steps", "i", "taxi": by cab, "cab": a cab could take part of it}.
    A Regular Cab costs mesos, so the route walks unless `taxi` (None: a Beginner rides, 90 % off).
    None when there's no way at all."""
    if taxi is None:
        taxi = prof.get("job") == "Beginner"
    walk = data.route(start, goal, came_from=came_from)
    if not walk:
        return None
    ride = data.route(start, goal, came_from=came_from, taxi=True)
    cab = bool(ride) and any(s.get("taxi") for s in ride) and not any(s.get("taxi") for s in walk)
    return {"steps": ride if taxi and cab else walk, "i": 0, "taxi": bool(taxi and cab), "cab": cab}


def _replan(data, state, start, came_from=None, taxi=None):
    """The active route again from `start`, the same place and the NPC there kept."""
    nav = state["nav"]
    got = plan(data, state["profile"], start, nav["to"]["id"], came_from, nav.get("taxi") if taxi is None else taxi)
    if got:
        if nav["steps"][-1].get("npc"):     # keep the NPC circled on the last map
            got["steps"][-1]["npc"] = nav["steps"][-1]["npc"]
        nav.update(got)


def choose_taxi(data, state, on):
    """Go to's "Take the cab" / "Walk instead": the route again from the step you're on."""
    nav = state.get("nav")
    if nav:
        _replan(data, state, nav["steps"][nav["i"]]["id"], taxi=bool(on))
        state["queue"].put(("nav",))


def set_current(data, state, mid):
    """Record the map you're on and move the active route to it."""
    came_from = state["profile"].get("current_map")
    state["profile"]["current_map"] = mid
    save_profile(state)
    nav = state.get("nav")
    if nav and mid != came_from and came_from == nav.get("reached") and not nav.get("guide_to"):
        # you got there: walking on ends the route. It used to re-plan back to the destination (or
        # step back along the route) the moment you left it, so Go to never stopped. Only a map
        # read on screen counts as there: "I went through" on the last step isn't (the screen may
        # still show the map before)
        state["nav"] = nav = None
    if nav:
        ids = [s["id"] for s in nav["steps"]]
        if mid in ids:
            nav["i"] = ids.index(mid)
            if nav["steps"][nav["i"]].get("arrived"):
                nav["reached"] = mid
        else:   # wandered off the route: re-plan from here, by cab or not as chosen
            _replan(data, state, mid, came_from)
    state["queue"].put(("nav",))


def guide_plan(data, state):
    """The quest guide: the quest step by step (take it, hunt and collect, see anyone on the way,
    bring it back), and a route to where the first step not done yet happens. A step is done when
    the game's Quest Helper shows its count reached, or when you tick it in the dashboard. The
    route card on the game and the Go to tab show the route, with the step on top."""
    g = state.get("guide")
    if not g:
        return
    q = data.quest(g["id"])
    if not q or str(g["id"]) in {str(x) for x in state["profile"].get("quests_done", [])}:
        # gone, or finished: the Quest window's Completed tab, or Done in the dashboard, also ends
        # it when the "Quest Complete!" notice was missed
        state["guide"] = None
        if q and state.get("nav") and state["nav"].get("guide_to"):
            state["nav"] = None
            state["queue"].put(("nav",))
        return
    prof = state["profile"]
    helper = next((h for h in (state.get("game") or {}).get("helper") or [] if h.get("id") == g["id"]), None)
    have = {n["what"]: n["have"] for n in (helper or {}).get("needs", [])}
    accepted = helper is not None or str(g["id"]) in {str(a.get("id")) for a in prof.get("quests_active", [])}
    steps = data.guide_steps(q, have, accepted, set(g.get("checked", [])), prof.get("current_map"), int(prof["level"]))
    i = next((k for k, st in enumerate(steps) if not st["done"]), len(steps) - 1)
    cur = steps[i]
    target = cur["where"]["id"] if cur.get("where") else None
    needs = [{"what": st["name"], "have": st.get("have"), "need": st["need"], "kind": st["kind"]}
             for st in steps if st["kind"] in ("mob", "item")]
    info = {"id": g["id"], "name": q["name"], "goal": cur["goal"], "text": cur["text"], "task": data.quest_text(q)[1],
            "steps": steps, "step": i, "needs": needs, "done": cur["kind"] == "back",
            "tracked": helper is not None, "where": cur.get("where"), "checked": sorted(g.get("checked", []))}
    g["info"] = info
    cur_map, nav = prof.get("current_map"), state.get("nav")
    # a step with no map to go to (an item no one knows where it drops) stays where you are, so the
    # card on the game shows that step, not the route and step before it
    dest = target or cur_map
    if dest and cur_map in data.maps and (not nav or nav.get("guide_to") != dest):
        got = plan(data, prof, cur_map, dest)
        if got:
            if cur.get("npc") and target:
                got["steps"][-1]["npc"] = cur["npc"]
            state["nav"] = {**got, "to": data.map_info(dest), "guide_to": dest}
    if state.get("nav") and state["nav"].get("guide_to") == dest:
        state["nav"]["quest"] = info
    state["queue"].put(("nav",))


SETTINGS = ["screen_reading", "draw_overlay", "consent", "label_side", "row_tolerance", "name_match_min",
            "price_is_per_bundle", "sound", "auto_interval", "ocr_scale", "nav_corner", "game_title",
            "setup_done", "discord_enabled", "discord_post_sales", "auto_reports"]
DEFAULT_SETTINGS = {"screen_reading": False, "draw_overlay": False, "consent": False, "label_side": "right",
                    "row_tolerance": 14, "name_match_min": 84, "price_is_per_bundle": False, "sound": True,
                    "auto_interval": 2.0, "ocr_scale": 3, "nav_corner": "top-right", "game_title": "MapleStory",
                    "setup_done": False, "discord_enabled": False, "discord_post_sales": True, "auto_reports": False}
RANGES = {"row_tolerance": (4, 60), "name_match_min": (50, 100), "auto_interval": (2.0, 10.0), "ocr_scale": (1, 6)}
CHOICES = {"label_side": ("right", "left", "inside"), "nav_corner": ("top-right", "bottom-right", "bottom-left", "top-left")}


def clean_setting(k, v):
    """The value to store for setting k, or None to ignore it. Keeps scans slow whatever is sent."""
    default = DEFAULT_SETTINGS[k]
    if isinstance(default, bool):
        return v if isinstance(v, bool) else None
    if k in RANGES:
        lo, hi = RANGES[k]
        try:
            return type(default)(min(hi, max(lo, float(v))))
        except (TypeError, ValueError):
            return None
    if k in CHOICES:
        return v if v in CHOICES[k] else None
    v = str(v).strip()[:80]       # game_title
    return v or None


def make_outbox(data, state, cfg):
    """The Discord outbox: sales and messages wait on disk until the #shop-sales webhook takes them.
    Linking your Discord ID is the only way cfg gets discord_id; the token never reaches a file."""
    setup = discord_link.load_discord_config()

    def webhook():
        if not setup or not cfg.get("discord_enabled") or not cfg.get("discord_id"):
            return None
        return setup["webhook"]

    def build(sales):
        mk = data.market
        today = time.strftime("%Y-%m-%d")
        sold = (state.get("myshop") or {}).get("sales") or []
        total = sum(x["price"] for x in sold if time.strftime("%Y-%m-%d", time.localtime(x["ts"])) == today)
        return discord_link.sale_message(sales, cfg["discord_id"], state["profile"].get("name"),
                                         median=lambda n: (mk.items.get(n) or {}).get("p"),
                                         img=data.item_img, total_today=total or None)
    import requests
    box = discord_link.Outbox(discord_link.OUTBOX, webhook, requests.post, build)
    box.setup = setup
    box.start()
    return box


def make_reports(data, state, cfg):
    """Problem reports sent on their own (autoreport): off until Settings → Problem reports is on,
    and only in a build with reports.json. state["report_watch"] is what the screen reader feeds."""
    import requests
    import report
    reports = autoreport.Reports(lambda: bool(cfg.get("auto_reports")), autoreport.load_reports_config(), requests.post)

    def context():
        prof = state["profile"]
        mid = prof.get("current_map")
        return {"version": VERSION, "screen": report.screen(), "game_size": state.get("game_size"),
                "settings": {k: v for k, v in cfg.items() if k not in autoreport.PERSONAL and k != "region"},
                "profile": {"name": prof.get("name"), "job": prof.get("job"), "level": prof.get("level"),
                            "map_id": mid, "map": (data.maps.get(mid) or {}).get("name") if mid else None}}
    state["report_watch"] = autoreport.Watch(reports, context)
    reports.start()
    return reports


def discord_status(state, cfg, port):
    box = state.get("outbox")
    setup = box.setup if box else None
    return {"setup": bool(setup), "linked": bool(cfg.get("discord_id")), "name": cfg.get("discord_name"),
            "enabled": bool(cfg.get("discord_enabled")), "post_sales": bool(cfg.get("discord_post_sales")),
            "authorize": discord_link.authorize_url(setup["client_id"], port) if setup else None,
            "port_ok": port == PORT, "pending": box.pending() if box else 0, "error": box.error if box else ""}


def discord_send(state, cfg, text):
    """A text message to #shop-sales tagging you, if Discord is linked and on."""
    box = state.get("outbox")
    if not (box and box.setup and cfg.get("discord_id") and cfg.get("discord_enabled")):
        return False
    msg = discord_link.text_message(cfg["discord_id"], state["profile"].get("name"), text)
    return box.add("text", msg, f"text:{time.time():.3f}")


DISCORD_PAGE = """<!doctype html><meta charset="utf-8"><title>Companion · Discord</title>
<style>body{font:16px system-ui;background:#16171d;color:#eee;display:grid;place-items:center;height:90vh}
main{max-width:30em;text-align:center}a{color:#8ab4ff}</style>
<main><h2 id="t">Connecting…</h2><p id="m"></p><p><a href="/">Back to the dashboard</a></p></main>
<script>
const h = new URLSearchParams(location.hash.slice(1)), token = h.get("access_token");
history.replaceState(null, "", "/discord");     // the token leaves the address bar at once
const say = (t, m) => { document.getElementById("t").textContent = t; document.getElementById("m").textContent = m; };
if (!token) say("Not connected", h.get("error_description") || new URLSearchParams(location.search).get("error_description") || "Discord didn't send who you are.");
else fetch("/api/discord/link", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({token})})
  .then(r => r.json()).then(j => j.error ? say("Not connected", j.error)
  : say("Connected as " + j.name + " \u2713", "A test message is on its way to #shop-sales, tagging you."))
  .catch(() => say("Not connected", "Companion didn't answer."));
</script>"""


def make_handler(data, state, cfg):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def trusted(self):
            """Only the dashboard itself may use the API: other web pages you visit could otherwise
            reach this port and, say, switch screen reading on (Host check also stops DNS rebinding)."""
            port = self.server.server_address[1]
            ok = {f"localhost:{port}", f"127.0.0.1:{port}"}
            if self.headers.get("Host", "") not in ok:
                return False
            origin = self.headers.get("Origin")
            if self.command == "POST":
                # a JSON content type can't be sent cross-site without a preflight, which we never answer
                if origin is not None and origin.removeprefix("http://") not in ok:
                    return False
                return (self.headers.get("Content-Type") or "").startswith("application/json")
            return origin is None or origin.removeprefix("http://") in ok

        def send(self, code, body, ctype="application/json", cache="no-store"):
            if isinstance(body, bytes):
                raw = body
            else:
                for attempt in range(3):
                    try:    # the screen reader may be adding to these dicts at this very moment
                        raw = json.dumps(body).encode("utf-8")
                        break
                    except RuntimeError:
                        if attempt == 2:
                            raise
                        time.sleep(0.02)
            self.send_response(code)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith(("text/", "application/json")) else ""))
            self.send_header("Cache-Control", cache)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):  # noqa: C901
            if not self.trusted():
                return self.send(403, {"error": "forbidden"})
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            prof = state["profile"]
            try:
                if url.path == "/":
                    return self.send(200, (RES_DIR / "web" / "index.html").read_bytes(), "text/html")
                if url.path in ("/logo.png", "/favicon.ico"):   # the Maple Leaf and Steely Throwing Knives, from the game
                    if url.path == "/logo.png":
                        return self.send(200, (RES_DIR / "web" / "logo.png").read_bytes(), "image/png")
                    return self.send(200, (RES_DIR / "web" / "logo.ico").read_bytes(), "image/x-icon")
                if url.path == "/equip_classic.png":   # Classic's Equipment Inventory window, for the Gear tab
                    return self.send(200, (RES_DIR / "web" / "equip_classic.png").read_bytes(), "image/png", "max-age=86400")
                if url.path == "/api/portal.webp":   # the game's portal, drawn on maps
                    p = data.portal_sprite()
                    return self.send(200, p.read_bytes(), "image/webp", "max-age=86400") if p else self.send(404, {"error": "no portal picture"})
                if url.path == "/api/tomb.png":      # the game's tombstone: deaths on Now
                    p = data.tomb_sprite()
                    return self.send(200, p.read_bytes(), "image/png", "max-age=86400") if p else self.send(404, {"error": "no tombstone picture"})
                if url.path == "/api/portal":
                    return self.send(200, (portal_meta() or {}) if data.portal_sprite() else {})
                if url.path == "/discord":           # where Discord sends you back after Authorize
                    return self.send(200, DISCORD_PAGE.encode("utf-8"), "text/html")
                if url.path == "/api/sellkeep":     # every item hovered this session, with its verdict
                    import advisor
                    out = []
                    for name, h in sorted((state.get("hovered") or {}).items(), key=lambda kv: -kv[1]["ts"]):
                        v = advisor.verdict(name, None, prof, data, data.market, h.get("untradable"))
                        out.append({"name": name, "img": data.item_img(name), "ts": h["ts"],
                                    "starred": name in (prof.get("starred") or []), "bag": bool(h.get("bag")),
                                    "alt": h.get("alt"), **v})
                    return self.send(200, out)
                if url.path == "/api/grind":         # EXP/hr now, the log, and your real EXP/hr per map
                    g = state.get("grind")
                    if not g:
                        return self.send(200, {"available": False})
                    return self.send(200, grind_view(g, data, prof, time.time()))
                if url.path == "/api/allmaps":       # every map of your last 5 levels, for Now's pop-up
                    g = state.get("grind")
                    return self.send(200, g.all_maps(int(prof.get("level") or 1)) if g else [])
                if url.path == "/api/history":       # the grind history, a page at a time
                    g = state.get("grind")
                    page = parse_qs(url.query).get("page", ["0"])[0]
                    return self.send(200, g.history_page(int(page) if page.isdecimal() and len(page) <= 9 else 0) if g else
                                     {"total": 0, "page": 0, "pages": 1, "multi_char": False, "rows": []})
                if url.path.startswith("/api/history/"):     # one session's card
                    g = state.get("grind")
                    card = g.history_card(url.path[len("/api/history/"):]) if g else None
                    return self.send(200, card_view(card, data)) if card else self.send(404, {"error": "not found"})
                if url.path == "/api/myshop":
                    return self.send(200, state.get("myshop") or {"watching": False, "sales": []})
                if url.path == "/api/state":
                    return self.send(200, {"profile": prof, "jobs": list(JOBS), "live": state["live"],
                                           "game": state.get("game") or {}, "has_frame": bool(state.get("frame")),
                                           "deals": state["deals"], "overlay": state["overlay"],
                                           "myshop": state.get("myshop"),
                                           "game_size": state.get("game_size") if state.get("game_found") else None,
                                           "min_height": MIN_HEIGHT,
                                           "screen": {"reading": bool(cfg.get("screen_reading")) and state["overlay"],
                                                      "drawing": bool(cfg.get("draw_overlay")) and state["overlay"]},
                                           "prices": data.market.updated, "nav": state["nav"],
                                           "cozy": {"updated": data.market.cozy.updated, "stale": data.market.cozy.stale,
                                                    "items": len(data.market.cozy.items)},
                                           "guide": (state.get("guide") or {}).get("info"),
                                           "on_island": on_island(data, prof),
                                           "recent": [data.map_info(m) for m in prof.get("recent_nav") or [] if m in data.maps],
                                           "current": data.map_info(prof["current_map"]) if prof.get("current_map") else None})
                if url.path == "/api/train":
                    return self.send(200, data.train(int(q.get("level", prof["level"])), prof.get("acc"), on_island(data, prof)))
                if url.path == "/api/gear":
                    return self.send(200, data.gear(prof["job"], int(prof["level"])))
                if url.path == "/api/skills":
                    now = prof.get("skills_now") or {}
                    return self.send(200, {"skills": data.skill_list(prof["job"], with_beginner=True), "plan": prof.get("skill_plan", {}),
                                           "now": now, "sp": prof.get("sp"),
                                           "next": data.next_points(prof["job"], int(prof["level"]), now, prof.get("stats"))})
                if url.path == "/api/frame.jpg":     # the latest look at the game, for the Live tab
                    if not state.get("frame") or not cfg.get("screen_reading"):
                        return self.send(404, {"error": "no picture yet"})
                    return self.send(200, state["frame"], "image/jpeg")
                if url.path == "/api/seen":          # items you've passed in player shops
                    import sniper
                    return self.send(200, sniper.seen_items(data.market, data.item_img))
                if url.path == "/api/settings":
                    return self.send(200, {**{k: cfg.get(k) for k in SETTINGS}, "screen_available": state["overlay"],
                                           "areas": {"region": bool(cfg.get("region"))},
                                           "game_found": state.get("game_found"),
                                           "game_size": state.get("game_size") if state.get("game_found") else None,
                                           "capture": (state.get("live") or {}).get("capture", "off"),
                                           "capture_error": (state.get("live") or {}).get("capture_error", ""),
                                           "discord": discord_status(state, cfg, self.server.server_address[1]),
                                           "reports": state["reports"].status() if state.get("reports") else {"setup": False}})
                if url.path == "/api/maps":
                    return self.send(200, data.find_maps(q.get("q", "")))
                if url.path == "/api/mobs":          # Train's monster search
                    return self.send(200, data.find_mobs(q.get("q", ""), level=int(prof.get("level") or 1)))
                if url.path == "/api/hunt":          # where a monster lives, nearest to the map you're on first
                    got = data.hunt(q.get("name", ""), prof.get("current_map"))
                    return self.send(200 if got else 404, got or {"error": "That monster doesn't spawn anywhere we know."})
                if url.path in ("/api/mapimg", "/api/mapsize"):   # a map's picture, kept on disk after the first time
                    got = data.map_image(int(q["id"]))
                    if not got:
                        return self.send(404, {"error": "no picture of this map"})
                    path, meta = got
                    if url.path == "/api/mapsize":
                        return self.send(200, meta)
                    return self.send(200, path.read_bytes(), "image/webp", "max-age=86400")
                if url.path == "/api/layout":
                    return self.send(200, data.layout(int(q["id"])))
                if url.path == "/api/here":          # the map you're on (or ?id=): monsters, drops, NPCs, portals
                    mid = int(q.get("id") or prof.get("current_map") or 0)
                    return self.send(200, data.here(mid) if mid in data.maps else {"error": "no map set"})
                if url.path == "/api/nav":
                    return self.send(200, state["nav"])
                if url.path == "/api/quests":
                    helper = (state.get("game") or {}).get("helper") or []
                    active = [h.get("id") for h in helper] + [a.get("id") for a in prof.get("quests_active", [])]
                    return self.send(200, data.quests(int(prof["level"]), prof["job"], prof.get("quests_done", []),
                                                      on_island(data, prof), active))
                self.send(404, {"error": "not found"})
            except Exception as e:
                self.send(500, {"error": str(e)})

        def do_POST(self):
            if not self.trusted():
                return self.send(403, {"error": "forbidden"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}") if n else {}
                if not isinstance(body, dict):
                    raise ValueError("expected a JSON object")
                return self.post(urlparse(self.path).path, body)
            except (KeyError, TypeError, ValueError) as e:
                return self.send(400, {"error": f"Bad request: {e}"})
            except Exception as e:
                return self.send(500, {"error": str(e)})

        def post(self, path, body):  # noqa: C901
            if path == "/api/profile":
                prof = state["profile"]
                if body.get("job") in JOBS:
                    prof["job"] = body["job"]
                if "level" in body:
                    prof["level"] = min(200, max(1, int(body["level"])))
                if "mesos" in body:
                    prof["mesos"] = max(0, int(body["mesos"]))
                if "acc" in body:
                    prof["acc"] = int(body["acc"]) if str(body["acc"]).strip() not in ("", "None") else None
                if "island" in body and body["island"] in (True, False, None):
                    prof["island"] = body["island"]
                if isinstance(body.get("skill_plan"), dict):
                    prof["skill_plan"] = {k: max(0, int(v)) for k, v in body["skill_plan"].items()}
                save_profile(state)
                return self.send(200, prof)
            if path == "/api/settings":
                for k, v in body.items():
                    if k in SETTINGS and (v := clean_setting(k, v)) is not None:
                        cfg[k] = v
                refused = False
                if not cfg.get("consent"):
                    refused = cfg.get("screen_reading") and body.get("screen_reading") is True
                    cfg["screen_reading"] = False
                if not cfg.get("screen_reading"):
                    cfg["draw_overlay"] = False
                if state["save_cfg"]:
                    state["save_cfg"](cfg)
                state["queue"].put(("settings",))
                if refused:
                    return self.send(400, {"error": "Confirm the risk notice first."})
                return self.send(200, {k: cfg.get(k) for k in SETTINGS})
            if path == "/api/discord/link":     # the token from Discord's redirect: read your ID, drop it
                box = state.get("outbox")
                if not (box and box.setup):
                    return self.send(400, {"error": "Discord isn't set up in this build."})
                token = str(body.get("token") or "")
                if not token or len(token) > 200:
                    return self.send(400, {"error": "No token from Discord."})
                try:
                    me = discord_link.who_is(token)
                except Exception as e:
                    return self.send(502, {"error": f"Couldn't ask Discord who you are: {e}"})
                del token
                cfg.update(discord_id=me["id"], discord_name=me["name"], discord_enabled=True, discord_post_sales=True)
                if state["save_cfg"]:
                    state["save_cfg"](cfg)
                discord_send(state, cfg, "connected Companion: sales from your shop will show up here.")
                return self.send(200, {"name": me["name"]})
            if path == "/api/discord/unlink":
                for k in ("discord_id", "discord_name"):
                    cfg.pop(k, None)
                cfg["discord_enabled"] = False
                if state["save_cfg"]:
                    state["save_cfg"](cfg)
                return self.send(200, {"ok": True})
            if path == "/api/discord/test":
                if not discord_send(state, cfg, "this is a test from Companion."):
                    return self.send(409, {"error": "Connect Discord and turn it on first."})
                return self.send(200, {"ok": True})
            if path == "/api/grind":            # Pause / Resume, Reset, No reset across maps
                g = state.get("grind")
                if not g:
                    return self.send(409, {"error": "Screen reading isn't available."})
                act = body.get("action")
                if act == "pause":
                    g.pause(bool(body.get("on", True)))
                elif act == "reset":
                    g.reset(time.time())
                elif act == "no_reset":
                    g.no_reset = bool(body.get("on", True))
                return self.send(200, g.summary(time.time()))
            if path == "/api/star":            # keep this item, whatever the market says
                name = str(body["name"])[:100]
                stars = [n for n in state["profile"].get("starred", []) if n != name]
                if body.get("on", True):
                    stars.append(name)
                state["profile"]["starred"] = stars
                save_profile(state)
                return self.send(200, {"ok": True})
            if path == "/api/sellkeep/clear":
                state["hovered"] = {}
                return self.send(200, {"ok": True})
            if path == "/api/myshop/seen":      # the "while you were away" summary, dismissed
                if state.get("myshop") is not None:
                    state["myshop"]["away_from"] = time.time()
                return self.send(200, {"ok": True})
            if path == "/api/here":            # "I'm on this map"
                mid = int(body["id"])
                if mid not in data.maps:
                    return self.send(400, {"error": "Unknown map."})
                set_current(data, state, mid)
                return self.send(200, state["nav"] or {})
            if path == "/api/quest_done":
                done = set(str(x) for x in state["profile"].get("quests_done", []))
                (done.add if body.get("done", True) else done.discard)(str(body["id"]))
                state["profile"]["quests_done"] = sorted(done)
                save_profile(state)
                return self.send(200, {"ok": True})
            if path == "/api/quest_active":   # "Not in progress": a quest the game misread, or you dropped
                qid = str(body["id"])
                prof = state["profile"]
                prof["quests_active"] = [a for a in prof.get("quests_active", []) if str(a.get("id")) != qid]
                save_profile(state)
                return self.send(200, {"ok": True})
            if path == "/api/nav":
                start, goal = int(body.get("from") or state["profile"].get("current_map") or 0), int(body["to"])
                if start not in data.maps:
                    return self.send(400, {"error": "Set where you are first, under Go to → Change where you are."})
                got = plan(data, state["profile"], start, goal, taxi=body.get("taxi"))
                if not got:
                    return self.send(404, {"error": "No route between these maps. You may need a boat or a quest portal."})
                steps = got["steps"]
                if body.get("npc_id") is not None:
                    place = data.npc_place(int(body["npc_id"]))
                    if place and place["id"] == steps[-1]["id"]:
                        steps[-1]["npc"] = {"x": place["x"], "y": place["y"], "name": body.get("npc_name", "")}
                state["nav"] = {**got, "to": data.map_info(goal)}
                state["guide"] = None          # a route you picked replaces the quest guide
                remember_recent(state["profile"], goal)
                set_current(data, state, start)
                return self.send(200, state["nav"])
            if path == "/api/nav/step":
                if state["nav"]:
                    state["nav"]["i"] = max(0, min(len(state["nav"]["steps"]) - 1, int(body["i"])))
                    state["profile"]["current_map"] = state["nav"]["steps"][state["nav"]["i"]]["id"]
                    save_profile(state)
                    state["queue"].put(("nav",))
                return self.send(200, state["nav"] or {})
            if path == "/api/nav/taxi":       # "Take the cab" / "Walk instead"
                choose_taxi(data, state, bool(body.get("on")))
                return self.send(200, state["nav"] or {})
            if path == "/api/nav/stop":
                state["nav"], state["guide"] = None, None
                state["queue"].put(("nav",))
                return self.send(200, {})
            if path == "/api/guide":           # guide me through a quest in the game
                if body.get("stop") or not data.quest(body.get("id")):
                    state["guide"] = None
                    if state.get("nav") and state["nav"].get("guide_to"):
                        state["nav"] = None
                    state["queue"].put(("nav",))
                    return self.send(200, {})
                if not state["profile"].get("current_map"):
                    return self.send(400, {"error": "Set where you are first, under Go to → Change where you are."})
                if body.get("check") is not None and (state.get("guide") or {}).get("id") == str(body["id"]):
                    # a step ticked (or unticked) by hand: talked to someone, or no screen reading
                    checked = set(state["guide"].get("checked", []))
                    (checked.add if body.get("on", True) else checked.discard)(str(body["check"]))
                    state["guide"]["checked"] = sorted(checked)
                    guide_plan(data, state)
                    return self.send(200, state["guide"].get("info") or {})
                state["guide"] = {"id": str(body["id"])}
                if state.get("nav"):
                    state["nav"].pop("guide_to", None)
                guide_plan(data, state)
                return self.send(200, state["guide"].get("info") or {})
            if path in ("/api/scan", "/api/auto", "/api/select", "/api/toggle", "/api/nav_corner"):
                if not state["overlay"] or not cfg.get("screen_reading"):
                    return self.send(409, {"error": "Screen reading is off. Turn it on in Settings."})
                state["queue"].put((path.rsplit("/", 1)[1],))
                return self.send(200, {"ok": True})
            self.send(404, {"error": "not found"})

    return Handler


class Server(ThreadingHTTPServer):
    # Python's HTTP server asks for SO_REUSEADDR, which on Windows lets a second copy bind a port
    # the first still holds, and then requests land on either copy
    allow_reuse_address = sys.platform != "win32"


def loot_tiles(data, picked, used):
    """One tile per item: picked up less drunk (potions drunk from the quick slots), most first,
    then the ones down to zero or below, most drunk first; with what each item is and is worth."""
    info = getattr(data, "item_info", {})
    names = list(picked) + [n for n in used if n not in picked]
    net = {n: picked.get(n, 0) - used.get(n, 0) for n in names}
    names = [n for n in names if net[n] > 0] + sorted((n for n in names if net[n] <= 0), key=lambda n: net[n])
    return [{"name": n, "count": net[n], "picked": picked.get(n, 0), "used": used.get(n, 0), "img": data.item_img(n),
             "kind": (info.get(n) or {}).get("kind", ""), "desc": (info.get(n) or {}).get("desc", ""),
             "msc": (data.market.items.get(n) or {}).get("p"), "npc": data.npc_price(n)}
            for n in names]


def card_view(card, data):
    """A history card as the pop-up draws it: the card plus its loot tiles, its kills with each
    monster's picture (None for names not on the map or unnamed), the best minute and the rates."""
    imgs = {}
    for mid in [card.get("map_id")] + list(card.get("map_ids") or []):     # every map the session ground on
        if mid in getattr(data, "maps", {}):
            for m in data.here(mid)["mobs"]:
                imgs.setdefault(m["name"], m.get("img"))
    kills = [{**k, "img": imgs.get(k["name"])} for k in card.get("kills") or []]
    vals = (card.get("minutes") or {}).get("vals") or []
    mins = (card.get("active_s") or 0) / 60
    kt = card.get("kills_total")
    mp = card.get("mesos_picked")
    return {**card, "kills": kills,
            "loot": loot_tiles(data, {x["name"]: x["count"] for x in card.get("loot") or []},
                               {x["name"]: x["count"] for x in card.get("used") or []}),
            "best_minute": max(vals) if vals else None,
            "kills_per_min": round(kt / mins, 1) if kt and mins >= 1 else None,
            "mesos_per_min": round(mp / mins) if mp and mins >= 1 else None}


def session_view(g, data, map_id, now):
    """This grind session as Now draws it: the map's monsters with your kills (and kills of monsters
    not on it, and unnamed ones), the loot with what each item is and is worth (for its tooltip),
    mesos picked up and a minute's worth, where the EXP bar started and moved, deaths, the chart."""
    s = g.summary(now)
    here = data.here(map_id) if map_id in getattr(data, "maps", {}) else {"mobs": []}
    counts = {k["name"]: k["count"] for k in s["kills"]}
    party = {k["name"]: k["count"] for k in s.get("party_kills", [])}
    kills = [{"name": m["name"], "count": counts.pop(m["name"], 0), "party": party.get(m["name"], 0), "img": m.get("img"),
              "level": m.get("level"), "hp": m.get("hp"), "exp": m.get("exp")} for m in here["mobs"]]
    kills += [{"name": n, "count": c, "party": party.get(n, 0), "img": None, "level": None, "hp": None, "exp": None}
              for n, c in counts.items()]          # killed elsewhere this session, or not named (None)
    loot = loot_tiles(data, {x["name"]: x["count"] for x in s["loot"]}, {x["name"]: x["count"] for x in s.get("used", [])})
    minutes = (now - s["since"]) / 60 if s.get("since") else 0
    return {"kills": kills, "kills_total": s["kills_total"], "loot": loot, "mesos_picked": s["mesos_picked"],
            "mesos_per_min": round(s["mesos_picked"] / minutes) if minutes >= 1 else None,
            "start": s["start"], "level": s["level"], "pct": s["pct"], "gain_pct": s["gain_pct"],
            "deaths": s["deaths"], "exp_lost": s["exp_lost"], "chart": s["chart"], "since": s["since"],
            "party": s["party"]}


def grind_view(g, data, prof, now):
    """Everything Now's grind side needs, for /api/grind."""
    mid = prof.get("current_map")
    level = int(prof.get("level") or 1)
    return {"available": True, "now": g.summary(now), "history": g.history(12), "best": g.best_maps(level),
            "by_map": {str(k): round(v) for k, v in g.by_map().items()},
            "session": session_view(g, data, mid, now), "last": g.last_session,
            "town": bool((getattr(data, "maps", {}).get(mid) or {}).get("is_town")), "keep": bool(g.no_reset),
            "corner": CORNER_READ}


def remember_recent(prof, map_id, keep=5):
    """Go to's Recent: the last places you navigated to, newest first, each once."""
    prof["recent_nav"] = ([int(map_id)] + [m for m in prof.get("recent_nav") or [] if m != int(map_id)])[:keep]


def start_server(handler):
    for port in range(PORT, PORT + 10):
        try:
            return Server(("127.0.0.1", port), handler), port   # this PC only
        except OSError:
            continue
    raise SystemExit(f"Ports {PORT}-{PORT + 9} are all busy. Close other copies of Companion.")


BELOW_NORMAL = 0x4000     # Windows' BELOW_NORMAL_PRIORITY_CLASS


def lower_priority(setter=None):
    """Run below normal priority, so the game always comes first: at Normal, Companion's reads took
    their share of the CPU beside the game's (2026-11-20). `setter(cls)`: sets the priority class, for
    tests. True if it was set; False off Windows or when it fails (nothing else changes)."""
    if setter is None:
        if sys.platform != "win32":
            return False

        def setter(cls):
            # handle types declared: by default ctypes passes GetCurrentProcess's -1 as a 32-bit int,
            # which 64-bit Windows refuses as an invalid handle (the call quietly did nothing)
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            if not k32.SetPriorityClass(k32.GetCurrentProcess(), cls):
                raise OSError(f"SetPriorityClass failed ({ctypes.get_last_error()})")
    try:
        setter(BELOW_NORMAL)
        return True
    except Exception:
        return False


def main():
    low = lower_priority()
    if "--report" in sys.argv:
        from sniper import report
        report()
        return
    if not hold_single_instance() and "--second-copy" not in sys.argv:   # running: its dashboard, not a 2nd copy
        show_running()
        return
    moved = paths.migrate()               # data files older versions left loose go into data/
    applog.setup(LOGS_DIR)
    applog.log(f"Companion {VERSION} starting in {APP_DIR}")
    if not low:
        applog.log("Couldn't lower Companion's priority: it runs at normal priority")
    if moved:
        applog.log("Moved into data/: " + ", ".join(moved))
    try:   # Companion's own window, with its logo, open from the first second
        from window import Window
        win = Window()
    except Exception as e:     # no Tk at all: the console is all there is, as before
        applog.log(f"Companion's window is unavailable: {e}")
        serve(None, {})
        return
    started = {}
    threading.Thread(target=update_then_serve, args=(win, started), daemon=True).start()
    win.run()                  # until the window is closed (or an update closes it)
    close_grind(started)
    if started.get("server"):
        started["server"].shutdown()


def close_grind(started):
    """The window closed: keep the grind session's card in the history."""
    g = (started.get("state") or {}).get("grind")
    if g is not None:
        try:
            g.close(time.time())
        except Exception as e:
            applog.log(f"Couldn't save the grind session on exit: {e}")


ALREADY_EXISTS = 183      # Windows' ERROR_ALREADY_EXISTS: the mutex was there before us


def hold_single_instance(create=None):
    """A named mutex for as long as Companion runs: the installer waits on it (AppMutex) to close
    Companion before an update or an uninstall. False when another copy already holds it: two
    copies would draw every label on the game twice and track one grind from two places.
    `create`: () -> (handle, last error), for tests."""
    if create is None:
        if sys.platform != "win32":
            return True

        def create():
            import ctypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            return k32.CreateMutexW(None, False, "Tura2.Companion"), ctypes.get_last_error()
    try:
        global _MUTEX
        _MUTEX, err = create()
        return err != ALREADY_EXISTS
    except Exception as e:
        applog.log(f"No single-instance mutex: {e}")
        return True


def _dashboard_up(port):
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/api/state", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def show_running(alive=_dashboard_up):
    """Companion is already running: open its dashboard (on the first of its ports that answers)."""
    for port in range(PORT, PORT + 10):
        if alive(port):
            url = f"http://localhost:{port}"
            webbrowser.open(url)
            return url
    return None


def update_then_serve(win, started):
    """An installed Companion first looks for a newer release (a few seconds at most). If there is
    one, it downloads and checks the setup, starts it and closes: the setup installs over it and
    starts the new version. Otherwise, or if anything goes wrong, this version starts as usual."""
    if getattr(sys, "frozen", False) and "--no-update" not in sys.argv:
        import updater
        folder = CACHE_DIR / "updates"
        updater.clean(folder, VERSION)
        note = updater.updated_note(sys.argv, VERSION)     # the setup restarted it after an update
        if note:
            applog.say(note)
        found = updater.find(updater.latest_release, VERSION)
        if found:
            win.note(f"Updating to {found.version}…")
            applog.say(f"Companion {found.version} is out. Downloading the update…")
            try:
                setup = updater.download(found, folder)
                applog.log(f"Starting {setup.name} to update {VERSION} -> {found.version}")
                updater.run_setup(setup)
                # the setup has no window of its own: say what happens, and long enough to read it
                applog.say(f"Installing {found.version}. Companion closes now and opens again by itself "
                           "in about half a minute.")
                win.call(lambda: win.root.after(5000, win.root.destroy))
                return
            except Exception as e:
                applog.problem("update", f"Couldn't update to {found.version}. Starting this version; "
                                         "it tries again next time.", exc=e)
    serve(win, started)


def serve(win, started):
    """Load the game data, start the dashboard, then the screen features. With Companion's window,
    the on-game windows are made on its thread and this returns; without one, it runs until quit."""
    try:
        start(win, started)
    except SystemExit as e:    # no game data and no internet, or every port busy: said in words
        applog.problem("start", str(e))
        if win:
            win.failed(str(e))
    except Exception as e:
        applog.problem("start", f"Companion couldn't start: {e}", exc=e)
        if win:
            win.failed(f"Companion couldn't start: {e}")


def start(win, started):
    applog.log("Loading game data and prices")
    data = GameData(force="--refresh" in sys.argv)
    # Cozy Market's prices: brought up to date now and kept that way, in the background
    threading.Thread(target=cozy.keep_fresh, args=(data,), daemon=True).start()

    try:   # screen features need Windows + Tk; the dashboard works without them
        import sniper
        cfg = sniper.load_config()
        screen_ok = sys.platform == "win32"
    except Exception as e:
        applog.problem("screen", "Screen reading and on-game labels aren't available on this PC. The dashboard still works.", exc=e)
        sniper, cfg, screen_ok = None, dict(DEFAULT_SETTINGS), False

    state = {"profile": load_profile(), "queue": queue.Queue(), "auto": False,
             "live": {"rows": [], "note": "Screen reading is off", "auto": False, "region": False},
             "deals": [], "overlay": screen_ok, "nav": None,
             "save_cfg": sniper.save_config if sniper else None}
    state["set_current"] = lambda mid: set_current(data, state, mid)
    state["save_profile"] = lambda: save_profile(state)
    state["guide_tick"] = lambda: guide_plan(data, state)     # the screen reader calls it after each look
    state["outbox"] = make_outbox(data, state, cfg)
    state["discord_send"] = lambda text: discord_send(state, cfg, text)
    state["reports"] = make_reports(data, state, cfg)

    server, port = start_server(make_handler(data, state, cfg))
    started["server"] = server
    started["state"] = state
    threading.Thread(target=server.serve_forever, daemon=True).start()
    local = f"http://localhost:{port}"
    applog.say(f"Ready. The dashboard is at {local}")
    if win:
        win.ready(local)
    if "--no-browser" not in sys.argv:
        webbrowser.open(local)

    if win:
        if screen_ok:
            def begin():          # Tk lives on the window's thread, and so do the on-game windows
                try:
                    sniper.App(data, state, cfg, root=win.root).start()
                except Exception as e:      # no on-game windows: the dashboard still works
                    applog.problem("screen", "Screen reading and on-game labels aren't available on this PC. The dashboard still works.", exc=e)
                    state["overlay"] = False
            win.call(begin)
        return
    if not screen_ok:
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return
    try:
        app = sniper.App(data, state, cfg)
    except Exception as e:      # no on-game windows (Tk failed): the dashboard still works
        applog.problem("screen", "Screen reading and on-game labels aren't available on this PC. The dashboard still works.", exc=e)
        state["overlay"] = False
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return
    app.run()
    server.shutdown()


if __name__ == "__main__":
    main()
