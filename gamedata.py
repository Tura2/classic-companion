"""
Game data and recommendations for MapleStory Classic World.

Sources
  - OSMS Data Explorer (MIT licensed datamine): monsters, maps, equipment, skills.
    https://github.com/ohmi69/osms_datamine_dashboard
  - maplestory-classic.com market.json (published for developers): real Free Market sale prices.
  - Cozy Market's public item pages (tools/scrape_cozy.py): a second sale price per item.
"""
import json
import math
import os
import re
import threading
import time
from datetime import datetime

import requests

from paths import APP_DIR, RES_DIR

HERE = APP_DIR
# SP order per job, from the class guides (meowdb.com/msclassic/guides); see make_builds.py
BUILDS_FILE = RES_DIR / "builds.json"
CACHE = HERE / "cache"
CACHE.mkdir(exist_ok=True)
MAP_CACHE = CACHE / "maps"   # map pictures, shrunk to MAP_MAX and kept, so a route's maps show at once
MAP_MAX = 4096               # longest side: the originals run to 7000 px and 1.7 MB each

OSMS = "https://raw.githubusercontent.com/ohmi69/osms_datamine_dashboard/main/data/"
# Quest steps (who to talk to where, who takes it back) and monster drops: Classic Maple Wiki
# contributors (classicmaple.wiki), much of it from MapleClassic Wiki (mapleclassic.wiki), under
# CC BY-NC-SA 4.0. Reformatted here; credited with links wherever it's shown.
WIKI = "https://classicmaple.wiki/data/"
# Every monster's drop list (rates only where players counted them), from MapleClassic Wiki via Club FM
CLUBFM = "https://raw.githubusercontent.com/maplefm/maplefm.github.io/live/data/itemguide.json"
MARKET_URL = "https://maplestory-classic.com/market.json"
UA = {"User-Agent": "companion/1.0 (personal use)"}

# NPC shop buy-back prices (game data, via maplestory-classic.com). Check in game before bulk buys.
NPC_PRICES = {
    "Opal Ore": 160, "Emerald": 400, "Wild Boar Tooth": 25, "Sapphire Ore": 120, "Diamond Ore": 240,
    "Charm of the Undead": 24, "Orihalcon Ore": 100, "Green Mushroom Cap": 14, "Bubbling's Huge Bubble": 15,
    "Topaz": 400, "Amethyst Ore": 200, "Slime Bubble": 50, "Horny Mushroom Cap": 22, "Evil Eye Tail": 27,
    "Opal": 800, "Silver Ore": 80, "Fire Boar's Tooth": 32, "Lupin's Banana": 37,
}

# job -> skills.json family, equipment job label, main stat, secondary stat, weapon types, skill groups
FAMILIES = {
    "warrior": ("Warrior", "STR", "DEX"),
    "magician": ("Mage", "INT", "LUK"),
    "archer": ("Bowman", "DEX", "STR"),
    "rogue": ("Thief", "LUK", "DEX"),
}
JOBS = {
    "Beginner":    (None,       [], ["Beginner"]),
    "Warrior":     ("warrior",  ["1H Sword", "2H Sword", "1H Axe", "2H Axe", "1H Blunt Weapon", "2H Blunt Weapon", "Spear", "Polearm"], ["Warrior"]),
    "Fighter":     ("warrior",  ["1H Sword", "2H Sword", "1H Axe", "2H Axe"], ["Warrior", "Fighter"]),
    "Page":        ("warrior",  ["1H Sword", "2H Sword", "1H Blunt Weapon", "2H Blunt Weapon"], ["Warrior", "Page"]),
    "Spearman":    ("warrior",  ["Spear", "Polearm"], ["Warrior", "Spearman"]),
    "Magician":    ("magician", ["Wand", "Staff"], ["Magician"]),
    "F/P Wizard":  ("magician", ["Wand", "Staff"], ["Magician", "F/P Wizard"]),
    "I/L Wizard":  ("magician", ["Wand", "Staff"], ["Magician", "I/L Wizard"]),
    "Cleric":      ("magician", ["Wand", "Staff"], ["Magician", "Cleric"]),
    "Archer":      ("archer",   ["Bow", "Crossbow"], ["Archer"]),
    "Hunter":      ("archer",   ["Bow"], ["Archer", "Hunter"]),
    "Crossbowman": ("archer",   ["Crossbow"], ["Archer", "Crossbowman"]),
    "Rogue":       ("rogue",    ["Claw", "Dagger"], ["Rogue"]),
    "Assassin":    ("rogue",    ["Claw"], ["Rogue", "Assassin"]),
    "Bandit":      ("rogue",    ["Dagger"], ["Rogue", "Bandit"]),
}
SLOT_ORDER = ["Weapon", "Hat", "Top", "Bottom", "Overall", "Shoes", "Glove", "Shield", "Earring", "Cape"]

# ACC to never miss a monster at equal level, by its Avoidability. Classic World doesn't use the
# old GMS formula; these points are NiaDB's acc_needed values (meowdb.com/msclassic, monster
# database), interpolated in between.
ACC_TABLE = [(0, 0), (5, 17), (6, 21), (7, 24), (8, 27), (9, 31), (11, 37), (12, 40), (13, 44), (14, 47),
             (15, 50), (16, 54), (17, 57), (18, 60), (20, 66), (21, 70), (22, 73), (24, 79), (25, 82), (26, 86),
             (27, 89), (28, 92), (29, 95), (30, 98), (31, 101), (32, 104), (33, 108), (34, 111), (35, 114),
             (36, 117), (37, 120), (41, 132), (42, 136), (48, 154), (49, 157)]


def acc_needed(avoid, gap=0):
    """Estimated ACC to never miss. A monster above your level scales your ACC by
    255 / (10 x gap + 255) before it's compared with its Avoidability (the Classic hit formula)."""
    if not avoid or avoid <= 0:
        return 0
    pts = ACC_TABLE
    i = next((i for i, (a, _) in enumerate(pts) if a > avoid), len(pts) - 1)
    (a0, n0), (a1, n1) = pts[i - 1], pts[i]
    base = n0 + (n1 - n0) * (avoid - a0) / (a1 - a0)
    return math.ceil((base - 0.5) * (10 * max(0, gap) + 255) / 255)


def num(v):
    try:
        return float(v) if "." in str(v) else int(v)
    except (TypeError, ValueError):
        return 0


def read_cache(path):
    """A cached download, or None when it's missing or damaged (a crash mid-write, a full disk)."""
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def load_drops(guide):
    """Club FM's item guide -> {monster id: [{"item", "rate"}]}. A row is [monster, level, rate or None,
    kills, map, ?, monster id]."""
    out = {}
    for item, entry in (guide.get("items") or {}).items():
        for row in entry.get("d") or []:
            if len(row) > 6 and row[6] is not None:
                out.setdefault(int(row[6]), []).append({"item": item, "rate": row[2]})
    return out


def fetch_json(url, name, max_age):
    path = CACHE / name
    if path.exists() and time.time() - path.stat().st_mtime < max_age and (data := read_cache(path)) is not None:
        return data
    try:
        r = requests.get(url, timeout=40, headers=UA)
        r.raise_for_status()
        data = r.json()
        tmp = path.with_name(name + ".tmp")     # written whole, then swapped in
        tmp.write_text(json.dumps(data), "utf-8")
        os.replace(tmp, path)
        return data
    except Exception as e:
        print(f"Download failed for {name}: {e}")
        if (data := read_cache(path)) is not None:
            return data
        raise SystemExit(f"No data for {name} yet. Connect to the internet and start again.")


# ---------------------------------------------------------------- map names as read
# Half the maps end in a number: "Ant Tunnel II", "Line 1 <Area 3>". OCR reads the I of a Roman
# numeral as l, 1, | or !, and a plain best match then lands on the map next door ("Ant Tunnel Il"
# scores higher against Ant Tunnel I than Ant Tunnel II). So the number is fixed up, then must match.
ROMAN_READ = re.compile(r"(?<=\s)([IVXl1|!]*[IVXl|!][IVXl1|!]*)\s*$")
# The <...> part is compared loosely: OCR reads "<1st Stage>" as "<Ist Stage>", "<1 st Stage>" or
# "<1st Stage)" (seen in Kerning PQ, 2026-11-07), and the game itself writes "<4th stage>".
NUMBER = re.compile(r"(?:(?<=\s)([IVX]+)|(<[^>)\]}]*[>)\]}]?))\s*$")
ORDINAL_ONE = re.compile(r"(?<![a-z0-9])[il|!](?=st(?![a-z]))")


def fix_numeral(text):
    """"Ant Tunnel Il" -> "Ant Tunnel II": a last word made only of I-like strokes, V and X."""
    return ROMAN_READ.sub(lambda m: m.group(1).translate(str.maketrans("l1|!", "IIII")), text.strip())


def name_number(name):
    """A map name's number ("II", "<area3>"), or None. The <...> part comes back without its
    brackets, spaces or case, with an I-like stroke before "st" read as 1."""
    m = NUMBER.search(name or "")
    if not m:
        return None
    if m.group(1):
        return m.group(1)
    inner = ORDINAL_ONE.sub("1", m.group(2).strip("<>)]}").lower())
    return "<" + re.sub(r"\s+", "", inner) + ">"


# Stage titles ("1st Accompaniment <2nd Stage>") read far worse in a live run (2026-11-08): the
# ordinal comes out as "cist", "end", "Ord" or "4tIi", the "<" is often lost and junk follows the
# ">". The stage is then told by the ordinal's ending, and the rest of the title is matched alone.
STAGE_WORD = re.compile(r"<?\s*([a-z0-9|!]{1,5}(?:\s+[a-z]{2})?)\s*stag")
STAGE_BASE_CUTOFF = 80


def stage_of(text):
    """(the title before its stage, the stage: "1"-"4" or "last"), or None if it names no stage."""
    low = (text or "").lower()
    m = None
    for m in STAGE_WORD.finditer(low):
        pass
    if not m:
        return None
    word = re.sub(r"\s+", "", m.group(1))
    if "a" in word:
        stage = "last"
    elif word[0] in "234":
        stage = word[0]
    elif word.endswith("st") or word[0] == "1":
        stage = "1"
    elif word.endswith("nd"):
        stage = "2"
    elif word.endswith("rd"):
        stage = "3"
    elif re.search(r"t[hil|!]*$", word):
        stage = "4"
    else:
        return None
    return text[:m.start()].strip(" <"), stage


def match_place(text, names, cutoff):
    """The name in names the text is, or None: the closest one with the same number as the text.
    A text whose number doesn't match any close name is left unread, never read as the next map."""
    from rapidfuzz import fuzz, process
    text = fix_numeral(text or "")
    if len(text) < 3:
        return None
    want = name_number(text)
    for name, _, _ in process.extract(text, names, scorer=fuzz.ratio, score_cutoff=cutoff, limit=8):
        if name_number(name) == want:
            return name
    read = stage_of(text)
    if not read or len(read[0]) < 3:
        return None
    best = None
    for name in names:
        st = stage_of(name)
        if st and st[1] == read[1]:
            score = fuzz.ratio(read[0].lower(), st[0].lower())
            if score >= STAGE_BASE_CUTOFF and (best is None or score > best[0]):
                best = (score, name)
    return best[1] if best else None


# ---------------------------------------------------------------- market prices
class Market:
    def __init__(self, force=False):
        data = fetch_json(MARKET_URL, "market.json", 0 if force else 1800)
        self.updated = data.get("updatedAt", "?")
        self.cozy = Cozy()
        today = self.updated[:10]
        self.items = {}
        for it in data.get("items", []):
            if it.get("p") is None or it.get("p25") is None:
                continue
            h = [e for e in it.get("h", []) if e[0] != today][-4:]   # last full days
            trend = (h[-1][1] - h[0][1]) / h[0][1] if len(h) >= 4 and h[0][1] else 0.0
            self.items[it["n"]] = {
                "p": it["p"], "p25": it["p25"], "p75": it.get("p75") or it["p"], "k": it.get("k", ""),
                "st": it.get("st") or 0, "trend": trend, "vol": h[-1][2] if h else 0, "asks": it.get("asks") or 0,
            }
        self.names = sorted(set(self.items) | set(NPC_PRICES))

    def match(self, text, minscore):
        from rapidfuzz import fuzz, process
        text = text.strip()
        if len(text) < 4:
            return None
        hit = process.extractOne(text, self.names, scorer=fuzz.WRatio, score_cutoff=minscore)
        return hit[0] if hit else None

    def flips(self, mesos, cap=0.25, limit=30):
        out = []
        for name, it in self.items.items():
            buy, sell = math.floor(it["p25"]), it["p"]
            per = sell - buy
            if buy <= 0 or per / buy < 0.03:
                continue
            crowd = it["asks"] / it["vol"] if it["vol"] else 99
            if it["trend"] < -0.2 or it["st"] < 0.5 or crowd > 6 or it["vol"] < 50:
                continue
            units = min(int(mesos * cap // buy), max(1, int(it["vol"] * 0.05)))
            if units < 1:
                continue
            mult = (0.5 if it["trend"] < -0.08 else 1.15 if it["trend"] > 0.08 else 1) * (0.7 if crowd > 3 else 1)
            out.append({"name": name, "type": it["k"], "buy": buy, "sell": sell, "per": per, "units": units,
                        "round": units * per, "vol": it["vol"], "st": it["st"], "trend": it["trend"],
                        "score": units * per * it["st"] * mult})
        out.sort(key=lambda x: -x["score"])
        npc = []
        for name, pays in NPC_PRICES.items():
            fm = self.items.get(name, {}).get("p")
            if fm and fm < pays:
                npc.append({"name": name, "fm": fm, "npc": pays, "per": pays - fm,
                            "units": int(mesos * cap // fm), "round": int(mesos * cap // fm) * (pays - fm)})
        npc.sort(key=lambda x: -(x["per"] / x["fm"]))
        return {"flips": out[:limit], "npc": npc}


# ---------------------------------------------------------------- second opinion
COZY_FILE = CACHE / "cozy_items.json"
COZY_MAX_AGE = 14 * 86400      # older prices than this are left out
QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})


def plain(name):
    """The name with curly quotes made straight: the two price sites write some names differently
    (maplestory-classic.com has Black “Hit Me” Shirt, Cozy Market Black "Hit Me" Shirt)."""
    return name.translate(QUOTES)


class Cozy:
    """Cozy Market's usual sale price per item, read from its public item pages by
    tools/scrape_cozy.py into cache/cozy_items.json.

    One number per item, with no spread and no history, so the verdicts take their shape from
    maplestory-classic.com and Cozy's number is checked against it (sniper.judge). A missing, damaged
    or too old file is left out, and the app works as it did without it.
    """
    def __init__(self):
        self.items, self.updated, self.stale = {}, None, False
        try:
            data = json.loads(COZY_FILE.read_text("utf-8"))
        except (OSError, ValueError):
            return
        # each price by its own age: one page the site keeps failing on must not age out the rest
        oldest = None
        for r in data.get("items", {}).values():
            # Only prices buyers paid. An item with no sales yet publishes a seller's asking price
            # instead (basis "listed"), and that can't stand beside a sale median.
            if not r or not r.get("price") or not r.get("name") or r.get("basis") == "listed":
                continue
            try:
                fetched = datetime.fromisoformat(r["fetched"].replace("Z", "+00:00")).timestamp()
            except (KeyError, AttributeError, ValueError):
                continue
            if time.time() - fetched > COZY_MAX_AGE:
                self.stale = True       # some prices left out as too old
                continue
            key = plain(r["name"])
            # Cozy gives an item's male and female versions the same name. Keep the one that trades
            # most, which is the one the name usually means.
            old = self.items.get(key)
            if old is None or (r.get("sales") or 0, r.get("listings") or 0) > (old.get("sales") or 0, old.get("listings") or 0):
                self.items[key] = r
            if oldest is None or fetched < oldest[0]:
                oldest = (fetched, r["fetched"])
        self.updated = oldest[1] if oldest else None    # when the oldest price in use was fetched
        self.stale = self.stale and not self.items     # "stale" only when nothing is left

    def get(self, name):
        return self.items.get(plain(name))


# ---------------------------------------------------------------- game data
class GameData:
    def __init__(self, force=False):
        age = 0 if force else 12 * 3600
        self.monsters = fetch_json(OSMS + "current/monsters.json", "monsters.json", age)["monsters"]
        items = fetch_json(OSMS + "current/items.json", "items.json", age)
        self.equips = [i for i in items["items"] if i.get("category") == "Equipment"]
        # what an NPC pays for an equip (the game data's "price"); other items only from NPC_PRICES
        self.npc_sell = {i["name"]: int(i["price"]) for i in self.equips if i.get("name") and i.get("price")}
        self.equip_names = {i["name"] for i in self.equips if i.get("name")}
        self.item_ids = {i["name"]: int(i["id"]) for i in items["items"] + items.get("scrolls", [])
                         if i.get("name") and i.get("id")}
        self.scroll_rates = {s["name"]: s["success_rate"] for s in items.get("scrolls", [])
                             if s.get("name") and s.get("success_rate") is not None}
        try:            # optional: without it, the map you're on shows its monsters and no drops
            self.drops_by_mob = load_drops(fetch_json(CLUBFM, "clubfm_itemguide.json", age))
        except (Exception, SystemExit) as e:
            print("Drop lists unavailable:", e)
            self.drops_by_mob = {}
        self.skills = fetch_json(OSMS + "current/skills.json", "skills.json", age)
        maps = fetch_json(OSMS + "current/maps.json", "maps.json", age)
        portals = fetch_json(OSMS + "current/portals.json", "portals.json", age)
        self.renders = fetch_json(OSMS + "current/map_manifest.json", "map_manifest.json", age)
        self.npc_names = {int(k): v.get("name") for k, v in (maps.get("npc_lookup") or {}).items() if k.isdigit()}
        self.maps = {m["id"]: m for r in maps["regions"] for m in r["maps"]}
        self.portals = {int(k): v for k, v in portals.items()}
        self.graph = {}
        for mid, ps in self.portals.items():
            for p in ps:
                dest = int(p.get("dest_map") or 0)
                if dest == mid or dest not in self.maps:
                    continue
                best = self.graph.setdefault(mid, {}).get(dest)
                if best is None or (p.get("type") == 2 and best.get("type") != 2):
                    self.graph[mid][dest] = p
        quests = fetch_json(OSMS + "current/quests.json", "quests.json", age)
        self.quest_list = quests["quests"]
        # quest lines, as the Quest window names them ("Caretaker's Ledger"): line -> its quest ids, in order
        self.chains = {c["parent"]: [str(i) for i in c["quest_ids"]] for c in quests.get("chains", []) if c.get("parent")}
        more = {}         # a few lines are only named on their quests, in the quests' order
        for q in self.quest_list:
            if q.get("parent") and q["parent"] not in self.chains:
                more.setdefault(q["parent"], []).append(str(q["id"]))
        self.chains.update(more)
        self.npc_maps = {}
        for mid, m in self.maps.items():
            for pos in m.get("npc_positions") or []:
                self.npc_maps.setdefault(pos["id"], []).append({"map": mid, "x": pos["x"], "y": pos["y"]})
        self.mob_maps = {}
        for mob in self.monsters:
            best = max(mob.get("maps") or [], key=lambda x: x.get("count") or 0, default=None)
            if best:
                self.mob_maps[mob.get("id")] = {"map": best["id"], "name": best["name"], "count": best.get("count")}
        self.map_labels = {f"{m['name']} ({m.get('street_name') or m.get('region')})": i for i, m in self.maps.items()}
        self.market = Market(force)
        try:
            self.builds = json.loads(BUILDS_FILE.read_text("utf-8"))
        except (OSError, ValueError):
            self.builds = {}
        self.npc_ids = {name: i for i, name in self.npc_names.items() if name}
        self.mob_ids = {m["name"]: m.get("id") for m in self.monsters}
        self.load_wiki(age)

    def load_wiki(self, age):
        """Quest steps and monster drops from Classic Maple Wiki. Optional: without it, quests show
        what the game data has (giver, requirements) and the guide goes back to the giver."""
        self.wiki_quests, self.drops = {}, {}
        try:
            w = {c: fetch_json(WIKI + f"{c}.json", f"wiki_{c}.json", age) for c in ("quests", "monsters", "npcs", "maps", "items")}
        except (Exception, SystemExit) as e:
            print("Quest steps and drops unavailable:", e)
            return
        self.wiki_names = {c: {r["id"]: r["name"] for r in w[c]} for c in ("npcs", "maps", "items", "monsters")}
        self.wiki_quests = {r["name"].lower(): r for r in w["quests"]}
        for m in w["monsters"]:
            for d in m.get("drops") or []:
                item = self.wiki_names["items"].get(d.get("item"))
                if item and d.get("rate_percent"):
                    self.drops.setdefault(item, []).append({"monster": m["name"], "rate": d["rate_percent"],
                                                            "kills": d.get("sample_kills"), "source": m.get("source_page")})
        for rows in self.drops.values():
            rows.sort(key=lambda r: -r["rate"])

    def wiki_quest(self, name):
        """The wiki's record of a quest: its steps and who to bring it back to, or None."""
        q = self.wiki_quests.get((name or "").lower())
        if not q:
            return None
        nm = self.wiki_names
        steps = []
        for st in q.get("steps") or []:
            if st.get("monster"):
                steps.append({"kind": "monster", "name": nm["monsters"].get(st["monster"], st["monster"].replace("-", " ").title())})
            elif st.get("npc"):
                steps.append({"kind": "npc", "name": nm["npcs"].get(st["npc"], st["npc"].replace("-", " ").title()),
                              "map": nm["maps"].get(st.get("map")) if st.get("map") else None})
            elif st.get("map"):
                steps.append({"kind": "map", "map": nm["maps"].get(st["map"], st["map"])})
        turn = nm["npcs"].get(q.get("turn_in")) if q.get("turn_in") else None
        return {"steps": steps, "turn_in": turn, "source": q.get("source_page")}

    def turn_in(self, q):
        """Who takes the quest back and where they stand: the wiki's turn-in NPC, else the one the
        quest's own words send you to ("deliver a letter to Lucas"), else the giver."""
        w = self.wiki_quest(q["name"])
        name = (w or {}).get("turn_in") or self.sent_to(q) or q.get("npc_name")
        npc_id = self.npc_ids.get(name, q.get("npc_id") if name == q.get("npc_name") else None)
        return name, npc_id, self.npc_place(npc_id) if npc_id is not None else None

    def sent_to(self, q):
        """The NPC the quest's what-to-do line sends you to ("deliver it to Mrs. Ming Ming", "return
        to Dances with Balrog", "to the Warrior Job Instructor"), if it names one with a place on a
        map; None otherwise. The last one named is who you end with ("take it to Grendel the Really
        Old ... then talk to Arwen the Fairy again" ends with Arwen, who gave it, so None). Only for
        a quest that hands you something to carry, or asks for nothing to hunt or collect: one that
        sends you out to collect ("go back to Shane in Ellinia", who only takes you to the herbs) is
        brought back to whoever gave it."""
        asks = any(r.get("type") in ("mob", "item") for r in q.get("requirements_list") or [])
        if asks and not q.get("start_items"):
            return None
        if getattr(self, "_npc_names", None) is None:
            # whole names only, longest first, so "Grendel the Really Old" isn't cut to "Grendel"
            names = sorted((n for n in self.npc_ids if n), key=len, reverse=True)
            self._npc_names = re.compile(r"\bto\s+(?:the\s+)?(" + "|".join(map(re.escape, names)) + r")(?![\w'])")
        named = [m.group(1) for m in self._npc_names.finditer(self.quest_text(q)[1] or "")
                 if m.group(1) == q.get("npc_name") or self.npc_place(self.npc_ids[m.group(1)])]
        return named[-1] if named and named[-1] != q.get("npc_name") else None

    @staticmethod
    def quest_text(q):
        """(what the quest is about, what to do), from the game's own description. Most have three
        lines: a teaser before you take it, what to do while it's going, and how it ended. Two-line
        ones skip the teaser."""
        lines = [ln.strip() for ln in (q.get("description") or "").split("\n") if ln.strip()]
        if len(lines) >= 3:
            return lines[0], lines[1]
        return None, lines[0] if lines else None

    def hops_from(self, start):
        """{map id: portals to walk through from start}, for every map you can reach."""
        if getattr(self, "_hops", (None,))[0] == start:
            return self._hops[1]
        from collections import deque
        dist, todo = {start: 0}, deque([start])
        while todo:
            u = todo.popleft()
            for v in self.graph.get(u, {}):
                if v not in dist:
                    dist[v] = dist[u] + 1
                    todo.append(v)
        self._hops = (start, dist)
        return dist

    def hunt_spot(self, mob_id, start=None):
        """Where to hunt a monster: {"map", "name", "count", "hops"}. Of the maps with at least half
        as many of it as the busiest, the nearest from where you are; the busiest if that's unknown.
        None if it isn't known to spawn anywhere."""
        if not hasattr(self, "_mob_by_id"):
            self._mob_by_id = {m.get("id"): m for m in self.monsters}
        spots = [x for x in (self._mob_by_id.get(mob_id) or {}).get("maps") or [] if x["id"] in self.maps and x.get("count")]
        if not spots:
            return None
        dist = self.hops_from(start) if start in self.maps else {}
        top = max(x["count"] for x in spots)
        best = min(spots, key=lambda x: (x["count"] < top / 2, dist.get(x["id"], 999) if dist else 0, -x["count"]))
        return {"map": best["id"], "name": best["name"], "count": best["count"], "hops": dist.get(best["id"]) if dist else None}

    def mob_line(self, mob_id, level):
        """"Lv 20, 296 HP, ~99 ACC to always hit": how hard a monster is for you."""
        if not hasattr(self, "_mob_by_id"):
            self._mob_by_id = {m.get("id"): m for m in self.monsters}
        m = self._mob_by_id.get(mob_id)
        if not m:
            return ""
        acc = acc_needed(m.get("eva") or 0, (m.get("level") or 0) - level)
        return f"Lv {m.get('level')}, {m.get('hp'):,} HP" + (f", ~{acc} ACC to always hit" if acc else "")

    def guide_steps(self, q, have, accepted, checked, start, level):
        """The quest, step by step: take it, each monster to hunt and item to collect, anyone the
        wiki says to see on the way, and who to bring it back to. Each step: key, kind, text (what
        to do), goal (short, for the strip on the game), how (where and how hard), where (the map to
        go to), npc (who to circle there), have / need, done. A step is done when the game's Quest
        Helper shows its count reached, or when you tick it (checked)."""
        given = {r.get("name") for r in q.get("start_items") or []}
        steps = []
        place = self.npc_place(q.get("npc_id")) if q.get("npc_id") is not None else None
        steps.append({"key": "take", "kind": "take", "text": f"Take the quest from {q['npc_name']}",
                      "goal": f"Talk to {q['npc_name']}", "how": f"in {place['name']}" if place else "",
                      "where": self.map_info(place["id"]) if place else None,
                      "npc": {"x": place["x"], "y": place["y"], "name": q["npc_name"]} if place else None,
                      "done": accepted or "take" in checked})
        reqs = [r for r in q.get("requirements_list") or [] if r.get("type") in ("mob", "item") and r.get("count")]
        hunted = [r for r in reqs if r["type"] == "mob"]
        for r in reqs:
            if r["type"] == "item" and r["name"] in given:
                continue        # handed to you when you take the quest: you only carry it
            key, got, need = "req:" + r["name"], have.get(r["name"]), r["count"]
            step = {"key": key, "kind": r["type"], "name": r["name"], "have": got, "need": need, "npc": None, "where": None}
            if r["type"] == "mob":
                spot = self.hunt_spot(r.get("id"), start)
                step.update(text=f"Defeat {need} {r['name']}", goal=f"Hunt {r['name']}",
                            how=", ".join(x for x in (self.mob_line(r.get("id"), level),
                                                      f"most at {spot['name']}" if spot else "") if x))
            else:
                drops = self.drops.get(r["name"], [])
                src = drops[0] if drops else None
                mob_id = self.mob_ids.get(src["monster"]) if src else None
                if src is None and len(hunted) == 1:
                    mob_id = hunted[0].get("id")    # quest items mostly drop from the quest's own monster
                spot = self.hunt_spot(mob_id, start) if mob_id is not None else None
                price = self.market.items.get(r["name"], {})
                buy = f"or buy all {need} for about {math.floor(price['p25']) * need:,} mesos" if price else ""
                if src:
                    kills = math.ceil(need / (src["rate"] / 100)) if src["rate"] else None
                    how = [f"drops from {src['monster']} ({src['rate']:g}%" + (f", about {kills:,} kills)" if kills else ")"),
                           f"most at {spot['name']}" if spot else "", buy]
                    goal = f"Collect {r['name']} from {src['monster']}"
                elif spot:
                    how = [f"likely drops from {hunted[0]['name']}, the monster this quest has you hunt",
                           f"most at {spot['name']}", buy]
                    goal = f"Collect {r['name']} from {hunted[0]['name']}"
                else:
                    how = ["where it drops isn't known", buy]
                    goal = f"Collect {r['name']}"
                step.update(text=f"Collect {need} {r['name']}", goal=goal, how="; ".join(x for x in how if x))
            if spot:
                step["where"] = self.map_info(spot["map"])
            step["done"] = (got is not None and got >= need) or key in checked
            steps.append(step)
        turn_name, _, turn_place = self.turn_in(q)
        wiki = self.wiki_quest(q["name"]) or {}
        npcs = [x for x in wiki.get("steps", []) if x["kind"] == "npc"]
        for x in npcs[1:-1]:        # the first is who gives it, the last who takes it back
            if x["name"] in (q["npc_name"], turn_name):
                continue
            nid = self.npc_ids.get(x["name"])
            at = self.npc_place(nid) if nid is not None else None
            key = "see:" + x["name"]
            steps.append({"key": key, "kind": "see", "text": f"See {x['name']}" + (f" in {x['map']}" if x.get("map") else ""),
                          "goal": f"See {x['name']}", "how": "tick it once you've talked to them",
                          "where": self.map_info(at["id"]) if at else None,
                          "npc": {"x": at["x"], "y": at["y"], "name": x["name"]} if at else None, "done": key in checked})
        carry = [r["name"] for r in reqs if r["type"] == "item"]
        steps.append({"key": "back", "kind": "back",
                      "text": f"Bring {', '.join(carry)} to {turn_name}" if carry else f"Talk to {turn_name}",
                      "goal": f"Bring it to {turn_name}", "how": f"in {turn_place['name']}" if turn_place else "",
                      "where": self.map_info(turn_place["id"]) if turn_place else None,
                      "npc": {"x": turn_place["x"], "y": turn_place["y"], "name": turn_name} if turn_place else None,
                      "done": False})
        return steps

    def refresh_market(self):
        self.market = Market(force=True)

    def npc_price(self, name):
        """What an NPC pays for one, or None when the game data doesn't say."""
        return NPC_PRICES.get(name) or self.npc_sell.get(name)

    def item_img(self, name):
        i = self.item_ids.get(name)
        return f"{OSMS}current/images/items/{i:08d}.png" if i else None

    def on_maple_island(self, level, current_map, override=None):
        """Still on Maple Island? The boat to Victoria Island leaves from level 7 and is one-way,
        so level alone can't tell: use your answer, else the map you're on, else your level."""
        if override is not None:
            return bool(override)
        region = self.maps.get(current_map, {}).get("region") if current_map else None
        if region:
            return region == "Maple Island"
        return level < 8   # most players finish the island's quests around level 8 and leave

    # ---- where to train
    def train(self, level, acc=None, on_island=False, limit=12):
        maps = {}
        for m in self.monsters:
            lv, hp, exp = m.get("level") or 0, m.get("hp") or 0, m.get("exp") or 0
            if not m.get("maps") or hp <= 0 or exp <= 0 or not (level - 6 <= lv <= level + 4):
                continue
            if m.get("special") or m.get("is_boss"):
                continue   # party quest, job test and jump quest copies, and bosses: not grind spots
            need_acc = acc_needed(m.get("eva") or 0, lv - level)
            mob = {"name": m["name"], "level": lv, "hp": hp, "exp": exp, "need_acc": need_acc,
                   "img": f"{OSMS}images/monsters/{m['thumbnail']}.png" if m.get("thumbnail") else None,
                   "undead": bool(m.get("undead")), "weak": [k for k, v in (m.get("elements") or {}).items() if v == "Weak"]}
            for mp in m["maps"]:
                if (self.maps.get(mp["id"], {}).get("region") == "Maple Island") != on_island:
                    continue   # the boat off Maple Island is one-way
                e = maps.setdefault(mp["id"], {"id": mp["id"], "name": mp["name"], "mobs": [], "exp": 0, "hp": 0, "count": 0})
                c = mp.get("count") or 0
                e["mobs"].append({**mob, "count": c})
                e["exp"] += c * exp
                e["hp"] += c * hp
                e["count"] += c
        out = []
        for e in maps.values():
            if e["count"] < 5:
                continue
            e["eff"] = e["exp"] / e["hp"]
            e["score"] = e["eff"] * math.sqrt(e["exp"])
            e["need_acc"] = max(x["need_acc"] for x in e["mobs"])
            e["hittable"] = acc is None or acc >= e["need_acc"]
            if not e["hittable"]:
                e["score"] *= 0.4
            e["mobs"].sort(key=lambda x: -x["count"])
            e["render"] = self.render_url(e["id"])
            e["street"] = self.map_info(e["id"])["street"]
            out.append(e)
        out.sort(key=lambda x: -x["score"])
        return out[:limit]

    # ---- what to wear
    def gear(self, job, level, per_slot=4):
        fam, weapons, _ = JOBS.get(job, JOBS["Beginner"])
        label, main, sub = FAMILIES.get(fam, (None, "STR", "DEX"))
        slots = {}
        for it in self.equips:
            st = {k: num(v) for k, v in (it.get("stats") or {}).items()}
            req = st.get("reqLevel", 0)
            if req > level + 5 or req < level - 15:
                continue
            name = it.get("name", "")
            if "Wizet" in name or name.startswith("GM ") or it.get("weapon_type") == "Cash Weapon":
                continue   # staff/event items nobody can get
            jobs = it.get("req_job_label", "All")
            if jobs != "All" and (label is None or label not in jobs.split("/")):
                continue
            slot = it.get("sub_category")
            if slot == "Shield" and fam == "archer":
                continue   # bows and crossbows take both hands
            if slot == "Weapon":
                if weapons and it.get("weapon_type") not in weapons:
                    continue
                atk = st.get("incMAD", 0) + st.get("incINT", 0) if fam == "magician" else st.get("incPAD", 0)
                score = atk * 10 + st.get(f"inc{main}", 0) * 2 + st.get("attackSpeed", 0) * -1
            else:
                score = (st.get(f"inc{main}", 0) * 3 + st.get(f"inc{sub}", 0) * 1.5 + st.get("incACC", 0)
                         + st.get("incEVA", 0) * 0.5 + st.get("incSpeed", 0) * 0.5 + st.get("incPDD", 0) * 0.15
                         + st.get("incMDD", 0) * 0.1 + st.get("incMHP", 0) * 0.05 + st.get("incMMP", 0) * 0.05
                         + st.get("incPAD", 0) * 8 + st.get("incMAD", 0) * (8 if fam == "magician" else 0))
            price = self.market.items.get(it["name"])
            cozy = (self.market.cozy.get(it["name"]) or {}).get("price")
            entry = {
                "name": it["name"], "slot": slot, "req": req, "soon": req > level, "score": round(score, 1),
                "weapon_type": it.get("weapon_type"), "speed": it.get("attack_speed_label"),
                "stats": {k: v for k, v in st.items() if k.startswith("inc") or k in ("tuc",)},
                "reqs": {k[3:]: v for k, v in st.items() if k.startswith("req") and k not in ("reqLevel", "reqJob") and v},
                "img": f"{OSMS}current/images/items/{int(it['id']):08d}.png",
                # snipe: the buy-at price, from maplestory-classic.com's cheapest quarter of sales; the
                # usual price on each site beside it
                "fm": {"median": price["p"] if price else None, "snipe": math.floor(price["p25"]) if price else None,
                       "sells": price["st"] if price else None, "cozy": cozy} if price or cozy else None,
            }
            slots.setdefault(slot, []).append(entry)
        out = []
        for slot in sorted(slots, key=lambda s: SLOT_ORDER.index(s) if s in SLOT_ORDER else 99):
            seen, xs = set(), []
            for e in sorted(slots[slot], key=lambda e: (-e["score"], e["req"])):
                if e["name"] not in seen:
                    seen.add(e["name"])
                    xs.append(e)
            now = [e for e in xs if not e["soon"]][:per_slot]
            soon = [e for e in xs if e["soon"]][:2]
            if now or soon:
                out.append({"slot": slot, "now": now, "soon": soon})
        return {"main": main, "sub": sub, "slots": out}

    # ---- skills
    def skill_list(self, job):
        fam, _, groups = JOBS.get(job, JOBS["Beginner"])
        src = self.skills.get(fam or "beginner", [])
        out = []
        for g in src:
            if g["class_name"] not in groups:
                continue
            for s in g["skills"]:
                stats = s.get("all_level_stats") or []
                passive = bool(s.get("passive")) or (s.get("mechanics") or {}).get("kind") == "passive"
                mobs, hits = s.get("mob_count"), s.get("attack_count")
                mobs = mobs[-1] if isinstance(mobs, list) else mobs
                hits = hits[-1] if isinstance(hits, list) else hits
                name = s["name"]
                top = stats[-1] if stats else ""
                mech = (s.get("mechanics") or {}).get("kind")
                is_attack = (bool(mobs) and mech not in ("self_buff", "party_support", "passive")
                             and re.search(r"(damage \d+|\d+% (in )?damage|basic attack \d+)", top, re.I) is not None)
                if passive:
                    kind, prio = "Passive", 3
                elif is_attack and "trigger rate" in top.lower():
                    kind, prio = "Final Attack proc", 3
                elif is_attack and mobs > 1:
                    kind, prio = "Mobbing attack", 1
                elif is_attack:
                    kind, prio = "Single-target", 2
                elif "Booster" in name or "Haste" in name:
                    kind, prio = "Speed buff", 2
                else:
                    kind, prio = "Buff / utility", 4
                desc = (s.get("description") or "").split("\n", 1)[-1]
                out.append({
                    "id": s["id"], "name": name, "job": g["class_name"], "tier": g["job"], "max": s.get("max_level", 0),
                    "kind": kind, "prio": prio, "mobs": mobs, "hits": hits, "desc": desc,
                    "first": stats[0] if stats else "", "maxed": stats[-1] if stats else "",
                    "img": f"{OSMS}current/{s['thumbnail']}" if s.get("thumbnail") else None,
                })
        out.sort(key=lambda s: (s["tier"], s["prio"]))
        return out


    def next_points(self, job, level, now, stats=None):
        """Where your next SP and AP go.

        SP follows the class guide's order for your job (first job, then second): the first
        skills in that order you haven't reached yet, from your levels in the game's Skills window.
        AP goes into your job's secondary stat while a weapon you'll want soon needs more of it,
        otherwise into the main stat; base stats come from the game's Character Stat window."""
        fam, _, groups = JOBS.get(job, JOBS["Beginner"])
        if len(groups) > 1 and level > 30:
            groups = groups[1:]        # second-job SP can't go into first-job skills
        plans = [self.builds[g] for g in groups if g in self.builds]
        steps = [s for p in plans for s in p["steps"]]
        sp, by_level = [], {}
        for lv, skill, to in steps:
            if lv <= level:
                by_level[skill] = max(by_level.get(skill, 0), to)
            if now and (now.get(skill) or 0) < to:
                if sp and sp[-1]["skill"] == skill and sp[-1]["to"] == to - 1:
                    sp[-1]["to"] = to                  # one line per run of points into one skill
                elif len(sp) < 4:
                    sp.append({"skill": skill, "from": now.get(skill) or 0, "to": to, "level": lv})
        out = {"sp": sp, "plan_now": by_level, "known": bool(now), "sources": [p["source"] for p in plans]}
        # the guides' level-by-level tables: yours, and for a first job the second jobs to pick at 30
        _, _, all_groups = JOBS.get(job, JOBS["Beginner"])
        nxt = [j for j, (_, _, g) in JOBS.items() if len(g) == 2 and g[0] == job]
        out["tables"] = [{"job": g, "source": self.builds[g]["source"], "rows": self.builds[g].get("rows", []),
                          "yours": g in all_groups} for g in list(all_groups) + nxt if g in self.builds]
        stats = stats or {}
        if not fam:
            out["ap"] = {"stat": None, "why": "Beginners: AP goes into the main stat of the job you’ll take (DEX for Bowman, LUK for Thief, STR for Warrior, INT for Magician)."}
            return out
        _, main, sub = FAMILIES[fam]
        weapons = next((s for s in self.gear(job, level)["slots"] if s["slot"] == "Weapon"), None)
        upcoming = (weapons["now"][:2] + weapons["soon"][:2]) if weapons else []
        need = max(upcoming, key=lambda e: e["reqs"].get(sub, 0), default=None)
        have = stats.get(sub.lower() + "_base", stats.get(sub.lower()))
        if have is None:
            out["ap"] = {"stat": main, "why": f"{main} is your main stat. Open Character Stat (S) in the game so Companion can check your {sub} against the weapons you’ll want."}
        elif need and have < need["reqs"].get(sub, 0):
            out["ap"] = {"stat": sub, "until": need["reqs"][sub],
                         "why": f"{need['name']} (level {need['req']}) needs {sub} {need['reqs'][sub]}; you have {have}. After that, back to {main}."}
        else:
            out["ap"] = {"stat": main, "why": f"Your {sub} {have} already covers the weapons you’ll want next, so everything goes into {main}."}
        return out

    # ---- navigation
    def map_info(self, mid):
        m = self.maps.get(mid, {})
        return {"id": mid, "name": m.get("name", "?"), "street": m.get("street_name") or m.get("region", ""),
                "town": bool(m.get("is_town"))}

    def find_maps(self, q, limit=10):
        from rapidfuzz import fuzz, process
        q = (q or "").strip()
        if not q:
            return []
        hits = process.extract(q, list(self.map_labels), scorer=fuzz.WRatio, limit=limit, score_cutoff=60)
        return [self.map_info(self.map_labels[h[0]]) for h in hits]

    def match_map_name(self, text, prefer=()):
        """Match OCR text from the in-game minimap title to a map id: the route's maps first."""
        pool = {self.maps[i]["name"]: i for i in prefer if i in self.maps}
        hit = match_place(text, list(pool), 80) if pool else None
        if hit:
            return pool[hit]
        names = {}
        for i, m in self.maps.items():
            names.setdefault(m["name"], i)
        hit = match_place(text, list(names), 90)
        return names[hit] if hit else None

    def render_url(self, mid):
        h = self.renders.get(f"{mid:09d}")
        return f"{OSMS}maps/{h}.webp" if h else None

    _map_locks, _map_guard = {}, threading.Lock()

    def map_image(self, mid):
        """(path, {"w", "h", "scale"}) of the map's picture on disk, downloaded and shrunk the first
        time. w and h are the original's size, the one map coordinates are in; scale is how much the
        stored picture was shrunk. None if the map has no picture."""
        h = self.renders.get(f"{int(mid):09d}")
        if not h:
            return None
        path, meta = MAP_CACHE / f"{h}.webp", MAP_CACHE / f"{h}.json"
        with self._map_guard:
            lock = self._map_locks.setdefault(h, threading.Lock())
        with lock:                       # the dashboard and the prefetch may ask for it at once
            if not (path.exists() and meta.exists()):
                import io
                from PIL import Image
                r = requests.get(f"{OSMS}maps/{h}.webp", timeout=60, headers=UA)
                r.raise_for_status()
                im = Image.open(io.BytesIO(r.content))
                im.load()
                w, ht = im.size
                s = min(1.0, MAP_MAX / max(w, ht))
                if s < 1:
                    im = im.resize((max(1, round(w * s)), max(1, round(ht * s))), Image.LANCZOS)
                MAP_CACHE.mkdir(exist_ok=True)
                tmp = path.with_suffix(".tmp")
                im.save(tmp, "WEBP", quality=82, method=4)
                tmp.replace(path)
                meta.write_text(json.dumps({"w": w, "h": ht, "scale": s}), "utf-8")
        return path, json.loads(meta.read_text("utf-8"))

    _prefetch_todo, _prefetch_busy = [], False

    def prefetch_maps(self, ids):
        """Fetch these maps' pictures in the background, one at a time, so each step of a route
        shows at once when you get there. One fetch runs at a time for every route: wandering off a
        route re-plans it on every map, and the newest route's maps go first, each fetched once."""
        ids = list(dict.fromkeys(ids))
        with self._map_guard:
            self._prefetch_todo = ids + [m for m in self._prefetch_todo if m not in ids]
            if self._prefetch_busy:
                return
            self._prefetch_busy = True
        threading.Thread(target=self._prefetch_run, daemon=True).start()

    def _prefetch_run(self):
        while True:
            with self._map_guard:
                if not self._prefetch_todo:
                    self._prefetch_busy = False
                    return
                mid = self._prefetch_todo.pop(0)
            try:
                self.map_image(mid)
            except Exception as e:
                print("Map picture unavailable:", mid, e)

    def _bounds(self, mid):
        m = self.maps.get(mid, {})
        pts = [(p["x"], p["y"]) for p in self.portals.get(mid, [])]
        pts += [(q["x"], q["y"]) for q in (m.get("mob_positions") or []) + (m.get("npc_positions") or [])]
        if not pts:
            return 0, 1, 0, 1
        xs, ys = [x for x, _ in pts], [y for _, y in pts]
        return min(xs), max(xs), min(ys), max(ys)

    def hint(self, mid, portal):
        x0, x1, y0, y1 = self._bounds(mid)
        rx = (portal["x"] - x0) / max(1, x1 - x0)
        ry = (portal["y"] - y0) / max(1, y1 - y0)
        name = (portal.get("name") or "").lower()
        if rx < 0.15:
            side, arrow = "far left", "←"
        elif rx < 0.4:
            side, arrow = "left side", "←"
        elif rx <= 0.6:
            side, arrow = "middle", "↑"
        elif rx <= 0.85:
            side, arrow = "right side", "→"
        else:
            side, arrow = "far right", "→"
        height = "up high" if ry < 0.3 else "down low" if ry > 0.75 else ""
        if height and arrow in ("←", "→"):        # a side and a height make a diagonal: right, up high is ↗
            arrow = {("←", "up high"): "↖", ("←", "down low"): "↙", ("→", "up high"): "↗", ("→", "down low"): "↘"}[arrow, height]
        if name.startswith(("up", "top")) and 0.4 <= rx <= 0.6:
            arrow = "↑"
        if name.startswith(("dun", "under", "down")) and 0.4 <= rx <= 0.6:
            arrow = "↓"
        return {"side": side, "height": height, "arrow": arrow,
                "text": side + (", " + height if height else "")}

    def route(self, start, goal):
        from collections import deque
        if start not in self.maps or goal not in self.maps:
            return None
        prev, q = {start: None}, deque([start])
        while q:
            u = q.popleft()
            if u == goal:
                break
            for v in self.graph.get(u, {}):
                if v not in prev:
                    prev[v] = u
                    q.append(v)
        if goal not in prev:
            return None
        path, u = [], goal
        while u is not None:
            path.append(u)
            u = prev[u]
        path.reverse()
        steps = []
        for a, b in zip(path, path[1:]):
            p = self.graph[a][b]
            steps.append({**self.map_info(a), "portal": {"x": p["x"], "y": p["y"], "name": p.get("name"),
                          "type": p.get("type")}, "hint": self.hint(a, p), "to": self.map_info(b),
                          "render": self.render_url(a)})
        steps.append({**self.map_info(goal), "portal": None, "hint": None, "to": None,
                      "render": self.render_url(goal), "arrived": True})
        self.prefetch_maps(path)
        return steps

    def layout(self, mid):
        m = self.maps.get(mid, {})
        return {
            **self.map_info(mid), "render": self.render_url(mid),
            "portals": [{"x": p["x"], "y": p["y"], "to": self.maps[int(p["dest_map"])]["name"]}
                        for p in self.portals.get(mid, []) if int(p.get("dest_map") or 0) in self.maps
                        and int(p["dest_map"]) != mid],
            "mobs": [{"x": q["x"], "y": q["y"]} for q in (m.get("mob_positions") or [])],
            "npcs": [{"x": q["x"], "y": q["y"], "name": self.npc_names.get(q["id"], "")} for q in (m.get("npc_positions") or [])],
        }

    def here(self, mid):
        """The map you're on, for Now and Go to: its monsters, every item they drop (most valuable on
        the market first, unpriced last), its NPCs with what they do, and where its portals lead."""
        m = self.maps.get(mid, {})
        mobs = []
        for mob in self.monsters:
            spot = next((x for x in mob.get("maps") or [] if x.get("id") == mid), None)
            if spot:
                mobs.append({"id": mob.get("id"), "name": mob["name"], "level": mob.get("level"),
                             "count": spot.get("count"), "exp": mob.get("exp"), "img": self.mob_img(mob.get("id"))})
        drops, seen = [], set()
        for mob in mobs:
            for d in self.drops_by_mob.get(mob["id"], []):
                if d["item"] in seen:
                    continue
                seen.add(d["item"])
                price = (self.market.items.get(d["item"]) or {}).get("p")
                drops.append({"item": d["item"], "img": self.item_img(d["item"]), "from": mob["name"],
                              "rate": d["rate"], "price": price, "success": self.scroll_rates.get(d["item"])})
        drops.sort(key=lambda d: -(d["price"] or -1))
        givers = {q.get("npc_id") for q in self.quest_list}
        npcs = []
        for p in m.get("npc_positions") or []:
            name = self.npc_names.get(p["id"], "")
            role = "Taxi" if "Cab" in name else "Quests" if p["id"] in givers else None
            npcs.append({"id": p["id"], "name": name, "x": p["x"], "y": p["y"], "role": role,
                         "img": f"{OSMS}current/images/npcs/{int(p['id']):07d}.png"})
        portals = [{"x": p["x"], "y": p["y"], "to": self.maps[int(p["dest_map"])]["name"], "to_id": int(p["dest_map"])}
                   for p in self.portals.get(mid, []) if int(p.get("dest_map") or 0) in self.maps
                   and int(p["dest_map"]) != mid]
        mark = m.get("map_mark")
        return {"id": mid, "name": m.get("name", "?"), "street": m.get("street_name") or m.get("region", ""),
                "town": bool(m.get("is_town")), "mark": f"{OSMS}current/images/map_marks/{mark}.png" if mark else None,
                "mobs": mobs, "drops": drops, "drops_ok": bool(self.drops_by_mob), "npcs": npcs, "portals": portals}


    # ---- quests
    JOB_REGIONS = {"warrior": "Warrior", "magician": "Magician", "archer": "Bowman", "rogue": "Thief"}
    JOB_BITS = {None: 1, "warrior": 2, "magician": 4, "archer": 8, "rogue": 16}   # quest reward job_mask

    def reward_items(self, q, fam):
        """Item rewards you'd get as this job, and their expected market value. Items for other
        jobs are left out, one-of-several random items count by their chance, and male / female
        versions count half each (the app doesn't know your character's gender)."""
        bit = self.JOB_BITS.get(fam, 1)
        mine = [r for r in q.get("rewards", []) if r.get("type") == "item" and (r.get("count") or 1) > 0
                and (not r.get("job_mask") or r["job_mask"] & bit)]
        pool = sum(r.get("prop") or 1 for r in mine if r.get("guaranteed") is False)
        out, total = [], 0
        for r in mine:
            price = self.market.items.get(r.get("name", ""), {}).get("p")
            cnt = r.get("count") or 1
            chance = (r.get("prop") or 1) / pool if r.get("guaranteed") is False and pool else 1.0
            only = {0: "male", 1: "female"}.get(r.get("gender"))
            if price:
                total += price * cnt * chance * (0.5 if only else 1)
            out.append({"name": r.get("name", ""), "count": cnt, "value": price * cnt if price else None,
                        "chance": round(chance * 100) if chance < 1 else None, "only": only})
        return out, total

    def npc_place(self, npc_id):
        spots = self.npc_maps.get(npc_id) or []
        if not spots:
            return None
        s = spots[0]
        return {**self.map_info(s["map"]), "x": s["x"], "y": s["y"]}

    def quest(self, qid):
        if not hasattr(self, "_quests_by_id"):
            self._quests_by_id = {str(q["id"]): q for q in self.quest_list}
        return self._quests_by_id.get(str(qid))

    def with_earlier(self, done):
        """The quests you've finished, and every quest those needed finished first, all the way back:
        Olaf's Second Training can't be done without the first, even if the game never showed the
        first one done (Companion wasn't running then, or it scrolled past in the Completed tab)."""
        out = {str(d) for d in done}
        todo = list(out)
        while todo:
            for r in (self.quest(todo.pop()) or {}).get("requirements_list") or []:
                # only "finish it first" (state 2); a quest that has to be in progress isn't done
                if r.get("type") == "quest" and r.get("state", 2) == 2 and str(r.get("id")) not in out:
                    out.add(str(r["id"]))
                    todo.append(str(r["id"]))
        return out

    def quests(self, level, job, done, on_island=False, active=()):
        """Quests to take now (ready), ones that need an earlier step first (locked), the ones in
        progress in the game (active ids) and the ones you've finished (done ids, with everything
        they needed first)."""
        fam = JOBS.get(job, JOBS["Beginner"])[0]
        own_job_region = self.JOB_REGIONS.get(fam)
        done = self.with_earlier(done)
        active = [str(a) for a in active if a and str(a) not in done]   # finished wins over in progress
        ready, locked = [], []
        for q in self.quest_list:
            qid = str(q["id"])
            if qid in done or qid in active or q["region"] == "Event":
                continue
            if q["region"] in self.JOB_REGIONS.values() and q["region"] != own_job_region:
                continue
            lvl = q.get("level_min") or 0
            if lvl > level or (lvl < level - 20 and q["region"] != own_job_region):
                continue   # too high, or too low to be worth the walk
            if (q["region"] == "Maple Island") != on_island:
                continue   # the boat off Maple Island is one-way: island quests only while you're there
            reqs = q.get("requirements_list") or []
            if any(r["type"] in ("citizenship", "skill") for r in reqs):
                continue   # town-citizenship and crafting chains need progress we can't see
            entry = self.quest_entry(q, fam, own_job_region, done)
            (locked if entry["needs"] else ready).append(entry)
        ready.sort(key=lambda e: -e["score"])
        locked.sort(key=lambda e: -e["score"])
        info = lambda ids: [self.quest_entry(self.quest(i), fam, own_job_region, done) for i in ids if self.quest(i)]
        return {"ready": ready[:40], "locked": locked[:20], "active": info(dict.fromkeys(active)),
                "done": sorted(info(done), key=lambda e: (e["region"], e["level"]))}

    def quest_entry(self, q, fam, own_job_region, done):
        """Everything the dashboard shows about one quest."""
        qid = str(q["id"])
        lvl = q.get("level_min") or 0
        reqs = q.get("requirements_list") or []
        missing = [r["name"] for r in reqs if r["type"] == "quest" and str(r["id"]).lstrip("0") not in
                   {d.lstrip("0") for d in done}]
        reward_items, items_value = self.reward_items(q, fam)
        exp = q.get("rewards_exp") or next((r["value"] for r in q.get("rewards", []) if r["type"] == "exp"), 0)
        money = q.get("rewards_money") or next((r["value"] for r in q.get("rewards", []) if r["type"] == "money"), 0)
        todo = []
        for r in reqs:
            if r["type"] == "mob":
                where = self.mob_maps.get(r.get("id"))
                todo.append({"kind": "mob", "name": r["name"], "count": r.get("count"), "label": r["label"], "where": where,
                             "img": self.mob_img(r.get("id"))})
            elif r["type"] == "item":
                price = self.market.items.get(r["name"], {})
                drops = self.drops.get(r["name"], [])[:3]
                where = self.mob_maps.get(self.mob_ids.get(drops[0]["monster"])) if drops else None
                todo.append({"kind": "item", "name": r["name"], "count": r.get("count"), "label": r["label"],
                             "img": self.item_img(r["name"]), "buy": math.floor(price["p25"]) if price else None,
                             "buy_total": math.floor(price["p25"]) * r.get("count", 1) if price else None,
                             "drops": drops, "where": where})
        entry = {
            "id": qid, "name": q["name"], "region": q["region"], "level": lvl, "npc": q["npc_name"],
            "npc_id": q.get("npc_id"), "where": self.npc_place(q.get("npc_id")),
            "npc_img": f"{OSMS}current/images/npcs/{int(q['npc_id']):07d}.png" if q.get("npc_id") is not None else None,
            "exp": exp, "money": money, "items": reward_items, "items_value": items_value,
            "todo": todo, "daily": bool(q.get("is_daily")), "weekly": bool(q.get("is_weekly")),
            "job_quest": q["region"] == own_job_region, "chain": q.get("parent"),
            "next": q.get("next_quest_name"), "needs": missing,
        }
        entry["intro"], entry["task"] = self.quest_text(q)
        wiki = self.wiki_quest(q["name"])
        if wiki:
            entry["steps"], entry["wiki"] = wiki["steps"], wiki["source"]
            name, _, place = self.turn_in(q)
            entry["turn_in"] = {"npc": name, "where": place} if name else None
        entry["score"] = (10**9 if entry["job_quest"] else 0) + exp * 2 + money + items_value * 0.5
        return entry

    def mob_img(self, mob_id):
        if not hasattr(self, "_mob_thumbs"):
            self._mob_thumbs = {m.get("id"): m.get("thumbnail") for m in self.monsters}
        t = self._mob_thumbs.get(mob_id)
        return f"{OSMS}images/monsters/{t}.png" if t else None
