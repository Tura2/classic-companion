"""
Screen features for Companion (opt-in, off by default).

  - Screen reading: looks at the whole game window every few seconds through Windows window
    capture and reads whatever is open, wherever it is: the HUD, the mini map, the Quest Helper and
    the CHARACTER STAT, ITEM INVENTORY, SKILL INVENTORY and QUEST windows (see reader.py). Results
    go to the dashboard. No window capture means no reading; there is no screenshot fallback.
  - Draw on game (separate opt-in): price labels and the route panel on top of the game window.

It never reads or changes game memory, never injects into the game process, never sends keys
or clicks, and installs no keyboard hooks. Everything is controlled from the dashboard.
This is still an unofficial third-party tool. Nexon has not authorized it.
"""
import asyncio
import ctypes
import queue
import re
import sqlite3
import statistics
import sys
import threading
import time
import traceback
from datetime import datetime

import io
import tkinter as tk
from PIL import Image, ImageDraw, ImageTk

import advisor
import overlay_art as art
import reader
from trust import Gate
from shopwatch import ShopWatch
from grind import PQS, Grind, pq_of, pq_of_read
import notices as notice_lines
import party as party_split
from capture import GameCapture, client_box, find_window, foreground_window, window_bounds
from gamedata import JOBS, NPC_PRICES, MapMove

if sys.platform == "win32":  # make Tk and window capture use the same physical pixels
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

from paths import APP_DIR, load_json, save_json

HERE = APP_DIR
CONFIG = HERE / "config.json"
DB = HERE / "scans.sqlite"
DEBUG = HERE / "debug"

DEFAULTS = {
    "region": None,            # [left, top, width, height] of a player shop list
    "bank": 80000,
    "label_side": "right",     # right | left | inside
    "row_tolerance": 14,       # px: OCR lines closer than this vertically are one shop row
    "ocr_scale": 3,            # upscale before OCR; pixel fonts read better bigger
    "auto_interval": 2.0,      # seconds between auto scans (kept slow on purpose)
    "name_match_min": 84,      # 0-100 fuzzy match threshold for item names
    "price_is_per_bundle": False,  # True: divide the row price by "x N" quantity
    "sound": True,
    "nav_corner": "top-right", # where the route panel sits: top-right | top-left | bottom-right | bottom-left
    "screen_reading": False,   # opt-in from the dashboard's Settings tab
    "draw_overlay": False,     # separate opt-in: draw labels and the route panel on the game
    "consent": False,          # user confirmed they understand the risk
    "game_title": "MapleStory",  # labels show only while a window with this in its title is in front
    "setup_done": False,       # the dashboard's first-run setup was finished or skipped
    "discord_enabled": False,  # post your shop's sales to the group's Discord (after Connect Discord)
    "discord_post_sales": True,
}

GREEN, AMBER, RED, GREY = "#2EE59D", "#FFC24B", "#FF6B5B", "#C9D3DF"
KEY = "#%02x%02x%02x" % art.KEY   # the overlay windows' see-through color
WINDOW_ALPHA = 0.96       # the on-game windows let a hint of the game through
STRIP_ALPHA = 0.80        # the route strip lets more of it through: it sits on the game itself
MINI_SECONDS = 6          # the strip sits under the mini map while it was seen this recently
STRIP_RANK = {"window": 2, "bar": 2, "title": 1}   # how sure a read of the mini map's place is
TIP_EVERY = 0.143         # quick looks for item tooltips, at the capture's seven frames a second
TIP_SECONDS = 1.0         # a tooltip's prices go away this long after it was last seen
SHOP_LABEL_SECONDS = 8    # labels disappear this long after the last scan that found shop rows
PAD_W = 300               # room for labels beside the shop, at 100% display scale
WATCH_EVERY = 1.5         # seconds between looks at the game while screen reading is on
SHOP_EVERY = 0.3          # seconds between quick re-reads of an open shop's item list
PREVIEW_W = 960           # width of the live picture of the game in the dashboard
SAMPLE_EVERY = 60         # seconds between saved pictures of a shop window (to tune the shop reader)
SAMPLES_KEPT = 30         # the newest pictures of shops that couldn't be read; older ones are deleted
CONFIRM_READS = 3         # a quest joins In progress or Done only after this many reads in a row agree
GRIND_ON = True           # the Grind card on Now
MYSHOP_EVERY = 6.0        # seconds between looks at your own store while it's open (nobody's using it)
MYSHOP_FULL_EVERY = 10    # every this many store looks, a full read, so the rest of the dashboard keeps up
CLOSED_READS = 3          # reads with neither your store nor the HUD before "your shop closed"


def current_step(chain_ids, done):
    """The step of a quest line you're on: its first quest not done, or None when all are."""
    return next((q for q in chain_ids if q not in done), None)


def line_step(chain_ids, done, active):
    """The quest a line seen In Progress adds to your quests: none when one of its quests is already
    going (a line can be a set of quests to choose from, like the six Omok sets), else its step."""
    return None if any(q in active for q in chain_ids) else current_step(chain_ids, done)


def skill_rules(data):
    """({skill: its max level}, {skill: its job}) from the game data, for the save gate."""
    top, job = {}, {}
    for groups in data.skills.values():
        for g in groups if isinstance(groups, list) else []:
            for sk in (g.get("skills") or []) if isinstance(g, dict) else []:
                if sk.get("name"):
                    top[sk["name"]] = sk.get("max_level") or 30
                    job[sk["name"]] = g.get("job")
    return top, job


class Agree:
    """What a read says counts only once it says it CONFIRM_READS times in a row: one misread title
    (or a tab taken for another) would otherwise put a quest you never took into In progress or Done."""

    def __init__(self, need=CONFIRM_READS):
        self.need, self.runs = need, {}

    def update(self, scope, keys):
        """keys: what this read saw in scope (a quest tab, the Quest Helper). Returns the ones it has
        now seen need reads in a row. Something missing from a read of that scope starts over."""
        runs = self.runs.setdefault(scope, {})
        keys = set(keys)
        for k in list(runs):
            if k not in keys:
                del runs[k]
        for k in keys:
            runs[k] = runs.get(k, 0) + 1
        return {k for k, n in runs.items() if n >= self.need}


class SteadyCounts:
    """Quest Helper counts as shown: a new count is taken once two reads in a row agree on it, so a
    3 read as 30 doesn't send you back to the NPC."""

    def __init__(self):
        self.raw, self.shown = {}, {}

    def update(self, quests):
        raw = {}
        for q in quests or []:
            for n in q.get("needs", []):
                k = (q.get("id"), n["what"])
                raw[k] = n["have"]
                if self.raw.get(k) == n["have"] or k not in self.shown and n["have"] == 0:
                    self.shown[k] = n["have"]
        self.raw = raw
        out = []
        for q in quests or []:
            needs = [{**n, "have": self.shown[(q.get("id"), n["what"])]} for n in q.get("needs", [])
                     if (q.get("id"), n["what"]) in self.shown]
            out.append({**q, "needs": needs})
        return out


def handle_grind(app, seen, prof):
    """Feed the grind tracker from a full read: the HUD's EXP, where you are, your mesos."""
    g = getattr(app, "grind", None)
    if g is None or not seen or seen.get("quick"):
        return
    now = time.time()
    # a party quest's title read too badly to name the stage ("1st Accornpanijnent") leaves the
    # profile on the town you came from; it still means you're in that PQ, until a map is read
    missed = seen.get("map_missed")
    if seen.get("map") or (missed and len(missed) >= 6):
        app.grind_pq = pq_of_read(missed) if not seen.get("map") else None   # another title: out of it
    hud = seen.get("hud") or {}
    if hud.get("exp") is not None:
        mid = prof.get("current_map")
        name = (app.data.maps.get(mid) or {}).get("name") if mid else None
        pq = getattr(app, "grind_pq", None)
        if pq and pq_of(name) != pq:
            mid, name = -1, dict(PQS)[pq]       # the PQ by its prefix: no stage known
        gain = g.update(hud["exp"], hud.get("exp_pct"), prof.get("level"), mid, name, now)
        if gain and gain > 0 and not getattr(g, "last_lump", False):
            # the kills behind this gain, named by this map's monsters' EXP; a gain none of them
            # explains (a party share, a bonus) is kills all the same, unnamed, at the usual kill
            split = getattr(app.data, "split_kills", None)
            on_map = split and mid in getattr(app.data, "maps", {})
            names = split(mid, gain) if on_map else None
            fit = getattr(app, "party", None)
            if fit is None:
                fit = app.party = party_split.Fitter()
            if on_map:
                fit.add(gain)
            told = None
            if not names and on_map:
                # not whole kills: in a party each kill's EXP is shared. Learn the split, then tell
                # the gain as your kills and your party's
                mobs = app.data.map_mobs(mid)
                model = fit.model(mobs)
                told = party_split.split(mobs, gain, model) if model else None
            if names:
                for n in names:
                    g.add_kill(n, now)
            elif told:
                for n, who in told:
                    g.add_kill(n, now, party=who == "party")
            else:
                k = g.per_kill()
                for _ in range(max(1, round(gain / k)) if k else 1):
                    g.add_kill(None, now)
    if (seen.get("inventory") or {}).get("mesos") is not None:
        g.mesos(seen["inventory"]["mesos"], now)
    tracker = getattr(app, "notices", None)
    if tracker is not None and "notices" in seen:
        data = app.data
        names = getattr(data, "_item_names", None)
        if names is None:
            names = data._item_names = list(getattr(data, "item_ids", {}) or {})
        mid = prof.get("current_map")
        for ev in tracker.update(seen["notices"], seen.get("notice_row") or 13, names):
            if ev[0] == "exp":
                continue                  # kills come from the HUD's EXP gains, named the same way
            if ev[0] == "mesos":
                g.add_mesos(ev[1], now)
            elif ev[0] == "item" and ev[1]:
                g.add_loot(ev[1], ev[2], now)


HOVER_KEEP = 120    # items Sell or keep remembers (hovered, or read off an inventory tab)


def note_hovered(state, tips):
    """Remember each item hovered this session, for the dashboard's Sell or keep list."""
    seen = state.setdefault("hovered", {})
    for t in tips or []:
        if t.get("name"):
            seen.pop(t["name"], None)       # hovered again: it moves to the newest end
            seen[t["name"]] = {"ts": time.time(), "untradable": bool(t.get("untradable"))}
    for old in list(seen)[:-HOVER_KEEP]:  # only the newest few, so the list never grows without end
        del seen[old]


def note_bag(state, items):
    """Items read off the open inventory tab (invgrid) join Sell or keep's list like hovered ones. One
    that looks like another item too is listed as both ("alt"); hovering it settles which."""
    seen = state.setdefault("hovered", {})
    now = time.time()
    for it in items or []:
        name = it.get("name")
        if not name or (name in seen and not seen[name].get("bag")):
            continue                      # hovered already: the tooltip said exactly what it is
        seen.pop(name, None)
        seen[name] = {"ts": now, "untradable": False, "bag": True, "alt": it.get("alt")}
    for old in list(seen)[:-HOVER_KEEP]:
        del seen[old]


def handle_myshop(app, seen, now):
    """Your own store, from one look at the game: sales into the dashboard, a beep, and Discord.
    `seen` None or with "error": the game couldn't be seen this time."""
    sw = getattr(app, "shopwatch", None)
    if sw is None:
        return []
    state, cfg = app.state, app.cfg
    ok = seen is not None and not seen.get("error")
    mine = seen.get("myshop") if ok else None
    was = sw.status["watching"] or sw.base is not None
    sales = sw.update(mine, now)
    ms = state.setdefault("myshop", {"sales": [], "away_from": now})
    if not cfg.get("screen_reading"):
        reason = "Screen reading is off."
    elif not ok:
        reason = "Can't see the game: is it minimized?"
    elif not mine:
        reason = "Your store isn't on screen."
    else:
        reason = ""
    ms.update(watching=sw.watching, total=sw.status["total"], reason=reason, ts=now,
              title=mine.get("title") if mine else ms.get("title"), sales=sw.sales[-100:],
              panel=bool(mine and mine.get("panel")))
    linked = cfg.get("discord_enabled") and cfg.get("discord_id")
    for sale in sales:
        what = f"{sale['item']} x{sale.get('count') or 1}" if sale.get("item") else "something"
        print(f"Your shop sold {what} for {sale['price']:,} mesos")
        if cfg.get("sound"):
            try:
                import winsound
                winsound.MessageBeep()
            except Exception:
                pass
        if linked and cfg.get("discord_post_sales") and state.get("outbox"):
            state["outbox"].add("sale", sale, sale["key"])
    told = getattr(app, "myshop_told", None)
    if told is None:
        told = app.myshop_told = set()
    send = state.get("discord_send") if linked else None
    for fix in sw.take_fixes():           # Total Sales doesn't show a sale told from the mesos box
        wrong = ", ".join(f"{s['item']} x{s.get('count') or 1}" if s.get("item") else "something"
                          for s in fix["wrong"])
        print(f"Correction: {wrong} didn't sell (Total Sales doesn't show it)")
        if send and cfg.get("discord_post_sales") and fix["key"] not in told:
            told.add(fix["key"])
            send(f"correction: {wrong} didn't sell after all, that post was wrong (your shop's Total Sales "
                 f"doesn't show it).")
    if "soldout" in sw.events and ("soldout", sw.session) not in told:
        told.add(("soldout", sw.session))
        send and send("your shop sold out: time to restock.")
    # gone with the HUD too, while the game window is there: disconnected, or back at the login screen
    app.closed_reads = (getattr(app, "closed_reads", 0) + 1) if ok and was and not mine and not seen.get("hud") \
        and not seen.get("quick") else 0
    if app.closed_reads >= CLOSED_READS and ("closed", sw.session) not in told:
        told.add(("closed", sw.session))
        send and send("your shop closed: the game left the Free Market (disconnected, or back at the login screen).")
    return sales


def fmt(n):
    return f"{int(round(n)):,}"


def load_config():
    cfg = dict(DEFAULTS)
    cfg.update(load_json(CONFIG, {}))
    return cfg


def save_config(cfg):
    save_json(CONFIG, cfg)


# ---------------------------------------------------------------- OCR
def ocr_lines(img, scale):
    """Return [(text, x, y, w, h)] in captured-image pixels."""
    big = img.convert("L").resize((img.width * scale, img.height * scale), Image.NEAREST).convert("RGB")
    out = []
    try:
        import winocr  # Windows built-in OCR, fast and needs no install beyond pip

        async def recognize():   # newer winrt hands back an awaitable, not a coroutine asyncio.run takes
            return await winocr.recognize_pil(big, "en")
        res = winocr.picklify(asyncio.run(recognize()))
        for line in res.get("lines", []):
            rects = [w["bounding_rect"] for w in line.get("words", [])]
            if not rects:
                continue
            x = min(r["x"] for r in rects)
            y = min(r["y"] for r in rects)
            x2 = max(r["x"] + r["width"] for r in rects)
            y2 = max(r["y"] + r["height"] for r in rects)
            out.append((line["text"], x / scale, y / scale, (x2 - x) / scale, (y2 - y) / scale))
    except ImportError:
        try:
            import pytesseract  # fallback: needs Tesseract installed
        except ImportError:
            raise RuntimeError("Windows OCR isn't available. Run: pip install winocr (and add the English "
                               "OCR language in Windows Settings > Time & language > Language).") from None
        d = pytesseract.image_to_data(big, output_type=pytesseract.Output.DICT)
        groups = {}
        for i, t in enumerate(d["text"]):
            if t.strip():
                groups.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), []).append(i)
        for idx in groups.values():
            x = min(d["left"][i] for i in idx)
            y = min(d["top"][i] for i in idx)
            x2 = max(d["left"][i] + d["width"][i] for i in idx)
            y2 = max(d["top"][i] + d["height"][i] for i in idx)
            text = " ".join(d["text"][i] for i in idx)
            out.append((text, x / scale, y / scale, (x2 - x) / scale, (y2 - y) / scale))
    return out


def group_rows(lines, tol):
    rows = []
    for ln in sorted(lines, key=lambda l: l[2]):
        cy = ln[2] + ln[4] / 2
        if rows and abs(rows[-1]["cy"] - cy) <= tol:
            rows[-1]["lines"].append(ln)
            rows[-1]["cy"] = (rows[-1]["cy"] + cy) / 2
        else:
            rows.append({"cy": cy, "lines": [ln]})
    return rows


NUM = re.compile(r"\d[\d,.]*")
QTY = re.compile(r"[x×]\s*(\d[\d,]*)", re.I)


def to_int(s):
    s = s.replace(",", "").replace(".", "")
    return int(s) if s.isdigit() else None


def parse_row(row, market, cfg):
    text = " ".join(l[0] for l in sorted(row["lines"], key=lambda l: l[1]))
    qty = 1
    m = QTY.search(text)
    if m:
        qty = to_int(m.group(1)) or 1
        text = text[:m.start()] + " " + text[m.end():]
    nums = [n for n in (to_int(t) for t in NUM.findall(text)) if n]
    words = re.sub(r"[\d,.:]+|\bmesos?\b|\bprice\b|\bqty\b", " ", text, flags=re.I)
    name = market.match(re.sub(r"\s+", " ", words), cfg["name_match_min"])
    if not name or not nums:
        return None
    price = max(nums)
    unit = price / qty if cfg["price_is_per_bundle"] and qty > 1 else price
    return {"name": name, "unit": unit, "qty": qty, "cy": row["cy"]}


TAGS = {"snipe": "SNIPE", "fair": "FAIR", "pricey": "PRICEY", "over": "OVERPRICED", "check": "CHECK PRICE",
        "npc": "NPC FLIP", "split": "SOURCES DIFFER", "info": "COZY ONLY"}
TONES = {"snipe": GREEN, "fair": GREY, "pricey": AMBER, "over": RED, "check": AMBER, "npc": GREEN,
         "split": AMBER, "info": GREY}


def price_text(n):
    """A price as the game shows it; under 10 mesos keeps its decimals (an arrow sells for 0.5)."""
    return fmt(n) if n >= 10 else f"{n:g}"


def source_prices(name, market):
    """Each site's usual price for the item, for a label: [("MSC", "3,999"), ("Cozy", "3,299")]."""
    it, cozy = market.items.get(name), (market.cozy.get(name) or {}).get("price")
    return ([("MSC", price_text(it["p"]))] if it else []) + ([("Cozy", price_text(cozy))] if cozy else [])


def where(u, low, mid, high):
    """Where a price sits among recent sales: in the cheapest quarter (and under the middle), at or
    under the middle, up to three quarters, or above."""
    if u <= low and mid > u:
        return "snipe"
    if u <= mid:
        return "fair"
    return "pricey" if u <= high else "over"


ORDER = ["snipe", "fair", "pricey", "over"]     # best to worst for the buyer
NEAR = 0.05      # a price this close to a line could be on either side of it


def near(u, low, mid, high):
    """Every verdict the price would get if it were up to NEAR higher or lower."""
    a, b = ORDER.index(where(u * (1 - NEAR), low, mid, high)), ORDER.index(where(u * (1 + NEAR), low, mid, high))
    return set(ORDER[a:b + 1])


def judge(r, market):
    """(text for the dashboard, color, verdict, parts for the on-game label), or all None.

    The label shows each source's price in that source's color -- MSC is maplestory-classic.com's
    median, Cozy is Cozy Market's usual price -- and a verdict:
      snipe       at or under the cheapest quarter of recent sales, and under the middle price
      fair        at or under the middle price
      pricey      above the middle, but not above three quarters of recent sales
      overpriced  above three quarters of recent sales
      npc flip    under what an NPC pays for it
      check       so far under every recent sale that the price was probably misread
      split       the two sources give different verdicts, so none is claimed
      info        only Cozy has a price, and one number gives no verdict

    The verdict is worked out against each source on its own and claimed only when both agree.
    MSC gives the spread of recent sales; Cozy gives one number, so its quarters are MSC's spread
    moved to Cozy's price. With MSC alone its verdict stands. There is no profit figure: the two
    prices side by side are the point, and the reader decides."""
    u, name = r["unit"], r["name"]
    npc = NPC_PRICES.get(name)
    it = market.items.get(name)
    cozy = (market.cozy.get(name) or {}).get("price")
    prices = source_prices(name, market)
    # Cozy's quarters: MSC's spread, scaled to Cozy's price
    k = cozy / it["p"] if it and cozy and it["p"] else None

    def result(verdict, note=None, risk=None, tone=None):
        shown = " · ".join(f"{s} {n}" for s, n in prices)
        text = TAGS[verdict] + (f"  ({shown})" if shown else "") + "".join(f" · {x}" for x in (note, risk) if x)
        return text, tone or TONES[verdict], verdict, {"tag": TAGS[verdict], "prices": prices, "note": note,
                                                        "risk": risk, "name": name}

    lows = [x for x in (it and it["p25"], k and it["p25"] * k, not it and cozy) if x]
    if lows and u < min(lows) * 0.35:
        return result("check")
    if npc and u < npc:
        return result("npc", note=f"NPC pays {price_text(npc)}")
    if not it:
        return result("info") if cozy else (None, None, None, None)
    falling, glut = it["trend"] < -0.2, it["st"] < 0.5
    risk = "falling" if falling else ("slow seller" if glut else None)
    verdict = where(u, it["p25"], it["p"], it["p75"])
    if k and where(u, it["p25"] * k, cozy, it["p75"] * k) != verdict:
        # A price right on a line lands on either side of it depending on the site (1,999 against
        # 1,799 and 1,750). If a verdict holds for both within NEAR, they agree, and the one less
        # favourable to the buyer is shown, so no deal is claimed on a technicality.
        both = near(u, it["p25"], it["p"], it["p75"]) & near(u, it["p25"] * k, cozy, it["p75"] * k)
        if not both:
            return result("split", risk=risk)
        verdict = max(both, key=ORDER.index)
    return result(verdict, risk=risk, tone=AMBER if verdict == "snipe" and risk else None)


WINDOW_LABELS = {"hud": "HUD", "stat": "Character stat", "inventory": "Inventory", "skills": "Skills",
                 "quest": "Quests", "helper": "Quest Helper", "shop": "Shop", "myshop": "Your shop"}


def preview(frame, seen):
    """A small JPEG of the game for the dashboard, with a tag on each window that was read."""
    img = frame.copy()
    img.thumbnail((PREVIEW_W, PREVIEW_W))
    d = ImageDraw.Draw(img)
    font = art.font(13, "bold")
    for key, (fx, fy) in (seen.get("windows") or {}).items():
        x, y = fx * img.width, fy * img.height
        label = WINDOW_LABELS.get(key, key)
        w = d.textlength(label, font=font) + 12
        y = max(0, y - 22) if key != "hud" else y - 26
        d.rounded_rectangle((x, y, x + w, y + 19), radius=6, fill=(46, 229, 157))
        d.text((x + 6, y + 2), label, font=font, fill=(6, 30, 18))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=72)
    return buf.getvalue()


# ---------------------------------------------------------------- your own price history
class ScanLog:
    def __init__(self):
        self.con = sqlite3.connect(DB, check_same_thread=False)
        self.con.execute("CREATE TABLE IF NOT EXISTS scans (ts TEXT, item TEXT, unit REAL, qty INT, verdict TEXT)")
        try:
            self.con.execute("ALTER TABLE scans ADD COLUMN seller TEXT")     # history from before sellers were read
        except sqlite3.OperationalError:
            pass
        self.seen = {}
        self.lock = threading.Lock()

    def add(self, r, verdict, seller=None):
        key, now = (r["name"], r["unit"], seller), time.time()
        if now - self.seen.get(key, 0) < 120:   # same listing seen recently: skip
            return False
        self.seen[key] = now
        with self.lock:
            self.con.execute("INSERT INTO scans (ts, item, unit, qty, verdict, seller) VALUES (?,?,?,?,?,?)",
                             (datetime.now().isoformat(timespec="seconds"), r["name"], r["unit"], r["qty"], verdict, seller))
            self.con.commit()
        return True


def seen_items(market, icon):
    """Items you've passed in player shops: how often, the lowest and latest price, and what that
    lowest price means against the market. Newest first."""
    if not DB.exists():
        return []
    con = sqlite3.connect(DB)
    try:
        cols = [c[1] for c in con.execute("PRAGMA table_info(scans)")]
        seller = "seller" if "seller" in cols else "NULL"
        rows = con.execute(f"SELECT item, unit, ts, {seller} FROM scans ORDER BY ts").fetchall()
    finally:
        con.close()
    items = {}
    for name, unit, ts, who in rows:
        e = items.setdefault(name, {"name": name, "seen": 0, "low": unit, "low_seller": who, "last": unit, "last_ts": ts})
        e["seen"] += 1
        if unit < e["low"]:
            e["low"], e["low_seller"] = unit, who
        e["last"], e["last_ts"] = unit, ts
    out = []
    for e in items.values():
        it, npc = market.items.get(e["name"]), NPC_PRICES.get(e["name"])
        verdict = judge({"name": e["name"], "unit": e["low"]}, market)[2]
        e.update(verdict=verdict, median=it["p"] if it else None, snipe=int(it["p25"]) if it else None,
                 p75=it["p75"] if it else None, cozy=(market.cozy.get(e["name"]) or {}).get("price"),
                 npc=npc, img=icon(e["name"]))
        out.append(e)
    out.sort(key=lambda e: e["last_ts"], reverse=True)
    return out


def report():
    if not DB.exists():
        print("No scans yet.")
        return
    con = sqlite3.connect(DB)
    data = {}
    for item, unit in con.execute("SELECT item, unit FROM scans"):
        data.setdefault(item, []).append(unit)
    print(f"{'item':38} {'seen':>5} {'lowest':>10} {'median':>10}")
    for item, xs in sorted(data.items(), key=lambda kv: -len(kv[1]))[:50]:
        print(f"{item[:38]:38} {len(xs):>5} {fmt(min(xs)):>10} {fmt(statistics.median(xs)):>10}")


# ---------------------------------------------------------------- overlay
def make_click_through(win):
    if sys.platform != "win32":
        return
    hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
    style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
    # layered + click-through + never takes focus, so the game keeps the keyboard
    ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20 | 0x08000000)


def see_through(win, alpha=WINDOW_ALPHA):
    """A borderless, always-on-top window whose KEY-colored pixels show the game through."""
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.config(bg=KEY)
    try:
        win.attributes("-transparentcolor", KEY)
        win.attributes("-alpha", alpha)
    except tk.TclError:
        win.attributes("-alpha", 0.85)


class Overlay:
    """Price labels beside the rows of a player shop, pointing at their row."""

    def __init__(self, root, cfg):
        self.cfg, self.scale, self.photos = cfg, 1.0, []
        self.region = None          # an open shop's item list found by the reader (else the selected area)
        self.win = tk.Toplevel(root)
        see_through(self.win)
        self.canvas = tk.Canvas(self.win, bg=KEY, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.win.update_idletasks()
        make_click_through(self.win)
        self.place()

    def pad(self):
        return round(PAD_W * self.scale)

    def place(self):
        r = self.region or self.cfg["region"]
        if not r:
            return
        l, t, w, h = r
        side = self.cfg["label_side"]
        x = l - self.pad() if side == "left" else l
        extra = 0 if side == "inside" else self.pad()
        self.win.geometry(f"{w + extra}x{h}+{x}+{t}")

    def draw(self, results):
        """Only the price labels next to shop rows: no frames, nothing else."""
        c = self.canvas
        c.delete("all")
        self.photos = []
        r = self.region or self.cfg["region"]
        if not r:
            return
        w = r[2]
        side, pad, gap = self.cfg["label_side"], self.pad(), round(4 * self.scale)
        notch = {"right": "left", "left": "right"}.get(side)   # the pointer faces the shop row
        for res in results:
            if not res.get("parts"):
                continue
            img = art.shop_label(res["parts"], res["verdict"], self.scale, notch,
                                 max_w=(w if side == "inside" else pad) - gap)
            photo = ImageTk.PhotoImage(img)
            self.photos.append(photo)      # Tk shows a picture only while Python keeps it
            if side == "right":
                c.create_image(w + gap, res["cy"], image=photo, anchor="w")
            elif side == "left":
                c.create_image(pad - gap, res["cy"], image=photo, anchor="e")
            else:
                c.create_image(w - gap, res["cy"], image=photo, anchor="e")

    def toggle(self):
        if self.win.state() == "withdrawn":
            self.win.deiconify()
        else:
            self.win.withdraw()



class Card:
    """One picture above the game, such as the route strip or the quest card: see-through where it's
    KEY, click-through, never focused."""

    def __init__(self, root, alpha=WINDOW_ALPHA):
        self.win = tk.Toplevel(root)
        see_through(self.win, alpha)
        self.canvas = tk.Canvas(self.win, bg=KEY, highlightthickness=0)
        self.canvas.pack()
        self.win.update_idletasks()
        make_click_through(self.win)
        self.photo, self.size, self.at = None, (1, 1), None
        self.win.withdraw()

    def show(self, img):
        self.photo = ImageTk.PhotoImage(img)      # Tk shows a picture only while Python keeps it
        self.canvas.delete("all")
        self.canvas.config(width=img.width, height=img.height)
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)
        self.size = img.size

    def move(self, x, y):
        if self.at != (round(x), round(y), self.size):
            self.at = (round(x), round(y), self.size)
            self.win.geometry(f"{self.size[0]}x{self.size[1]}+{round(x)}+{round(y)}")


def select_region(root, done):
    gm = ctypes.windll.user32.GetSystemMetrics if sys.platform == "win32" else (lambda i: [0, 0, 1920, 1080][i - 76])
    v = {"left": gm(76), "top": gm(77), "width": gm(78), "height": gm(79)}   # the whole virtual desktop
    sel = tk.Toplevel(root)
    sel.overrideredirect(True)
    sel.attributes("-topmost", True)
    sel.attributes("-alpha", 0.3)
    sel.geometry(f"{v['width']}x{v['height']}+{v['left']}+{v['top']}")
    cv = tk.Canvas(sel, bg="black", highlightthickness=0, cursor="crosshair")
    cv.pack(fill="both", expand=True)
    cv.create_text(v["width"] // 2, 40, text="Drag a box around the shop window. Esc cancels.",
                   fill="white", font=("Segoe UI", 16, "bold"))
    st = {}

    def down(e):
        st["x"], st["y"] = e.x_root, e.y_root
        st["box"] = cv.create_rectangle(e.x, e.y, e.x, e.y, outline=GREEN, width=2)
        st["ox"], st["oy"] = e.x, e.y

    def move(e):
        if "box" in st:
            cv.coords(st["box"], st["ox"], st["oy"], e.x, e.y)

    def up(e):
        if "x" not in st:
            return
        x1, y1 = min(st["x"], e.x_root), min(st["y"], e.y_root)
        w, h = abs(e.x_root - st["x"]), abs(e.y_root - st["y"])
        sel.destroy()
        if w > 30 and h > 30:
            done([x1, y1, w, h])

    cv.bind("<ButtonPress-1>", down)
    cv.bind("<B1-Motion>", move)
    cv.bind("<ButtonRelease-1>", up)
    sel.bind("<Escape>", lambda e: sel.destroy())
    sel.focus_force()


# ---------------------------------------------------------------- app
class App:
    """On-game windows and screen reading. Shares `state` and the command queue with the web dashboard."""

    def __init__(self, data, state, cfg, root=None):
        """root: Companion's own window, whose Tk the on-game windows share; without one, a hidden
        root of their own."""
        self.data = data            # gamedata.GameData (has .market)
        self.state = state          # dict shared with the web server
        self.cfg = cfg              # shared with the web server's Settings tab
        self.log = ScanLog()
        self.q = state["queue"]
        self.busy = False
        self.results, self.note = [], "Select a shop area to start"
        if self.cfg["region"]:
            self.note = "Ready to scan"
        DEBUG.mkdir(exist_ok=True)

        self.root = root
        if root is None:
            self.root = tk.Tk()
            self.root.withdraw()
        self.overlay = Overlay(self.root, self.cfg)
        self.strip = Card(self.root, STRIP_ALPHA)      # the route (and quest step): by the mini map
        self.scale = self.overlay.scale = art.dpi_scale()   # refined to the game's monitor once it's found
        self.bounds = None          # the game window (left, top, right, bottom), for the corner
        self.mini = None            # where the route strip goes under the mini map, as last seen
        self.mini_next = None       # a new place for it, waiting for a second read to agree
        self.map_move = MapMove()   # a new map read from the mini map, waiting for enough reads to agree
        self.strip_key = None       # what the route strip was last drawn for
        # prices under the game's item tooltips: two, since an equip's comes with the one you wear
        self.tip_cards = [Card(self.root, STRIP_ALPHA), Card(self.root, STRIP_ALPHA)]
        self.tips, self.tips_ts, self.tips_key = [], 0.0, None
        self.read_tips = (0.0, [])  # the tooltips the last full read saw, drawing or not
        self.tip_shown = [False, False]
        self.tip_mask = None        # the last quick look's navy, to see a tooltip come up
        self.tip_busy = False       # a quick look is in progress
        self.capture = GameCapture(lambda: self.cfg["game_title"])
        self.reader = reader.Reader(data)
        self.agree, self.notice, self.counts = Agree(), Agree(2), SteadyCounts()
        self.gate = Gate(*skill_rules(data))   # what a read may change in the profile (trust.py)
        self.shop_rows = []         # verdicts for the shop window open in the game (found by the reader)
        self.last_listings = set()  # listings in the previous read: a deal is announced once two reads agree
        self.announced = set()      # deals already announced this session
        self.shop_anchor = None     # where the open shop's LEAVE STORE button was, for the quick re-read
        self.shopwatch = ShopWatch()  # sales in your own store
        self.grind = Grind(APP_DIR / "grind.sqlite") if GRIND_ON else None   # EXP/hr per session and per map
        self.notices = notice_lines.Tracker()   # the corner's EXP / mesos / item lines, each counted once
        self.party = party_split.Fitter()        # learns how a party splits kills' EXP, from the gains
        state["grind"] = self.grind
        self.myshop_anchor = None   # your own store's fee notice, for the slow store-only look
        self.myshop_panel = None    # its SOLD ITEMS panel's title, when that's open
        self.my_reads = 0
        self.last_shop = None       # the open shop's last full read, for when an item's tooltip covers it
        self.watching = False       # a look at the game is in progress
        self.sample_ts = 0.0        # when a shop window's picture was last saved
        self.auto_job = None        # the pending auto-scan timer, so there's only ever one
        self.game_hwnd = None       # the game window, looked up every 3 s
        self.apply_settings()

    def start(self):
        """Begin looking at the game and drawing on it, on the Tk loop already running."""
        self.publish()
        self.root.after(50, self.pump)
        self.root.after(30 * 60 * 1000, self.refresh_prices)
        self.root.after(1000, self.watch_loop)
        self.root.after(1200, self.tip_loop)
        self.root.after(500, self.focus_loop)

    def run(self):
        self.start()
        self.root.mainloop()

    @property
    def market(self):
        return self.data.market

    def apply_settings(self):
        """Show or hide on-game drawing to match the Settings tab."""
        if self.cfg["draw_overlay"] and self.cfg["screen_reading"]:
            self.overlay.place()
            self.redraw()
        for w in (self.overlay.win, self.strip.win, *(c.win for c in self.tip_cards)):
            w.withdraw()                 # focus_loop shows things only when they apply
        if not self.cfg["screen_reading"]:
            self.set_auto(False)
            if self.capture.control:   # off means off: end the capture session now, not at exit
                threading.Thread(target=self.capture.stop, daemon=True).start()

    def drawing(self):
        return self.cfg["draw_overlay"] and self.cfg["screen_reading"]

    def publish(self):
        if self.results or self.shop_rows:
            self.rows_ts = time.time()
        if self.drawing():
            self.overlay.draw(self.shop_rows or self.results)
        self.state["live"] = {"rows": self.results, "note": self.note, "auto": self.state["auto"],
                              "region": bool(self.cfg["region"]), "ts": time.time(),
                              "capture": self.capture.mode, "capture_error": self.capture.error}

    def pump(self):
        while True:
            try:
                msg = self.q.get_nowait()
            except queue.Empty:
                break
            if msg[0] == "quit":
                self.root.destroy()
                return
            try:
                self.handle(msg)
            except Exception:
                traceback.print_exc()      # one bad message must not stop the ones after it
        self.root.after(50, self.pump)

    def handle(self, msg):
        kind = msg[0]
        if kind == "select":
            self.cfg["screen_reading"] and select_region(self.root, self.set_region)
        elif kind == "scan":
            self.scan()
        elif kind == "settings":
            self.apply_settings()
            self.publish()
        elif kind == "auto":
            if not self.cfg["screen_reading"]:
                return
            self.set_auto(not self.state["auto"])
            self.publish()
        elif kind == "toggle":
            self.user_hidden = not getattr(self, "user_hidden", False)
        elif kind == "nav":
            if self.drawing():
                self.redraw()
        elif kind == "seen":
            self.apply_seen(msg[1], msg[2])
        elif kind == "tips_up":
            self.tips_ts = time.time()      # the same tooltip is still up: its prices stay
        elif kind == "bag":
            note_bag(self.state, msg[1])
        elif kind == "tips":
            note_hovered(self.state, msg[1])
            if self.drawing():
                self.set_tips(msg[1])
        elif kind == "nav_corner":
            order = ["top-right", "bottom-right", "bottom-left", "top-left"]
            cur = self.cfg["nav_corner"]
            self.cfg["nav_corner"] = order[(order.index(cur) + 1) % 4 if cur in order else 0]
            save_config(self.cfg)
            self.layout()
        elif kind == "result":
            self.busy = False
            self.results, self.note = msg[1], msg[2]
            self.publish()

    def set_region(self, region):
        self.cfg["region"] = region
        save_config(self.cfg)
        self.overlay.place()
        self.results, self.note = [], "Shop area saved. Ready to scan"
        self.publish()

    # ---- looking at the game
    def watch_loop(self):
        """While screen reading is on, look at the whole game every few seconds and read whatever
        windows are open, wherever they are. Nothing to select. While a shop is open, only its item
        list is re-read, about three times a second, so prices and labels keep up as you scroll."""
        every = SHOP_EVERY if self.shop_anchor else MYSHOP_EVERY if self.myshop_anchor else WATCH_EVERY
        self.root.after(int(every * 1000), self.watch_loop)
        if self.cfg["screen_reading"] and not self.watching:
            self.watching = True
            threading.Thread(target=self._watch, daemon=True).start()

    def tip_loop(self):
        """Seven times a second while the game is in front and drawing on it is on: has an item
        tooltip come up, moved or gone? A cheap look at the frame; OCR only on the small area where
        one just came up, so the prices follow the mouse without reading the whole game."""
        self.root.after(int(TIP_EVERY * 1000), self.tip_loop)
        if self.drawing() and self.game_in_front() and not self.tip_busy:
            self.tip_busy = True
            threading.Thread(target=self._tip_look, daemon=True).start()

    def _tip_look(self):
        try:
            frame = self.capture.grab_game()
            if frame is None:
                return
            mask, before = reader.navy_mask(frame), self.tip_mask
            self.tip_mask = mask
            tips = self.tips
            if tips and all(reader.tooltip_still_up(frame, t) for t in tips):
                self.q.put(("tips_up",))     # the same tooltip: its prices stay
                return
            region = reader.new_navy(mask, before)
            for t in tips:
                # it moved or went: look around where it was too, the next item's comes up beside it
                l, tp, r, b = t["box"]
                pad = round(160 * frame.height / reader.REF_HEIGHT)
                near = [l - pad, tp - pad, r + pad, b + pad]
                region = near if region is None else [min(region[0], near[0]), min(region[1], near[1]),
                                                      max(region[2], near[2]), max(region[3], near[3])]
            found = self.reader.look_for_tooltips(frame, region) if region else []
            if found or tips:
                self.q.put(("tips", self.tips_on_screen(found, frame)))
        except Exception as e:
            print("Looking for item tooltips failed:", e)
        finally:
            self.tip_busy = False

    def tips_on_screen(self, tips, frame):
        """Each item tooltip's place on screen, and whether its price strip fits under it."""
        cl, ct, _, _ = client_box(self.capture.hwnd) if self.capture.hwnd else (0, 0, 0, 0)
        for tip in tips:
            l, t, r, b = tip["box"]
            tip["screen"] = [cl + l, ct + t, cl + r, ct + b]
            tip["room_below"] = frame.height - b
        return tips

    def _watch(self):
        try:
            frame = self.capture.grab_game()
            if frame is None:
                self.shop_anchor = self.myshop_anchor = None   # no game: back to the usual pace
                self.q.put(("seen", None, None))
                return
            if frame.convert("L").getextrema()[1] < 12:
                # Windows hands over a black picture of a game in exclusive full screen. A loading
                # screen or a map change is black too, but only for a moment
                self.black = getattr(self, "black", 0) + 1
                if self.black >= 4:
                    self.q.put(("seen", {"error": "The game's picture comes through all black. In full screen it "
                                                  "can't be captured: set the game to windowed mode."}, None))
                return
            self.black = 0
            if frame.height < reader.MIN_HEIGHT:
                # too small to read right: reading anyway would fill Quests with misread titles. No
                # shop is read either, so back to the slow pace, not a shop's three looks a second
                self.shop_anchor = None
                self.q.put(("seen", {"error": f"The game area is {frame.width}×{frame.height}. Companion reads the game "
                                              f"only at {reader.MIN_HEIGHT} px tall or more: set the game to 1920×1080 or larger.",
                                     "too_small": [frame.width, frame.height]}, None))
                return
            self.reader.set_job(self.state["profile"].get("job"))
            # quests you're known to have going win over look-alikes when the Quest Helper lists too many
            self.reader.active_ids = {str(a.get("id")) for a in self.state["profile"].get("quests_active", []) if a.get("id")}
            seen = None
            if self.shop_anchor:
                seen = self.reader.read_shop_only(frame, self.shop_anchor)
                self.quick_reads = getattr(self, "quick_reads", 0) + 1
                if seen and self.quick_reads % 6 == 0:
                    seen = None     # a full look now and then, so the rest of the dashboard keeps up
            elif self.myshop_anchor:
                # your own store: nobody's using it, so only it, every few seconds
                seen = self.reader.read_my_shop_only(frame, self.myshop_anchor, self.myshop_panel)
                self.my_reads += 1
                if seen and self.my_reads % MYSHOP_FULL_EVERY == 0:
                    seen = None
            if seen is None:
                seen = self.reader.read(frame)
            shop = seen.get("shop")
            self.shop_anchor = shop["anchor"] if shop else None
            mine = seen.get("myshop")
            self.myshop_anchor = mine["anchor"] if mine else None
            self.myshop_panel = mine["panel_anchor"] if mine else None
            cl, ct, _, _ = client_box(self.capture.hwnd) if self.capture.hwnd else (0, 0, 0, 0)
            mini, s = seen.get("map"), seen.get("scale", 1)
            if mini and mini.get("window"):
                # the route strip hangs under the open mini map, as wide as its window
                wl, _, wr, wb = mini["window"]
                mini["strip_at"] = [cl + wl, ct + wb + round(3 * s), wr - wl + 1]
            elif mini and mini.get("collapsed"):
                # or under the collapsed mini map's bar, at its own width
                tl, _, _, tb = mini["title"]
                mini["strip_at"] = [cl + tl - round(10 * s), ct + tb + round(10 * s), None]
            elif mini:
                # open, but its frame wasn't found: beside its title, so it still stays by the mini map
                _, tt, tr, _ = mini["title"]
                mini["strip_at"] = [cl + tr + round(8 * s), ct + tt, None]
            self.tips_on_screen(seen.get("tooltips") or [], frame)
            if not seen.get("quick"):
                self.read_tips = (time.time(), seen.get("tooltips") or [])
            if not shop:
                self.last_shop = None
            if shop:
                # hovering an item in the list puts its tooltip over the rows: they can't be read under
                # it, so the same shop keeps what was read before the tooltip came up
                bl, bt, bw, bh = shop["box"]
                # a quick re-read doesn't look for tooltips: the quick tooltip check knows (while
                # drawing), else what the last full read saw, if it's recent
                if not seen.get("quick"):
                    tips = seen.get("tooltips") or []
                elif self.drawing():
                    tips = self.tips
                else:
                    tips = self.read_tips[1] if time.time() - self.read_tips[0] < 2 else []
                covered = any(t["box"][0] < bl + bw and t["box"][2] > bl and t["box"][1] < bt + bh and t["box"][3] > bt
                              for t in tips)
                last, at = self.last_shop, shop["anchor"][1:3]
                same = last and abs(last["at"][0] - at[0]) < 6 and abs(last["at"][1] - at[1]) < 6
                if covered and same and len(shop["items"]) < len(last["items"]):
                    shop["items"] = last["items"]
                elif shop["items"]:
                    self.last_shop = {"at": at, "items": shop["items"]}
                listings = [{"name": i["name"], "unit": i["unit"], "qty": i["count"], "cy": i["cy"]}
                            for i in shop["items"] if not i["sold"]]
                rows, _ = self.judge_listings(listings, shop["seller"], keep_unpriced=True)
                shop["rows"] = rows
                # where the item list is on screen, so labels can sit beside its rows
                shop["screen_box"] = [cl + bl, ct + bt, bw, bh]
                if not shop["items"] and not covered and time.time() - self.sample_ts > SAMPLE_EVERY:   # a shop we couldn't read
                    self.sample_ts = time.time()
                    (DEBUG / "samples").mkdir(exist_ok=True)
                    frame.save(DEBUG / "samples" / f"shop_{datetime.now():%Y%m%d_%H%M%S}.png")
                    for old in sorted((DEBUG / "samples").glob("shop_*.png"))[:-SAMPLES_KEPT]:
                        old.unlink(missing_ok=True)
            self.q.put(("seen", seen, preview(frame, seen)))
        except Exception as e:
            print("Reading the game failed:", e)
            self.q.put(("seen", {"error": f"Reading failed: {e}"}, None))
        finally:
            self.watching = False

    def apply_seen(self, seen, picture):
        """Fold what was just seen into the profile and the dashboard (UI thread)."""
        game = self.state.setdefault("game", {})
        if picture:
            self.state["frame"] = picture
        handle_myshop(self, seen, time.time())
        if seen is None or seen.get("error"):
            game.update(error=(seen or {}).get("error") or self.capture.error or "Can't see the game window.",
                        ts=time.time(), too_small=(seen or {}).get("too_small"))
            return
        game["too_small"] = None
        if not seen.get("quick"):
            # "in a row" means in reads that could have seen it: a closed window starts its quests over
            if not seen.get("quest"):
                for scope in [k for k in self.agree.runs if k.startswith("tab:")]:
                    self.agree.update(scope, [])
            if seen.get("helper") is None:
                self.agree.update("helper", [])
            if not seen.get("quest_complete"):
                self.notice.update("complete", [])
        prof, changed = self.state["profile"], False

        def put(key, value):
            nonlocal changed
            if value is not None and prof.get(key) != value:
                prof[key], changed = value, True

        hud, stat = seen.get("hud") or {}, seen.get("stat") or {}
        # only what fits the game's rules goes in (trust.py): a misread repeats on every read
        ok = self.gate.check(prof, seen)
        game["other_name"] = ok.get("other_name")     # another character on screen: none of it is saved
        if not ok.get("other_name") and not ok.get("blocked"):
            put("job", stat.get("job") if stat.get("job") in JOBS else hud.get("job") if hud.get("job") in JOBS else None)
        put("name", ok.get("name"))
        put("stats", ok.get("stats"))            # base stats, for where your next AP should go
        put("acc", ok.get("acc"))
        acc_cap = 40 + 6 * int(ok.get("level") or prof.get("level") or 1)
        if (prof.get("acc") or 0) > acc_cap:     # ACC well past what anyone this level has is a misread
            prof["acc"], changed = None, True
        put("mesos", ok.get("mesos"))
        hint = None
        if hud.get("level") and not hud.get("level_exact") and "level" not in ok and hud["level"] != prof.get("level"):
            hint = hud["level"]     # a guess from digit shapes not seen before: ask to confirm
        put("level", ok.get("level"))
        if stat.get("level") and stat["level"] == prof.get("level") and not (ok.get("other_name") or ok.get("blocked")):
            self.reader.learn_level(prof["level"])   # the HUD's digit shapes, from a level the gate let in
        put("skills_now", ok.get("skills_now"))
        put("sp", ok.get("sp"))
        if (qw := seen.get("quest")) and qw.get("quests"):
            lv = int(prof.get("level") or 200)
            # the names this read was matched against: the reader's list changes with your job, and
            # a job change between the read and now may have taken a name out of it
            byname = self.reader.quests_by_name
            found = [(x, byname[x["quest"]]) for x in qw["quests"] if x["quest"] in byname]
            # a quest above your level can't be taken yet, let alone done: that's a misread title
            seen_ids = [str(q["id"]) for _, q in found if (q.get("level_min") or 0) <= lv]
            lines = [x["line"] for x in qw["quests"] if x.get("line") in self.data.chains] if qw["tab"] == "in_progress" else []
            sure = self.agree.update("tab:" + qw["tab"], seen_ids + ["line:" + n for n in lines])
            ids = [i for i in dict.fromkeys(seen_ids) if i in sure]
            qw = {**qw, "quests": [{**x, "id": str(q["id"])} for x, q in found if str(q["id"]) in sure]}
            if ids and qw["tab"] == "completed":
                put("quests_done", sorted(set(map(str, prof.get("quests_done", []))) | set(ids)))
                put("quests_active", [a for a in prof.get("quests_active", []) if str(a.get("id")) not in ids])
            elif ids and qw["tab"] == "in_progress":
                # added to what's known: the window shows one page of the list, and a quest scrolled
                # out of sight is still in progress. Finished ones leave through quests_done
                have = {(a.get("id"), a.get("name")) for a in prof.get("quests_active", [])}
                new = [{"name": q["quest"], "id": q["id"]} for q in qw["quests"]]
                new = [a for a in new if (a["id"], a["name"]) not in have]
                if new:
                    put("quests_active", prof.get("quests_active", []) + new)
            if lines:
                # a quest line In Progress: its step joins your quests, unless one of its quests is
                # already going (once three reads in a row agree, like any quest seen there)
                done = set(map(str, prof.get("quests_done", [])))
                active = {str(a.get("id")) for a in prof.get("quests_active", [])}
                names = {str(q["id"]): q["name"] for q in self.data.quest_list}
                steps = [line_step(self.data.chains[n], done, active) for n in dict.fromkeys(lines) if "line:" + n in sure]
                new = [{"name": names.get(i, i), "id": i} for i in dict.fromkeys(steps) if i]
                if new:
                    put("quests_active", prof.get("quests_active", []) + new)
        # a quest tracked in the Quest Helper is in progress, and stays so in the Quests tab until the
        # game says it's done, not only while a read happens to catch it
        done = set(map(str, prof.get("quests_done", [])))
        known = {str(a.get("id")) for a in prof.get("quests_active", []) if a.get("id")} | done
        helper_seen = seen.get("helper") is not None
        sure = self.agree.update("helper", [str(q["id"]) for q in (seen.get("helper") or {}).get("quests", [])
                                            if q.get("id")]) if helper_seen else set()
        tracked = [{"name": q["quest"], "id": str(q["id"])} for q in (seen.get("helper") or {}).get("quests", [])
                   if q.get("id") and str(q["id"]) in sure and str(q["id"]) not in known]
        if tracked:
            put("quests_active", prof.get("quests_active", []) + tracked)
        if (qc := seen.get("quest_complete")):
            # "Quest Complete!": the notice cuts long names, so prefer a quest you have in progress
            cut = qc["text"].lower()
            going = [a["name"] for a in prof.get("quests_active", [])] + [h["quest"] for h in game.get("helper") or [] if h.get("quest")]
            name = next((n for n in going if n and n.lower().startswith(cut[:max(6, len(cut) - 1)])), None)
            if name is None and qc["quest"]:
                # not one you're known to have going: believe it once two reads agree (the notice stays a few seconds)
                name = qc["quest"] if qc["quest"] in self.notice.update("complete", [qc["quest"]]) else None
            q = self.reader.quests_by_name.get(name) if name else None
            if q and str(q["id"]) not in map(str, prof.get("quests_done", [])):
                put("quests_done", sorted(set(map(str, prof.get("quests_done", []))) | {str(q["id"])}))
                put("quests_active", [a for a in prof.get("quests_active", []) if a.get("name") != name])
                game["completed"] = {"name": name, "ts": time.time()}
                print(f"Quest complete: {name}")
                if (self.state.get("guide") or {}).get("id") == str(q["id"]):
                    self.state["guide"] = None              # guided quest done: the guide ends
                    if self.state.get("nav") and self.state["nav"].get("guide_to"):
                        self.state["nav"] = None
                    self.q.put(("nav",))
        mid = None
        missed = seen.get("map_missed")
        if missed and missed != getattr(self, "map_missed", None):
            print(f"Mini map title not recognised: {missed!r}")   # once per title, to fix the matching
        self.map_missed = missed or getattr(self, "map_missed", None)
        if seen.get("map"):
            nav = self.state["nav"]
            mid = self.data.match_map_name(seen["map"]["name"], prefer=[s["id"] for s in nav["steps"]] if nav else ())
            # a move counts only once a few reads in a row agree (gamedata.MapMove): a misread title
            # moved Grind and the route, and re-planned the route from the wrong map
            if self.map_move.read(self.data, prof.get("current_map"), mid):
                self.state["set_current"](mid)         # saves the profile and moves an active route along
            at = seen["map"].get("strip_at")
            if at:
                m, name = self.mini, seen["map"]["name"]
                kind = "window" if seen["map"].get("window") else "bar" if seen["map"].get("collapsed") else "title"
                near = lambda o: abs(o["x"] - at[0]) <= 4 and abs(o["y"] - at[1]) <= 4 and abs((o["w"] or 0) - (at[2] or 0)) <= 6
                same = m and m["map"] == name and m["bounds"] == self.bounds
                if same and (m["kind"] == kind and near(m) or STRIP_RANK[kind] < STRIP_RANK[m["kind"]]):
                    # the same mini map, where it was: a read a pixel or two off, or one that only made
                    # out its title, leaves the strip still
                    m["ts"], self.mini_next = time.time(), None
                elif (p := self.mini_next) and p["kind"] == kind and p["map"] == name and near(p):
                    # a new place, read the same way twice in a row: the strip moves there. One odd read
                    # (another window's border taken for the mini map's) doesn't move it
                    width = m and m["w"]
                    self.mini, self.mini_next = {**p, "ts": time.time(), "bounds": self.bounds}, None
                    if self.drawing() and at[2] != width:
                        self.redraw()              # no wider than this mini map
                    else:
                        self.layout()
                else:
                    self.mini_next = {"x": at[0], "y": at[1], "w": at[2], "map": name, "kind": kind}
        if changed:
            self.state["save_profile"]()
            print(f"Character: {prof.get('name') or '?'}, {prof['job']} level {prof['level']}")
        shop = seen.get("shop")
        if shop:
            verdicts = {(r["name"], r["unit"]): r for r in shop["rows"]}
            game["shop"] = {"seller": shop["seller"], "ts": time.time(), "items": [
                {**{k: i[k] for k in ("name", "count", "price", "unit", "sold")}, "img": self.data.item_img(i["name"]),
                 "verdict": verdicts.get((i["name"], i["unit"]), {}).get("verdict"),
                 **{k: (self.market.items.get(i["name"]) or {}).get(src) for k, src in (("median", "p"), ("p25", "p25"), ("p75", "p75"))},
                 # Cozy's own price for the item, shown beside the median as a second opinion
                 "cozy": (self.market.cozy.get(i["name"]) or {}).get("price"),
                 "npc": NPC_PRICES.get(i["name"])}
                for i in shop["items"]]}
            self.shop_rows = [r for r in shop["rows"] if r.get("parts")]
            if self.overlay.region != shop["screen_box"]:
                self.overlay.region = shop["screen_box"]
                self.overlay.place()
            self.publish()          # labels beside the rows, if drawing on the game is on
        elif self.shop_rows or self.overlay.region:     # the shop was closed
            self.shop_rows, self.overlay.region = [], None
            self.overlay.place()
            self.publish()
        if seen.get("quick"):        # a shop-only re-read: everything else stays as last seen
            game.update(error="", ts=time.time(), windows={**game.get("windows", {}), **seen["windows"]})
            return
        note_hovered(self.state, seen.get("tooltips"))
        self.read_bag(seen.get("inventory"))
        if self.drawing() and seen.get("tooltips"):
            # only adds: a full read takes about a second and can miss a tooltip that came up
            # meanwhile; the quick tooltip check is what takes them away
            self.set_tips(seen["tooltips"])
        game.update(error="", ts=time.time(), windows=seen.get("windows", {}), level_hint=hint,
                    stat=stat or game.get("stat"),
                    helper=self.counts.update(seen["helper"]["quests"]) if helper_seen else game.get("helper"),
                    map={**seen["map"], "id": mid} if seen.get("map") else game.get("map"),
                    skills=seen.get("skills") or game.get("skills"))
        if self.state.get("guide") and self.state.get("guide_tick"):
            self.state["guide_tick"]()       # follow the guided quest's counts and where you are
        handle_grind(self, seen, prof)

    def read_bag(self, inv):
        """Tell apart the items on the open inventory tab, on the side: the first look at a tab
        downloads its icons and takes a few seconds, later looks only match slots not seen before."""
        if not inv or inv.get("grid") is None or getattr(self, "bag_busy", False):
            return
        import invgrid
        if inv.get("tab") not in invgrid.KINDS:
            return
        if getattr(self, "bag", None) is None:
            from gamedata import CACHE, OSMS
            self.bag = invgrid.Bag(self.data.bag_items, lambda i: f"{OSMS}current/images/items/{i:08d}.png", CACHE / "icons")
        self.bag_busy = True

        def run():
            try:
                items = self.bag.read(inv["grid"], inv["tab"])
            except Exception as e:
                print("Reading the inventory failed:", e)
                items = []
            finally:
                self.bag_busy = False
            self.q.put(("bag", items))
        threading.Thread(target=run, daemon=True).start()

    def anchor(self):
        """Where the route strip goes under the mini map: where the mini map was last seen, for as
        long as the game window hasn't moved since (or for a few seconds, before its place is known)."""
        m = self.mini
        if not m:
            return None
        return m if (m["bounds"] and m["bounds"] == self.bounds) or time.time() - m["ts"] < MINI_SECONDS else None

    def redraw(self):
        """Draw the route strip, with the quest's step on it during a quest guide (UI thread)."""
        nav, mini = self.state["nav"], self.anchor()
        if nav:
            self.strip.show(art.route_strip(nav, self.scale, mini and mini["w"]))
        self.strip_key = bool(mini and mini["w"])
        self.layout()

    def layout(self):
        """The route strip stays by the mini map; only until the mini map has been seen does it wait
        in the chosen corner of the game window."""
        mini = self.anchor()
        if mini:
            self.strip.move(mini["x"], mini["y"])
            return
        l, t, r, b = self.bounds or (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        s, corner, (w, h) = self.scale, self.cfg["nav_corner"], self.strip.size
        self.strip.move(l + 16 * s if "left" in corner else r - w - 16 * s,
                        t + 70 * s if "top" in corner else b - h - 70 * s)

    def set_tips(self, tips):
        """Prices under the item tooltips just read: each site's in its color, what an NPC pays when
        it's known, and nothing for an untradable item. Under the tooltip, or over it when the game
        window ends right below it (UI thread)."""
        self.tips, self.tips_ts = tips, time.time()
        key = [(t["name"], tuple(t["screen"]), self.scale) for t in tips]
        if key == self.tips_key:
            return
        self.tips_key = key
        for i, card in enumerate(self.tip_cards):
            tip = tips[i] if i < len(tips) else None
            self.tip_shown[i] = bool(tip and not tip["untradable"])
            if not self.tip_shown[i]:
                continue
            npc = self.data.npc_price(tip["name"])
            v = advisor.verdict(tip["name"], None, self.state["profile"], self.data, self.market)
            note = advisor.short(v) or (f"NPC pays {price_text(npc)}" if npc else None)
            img = art.price_strip(source_prices(tip["name"], self.market), self.scale,
                                  tip["screen"][2] - tip["screen"][0] + 1, note)
            card.show(img)
            l, t, _, b = tip["screen"]
            gap = round(3 * self.scale)
            card.move(l, b + gap if tip["room_below"] > img.height + gap else t - img.height - gap)
        self.show_tips()            # now, not at the next focus_loop: the price is wanted right away

    def show_tips(self):
        """Show the tooltip price strips while their tooltip is up and the game is in front."""
        up = self.game_in_front() and time.time() - self.tips_ts < TIP_SECONDS
        for i, card in enumerate(self.tip_cards):
            want, shown = up and self.tip_shown[i], card.win.state() != "withdrawn"
            if want and not shown:
                card.win.deiconify()
            elif not want and shown:
                card.win.withdraw()

    def game_in_front(self):
        return bool(self.game_hwnd) and foreground_window() == self.game_hwnd and not getattr(self, "user_hidden", False)

    def route_active(self):
        """True while a route is running; the panel goes away 15 s after you arrive, unless a quest
        guide is on (then it stays, showing the quest's counts while you hunt)."""
        nav = self.state["nav"]
        if not nav:
            return False
        if nav.get("quest"):
            return True
        if nav["steps"][nav["i"]].get("arrived"):
            nav.setdefault("arrived_at", time.time())
            return time.time() - nav["arrived_at"] < 15
        nav.pop("arrived_at", None)
        return True

    def focus_loop(self):
        """Show on-game drawing only while the game is the window in front, keep the route strip
        under the mini map (or in the game window's corner), and end the capture session when
        nothing is reading it."""
        self.root.after(500, self.focus_loop)     # first, so a failed step doesn't end the loop
        self.focus_ticks = getattr(self, "focus_ticks", 0) + 1
        if self.focus_ticks % 6 == 1:   # every 3 s: is the game running, and where is its window?
            # with screen reading off the app doesn't even look for the game window
            self.game_hwnd = find_window(self.cfg["game_title"]) if self.cfg["screen_reading"] else None
            self.state["game_found"] = bool(self.game_hwnd)
            # the game's drawing size, so the dashboard's setup can say how well it reads
            self.state["game_size"] = list(client_box(self.game_hwnd)[2:]) if self.game_hwnd else None
            if self.game_hwnd and self.drawing():
                scale = art.dpi_scale(self.game_hwnd)
                if scale != self.overlay.scale:          # game moved to a monitor with other scaling
                    self.scale = self.overlay.scale = scale
                    self.overlay.place()
                    self.overlay.draw(self.results)
                    self.redraw()
                self.bounds = window_bounds(self.game_hwnd)
        self.capture.stop_if_idle()
        if self.drawing():
            mini = self.anchor()
            if self.state["nav"] and bool(mini and mini["w"]) != self.strip_key:
                self.redraw()       # the mini map opened or went away: the strip changes width
            else:
                self.layout()       # and place, under the mini map or in the corner
            front = self.game_in_front()
            shop_open = bool(self.shop_rows or self.results) and time.time() - getattr(self, "rows_ts", 0) < SHOP_LABEL_SECONDS
            active, nav = self.route_active(), self.state["nav"]
            self.show_tips()        # prices under an item tooltip while it's up
            # labels only while a shop is being read; the route strip during a route
            for w, want in ((self.overlay.win, front and shop_open),
                            (self.strip.win, front and active)):
                shown = w.state() != "withdrawn"
                if want and not shown:
                    w.deiconify()
                elif not want and shown:
                    w.withdraw()

    def set_auto(self, on):
        """Turn auto-scan on or off, keeping a single timer however fast it's toggled."""
        self.state["auto"] = on
        if self.auto_job:
            self.root.after_cancel(self.auto_job)
            self.auto_job = None
        if on:
            self.auto_loop()

    def auto_loop(self):
        self.auto_job = None
        if not self.state["auto"]:
            return
        self.scan()
        self.auto_job = self.root.after(int(self.cfg["auto_interval"] * 1000), self.auto_loop)

    def scan(self):
        if self.busy or not self.cfg["region"] or not self.cfg["screen_reading"]:
            return
        self.busy = True
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        try:
            img = self.capture.grab(self.cfg["region"])
            if img is None:
                self.q.put(("result", [], f"Not scanned: {self.capture.error}"))
                return
            img.save(DEBUG / "last_capture.png")
            lines = ocr_lines(img, self.cfg["ocr_scale"])
            (DEBUG / "last_ocr.txt").write_text("\n".join(f"{int(y):4d}  {txt}" for txt, x, y, _, _ in lines), "utf-8")
            out, deals = self.judge_rows(lines, self.cfg["row_tolerance"])
            note = f"{len(out)} rows read, {deals} deals" if out else "No items read. Check debug/last_ocr.txt"
            self.q.put(("result", out, note))
        except Exception as e:
            self.q.put(("result", [], f"Scan error: {e}"))

    def judge_rows(self, lines, tol):
        """Shop rows from a selected area's OCR lines (see judge_listings)."""
        rows = [parse_row(row, self.market, self.cfg) for row in group_rows(lines, tol)]
        return self.judge_listings([r for r in rows if r])

    def judge_listings(self, listings, seller=None, keep_unpriced=False):
        """Price verdicts for shop listings, logged to your price history, deals announced.
        Listings the market has no price for are kept (as unpriced) only if keep_unpriced."""
        out, deals = [], 0
        seen_now = set()
        for r in listings:
            text, color, verdict, parts = judge(r, self.market)
            if not text:
                if not keep_unpriced:
                    continue
                text, color = "no market price yet", GREY
            if verdict != "check":
                self.log.add(r, verdict, seller)
            key = (r["name"], r["unit"], seller)
            seen_now.add(key)
            if verdict in ("snipe", "npc"):
                deals += 1
                # a deal counts once two reads in a row agree on its price, so a misread never beeps
                if key in self.last_listings and key not in self.announced:
                    self.announced.add(key)
                    stamp = datetime.now().strftime("%H:%M:%S")
                    print(f"[{stamp}] {r['name']} at {fmt(r['unit'])}: {text}")
                    self.state["deals"].insert(0, {"time": stamp, "name": r["name"], "unit": r["unit"],
                                                    "text": text, "verdict": verdict})
                    del self.state["deals"][40:]
                    if self.cfg["sound"] and sys.platform == "win32":
                        import winsound
                        winsound.MessageBeep()
            out.append({"cy": r["cy"], "name": r["name"], "unit": r["unit"], "verdict": verdict,
                        "text": f"{r['name']}: {text}", "color": color, "parts": parts})
        self.last_listings = seen_now
        return out, deals

    def refresh_prices(self):
        threading.Thread(target=self.data.refresh_market, daemon=True).start()
        self.root.after(30 * 60 * 1000, self.refresh_prices)
