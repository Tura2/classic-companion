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

from paths import APP_DIR, RES_DIR
from anchors import Titles
from hudexp import ExpDigits, exp_glyphs
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
WHITE = 200     # a pixel of white text: its darkest channel at least this bright


def ink(img, prep=None):
    """The picture OCR is given. Plain gray suits most of the game's text. The mini map's title is
    white on a see-through light blue, so in gray it has little contrast and Windows OCR often drops
    the map's name and always the "<7>" of "Free Market <7>". "white" keeps just the white text, black
    on white; "bright" is each pixel's darkest channel, white text standing out of any colored
    background, edges kept (2026-11-13: West Rocky Mountain IV read by both, never in gray)."""
    if prep is None:
        return ImageOps.grayscale(img)
    import numpy as np
    low = np.asarray(img.convert("RGB")).min(axis=2)
    if prep == "white":
        return Image.fromarray(np.where(low >= WHITE, 0, 255).astype("uint8"))
    return Image.fromarray(low.astype("uint8"))


def ocr(img, scale=1, x0=0, y0=0, prep=None):
    """[(text, x, y, w, h)] in frame pixels. `img` is a crop whose top-left sits at (x0, y0); `prep`
    is how its picture is made for OCR (see ink)."""
    import winocr
    im = ink(img, prep)
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


def read_box(frame, box, s=1.0, pad=0, prep=None):
    """OCR one area of the frame (clipped to it), lines sorted top to bottom. Small UI text reads
    best at about 3x the 1200 px UI size. `pad` adds blank margin in the area's own background
    color, for text that starts right at the area's edge. `prep`: see ink."""
    l, t, r, b = (int(v) for v in box)
    l, t, r, b = max(0, l), max(0, t), min(frame.width, r), min(frame.height, b)
    if r - l < 8 or b - t < 8:
        return []
    crop = frame.crop((l, t, r, b))
    if pad:
        bg = max(crop.getcolors(crop.width * crop.height) or [(0, (255, 255, 255))])[1]
        crop = ImageOps.expand(crop, border=pad, fill=bg)
        l, t = l - pad, t - pad
    return sorted(ocr(crop, 3 / s, l, t, prep), key=lambda ln: (ln[2], ln[1]))


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
        mine = my_shop_line(text)
        if mine:
            if mine not in found or ln[2] < found[mine][2]:     # the notice's first line
                found[mine] = ln
            continue
        for button, above in SHOP_BUTTONS.items():
            score = fuzz.ratio(button, letters)
            if score >= 75 and score - above / 10 > best.get("shop", 0):   # LEAVE STORE wins a tie
                s = ln[4] / 12        # the buttons' text is 12 px tall at the 1200 px UI size
                found["shop"] = (button, ln[1], ln[2] + above * s, ln[3], ln[4])
                best["shop"] = score - above / 10
    if "myshop" in found and "shop" in found:
        # someone else's shop shows the same fee notice under it: a LEAVE STORE above it is theirs
        x, y = found["myshop"][1:3]
        if abs(found["shop"][1] - x) < 400 and -700 < found["shop"][2] - y < 0:
            del found["myshop"]
    return found


# ---------------------------------------------------------------- your own store
# Your own personal store (the character sits in it) has no LEAVE STORE button. Under it the game
# always shows "Please be aware that a 3% fee / will be deducted from sales.", which the 1x pass
# reads well at every UI size, so that notice is its anchor. The SOLD ITEMS side panel is found by
# its "Total Sales / Total Received" line. Measured 2026-11-07 on two UI sizes (u = 1.0 and 0.73).
FEE_NOTICE = "please be aware that a 3% fee"
FEE_WIDTH = 232          # the notice's first line, px wide at the 1200 px UI size
SALES_TITLE = "total sales total received"
SALES_WIDTH = 214        # the panel's "Total Sales / Total Received" line at the same size
MY_NAME_CUT = 180       # a name line this wide (at the 1200 px UI size) reaches the list's edge: cut short
MESOS = re.compile(r"^\s*([\dOoIl|,.\s]{1,13})\s*mes[o0]s\s*$", re.I)
AMOUNT = re.compile(r"^\s*\d{1,3}(?:[,.\s]\d{3})*\s*$")


def my_shop_line(text):
    """"myshop" for the fee notice's first line, "mysales" for the SOLD ITEMS panel's title, else None."""
    from rapidfuzz import fuzz
    low = re.sub(r"[^a-z0-9% ]", " ", text.lower())
    low = re.sub(r"\s+", " ", low).strip()
    if len(low) >= 20 and fuzz.partial_ratio(FEE_NOTICE, low) >= 85:
        return "myshop"
    letters = re.sub(r"[^a-z ]", " ", low)
    letters = re.sub(r"\s+", " ", letters).strip()
    if len(letters) >= 18 and fuzz.ratio(SALES_TITLE, re.sub(r"\b[a-z]\b ?", "", letters).strip()) >= 85:
        return "mysales"
    return None


def _width_from(line, start):
    """The width of an OCR line from the word `start` on: a stray mark read in front ("g Please")
    widens the line without being part of the text."""
    text, w = line[0], line[3]
    i = text.lower().find(start)
    return w * (len(text) - i) / len(text) if i > 0 else w


def orange_buttons(frame, line):
    """How many orange buttons the store has right of the character: someone else's shop has two
    (BUY ITEM, LEAVE STORE), your open store one (CLOSE STORE; OPEN STORE is grayed out)."""
    u = _width_from(line, "please") / FEE_WIDTH
    x = line[1] + line[3] - _width_from(line, "please")
    y = line[2]
    l, t = max(0, int(x + 145 * u)), max(0, int(y - 520 * u))
    r, b = min(frame.width, int(x + 270 * u)), min(frame.height, int(y - 395 * u))
    if r - l < 10 or b - t < 10:
        return 0
    area = frame.crop((l, t, r, b)).convert("RGB")
    px = area.load()
    # a button's white lettering leaves only a little orange on its middle rows: a low bar, and
    # a gap of a row or two inside a button doesn't split it
    rows = [sum(_orange(px[c, rr]) for c in range(area.width)) >= area.width * 0.12 for rr in range(area.height)]
    on = [i for i, v in enumerate(rows) if v]
    return sum(1 for i, rr in enumerate(on) if i == 0 or rr - on[i - 1] > 3)


def read_my_shop(frame, line, item_names):
    """Your own store, from its fee notice's first line: its title, the mesos box under your
    character and the listed items ("1 for 388,887 mesos"), with u, the UI's size against 1200 px."""
    u = _width_from(line, "please") / FEE_WIDTH
    x = line[1] + line[3] - _width_from(line, "please")      # where "Please" starts
    y = line[2]
    box = left, top, right, bottom = x - 60 * u, y - 600 * u, x + 280 * u, y - 30 * u
    lines = read_box(frame, box, u)
    title = [ln for ln in lines if ln[2] < y - 540 * u and ln[1] < x + 200 * u]
    # the mesos box under your character reads only on its own, not with the whole store
    mesos = next((to_int(t) for t, *_ in read_box(frame, (x + 130 * u, y - 420 * u, x + 275 * u, y - 368 * u), u)
                  if AMOUNT.match(t)), None)
    rows = [ln for ln in lines if abs(ln[1] - (x + 18 * u)) < 14 * u and ln[2] > y - 385 * u]   # not your name
    return {"title": title[0][0] if title else None, "mesos": mesos, "items": _my_items(rows, frame, u, item_names),
            "u": round(u, 3), "box": [round(left), round(top), round(right - left), round(bottom - top)]}


def _my_items(lines, frame, u, item_names):
    """Your store's listed rows, like _shop_items, but a name the list cuts short ("Overall Armor
    DEF Scroll:..") that matches more than one item is kept as its text, with no item: it can still
    say what sold. Each row: {"name", "text", "count", "price", "sold"}."""
    items, i = [], 0
    while i < len(lines):
        name_line = lines[i]
        if LISTING.match(name_line[0]):
            i += 1
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) and 18 * u <= lines[i + 1][2] - name_line[2] <= 34 * u else None
        m = LISTING.match(nxt[0]) if nxt else None
        if not m:
            # the price line misread ("1 ,6gg mesos"): read it again on its own, with a margin
            nx, ny = name_line[1], name_line[2] + 24 * u
            for pad in (4, 8):
                again = read_box(frame, (nx - 4 * u, ny - 5 * u, nx + 225 * u, ny + 19 * u), u, pad=pad)
                m = next((LISTING.match(a[0]) for a in again if LISTING.match(a[0])), None)
                if m:
                    break
        i += 2 if nxt and m else 1
        if not m:
            continue
        count, price = _num(m.group(1)), _num(m.group(2))
        if not count or not price:
            continue
        text = name_line[0].replace("VV", "W").strip()
        nx, ny, nw, nh = name_line[1:]
        if nw / u >= MY_NAME_CUT and not text.endswith(("..", "…")):
            text = text[:-1] + ".."      # as wide as the column: cut short, its last mark a misread "..."
        dark = ImageOps.grayscale(frame.crop((int(nx), int(ny), int(nx + nw), int(ny + nh)))).getextrema()[0]
        items.append({"name": match_item(text, item_names), "text": text.rstrip(".… :").strip(), "count": count,
                      "price": price, "sold": dark > 120})
    return items


BUYER = re.compile(r"^\s*bu[yv]er(?![a-z])", re.I)
PURCHASED = re.compile(r"^\s*number\s*purchased\s*[:;.]?\s*([\dIlOo|]+)", re.I)
SOLD_ROW = 82             # one row of the SOLD ITEMS panel, at the 1200 px UI size


def read_sales_panel(frame, line, item_names):
    """The SOLD ITEMS panel, from its "Total Sales / Total Received" line: the two totals under it
    ("20 mesos" each) and, above it, a row per sale: the item, "Buyer: ..." and "Number purchased: N"
    (seen 2026-11-07; the totals row moves down one row with each sale). Rows: {"name", "count"},
    oldest first; the buyer's name isn't kept."""
    u = line[3] / SALES_WIDTH
    x, y = line[1], line[2]
    lines = read_box(frame, (x - 10 * u, y + 12 * u, x + 230 * u, y + 76 * u), u, pad=4)
    totals = [_num(m.group(1)) for ln in lines[:4] if (m := MESOS.match(ln[0]))]
    rows = []
    above = read_box(frame, (x - 10 * u, y - 4 * SOLD_ROW * u - 10 * u, x + 230 * u, y - 4 * u), u)
    for i, ln in enumerate(above):
        nxt = above[i + 1:i + 3]
        if len(nxt) < 2 or not BUYER.match(nxt[0][0]) or not (m := PURCHASED.match(nxt[1][0])):
            continue
        if abs(nxt[0][1] - ln[1]) > 12 * u or not (15 * u <= nxt[0][2] - ln[2] <= 35 * u):
            continue
        text = ln[0].replace("VV", "W").strip()
        rows.append({"name": match_item(text, item_names) or text, "count": _num(m.group(1))})
    return {"total_sales": totals[0] if totals else None, "total_received": totals[1] if len(totals) > 1 else None,
            "rows": rows, "u": round(u, 3)}


def find_sales_panel(frame, fee_line):
    """The SOLD ITEMS panel's "Total Sales / Total Received" line, looked for right of your store
    (the panel sits there; its totals line moves down a row with each sale). None if it's closed."""
    u = _width_from(fee_line, "please") / FEE_WIDTH
    x = fee_line[1] + fee_line[3] - _width_from(fee_line, "please")
    y = fee_line[2]
    for ln in read_box(frame, (x + 600 * u, y - 600 * u, x + 1060 * u, y - 60 * u), u):
        if my_shop_line(ln[0]) == "mysales":
            return ln
    return None


def my_shop_still_open(frame, line):
    """True if the fee notice still reads where it was: the check before a store-only re-read."""
    u = _width_from(line, "please") / FEE_WIDTH
    _, x, y, w, h = line
    return any(my_shop_line(t) == "myshop" for t, *_ in
               read_box(frame, (x - 12 * u, y - 8 * u, x + w + 12 * u, y + h + 8 * u), u))


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
            d = self.known.get(_bits(g)) or self.nearest(g)
            if d is None:
                exact = False
                big = g.resize((g.width * 4, g.height * 4), Image.NEAREST)
                d = max("0123456789", key=lambda c: _similar(big, _font_digit(c, big.size)))
            digits += d
        return int(digits), exact

    def nearest(self, g, min_same=0.92):
        """The digit of the learned shape this one is nearly the same as (the game can draw a digit a
        pixel differently), or None. Only shapes of the same size count."""
        size, bits = _bits(g).split(":")
        best, d = min_same, None
        for k, v in self.known.items():
            ksize, kbits = k.split(":")
            if ksize == size:
                same = sum(a == b for a, b in zip(bits, kbits)) / len(bits)
                if same >= best:
                    best, d = same, v
        return d

    def learn(self, glyphs, level):
        """Learn the digit shapes of a level known to be right. A shape already learned as another
        digit is forgotten, never remapped: one of the two reads was wrong."""
        s = str(level)
        if len(s) != len(glyphs):
            return
        changed = False
        for g, d in zip(glyphs, s):
            k = _bits(g)
            if k not in self.known:
                self.known[k], changed = d, True
            elif self.known[k] != d:
                del self.known[k]
                changed = True
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


def join_digits(text):
    """OCR puts a space after a 1 ("1 52 (1 42+1 0)"): spaces between two digits go."""
    return re.sub(r"(?<=\d)\s+(?=\d)", "", text or "")


def stat_number(text):
    """(total, base) of a stat row: "152 (142+10)" is 152 in all, 142 of it from AP, the rest from gear."""
    text = join_digits(text)
    total = to_int(text.split("(")[0])
    m = re.search(r"\(\s*(\d+)\s*\+", text)
    return total, int(m.group(1)) if m else total


def fix_one_vs_l(text, crop):
    """A name with the 1s OCR read as l put right ("Tural" is "Tura1"): the game's 1 has a flag
    reaching left from the top of its stem, its l is a plain stem. Only when the crop's letters
    can be told apart one by one (names have no spaces); an I without a flag stays as read."""
    import numpy as np
    ink = np.asarray(ImageOps.grayscale(crop)) < 150
    cols = ink.any(axis=0)
    glyphs, x = [], 0
    while x < len(cols):
        if cols[x]:
            start = x
            while x < len(cols) and cols[x]:
                x += 1
            glyphs.append(ink[:, start:x])
        x += 1
    if len(glyphs) != len(text):
        # the letters can't be told apart (a see-through tooltip over the name): an l or I in it
        # may be a 1, so the name isn't known from this read
        return None if any(c in "lI|1" for c in text) else text
    out = []
    for ch, g in zip(text, glyphs):
        if ch in "lI|1":
            rows = np.where(g.any(axis=1))[0]
            g = g[rows[0]:rows[-1] + 1]
            stem = np.where(g.sum(axis=0) >= 0.7 * g.shape[0])[0]
            top = g[:max(1, g.shape[0] // 3)]
            flag = len(stem) and top[:, :max(0, stem.min() - 1)].any()
            ch = "1" if flag else ("I" if ch == "I" else "l")
        out.append(ch)
    return "".join(out)


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
    name = v.get("name")
    line = next((ln for ln in vals if ln[0] == name), None) if name else None
    if line:      # OCR reads Tura1 as Tural: the 1's own shape says which it is
        _, lx, ly, lw, lh = line
        name = fix_one_vs_l(name, frame.crop((int(lx - 3 * s), int(ly - 2 * s), int(lx + lw + 4 * s), int(ly + lh + 2 * s))))
    out = {"name": name, "job": job}
    lv = to_int(v.get("level", ""))
    out["level"] = lv if lv and 1 <= lv <= 200 else None
    m = re.search(r"^([\d,\s]+)\((\d+)", join_digits(v.get("exp", "")))     # "11392 (56%)", read "1 1392 (56%)"
    if m:
        out["exp"], out["exp_pct"] = to_int(m.group(1)), int(m.group(2))
    for k in ("str", "dex", "int", "luk"):
        total, base = stat_number(v.get(k, ""))
        if total is not None:
            out[k], out[k + "_base"] = total, base
    # unspent AP: a lone number in a box, which the values column reads as its border's "1"
    out["ap"] = read_small_number(frame, (x + 122 * s, y + 388 * s, x + 170 * s, y + 410 * s), s)
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

    def starting(low):
        """The one name starting so; None when none does, or when several do (never a guess)."""
        hits = [q for q in names if q.lower().startswith(low)]
        return hits[0] if len(hits) == 1 else (None if hits else False)
    if text.endswith(("...", "..", "…", ":")) and len(cut) >= 8:
        hit = starting(cut.lower()[:len(cut) - 1])
        if hit is not False:
            return hit       # "Maple World's Unique Fun:..." is two lines (Match Cards, Omok): None
    hit = process.extractOne(text, names, scorer=fuzz.WRatio, score_cutoff=cutoff) if len(text) >= 6 else None
    if hit:
        return hit[0]
    if len(cut) >= 14:            # the Quest Helper cuts long titles without "..."
        return starting(cut.lower()[:-2]) or None
    return None


def read_quest_window(frame, t, s, quest_names, line_names=()):
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
        quest = match_quest(text, quest_names)
        # a quest line shows under its own name ("Caretaker's Ledger"), not its step's
        names.append({"text": text.rstrip(".:… "), "quest": quest,
                      "line": None if quest else match_quest(text, line_names)})
    return {"tab": tab, "quests": names}


PROGRESS = re.compile(r"^\s*(\d[\d\s/\\Il!|$t.,'`]*?)\s*(?:no\s+)?([A-Za-z].*)?$")   # "1 \ 1": a slash read as \


def _count_text(text):
    """A Quest Helper count line as the OCR gives it, cleaned up. In a small game window the digits
    are a few pixels tall, so a 0 often reads as O and the slash as a letter: "O j 40 Charm" is
    "0/40 Charm", "O 75 Zombie" is "0 75 Zombie"."""
    text = re.sub(r"^\s*[OoQD](?=\s*[^A-Za-z\s]|\s*[jrIl!|]\s*\d|\s+\d)", "0", text)
    return re.sub(r"(?<=\d)\s*[jrIl!|\\]\s*(?=\d)", "/", text)
SLASHES = "/\\Il1!|$t.,'`7"


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
    # a lone number isn't a count: "0 / 25" with "0 / 2" hidden behind a rope reads "5"
    return None


def helper_count(text):
    """How many quests the Quest Helper says it tracks: the 4 in "Quest Helper (4/5)", or None."""
    m = re.search(r"\(\s*(\d)", text or "")
    return int(m.group(1)) if m else None


def _join_rows(lines, s):
    """OCR lines on the same row joined left to right: a rope or a vine across the see-through
    Quest Helper cuts its lines in pieces ("Make a Pig & Oct", "us Omok Set")."""
    rows = []
    for ln in sorted(lines, key=lambda ln: (ln[2], ln[1])):
        r = rows[-1] if rows else None
        if r and abs(ln[2] - r[2]) <= 4 * s:
            x, y = min(r[1], ln[1]), min(r[2], ln[2])
            rows[-1] = (r[0] + " " + ln[0], x, y, max(r[1] + r[3], ln[1] + ln[3]) - x, max(r[2] + r[4], ln[2] + ln[4]) - y)
        else:
            rows.append(tuple(ln))
    return rows


def read_helper(frame, t, s, quests_by_name, active_ids=frozenset()):
    """Tracked quests and their kill / collect counts, as listed in the Quest Helper. The counts'
    text is often half-read over a busy map, so each line is matched to what the quest asks for.
    "bottom" is where its last quest or count line ends: the Quest Helper is only as tall as the
    quests you track, and a tooltip right under it is still a tooltip."""
    from rapidfuzz import fuzz, process
    names = list(quests_by_name)
    x, y = t[1], t[2]
    # "Quest Helper (4/5)": how many quests it tracks, read close up (the 1x pass gives "(4.15)")
    title = read_box(frame, (x - 4 * s, y - 4 * s, x + 220 * s, y + 21 * s), s)
    tracked = helper_count(title[0][0]) if title else None
    rows = _join_rows(read_box(frame, (x - 4 * s, y + 22 * s, x + 330 * s, y + 640 * s), s), s)
    # titles are matched strictly: a title half-hidden by a rope is left out, never matched loosely
    # (tried: "[E entl The Jourt' y Begins" then lands on "The Best Dad")
    quests, bottom = _helper_rows(rows, s, quests_by_name, names, active_ids)
    quests = cap_quests(quests, tracked)
    for q in quests:
        q["asks"] = len(q.pop("reqs"))     # how many counts the quest has, read or not
        del q["score"]
    return {"quests": quests, "bottom": bottom}


def cap_quests(quests, tracked):
    """More titles than the Quest Helper tracks means a misread line landed on a look-alike quest
    ("Make a Slime & Octopus Omok Set"): the best-read ones stay, in their order on screen."""
    if tracked is None or len(quests) <= tracked:
        return quests
    keep = sorted(quests, key=lambda q: -q["score"])[:tracked]
    return [q for q in quests if any(q is k for k in keep)]


def _helper_rows(rows, s, quests_by_name, names, active_ids):
    """The Quest Helper's rows read as quests with their counts: (quests, bottom of the last row)."""
    from rapidfuzz import fuzz
    quests, cur, bottom = [], None, None
    for text, _, ly, _, lh in rows:
        m = PROGRESS.match(_count_text(text))
        if m:
            bottom = ly + lh
            if cur is None:
                continue
            what = (m.group(2) or "").strip(" .")
            reqs = cur["reqs"]
            # whole-name similarity first, so "Blue Snail Shell" doesn't count as "Snail Shell"
            score = {r: max(fuzz.ratio(what, r), 0.9 * fuzz.partial_ratio(what, r)) for r in reqs} if what else {}
            # each count shows once per quest: a line that looks most like a count already read is the
            # look-alike next to it ("Omok Piece: Pig", "Omok Piece: Octopus"), not a repeat
            taken = {n["what"] for n in cur["needs"]}
            best = next(((r,) for r in sorted(score, key=score.get, reverse=True)
                         if r not in taken and score[r] >= 60), None)
            need = reqs[best[0]] if best else None
            have = _have(m.group(1), need)
            if have is not None and best:
                cur["needs"].append({"what": best[0], "have": have, "need": need})
            continue
        hit = match_quest(text, names)
        if hit:
            bottom = ly + lh
            q = quests_by_name[hit]
            cur = {"quest": hit, "id": str(q["id"]), "needs": [],
                   "score": fuzz.WRatio(text, hit) + (10 if str(q["id"]) in active_ids else 0),
                   "reqs": {r["name"]: r["count"] for r in q.get("requirements_list") or []
                            if r.get("type") in ("item", "mob") and r.get("count")}}
            quests.append(cur)
        elif not text.lstrip()[:1].isdigit():
            cur = None    # a title we couldn't place: skip its counts rather than pin them on another quest
    return quests, bottom


def read_hud(frame, t, s, job_names):
    from rapidfuzz import fuzz, process
    x, y = t[1], t[2]
    job = None
    for text, *_ in read_box(frame, (x + 95 * s, y - 12 * s, x + 300 * s, y + 40 * s), s):
        hit = process.extractOne(text, job_names + list(JOB_ALIASES), scorer=fuzz.ratio, score_cutoff=85)
        if hit and job is None:
            job = JOB_ALIASES.get(hit[0], hit[0])
    return {"job": job}


def title_lines(lines):
    """(street, name) of a mini map title read as OCR lines, sorted top to bottom. OCR can give one
    row as two pieces ("Kerning" | "City") and the one a pixel lower sorts last, so the name is
    every piece on the last row, left to right; the street is the row above it."""
    if not lines:
        return None, None
    rows = []
    for ln in sorted(lines, key=lambda ln: ln[2] + ln[4] / 2):
        mid = ln[2] + ln[4] / 2
        if rows and abs(mid - rows[-1][0]) <= max(ln[4], rows[-1][1][0][4]) / 2:
            rows[-1][1].append(ln)
        else:
            rows.append((mid, [ln]))
    text = [" ".join(p[0] for p in sorted(row, key=lambda p: p[1])) for _, row in rows]
    return (text[-2] if len(text) > 1 else None), text[-1]


def read_minimap(lines, frame, s, map_names, streets=None):
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
        street, name, _, last = read_title(frame, box, s, map_names, streets)
        if street is None:
            continue
        score = fuzz.ratio(fix_numeral(last), name) if name else 0
        if name and (best is None or score > best[0]):
            best = (score, street, name, [round(v) for v in box])
    if best:
        return best[1], best[2], best[3], False
    return read_minimap_bar(lines, frame, s, map_names, streets)


def _text_box(lines, s, left=24, right=40, below=5):
    """The box minimap_window and the route strip place things by: the text's box, widened by the
    emblem's room on the left and the buttons' room on the right (at the 1200 px UI size)."""
    return [round(min(ln[1] for ln in lines) - left * s), round(lines[0][2] - 4 * s),
            round(max(ln[1] + ln[3] for ln in lines) + right * s), round(lines[-1][2] + lines[-1][4] + below * s)]


MISSED = {"text": None}   # the last mini map title read close up that named no map (for the log)


def title_map(street, last, map_names, streets=None):
    """The map a mini map title names: its last row matched to the game's maps. `streets` maps each
    map name that is also a street's name to that map's own street. Such a name counts only under
    its own street: "Victoria Road", the street of most of Victoria Island, is one map's name in the
    data too, and the street line read alone (or under the "MINI MAP" title, by the 1x fallback)
    moved you there every few seconds (2026-11-09, East Rocky Mountain VI)."""
    from rapidfuzz import fuzz
    name = match_place(last, map_names, 86)
    if name and streets and name in streets:
        own = streets[name]
        if not street or not own or fuzz.ratio(street.lower(), own.lower()) < 80:
            return None
    return name


TITLE_PREPS = ("white", "bright", None)


def read_title(frame, box, s, map_names, streets=None, split=title_lines):
    """(street, map name, lines, last row) of a mini map title in `box`, read close up from more than
    one picture of it (see ink): the map two of them agree on, else the one read closest to its
    map's name. A misread rarely comes out the same twice, and each picture misses different
    things. The street is the one most pictures read. `split` turns the lines into (street, last row). All None but the last row if none
    names a map."""
    from collections import Counter

    from rapidfuzz import fuzz
    got, last_text, streets_read = {}, None, Counter()
    for prep in TITLE_PREPS:
        lines = read_box(frame, box, s, prep=prep)
        street, last = split(lines)
        if street:
            streets_read[street] += 1
        if last and last_text is None:
            last_text = last
        name = title_map(street, last, map_names, streets) if last else None
        if not name:
            continue
        score = fuzz.ratio(fix_numeral(last), name)
        votes = got.setdefault(name, [0, 0, street, lines, last])
        votes[0] += 1
        votes[1] = max(votes[1], score)
        if votes[0] >= 2:
            break
    if not got:
        return None, None, None, last_text
    name, (_, _, street, lines, last) = max(got.items(), key=lambda kv: (kv[1][0], kv[1][1]))
    # the street as most pictures read it: the one that made out the map's name can garble it
    if streets_read and streets_read.most_common(1)[0][1] > streets_read[street]:
        street = streets_read.most_common(1)[0][0]
    return street, name, lines, last


def read_minimap_at(frame, title, s, map_names, buttons=None, streets=()):
    """(street, map name, title box, False) of the open mini map whose "MINI MAP" title (found by
    its picture) is `title`: its two lines under the title, read close up. The window's own
    "– + WORLD" buttons, when found, mark its right edge (8 px past them), so a window beside the
    mini map isn't read with it. All None if the lines don't name a map."""
    x, y = title[1], title[2]
    right = buttons[1] + buttons[3] + 8 * s if buttons and abs(buttons[2] - y) < 20 * s else x + 340 * s
    street, name, lines, last = read_title(frame, (x + 60 * s, y + 24 * s, right, y + 82 * s), s, map_names, streets)
    if not name:
        MISSED["text"] = last
        return None, None, None, None
    return street, name, _text_box(lines, s), False


BAR_SPLIT = re.compile(r"\s*[:•·]\s*")


def read_minibar_at(frame, buttons, s, map_names, streets=None):
    """(street, map name, bar box, True) of the collapsed mini map, from the bar's text left of its
    "– + WORLD" buttons (found by their picture), read close up. All None if it names no map."""
    bx, by, _, bh = buttons[1:]
    street, name, lines, last = read_title(frame, (bx - 470 * s, by - 4 * s, bx, by + bh + 4 * s), s, map_names,
                                           streets, split=bar_parts)
    if not name:
        MISSED["text"] = last
        return None, None, None, None
    return street, name, _text_box(lines, s, 0, 0, 0), True


def bar_parts(lines):
    """(street, map) of the collapsed mini map's bar, "Victoria Road : Lith Harbor", read as lines."""
    parts = BAR_SPLIT.split(" : ".join(ln[0] for ln in lines), maxsplit=1)
    if len(parts) < 2:
        return None, (parts[0].strip() or None) if parts else None
    return parts[0].strip(), parts[1].strip()


def read_minimap_bar(lines, frame, s, map_names, streets=None):
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
        hit = title_map(parts[0].strip(), parts[1], map_names, streets)
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
    dark-blue line down each side. Of every long line near it, the two sides are the pair that ends
    on the same row, one left and one right of the title: the map's emblem, a rope in the map, or
    the border of a window beside it (the Quest Helper's is blue too) won't pair up that way.
    None if the frame isn't there."""
    px = frame.load()
    l, t, r, b = title                                    # the title's box: 24 px left, 40 px right of its text
    text_l, text_r = l + 24 * s, r - 40 * s
    y = int(b + 12 * s)                                   # inside the window, under the title
    if y >= frame.height:
        return None
    # only columns that run on down count: with a long map name the title box is taller, and this
    # row can fall on the frame's line across, which is the same blue from one side to the other
    lines = []                                            # a line is a few columns wide: one per line
    for x in range(max(1, int(l - 140 * s)), min(frame.width - 1, int(r + 160 * s))):
        if _frame_line(px[x, y]) and (end := _line_end(px, x, y, frame.height)) - y >= 60 * s:
            if lines and x - lines[-1][-1][0] <= 2:
                lines[-1].append((x, end))
            else:
                lines.append([(x, end)])
    sides = [cols[len(cols) // 2] for cols in lines]
    best = None
    for lx, le in sides:
        if lx > text_l:
            continue
        for rx, rend in sides:
            if rx < text_r or abs(le - rend) > 4 * s:
                continue
            if best is None or rx - lx < best[1] - best[0]:
                best = (lx, rx, max(le, rend))
    if not best:
        return None
    return [best[0], round(t - 30 * s), best[1], best[2]]


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


def match_item(text, names):
    """The item a shop row names. A name the list cuts short ("Hat Accuracy Scroll: Inter...") is
    matched by its start, and only when one item starts so: a whole-name best match picks the
    wrong grade ("…: Greater"). None rather than a guess."""
    from rapidfuzz import fuzz, process
    cut = text.rstrip(".… ")
    if text.rstrip().endswith(("..", "…")) and len(cut) >= 4:
        low = cut.lower()[:-1]
        hits = [n for n in names if n.lower().startswith(low)]
        return hits[0] if len(hits) == 1 else None
    hit = process.extractOne(text, names, scorer=fuzz.ratio, score_cutoff=80)
    return hit[0] if hit else None


NPC_PRICE = re.compile(r"^\W{0,3}\d[\d,]*\s*Mesos\s*$", re.I)    # an NPC shop's row: "50 Mesos"


def read_shop(frame, t, s, item_names):
    """A player shop: the seller and each listed item with its price. Rows show the item's name
    with "<count> for <price> mesos" under it; sold-out rows are grayed out."""
    x, y = t[1], t[2]          # the LEAVE STORE button
    box = left, top, right, bottom = x - 168 * s, y + 60 * s, x + 92 * s, y + 440 * s
    rows = lambda lines: [ln for ln in lines if abs(ln[1] - (x - 164 * s)) < 12 * s]   # not item tooltips
    lines = read_box(frame, box, s)
    items = _shop_items(rows(lines), frame, s, top, item_names)
    # an NPC's store has the same LEAVE STORE and BUY ITEM buttons, but no SELLER INFO above them,
    # and rows priced "50 Mesos" (a dialog over the list can hide those)
    kind = "player"
    if not items:
        from rapidfuzz import fuzz
        w, h = t[3], t[4]
        above = read_box(frame, (x - 12 * s, y - 88 * s, x + w + 12 * s, y - 80 * s + h + 8 * s), s)
        seller_info = any(fuzz.partial_ratio("SELLER INFO", re.sub(r"[^A-Za-z ]", "", ln[0]).upper()) >= 80
                          and len(ln[0]) >= 4 for ln in above)
        if not seller_info or sum(bool(NPC_PRICE.match(ln[0])) for ln in lines) >= 2:
            kind = "npc"
    if not items and kind == "player":   # nothing read at once: try again a few rows at a time
        items = _shop_items(rows(read_banded(frame, box, s)), frame, s, top, item_names)
    seller = read_box(frame, (x - 205 * s, y + 24 * s, x - 90 * s, y + 50 * s), s)
    return {"kind": kind, "seller": seller[0][0] if seller else None, "items": items,
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
        hit = match_item(name_line[0].replace("VV", "W"), item_names)
        if not count or not price or not hit:
            continue
        # sold-out rows are drawn in light gray: no dark pixels in their name
        nx, ny, nw, nh = name_line[1:]
        dark = ImageOps.grayscale(frame.crop((int(nx), int(ny), int(nx + nw), int(ny + nh)))).getextrema()[0]
        items.append({"name": hit, "count": count, "price": price, "unit": price / count,
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
        self.exp_digits = ExpDigits()   # the HUD's EXP digit shapes
        self.titles = Titles(APP_DIR, RES_DIR)   # windows found by their title picture
        self.map_titles = {}      # the mini map's title or collapsed bar, found by picture
        self.reads = 0
        self.last_glyphs = None   # the HUD level's digit shapes in the last read, to learn once it's sure
        self.active_ids = set()  # quests the profile has in progress (set by the app), for the Quest Helper
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
        streets = {m["street_name"].strip() for m in data.maps.values() if m.get("street_name")}
        # map names that are also streets, with each one's own street (title_map)
        self.street_names = {m["name"].strip(): (m.get("street_name") or "").strip() for m in data.maps.values()
                             if m.get("name") and m["name"].strip() in streets}
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
        self.line_names = sorted(getattr(self.data, "chains", {}))

    def start_read(self):
        """What a read keeps for afterwards starts empty: digit shapes of an older read are not this one's."""
        self.last_glyphs = None

    def learn_level(self, level):
        """Learn the last read's HUD digit shapes as `level`, once the app is sure of it."""
        if self.last_glyphs:
            self.digits.learn(self.last_glyphs, level)

    def place_by_picture(self, frame, s, wins):
        """Put each window OCR found (or saw last time) exactly where its title picture is: OCR's own
        box can be a few pixels off, and every field read from the window would shift with it. The
        mini map, which OCR can't find, is looked for over the whole frame every third read while
        its place isn't known. A title OCR read cleanly that its picture didn't match is learned as
        the game draws it at this size."""
        from rapidfuzz import fuzz
        self.reads += 1
        hints = {k: v for k, v in wins.items() if k in self.titles.boxes}
        full = {n for n in ("minimap", "minibar") if n not in self.titles.last} if self.reads % 3 == 1 else set()
        found = self.titles.find(frame, s, hints, full)
        self.map_titles = {k: found.pop(k) for k in ("minimap", "minibar") if k in found}
        wins.update(found)
        for k, line in hints.items():
            clean = re.sub(r"[^A-Za-z ]", "", line[0]).strip().upper()
            want = self.titles.boxes[k]["text"].rstrip(" (")
            if k not in found and fuzz.ratio(clean[:len(want)], want) >= 90 and clean.startswith(want[:3])                     and not (self.titles.learned / str(frame.height) / f"{k}.png").exists():
                self.titles.learn(frame, k, line)

    def read(self, frame):
        """Everything visible in one frame of the game area, plus where each window is."""
        s = frame.height / REF_HEIGHT
        self.start_read()
        lines = ocr(frame)
        wins = find_windows(lines, frame.height)
        self.place_by_picture(frame, s, wins)
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
        glyphs = exp_g = None
        if "hud" in wins:
            seen["hud"] = read_hud(frame, wins["hud"], s, self.job_names)
            glyphs = self.last_glyphs = level_glyphs(frame, wins["hud"])
            lv, exact = self.digits.read(glyphs)
            seen["hud"].update(level=lv, level_exact=exact)
            exp_g = exp_glyphs(frame, wins["hud"])
            got = self.exp_digits.read(exp_g)
            if got:
                seen["hud"].update(exp=got["exp"], exp_pct=got["pct"])
        done = quest_completed(lines, s, self.quest_names)
        if done:
            seen["quest_complete"] = done
        self._read_map(frame, s, self.map_titles, seen, lines)
        tips = read_tooltips(lines, frame, s, self.item_names, self.tip_skip(frame))
        if tips:
            seen["tooltips"] = tips
        if "stat" in wins:
            seen["stat"] = read_stat(frame, wins["stat"], s, self.job_names)
            lv = seen["stat"].get("level")
            if glyphs and lv and len(str(lv)) == len(glyphs):    # both agree on the digit count
                seen["hud"].update(level=lv, level_exact=True)
            st = seen["stat"]
            if exp_g and st.get("exp") is not None and seen["hud"].get("exp") in (None, st["exp"]):
                # CHARACTER STAT's EXP is the HUD's, in the same frame: learn the HUD's digit shapes
                if self.exp_digits.learn(exp_g, st["exp"], st.get("exp_pct")) and (got := self.exp_digits.read(exp_g)):
                    seen["hud"].update(exp=got["exp"], exp_pct=got["pct"])
        if "inventory" in wins:
            seen["inventory"] = read_inventory(frame, wins["inventory"], s)
        if "skills" in wins:
            seen["skills"] = read_skills(frame, wins["skills"], s, self.skill_names)
        if "quest" in wins:
            seen["quest"] = read_quest_window(frame, wins["quest"], s, self.quest_names, self.line_names)
            if seen["quest"] is None:
                del seen["quest"], wins["quest"], seen["windows"]["quest"]
                self.kept.pop("quest", None)
        if "helper" in wins:
            seen["helper"] = read_helper(frame, wins["helper"], s, self.quests_by_name, self.active_ids)
            bottom = seen["helper"].pop("bottom")
            if bottom is not None:      # kept while a read makes out none of its lines
                self.helper_depth = (bottom - wins["helper"][2]) / s
        if "shop" in wins:
            shop = read_shop(frame, wins["shop"], s, self.item_names)
            if shop["kind"] == "player":     # an NPC's store has nothing to price
                seen["shop"] = shop
                seen["shop"]["anchor"] = list(wins["shop"])
            else:
                seen["windows"].pop("shop", None)
        if "myshop" in wins and orange_buttons(frame, wins["myshop"]) == 1:
            seen["myshop"] = self.read_my_shop_at(frame, wins["myshop"], wins.get("mysales"))
        else:
            seen["windows"].pop("myshop", None)
        seen["windows"].pop("mysales", None)
        return seen

    def _read_map(self, frame, s, mt, seen, lines=None):
        """The mini map, by its title picture (`mt`: title -> its line), read close up: open, by its
        title (its buttons look like the collapsed bar's, so the bar counts only when there's no open
        mini map); else, given the frame's OCR `lines`, as OCR saw it. Into seen["map"], or the title
        that named no map into seen["map_missed"]."""
        street = name = None
        MISSED["text"] = None
        if "minimap" in mt:
            street, name, title, collapsed = read_minimap_at(frame, mt["minimap"], s, self.map_names, mt.get("minibar"),
                                                             self.street_names)
        elif "minibar" in mt:
            street, name, title, collapsed = read_minibar_at(frame, mt["minibar"], s, self.map_names, self.street_names)
        if not name and lines is not None:
            street, name, title, collapsed = read_minimap([ln for ln in lines if ln[2] < frame.height * 0.9], frame,
                                                          s, self.map_names, self.street_names)
        if not name and MISSED["text"]:
            seen["map_missed"] = MISSED["text"]
        if name:
            seen["map"] = {"street": street, "name": name, "title": title, "collapsed": collapsed,
                           "window": None if collapsed else minimap_window(frame, title, s)}

    def read_map_only(self, frame):
        """The quick look between full reads: just the mini map, around where its title was last
        found by its picture, read close up (about 50 ms against a full read's 500). None while its
        place isn't known: the next full read looks for it."""
        if not {"minimap", "minibar"} & set(self.titles.last):
            return None
        s = frame.height / REF_HEIGHT
        mt = self.titles.find(frame, s, None, set(), names=("minimap", "minibar"))
        seen = {"scale": round(s, 3), "quick": True, "map_only": True, "windows": {}}
        if mt:
            self._read_map(frame, s, mt, seen)
        return seen

    def read_my_shop_at(self, frame, line, panel_line=None):
        """Your own store, plus its SOLD ITEMS panel when that's open."""
        mine = read_my_shop(frame, line, self.item_names)
        mine["anchor"] = list(line)
        mine["panel"] = read_sales_panel(frame, panel_line, self.item_names) if panel_line else None
        mine["panel_anchor"] = list(panel_line) if panel_line else None
        return mine

    def read_my_shop_only(self, frame, anchor, panel_anchor=None):
        """The slow look while your own store is open: just the store and its SOLD ITEMS panel."""
        if not my_shop_still_open(frame, anchor) or orange_buttons(frame, anchor) != 1:
            return None
        panel = panel_anchor
        if panel:
            u = panel[3] / SALES_WIDTH
            near = read_box(frame, (panel[1] - 12 * u, panel[2] - 8 * u, panel[1] + panel[3] + 12 * u,
                                    panel[2] + panel[4] + 8 * u), u)
            panel = panel if any(my_shop_line(t) == "mysales" for t, *_ in near) else None
        if not panel:
            panel = find_sales_panel(frame, anchor)     # opened since, or moved down a row after a sale
        s = frame.height / REF_HEIGHT
        return {"myshop": self.read_my_shop_at(frame, tuple(anchor), tuple(panel) if panel else None),
                "scale": round(s, 3), "quick": True,
                "windows": {"myshop": [round(anchor[1] / frame.width, 4), round(anchor[2] / frame.height, 4)]}}

    def read_shop_only(self, frame, anchor):
        """The quick look while a shop is open: just its item list, about a fifth of a full read."""
        s = frame.height / REF_HEIGHT
        if not shop_still_open(frame, anchor, s):
            return None
        shop = read_shop(frame, anchor, s, self.item_names)
        if shop["kind"] != "player":
            return None
        shop["anchor"] = list(anchor)
        return {"shop": shop, "scale": round(s, 3), "quick": True,
                "windows": {"shop": [round(anchor[1] / frame.width, 4), round(anchor[2] / frame.height, 4)]}}
