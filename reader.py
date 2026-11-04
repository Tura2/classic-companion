"""
Reads the game window the way you would look at it: finds each open window by its title, wherever
it's been dragged, and reads what's in it. Works on captured frames only: nothing is clicked or typed.

  HUD              level, job                     (always on screen)
  Mini map         street and map name
  Quest Helper     quests you track and their counts
  CHARACTER STAT   name, job, level, EXP, stats, ACC (with Detail open)
  ITEM INVENTORY   mesos
  SKILL INVENTORY  skill levels and SP left
  QUEST            quests in the open tab (Available / In Progress / Completed)

Each window has a fixed size, so once its title is found its fields sit at fixed offsets from it.
The game scales its whole UI with the height of its drawing area, so offsets are measured at a
1200 px tall game area (1920 x 1200) and scaled to the frame being read.
"""
import asyncio
import json
import re

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

from paths import APP_DIR
from gamedata import fix_numeral, match_place

DIGITS_FILE = APP_DIR / "cache" / "hud_digits.json"   # level digit shapes learned from CHARACTER STAT
JOB_ALIASES = {"Bowman": "Archer", "Thief": "Rogue"}   # Nexon's 1st-job names -> the game data's
REF_HEIGHT = 1200                                      # game area height the offsets were measured at
# The smallest game area the reader can be trusted at: its text is read at the size the game draws
# it, and below about 1000 px tall (a 1920 x 1080 game) the Quest Helper and quest list read wrong
MIN_HEIGHT = 1000
JOB_REGIONS = {"warrior": "Warrior", "magician": "Magician", "archer": "Bowman", "rogue": "Thief"}
KEPT = ("stat", "inventory", "skills", "helper", "quest")   # windows remembered between reads


# ---------------------------------------------------------------- OCR
def ocr(img, scale=1, x0=0, y0=0):
    """[(text, x, y, w, h)] in frame pixels. `img` is a crop whose top-left sits at (x0, y0)."""
    import winocr
    im = ImageOps.grayscale(img)
    if scale != 1:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)

    async def run():        # newer winrt hands back an awaitable, not a coroutine asyncio.run takes
        return await winocr.recognize_pil(im.convert("RGB"), "en")
    res = winocr.picklify(asyncio.run(run()))
    out = []
    for line in res.get("lines", []):
        r = [w["bounding_rect"] for w in line.get("words", [])]
        if not r:
            continue
        x, y = min(q["x"] for q in r), min(q["y"] for q in r)
        x2, y2 = max(q["x"] + q["width"] for q in r), max(q["y"] + q["height"] for q in r)
        out.append((line["text"].strip(), x0 + x / scale, y0 + y / scale, (x2 - x) / scale, (y2 - y) / scale))
    return out


def read_box(frame, box, s=1.0, pad=0):
    """OCR one area of the frame (clipped to it), lines sorted top to bottom. Small UI text reads
    best at about 3x the 1200 px UI size. `pad` adds blank margin in the area's own background
    color, for text that starts right at the area's edge."""
    l, t, r, b = (int(v) for v in box)
    l, t, r, b = max(0, l), max(0, t), min(frame.width, r), min(frame.height, b)
    if r - l < 8 or b - t < 8:
        return []
    crop = frame.crop((l, t, r, b))
    if pad:
        bg = max(crop.getcolors(crop.width * crop.height) or [(0, (255, 255, 255))])[1]
        crop = ImageOps.expand(crop, border=pad, fill=bg)
        l, t = l - pad, t - pad
    return sorted(ocr(crop, 3 / s, l, t), key=lambda ln: (ln[2], ln[1]))


def to_int(s):
    s = re.sub(r"[^\d]", "", s or "")
    return int(s) if s else None


def _ink(img):
    """Dark-on-light pixels of a crop as a 0/1 grid (rows of lists)."""
    g = ImageOps.grayscale(img)
    px, w, h = g.load(), g.width, g.height
    return [[1 if px[x, y] < 110 else 0 for x in range(w)] for y in range(h)]


def _looks_like_zero(img):
    """True if the crop holds one closed loop: Windows OCR drops a lone "0", but reads every other digit."""
    grid = _ink(img)
    h, w = len(grid), len(grid[0]) if grid else 0
    # drop a text box's border lines: columns or rows that are ink almost all the way along
    for x in [x for x in range(w) if sum(grid[y][x] for y in range(h)) > 0.7 * h]:
        for y in range(h):
            grid[y][x] = 0
    for y in [y for y in range(h) if sum(grid[y]) > 0.7 * w]:
        grid[y] = [0] * w
    cells = [(x, y) for y, row in enumerate(grid) for x, v in enumerate(row) if v]
    if len(cells) < 6:
        return False
    xs, ys = [c[0] for c in cells], [c[1] for c in cells]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if x1 - x0 < 3 or y1 - y0 < 5:
        return False
    # an empty middle with ink on both sides of it, on most rows
    rows = [grid[y][x0:x1 + 1] for y in range(y0 + 2, y1 - 1)]
    hollow = sum(1 for r in rows if (r[0] or r[1]) and (r[-1] or r[-2]) and not any(r[2:-2]))
    return bool(rows) and hollow >= len(rows) * 0.6


def read_small_number(frame, box, s=1.0):
    """A short number in a box (skill level, SP). None if the box is empty."""
    l, t, r, b = (int(v) for v in box)
    crop = frame.crop((max(0, l), max(0, t), min(frame.width, r), min(frame.height, b)))
    if crop.width < 4 or crop.height < 4:
        return None
    g = ImageOps.grayscale(crop)
    g = g.resize((round(g.width * 3 / s), round(g.height * 3 / s)), Image.LANCZOS)
    # a word in front makes the OCR treat a lone digit as text it should read
    font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", max(10, int(g.height * 0.55)))
    canvas = Image.new("L", (g.width + g.height * 4, g.height), 235)
    ImageDraw.Draw(canvas).text((6, int(g.height * 0.12)), "Level", font=font, fill=20)
    canvas.paste(g, (g.height * 4 - 6, 0))
    for text, *_ in ocr(canvas.convert("RGB")):
        m = re.search(r"(\d+)", text)
        if m:
            return int(m.group(1))
    return 0 if _looks_like_zero(crop) else None


# ---------------------------------------------------------------- finding windows
TITLES = {   # window -> its title, as written in the game
    "stat": "CHARACTER STAT",
    "inventory": "ITEM INVENTORY",
    "skills": "SKILL INVENTORY",
    "helper": "QUEST HELPER",
}
# A player shop's title is whatever its owner typed, so the shop is found by its LEAVE STORE
# button instead (or BUY ITEM / SELLER INFO above it, measured from LEAVE STORE)
SHOP_BUTTONS = {"LEAVE STORE": 0, "BUY ITEM": 31, "SELLER INFO": 80}


def find_windows(lines, height):
    """{window: its title line}. Titles are matched loosely, since the 1x pass misreads a letter or
    two, and the closest title wins ("SKILL INVENTORY" also looks a lot like "ITEM INVENTORY")."""
    from rapidfuzz import fuzz
    found, best = {}, {}
    for ln in lines:
        text, y = ln[0], ln[2]
        if y > height * 0.92:        # the HUD's own buttons (CASH SHOP ...) aren't windows
            if re.match(r"^LV\.?", text) and "hud" not in found:
                found["hud"] = ln
            continue
        letters = re.sub(r"[^A-Za-z ]", "", text).strip().upper()
        if letters == "QUEST" and "quest" not in found:
            found["quest"] = ln
            continue
        scores = {k: fuzz.ratio(t, letters[:len(t) + 1]) for k, t in TITLES.items()}
        key = max(scores, key=scores.get)
        if scores[key] >= 78 and scores[key] > best.get(key, 0):
            if key == "helper" and not re.search(r"[(\d]", text):
                continue     # the Quest window's QUEST HELPER button; the real title shows "(2/5)"
            found[key], best[key] = ln, scores[key]
            continue
        for button, above in SHOP_BUTTONS.items():
            score = fuzz.ratio(button, letters)
            if score >= 75 and score - above / 10 > best.get("shop", 0):   # LEAVE STORE wins a tie
                s = ln[4] / 12        # the buttons' text is 12 px tall at the 1200 px UI size
                found["shop"] = (button, ln[1], ln[2] + above * s, ln[3], ln[4])
                best["shop"] = score - above / 10
    return found


# ---------------------------------------------------------------- HUD level digits
def _orange(p):
    r, g, b = p[:3]
    return r > 200 and 90 < g < 200 and b < 110


def level_glyphs(frame, lv_line):
    """Bitmaps of the white digits in the orange tiles right of "LV.", left to right."""
    x, y, w, h = lv_line[1:]     # "LV." is about 1.5 times as wide as it's tall; the OCR may glue more on
    box = (int(x + h * 1.2), int(y - h * 0.6), int(x + h * 5.5), int(y + h * 1.6))
    area = frame.crop(box).convert("RGB")
    px = area.load()
    cols = [c for c in range(area.width) if sum(_orange(px[c, r]) for r in range(area.height)) >= 3]
    rows = [r for r in range(area.height) if sum(_orange(px[c, r]) for c in range(area.width)) >= 3]
    if not cols or not rows:
        return []
    tiles, start = [], cols[0]
    for a, b in zip(cols, cols[1:] + [None]):
        if b is None or b != a + 1:
            tiles.append((start, a + 1))
            start = b
    out = []
    for c0, c1 in tiles:
        if c1 - c0 < h * 0.25:
            continue
        t = area.crop((c0, rows[0], c1, rows[-1] + 1)).convert("L").point(lambda v: 0 if v >= 215 else 255)
        bb = ImageOps.invert(t).getbbox()
        if bb:
            out.append(t.crop(bb))
    return out


def _bits(g):
    return f"{g.width}x{g.height}:" + "".join("1" if v < 128 else "0" for v in g.getdata())


_TEMPLATES = {}


def _font_digit(d, size):
    key = (d, size)
    if key not in _TEMPLATES:
        f = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 64)
        im = Image.new("L", (80, 90), 255)
        ImageDraw.Draw(im).text((8, 4), d, font=f, fill=0)
        bb = ImageOps.invert(im).getbbox()
        _TEMPLATES[key] = im.crop(bb).resize(size, Image.BILINEAR).point(lambda v: 0 if v < 128 else 255)
    return _TEMPLATES[key]


def _similar(a, b):
    pa, pb = list(a.getdata()), list(b.getdata())
    return sum((x < 128) == (y < 128) for x, y in zip(pa, pb)) / len(pa)


class LevelDigits:
    """Reads the HUD level. Exact once CHARACTER STAT has shown the level with these digit shapes;
    until then a best guess from the digits' shapes, which the app double-checks before using."""

    def __init__(self):
        try:
            self.known = json.loads(DIGITS_FILE.read_text("utf-8"))
        except (OSError, ValueError):
            self.known = {}

    def read(self, glyphs):
        if not glyphs:
            return None, False
        digits, exact = "", True
        for g in glyphs:
            d = self.known.get(_bits(g))
            if d is None:
                exact = False
                big = g.resize((g.width * 4, g.height * 4), Image.NEAREST)
                d = max("0123456789", key=lambda c: _similar(big, _font_digit(c, big.size)))
            digits += d
        return int(digits), exact

    def learn(self, glyphs, level):
        s = str(level)
        if len(s) != len(glyphs):
            return
        changed = False
        for g, d in zip(glyphs, s):
            k = _bits(g)
            if self.known.get(k) != d:
                self.known[k], changed = d, True
        if changed:
            try:
                DIGITS_FILE.write_text(json.dumps(self.known), "utf-8")
            except OSError:
                pass


# ---------------------------------------------------------------- per-window readers
def nearest_row(lines, rows, y0, s, tol=11):
    """{row name: text} for value lines whose top is within tol px of a row's offset below y0."""
    out = {}
    for text, x, y, w, h in lines:
        off = (y - y0) / s
        best = min(rows.items(), key=lambda kv: abs(kv[1] - off))
        if abs(best[1] - off) <= tol and best[0] not in out:
            out[best[0]] = text
    return out


STAT_ROWS = {"name": 42, "job": 70, "job2": 89, "level": 114, "hp": 142, "mp": 170, "exp": 198, "fame": 226,
             "str": 262, "dex": 290, "int": 318, "luk": 346, "ap": 394}
DETAIL_ROWS = {"attack": 97, "wdef": 125, "magic": 153, "mdef": 181, "acc": 209, "avoid": 237, "crit": 265,
               "critdmg": 293, "speed": 321, "jump": 350}


def read_stat(frame, t, s, job_names):
    from rapidfuzz import fuzz, process
    x, y = t[1], t[2]     # values start right of the colored label cells, whose edge can read as a "1"
    vals = read_box(frame, (x + 76 * s, y + 30 * s, x + 230 * s, y + 415 * s), s)
    v = nearest_row(vals, STAT_ROWS, y, s)
    # JOB shows the class ("BOWMAN") with the job under it ("ARCHER"); the second is the game data's name
    job = None
    for text in (v.get("job2"), v.get("job")):
        hit = process.extractOne((text or "").title(), job_names, scorer=fuzz.ratio, score_cutoff=70) if text else None
        if hit:
            job = hit[0]
            break
    out = {"name": v.get("name"), "job": job}
    lv = to_int(v.get("level", ""))
    out["level"] = lv if lv and 1 <= lv <= 200 else None
    m = re.search(r"^([\d,\s]+)\((\d+)", v.get("exp", ""))     # "11392 (56%)", sometimes read "1 1392 (56%)"
    if m:
        out["exp"], out["exp_pct"] = to_int(m.group(1)), int(m.group(2))
    for k in ("str", "dex", "int", "luk", "ap"):
        n = to_int(re.split(r"\(", v.get(k, ""))[0])
        if n is not None:
            out[k] = n
            # "93 (92+1)": 92 is the base you put AP into, +1 comes from gear
            m = re.search(r"\(\s*(\d+)\s*\+", v.get(k, ""))
            out[k + "_base"] = int(m.group(1)) if m else n
    detail = read_box(frame, (x + 388 * s, y + 85 * s, x + 550 * s, y + 375 * s), s)
    d = nearest_row(detail, DETAIL_ROWS, y, s)
    if d:
        m = re.match(r"\s*(\d{1,3})(?!\d)", d.get("acc", ""))     # just the number, nothing read beside it
        out["acc"] = int(m.group(1)) if m else None
        out["attack"] = d.get("attack")
    return out


def read_inventory(frame, t, s):
    x, y = t[1], t[2]
    for text, *_ in read_box(frame, (x + 20 * s, y + 395 * s, x + 252 * s, y + 424 * s), s):
        if re.fullmatch(r"\d{1,3}([,.\s]\d{3})*", text.strip()):     # "89,460", the comma sometimes read as a space
            return {"mesos": to_int(text)}
    return {}


def read_skills(frame, t, s, skill_names):
    """{skill name: level} for the visible rows, the open tab's name and the SP left."""
    from rapidfuzz import fuzz, process
    x, y = t[1], t[2]
    lines = read_box(frame, (x + 50 * s, y + 75 * s, x + 262 * s, y + 510 * s), s)
    tab = next((ln[0] for ln in lines if ln[2] < y + 105 * s), None)
    levels = {}
    for text, lx, ly, lw, lh in lines:
        hit = process.extractOne(text, skill_names, scorer=fuzz.ratio, score_cutoff=80) if len(text) >= 4 else None
        if not hit:
            continue
        below = [ln for ln in lines if 14 * s <= ln[2] - ly <= 45 * s and abs(ln[1] - lx) < 30 * s
                 and re.fullmatch(r"[.,']?\d{1,2}", ln[0])]
        lv = to_int(below[0][0]) if below else \
            read_small_number(frame, (lx - 3 * s, ly + 22 * s, lx + 32 * s, ly + 48 * s), s)
        if lv is not None:
            levels[hit[0]] = lv
    sp = read_small_number(frame, (x + 119 * s, y + 528 * s, x + 164 * s, y + 556 * s), s)
    return {"tab": tab, "levels": levels, "sp": sp}


QUEST_TABS = (("available", -4, 105), ("in_progress", 107, 217), ("completed", 219, 330))


def match_quest(text, names, cutoff=86):
    """The quest a (maybe cut short or half-read) title names, or None."""
    from rapidfuzz import fuzz, process
    cut = text.rstrip(".:… ")
    if text.endswith(("...", "..", "…", ":")) and len(cut) >= 8:
        low = cut.lower()[:len(cut) - 1]
        hit = next((q for q in names if q.lower().startswith(low)), None)
        if hit:
            return hit
    hit = process.extractOne(text, names, scorer=fuzz.WRatio, score_cutoff=cutoff) if len(text) >= 6 else None
    if hit:
        return hit[0]
    if len(cut) >= 14:            # the Quest Helper cuts long titles without "..."
        low = cut.lower()[:-2]
        return next((q for q in names if q.lower().startswith(low)), None)
    return None


def read_quest_window(frame, t, s, quest_names):
    x, y = t[1], t[2]
    tab_area = frame.crop((int(x - 4 * s), int(y + 26 * s), int(x + 330 * s), int(y + 44 * s))).convert("RGB")
    px = tab_area.load()

    def red(c0, c1):
        c0, c1 = int((c0 + 4) * s), min(int((c1 + 4) * s), tab_area.width)
        return sum(1 for cx in range(c0, c1) for cy in range(tab_area.height)    # the open tab is pink-red
                   if px[cx, cy][0] > 190 and px[cx, cy][0] - px[cx, cy][1] > 80 and px[cx, cy][0] - px[cx, cy][2] > 50)
    reds = {tb[0]: red(tb[1], tb[2]) for tb in QUEST_TABS}
    tab = max(reds, key=reds.get)
    if reds[tab] < 300 * s * s:
        return None     # no open tab under it: "Quest" was other text, like a half-covered Quest Helper title
    if sorted(reds.values())[-2] * 1.8 > reds[tab]:
        return None     # no clear open tab: reading Available as Completed would mark quests you never did
    names = []
    for text, *_ in read_box(frame, (x + 53 * s, y + 60 * s, x + 340 * s, y + 560 * s), s):
        if re.search(r"\(\d+\)\s*$", text) or len(text) < 4:
            continue     # area headers like "Henesys (2)"
        text = text.replace("VV", "W")      # the quest list's font reads W as VV
        from rapidfuzz import fuzz
        if any(fuzz.ratio(text.rstrip(".:… "), n["text"]) >= 75 for n in names):
            continue     # the same quest read twice (a row half-scrolled into view)
        names.append({"text": text.rstrip(".:… "), "quest": match_quest(text, quest_names)})
    return {"tab": tab, "quests": names}


PROGRESS = re.compile(r"^\s*(\d[\d\s/Il!|$t.,'`]*?)\s*(?:no\s+)?([A-Za-z].*)?$")


def _count_text(text):
    """A Quest Helper count line as the OCR gives it, cleaned up. In a small game window the digits
    are a few pixels tall, so a 0 often reads as O and the slash as a letter: "O j 40 Charm" is
    "0/40 Charm", "O 75 Zombie" is "0 75 Zombie"."""
    text = re.sub(r"^\s*[OoQD](?=\s*[^A-Za-z\s]|\s*[jrIl!|]\s*\d|\s+\d)", "0", text)
    return re.sub(r"(?<=\d)\s*[jrIl!|]\s*(?=\d)", "/", text)
SLASHES = "/Il1!|$t.,'`7"


def _have(nums, need):
    """How many you have, from the count's digits as read: "30130" is "30 / 30" with the slash read
    as a 1, "3013" the same with the last digit lost."""
    digits = re.sub(r"\s", "", nums)
    n = str(need) if need else ""
    if n and digits.endswith(n) and len(digits) > len(n):
        rest = digits[:-len(n)]
        rest = rest[:-1] if len(rest) > 1 and rest[-1] in SLASHES else rest
        if to_int(rest) is not None and rest.isdigit():
            return int(rest)
    if n:
        for i in range(1, len(digits)):
            have, sep, tail = digits[:i], digits[i], digits[i + 1:]
            if have.isdigit() and sep in SLASHES and (tail == "" or n.startswith(tail)) and int(have) <= need * 5:
                return int(have)
    if n and digits == n:
        # only the goal read: "3 / 25" over a busy map often comes out as "25", and taking that as
        # the count would say the quest is done and send you back to the NPC
        return None
    first = re.match(r"\d+", digits)
    if first and (not need or int(first.group()) <= need * 5) and len(first.group()) <= 4:
        return int(first.group())
    return None


def read_helper(frame, t, s, quests_by_name):
    """Tracked quests and their kill / collect counts, as listed in the Quest Helper. The counts'
    text is often half-read over a busy map, so each line is matched to what the quest asks for.
    "bottom" is where its last quest or count line ends: the Quest Helper is only as tall as the
    quests you track, and a tooltip right under it is still a tooltip."""
    from rapidfuzz import fuzz, process
    names = list(quests_by_name)
    x, y = t[1], t[2]
    quests, cur, bottom = [], None, None
    for text, _, ly, _, lh in read_box(frame, (x - 4 * s, y + 22 * s, x + 330 * s, y + 640 * s), s):
        m = PROGRESS.match(_count_text(text))
        if m:
            bottom = ly + lh
            if cur is None:
                continue
            what = (m.group(2) or "").strip(" .")
            reqs = cur["reqs"]
            # whole-name similarity first, so "Blue Snail Shell" doesn't count as "Snail Shell"
            score = {r: max(fuzz.ratio(what, r), 0.9 * fuzz.partial_ratio(what, r)) for r in reqs} if what else {}
            best = max(score, key=score.get) if score else None
            best = (best,) if best and score[best] >= 60 else None
            need = reqs[best[0]] if best else None
            have = _have(m.group(1), need)
            if best and any(n["what"] == best[0] for n in cur["needs"]):
                continue     # each count shows once per quest; a repeat is a misread line
            if have is not None and best:
                cur["needs"].append({"what": best[0], "have": have, "need": need})
            continue
        hit = match_quest(text, names)
        if hit:
            bottom = ly + lh
            q = quests_by_name[hit]
            cur = {"quest": hit, "id": str(q["id"]), "needs": [],
                   "reqs": {r["name"]: r["count"] for r in q.get("requirements_list") or []
                            if r.get("type") in ("item", "mob") and r.get("count")}}
            quests.append(cur)
        else:
            cur = None    # a title we couldn't place: skip its counts rather than pin them on another quest
    for q in quests:
        q["asks"] = len(q.pop("reqs"))     # how many counts the quest has, read or not
    return {"quests": quests, "bottom": bottom}


def read_hud(frame, t, s, job_names):
    from rapidfuzz import fuzz, process
    x, y = t[1], t[2]
    job = None
    for text, *_ in read_box(frame, (x + 95 * s, y - 12 * s, x + 300 * s, y + 40 * s), s):
        hit = process.extractOne(text, job_names + list(JOB_ALIASES), scorer=fuzz.ratio, score_cutoff=85)
        if hit and job is None:
            job = JOB_ALIASES.get(hit[0], hit[0])
    return {"job": job}


def read_minimap(lines, frame, s, map_names):
    """(street, map name, title box, collapsed) from the mini map's title. Open, it's two stacked
    lines, the street over the map name; collapsed, one bar along the top ("Street : Map"). Read
    closer up and matched against the game's maps; all None if no mini map is showing. The title
    box (left, top, right, bottom) is where the title was read, so things can be placed by it."""
    from rapidfuzz import fuzz, process
    pairs = []
    for a in lines:
        if fuzz.partial_ratio("mini map", a[0].lower()) >= 60 and len(a[0]) <= 12:
            continue     # the mini map's own title bar
        for b in lines:
            overlap = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
            if not (14 * s <= b[2] - a[2] <= 32 * s and overlap > 0.4 * min(a[3], b[3]) and len(b[0]) >= 4):
                continue
            hint = process.extractOne(b[0], map_names, scorer=fuzz.WRatio, score_cutoff=75)
            if hint:
                pairs.append((hint[1], a, b))
    best = None
    for _, a, b in sorted(pairs, key=lambda p: -p[0])[:3]:
        # the map's emblem sits just left of the title and can clip its first letter at 1x
        box = (min(a[1], b[1]) - 24 * s, a[2] - 4 * s, max(a[1] + a[3], b[1] + b[3]) + 40 * s, b[2] + b[4] + 5 * s)
        crop = read_box(frame, box, s)
        if len(crop) < 2:
            continue
        name = match_place(crop[-1][0], map_names, 86)
        score = fuzz.ratio(fix_numeral(crop[-1][0]), name) if name else 0
        if name and (best is None or score > best[0]):
            best = (score, crop[0][0], name, [round(v) for v in box])
    if best:
        return best[1], best[2], best[3], False
    return read_minimap_bar(lines, frame, s, map_names)


BAR_SPLIT = re.compile(r"\s*[:•·]\s*")


def read_minimap_bar(lines, frame, s, map_names):
    """The collapsed mini map: a bar at the top reading "Victoria Road : Lith Harbor Weapon Shop".
    The OCR gives it as one line, as one line with the colon read as a dot, or as two pieces on the
    same row."""
    from rapidfuzz import fuzz, process
    top = sorted((ln for ln in lines if ln[2] < frame.height * 0.12 and ln[1] < frame.width * 0.5),
                 key=lambda ln: (ln[2], ln[1]))
    for a in top:
        row = sorted((b for b in top if abs(b[2] - a[2]) <= 6 * s and b[1] >= a[1]), key=lambda ln: ln[1])
        parts = BAR_SPLIT.split(" : ".join(b[0] for b in row), maxsplit=1)
        if len(parts) < 2:
            continue
        hit = match_place(parts[1], map_names, 86)
        if hit:
            box = [round(min(b[1] for b in row)), round(min(b[2] for b in row)),
                   round(max(b[1] + b[3] for b in row)), round(max(b[2] + b[4] for b in row))]
            return parts[0], hit, box, True
    return None, None, None, None


def _frame_line(p):
    """The thin dark-blue line around the mini map window. When the game draws its UI larger or
    smaller than at 1200 px, the line blends with what's beside it, so only its blue cast counts
    here; minimap_window then wants it long and straight."""
    r, g, b = p[:3]
    return r <= 135 and b >= 130 and b - r >= 35 and b > g


def _line_end(px, x, y, height):
    """How far down the frame line at column x runs from row y (it may skip a pixel or two)."""
    end, miss = y, 0
    while end + 1 < height and miss <= 2:
        end += 1
        miss = 0 if any(_frame_line(px[c, end]) for c in (x - 1, x, x + 1)) else miss + 1
    return end - miss


def minimap_window(frame, title, s):
    """(left, top, right, bottom) of the open mini map window, found from its frame: a thin
    dark-blue line down each side. Only long lines count, so the map's emblem by the title doesn't.
    None if the frame isn't there."""
    px = frame.load()
    l, t, r, b = title
    y = int(b + 12 * s)                                   # inside the window, under the title
    if y >= frame.height:
        return None
    sides = [x for x in range(max(1, int(l - 140 * s)), min(frame.width - 1, int(r + 160 * s)))
             if _frame_line(px[x, y]) and _line_end(px, x, y, frame.height) - y >= 60 * s]
    if len(sides) < 2:
        return None
    left, right = sides[0], sides[-1]
    return [left, round(t - 30 * s), right, _line_end(px, left, y, frame.height)]


# "Blue Sauna Robe (M) (+2)": a gender and upgrades after the name; the item is still a Blue Sauna Robe
TIP_UPGRADES = re.compile(r"(\s*\((?:\+\d+|[MF])\))+\s*$")
# a tooltip's title: its dot, then the name. The box's edge beside it can read as "I", "|" or "."
# ("I •Bow"), and the game's own mouse cursor often covers the dot, so the dot is optional: what makes
# a title is tooltip navy right above it (a shop row's name has the list's light gray there)
TIP_TITLE = re.compile(r"^[\s|Il!.:]{0,4}[•·]?\s*(.+)$")


def _tip_navy(p):
    """The item tooltip's see-through navy, over anything: light over a shop list, near black over
    wood. What stays is blue well above red and green."""
    r, g, b = p[:3]
    return r < 130 and b - r >= 25 and b - g >= 20


def read_tooltips(lines, frame, s, item_names, skip=()):
    """The item tooltips on screen, as [{"name", "box", "title", "untradable"}], left to right.
    Usually one, the item under the mouse; for an equip the game adds a second beside it, the item
    you wear, to compare. A title line starts with a dot ("• Return Scroll to Ellinia"); a box (left,
    top, right, bottom) is measured from its see-through navy, and ends where the next one begins."""
    from rapidfuzz import fuzz, process, utils
    px = frame.load()

    def navy_above(text, x, y, w, h):
        """Tooltip navy just over the title: at least two of three spots along it."""
        row = int(y - 4 * s)
        return row >= 0 and sum(_tip_navy(px[min(frame.width - 1, int(x + w * f)), row]) for f in (0.25, 0.5, 0.75)) >= 2

    titles = []
    for ln in lines:
        if any(a <= ln[1] <= c and b <= ln[2] <= d for a, b, c, d in skip):
            continue        # inside the Quest Helper or Quest window: an item to collect, not a tooltip
        m = TIP_TITLE.match(ln[0])
        names = item_names
        if m and not m.group(1)[:1].isalpha():
            # a title starting with a number is one of the few items named so ("10,000 Meso Pouch",
            # "2x EXP Coupon"), never "0/20 Broken Mirror Glass", a Quest Helper count
            names = [n for n in item_names if n[:1].isdigit()]
        if m and names and navy_above(*ln):
            hit = process.extractOne(TIP_UPGRADES.sub("", m.group(1)), names, scorer=fuzz.ratio,
                                     processor=utils.default_process, score_cutoff=86)
            if hit:
                titles.append((hit[0], ln))
    titles.sort(key=lambda t: (round(t[1][2] / (10 * s)), t[1][1]))      # top to bottom, then left to right
    tips = []
    for name, (text, x, y, w, h) in titles:
        row = int(y + h + 6 * s)
        if row >= frame.height:
            continue
        if any(t["box"][0] <= x <= t["box"][2] and t["title"][1] + 10 * s < y <= t["box"][3] for t in tips):
            continue        # inside a tooltip already found: a shop row's name, seen through its navy
        # side by side, one tooltip starts right where the other ends, in the same navy
        stop = min([nx - 4 * s for _, (_, nx, ny, _, _) in titles if nx > x and abs(ny - y) < 10 * s] + [frame.width - 1])
        floor = max([t["box"][2] + 1 for t in tips if abs(t["title"][1] - y) < 10 * s] + [0])
        left = int(x)
        while left > floor and _tip_navy(px[left - 1, row]):
            left -= 1
        right, gap = int(x + w), 0              # the box runs on past the title; text inside it isn't navy
        while right + 1 < stop and gap < 40 * s:
            right += 1
            gap = 0 if _tip_navy(px[right, row]) else gap + 1
        right -= int(gap)

        def depth(col):
            b, gap = row, 0
            while b + 1 < frame.height and gap < 10 * s:
                b += 1
                gap = 0 if _tip_navy(px[col, b]) else gap + 1
            return b - int(gap)
        # down a few columns inside it, the deepest wins: an equip's tooltip has a light border down
        # its edge, and lines of text break the navy elsewhere
        bottom = max(depth(c) for c in (right - int(3 * s), right - int(12 * s), right - int(30 * s), left + int(4 * s))
                     if left <= c <= right)
        if right - left < 120 * s or bottom - row < 20 * s:
            continue                            # no tooltip box around it
        # "Untradable", in orange just under the title: no market price can apply
        untradable = any(fuzz.partial_ratio("untradable", t.lower()) >= 85 and left <= tx <= right and y < ty < y + h + 30 * s
                         for t, tx, ty, _, _ in lines)
        title = [int(x), int(y), int(x + w), int(y + h)]
        tips.append({"name": name, "box": [left, round(y - 8 * s), right, bottom], "title": title,
                     "untradable": untradable,
                     "look": frame.crop(tuple(title)).convert("L")})    # for tooltip_still_up's quick looks
    return tips[:2]


NAVY_SHRINK = 4           # the quick looks see the frame at a quarter of its size


def navy_mask(frame):
    """The frame at a quarter of its size, white where it's tooltip navy: how the quick looks see a
    tooltip come up without reading anything."""
    small = frame.resize((frame.width // NAVY_SHRINK, frame.height // NAVY_SHRINK), Image.BOX)
    r, g, b = small.split()
    on = lambda img, test: img.point(lambda v: 255 if test(v) else 0)
    return ImageChops.multiply(ImageChops.multiply(on(ImageChops.subtract(b, r), lambda v: v >= 25),
                                                   on(ImageChops.subtract(b, g), lambda v: v >= 20)),
                               on(r, lambda v: v < 130))


def new_navy(mask, before):
    """Where navy just came up since the last look, as a full-size box, or None. A tooltip appears as
    one solid block of it; small changes (a monster, a spell) are worn away, and the whole scene
    shifting as you walk is too big to be one."""
    if before is None or before.size != mask.size:
        return None
    box = ImageChops.subtract(mask, before).filter(ImageFilter.MinFilter(5)).getbbox()
    if not box or (box[2] - box[0]) * (box[3] - box[1]) > mask.width * mask.height * 0.4:
        return None
    return [v * NAVY_SHRINK for v in box]


def look_for_tooltips(frame, region, item_names, skip=()):
    """The item tooltips in one area of the frame: read_tooltips on that area's text only, which is
    far quicker than reading the whole game."""
    l, t, r, b = (int(v) for v in region)
    l, t, r, b = max(0, l - 20), max(0, t - 20), min(frame.width, r + 20), min(frame.height, b + 20)
    if r - l < 40 or b - t < 20:
        return []
    return read_tooltips(ocr(frame.crop((l, t, r, b)), 1, l, t), frame, frame.height / REF_HEIGHT, item_names, skip)


# where the windows that list items you don't hover sit, measured from their title, at the 1200 px UI
# size: the Quest window is always 375 x 607. The Quest Helper is 345 wide but only as tall as the
# quests you track, so its bottom comes from the last line it shows; until one has read, only its title
NOT_TIPS = {"helper": (-8, -4, 340, 30), "quest": (-10, -9, 366, 600)}
HELPER_MARGIN = 10      # the Quest Helper's frame below its last line


def tooltip_still_up(frame, tip):
    """True if the same tooltip is still on screen: its title looks as it did when it was read (a
    quick look, no OCR)."""
    now = frame.crop(tuple(tip["title"])).convert("L")
    return now.size == tip["look"].size and ImageStat.Stat(ImageChops.difference(now, tip["look"])).mean[0] < 12


# "1 for 4,500 mesos". The shop list's pixel font makes the OCR read some digits as letters:
# 9 as g ("5,ggg" is 5,999, "Igg" is 199), 1 as I or l, 0 as O, 5 as S, 8 as B, 2 as Z.
LOOKALIKE = str.maketrans({"g": "9", "q": "9", "O": "0", "o": "0", "D": "0", "I": "1", "l": "1", "|": "1",
                           "i": "1", "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2"})
LISTING = re.compile(r"^\s*([\dIlOo|, ]+?)\s*[ft]or\s*([\dgqOoDIl|iSsBZz,.;' ]+)", re.I)


def _num(text):
    return to_int(text.translate(LOOKALIKE))


def read_banded(frame, box, s, band=90, overlap=30):
    """read_box, a few rows at a time. Over a list of mostly faint rows (a shop that's nearly sold
    out) the OCR can drop lines when it reads the whole list at once; a strip a few rows tall reads
    them. Strips overlap, so a row cut by one is whole in the next; repeats are dropped."""
    l, t, r, b = box
    out, y = [], t
    while y < b:
        for ln in read_box(frame, (l, y, r, min(b, y + band * s)), s):
            if not any(abs(ln[2] - o[2]) < 6 * s and abs(ln[1] - o[1]) < 12 * s for o in out):
                out.append(ln)
        y += (band - overlap) * s
    return sorted(out, key=lambda ln: (ln[2], ln[1]))


def read_shop(frame, t, s, item_names):
    """A player shop: the seller and each listed item with its price. Rows show the item's name
    with "<count> for <price> mesos" under it; sold-out rows are grayed out."""
    x, y = t[1], t[2]          # the LEAVE STORE button
    box = left, top, right, bottom = x - 168 * s, y + 60 * s, x + 92 * s, y + 440 * s
    rows = lambda lines: [ln for ln in lines if abs(ln[1] - (x - 164 * s)) < 12 * s]   # not item tooltips
    items = _shop_items(rows(read_box(frame, box, s)), frame, s, top, item_names)
    if not items:              # nothing read at once: try again a few rows at a time
        items = _shop_items(rows(read_banded(frame, box, s)), frame, s, top, item_names)
    seller = read_box(frame, (x - 205 * s, y + 24 * s, x - 90 * s, y + 50 * s), s)
    return {"seller": seller[0][0] if seller else None, "items": items,
            "box": [round(left), round(top), round(right - left), round(bottom - top)]}


def _shop_items(lines, frame, s, top, item_names):
    """Each listed item in a shop list's text: a name line with "<count> for <price> mesos" under it."""
    from rapidfuzz import fuzz, process
    items = []
    for i, ln in enumerate(lines):
        m = LISTING.match(ln[0])
        if not m or i == 0 or LISTING.match(lines[i - 1][0]) or not 18 * s <= ln[2] - lines[i - 1][2] <= 34 * s:
            continue
        name_line = lines[i - 1]
        count, price = _num(m.group(1)), _num(m.group(2))
        hit = process.extractOne(name_line[0].replace("VV", "W"), item_names, scorer=fuzz.ratio, score_cutoff=80)
        if not count or not price or not hit:
            continue
        # sold-out rows are drawn in light gray: no dark pixels in their name
        nx, ny, nw, nh = name_line[1:]
        dark = ImageOps.grayscale(frame.crop((int(nx), int(ny), int(nx + nw), int(ny + nh)))).getextrema()[0]
        items.append({"name": hit[0], "count": count, "price": price, "unit": price / count,
                      "sold": dark > 120, "cy": (name_line[2] + ln[2] + ln[4]) / 2 - top})
    return items


def quest_completed(lines, s, quest_names):
    """The quest in a "Quest Complete!" notice (the red bubble over the HUD), as {"text", "quest"}.
    Its name line is cut short ("[Event] The Journ..."), so the app also checks it against the
    quests you have in progress."""
    from rapidfuzz import fuzz
    for ln in lines:
        if len(ln[0]) > 22 or fuzz.partial_ratio("quest complete", ln[0].lower()) < 85:
            continue
        above = [a for a in lines if 8 * s <= ln[2] - a[2] <= 35 * s and abs(a[1] - ln[1]) <= 25 * s]
        if above:
            text = above[-1][0].replace("VV", "W")
            cut = text if text.rstrip().endswith(("...", "..", "…")) else text + "..."
            return {"text": text.rstrip(".… "), "quest": match_quest(cut, quest_names)}
    return None


def shop_still_open(frame, anchor, s):
    """True if the LEAVE STORE button is still where it was: the quick check before a shop-only re-read."""
    from rapidfuzz import fuzz
    x, y, w, h = anchor[1:]
    for text, *_ in read_box(frame, (x - 12 * s, y - 8 * s, x + w + 12 * s, y + h + 8 * s), s):
        if fuzz.ratio("LEAVE STORE", re.sub(r"[^A-Za-z ]", "", text).upper()) >= 70:
            return True
    return False


# ---------------------------------------------------------------- everything at once
def _title_look(frame, line):
    """A window's title, as pixels: how a later read knows the window is still there, unmoved."""
    _, x, y, w, h = line
    box = (int(x), int(y), int(x + w), int(y + h))
    return box, frame.crop(box).convert("L")


def still_there(frame, kept):
    """True if a window's title is still exactly where it was last read (a quick look, no OCR)."""
    box, look = kept["look"]
    if box[2] > frame.width or box[3] > frame.height:
        return False
    now = frame.crop(box).convert("L")
    return now.size == look.size and ImageStat.Stat(ImageChops.difference(now, look)).mean[0] < 10


class Reader:
    def __init__(self, data):
        self.data = data
        self.digits = LevelDigits()
        self.kept = {}            # window -> its title line and look, from the last read that saw it
        self.helper_depth = None  # how far the Quest Helper's last line reaches below its title
        self.by_name = {}         # quest name -> every quest with that name (job quests share names)
        for q in data.quest_list:
            self.by_name.setdefault(q["name"], []).append(q)
        self.job = None
        self.set_job("Beginner")
        self.skill_names = sorted({s["name"] for fam, groups in data.skills.items() if isinstance(groups, list)
                                   for g in groups if isinstance(g, dict) for s in g.get("skills", [])})
        self.map_names = sorted({m["name"].strip() for m in data.maps.values() if m.get("name")})
        self.item_names = sorted(set(data.item_ids) | set(data.market.names))
        from gamedata import JOBS
        self.job_names = list(JOBS)

    def tip_skip(self, frame):
        """The Quest Helper's and Quest window's areas, as last seen: item names in them aren't tooltips."""
        s = frame.height / REF_HEIGHT
        out = []
        for k, (a, b, c, d) in NOT_TIPS.items():
            if not (ln := (self.kept.get(k) or {}).get("line")):
                continue
            if k == "helper" and self.helper_depth:
                d = self.helper_depth + HELPER_MARGIN
            out.append((ln[1] + a * s, ln[2] + b * s, ln[1] + c * s, ln[2] + d * s))
        return out

    def look_for_tooltips(self, frame, region):
        return look_for_tooltips(frame, region, self.item_names, self.tip_skip(frame))

    def set_job(self, job):
        """The quests a title can name, for this job. Four quests are called "Test of Qualification",
        one per job; and another job's quests are left out, so a half-read title can't land on one."""
        if job == self.job:
            return
        from gamedata import JOBS
        self.job = job
        own = JOB_REGIONS.get(JOBS.get(job, JOBS["Beginner"])[0])
        self.quests_by_name = {}
        for name, qs in self.by_name.items():
            mine = [q for q in qs if q["region"] == own] or \
                   [q for q in qs if q["region"] not in JOB_REGIONS.values() or own is None]
            if mine:
                self.quests_by_name[name] = mine[0]
        self.quest_names = sorted(self.quests_by_name)

    def read(self, frame):
        """Everything visible in one frame of the game area, plus where each window is."""
        s = frame.height / REF_HEIGHT
        lines = ocr(frame)
        wins = find_windows(lines, frame.height)
        # windows move whenever you drag them, so each read looks for them again. When a title didn't
        # read this time, a window whose title is still pixel for pixel where it was is still open
        for k in KEPT:
            if k not in wins and k in self.kept and still_there(frame, self.kept[k]):
                wins[k] = self.kept[k]["line"]
        self.kept = {k: {"line": wins[k], "look": _title_look(frame, wins[k])} for k in KEPT if k in wins}
        if "hud" not in wins:
            # "LV." doesn't always read; the job name next to it does, 110 px to its right
            from rapidfuzz import fuzz, process
            for ln in lines:
                if ln[2] > frame.height * 0.92 and process.extractOne(
                        ln[0], self.job_names + list(JOB_ALIASES), scorer=fuzz.ratio, score_cutoff=85):
                    wins["hud"] = ("LV.", ln[1] - 110 * s, ln[2] + 9 * s, 32 * s, 21 * s)
                    break
        seen = {"windows": {k: [round(v[1] / frame.width, 4), round(v[2] / frame.height, 4)] for k, v in wins.items()},
                "scale": round(s, 3)}
        glyphs = None
        if "hud" in wins:
            seen["hud"] = read_hud(frame, wins["hud"], s, self.job_names)
            glyphs = level_glyphs(frame, wins["hud"])
            lv, exact = self.digits.read(glyphs)
            seen["hud"].update(level=lv, level_exact=exact)
        done = quest_completed(lines, s, self.quest_names)
        if done:
            seen["quest_complete"] = done
        street, name, title, collapsed = read_minimap([ln for ln in lines if ln[2] < frame.height * 0.9], frame, s,
                                                      self.map_names)
        if name:
            seen["map"] = {"street": street, "name": name, "title": title, "collapsed": collapsed,
                           "window": None if collapsed else minimap_window(frame, title, s)}
        tips = read_tooltips(lines, frame, s, self.item_names, self.tip_skip(frame))
        if tips:
            seen["tooltips"] = tips
        if "stat" in wins:
            seen["stat"] = read_stat(frame, wins["stat"], s, self.job_names)
            lv = seen["stat"].get("level")
            if glyphs and lv and len(str(lv)) == len(glyphs):    # both agree on the digit count
                self.digits.learn(glyphs, lv)
                seen["hud"].update(level=lv, level_exact=True)
        if "inventory" in wins:
            seen["inventory"] = read_inventory(frame, wins["inventory"], s)
        if "skills" in wins:
            seen["skills"] = read_skills(frame, wins["skills"], s, self.skill_names)
        if "quest" in wins:
            seen["quest"] = read_quest_window(frame, wins["quest"], s, self.quest_names)
            if seen["quest"] is None:
                del seen["quest"], wins["quest"], seen["windows"]["quest"]
                self.kept.pop("quest", None)
        if "helper" in wins:
            seen["helper"] = read_helper(frame, wins["helper"], s, self.quests_by_name)
            bottom = seen["helper"].pop("bottom")
            if bottom is not None:      # kept while a read makes out none of its lines
                self.helper_depth = (bottom - wins["helper"][2]) / s
        if "shop" in wins:
            seen["shop"] = read_shop(frame, wins["shop"], s, self.item_names)
            seen["shop"]["anchor"] = list(wins["shop"])
        return seen

    def read_shop_only(self, frame, anchor):
        """The quick look while a shop is open: just its item list, about a fifth of a full read."""
        s = frame.height / REF_HEIGHT
        if not shop_still_open(frame, anchor, s):
            return None
        shop = read_shop(frame, anchor, s, self.item_names)
        shop["anchor"] = list(anchor)
        return {"shop": shop, "scale": round(s, 3), "quick": True,
                "windows": {"shop": [round(anchor[1] / frame.width, 4), round(anchor[2] / frame.height, 4)]}}
