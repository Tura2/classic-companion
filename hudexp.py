"""
The HUD's EXP, "EXP 73,665 [60.01%]", right of the level.

The game draws it in a tiny pixel font that Windows OCR can't tell apart (6, 5 and S all read as
"s"), so it is read like the HUD level: each digit's shape is looked up among shapes known to be
that digit. Shapes seen in the game ship in assets/exp_digits.json; others are learned the first
time CHARACTER STAT (S) shows your EXP while the HUD shows the same number (cache/exp_digits.json).
A digit whose shape isn't known yet makes the whole read None: never a guess.

The text is found by its green brackets: "[" and "]" around the percent are the only thin
upright green strokes in the HUD (the EXP bar under them is green too, but wide).
"""
import json

from PIL import Image

from paths import APP_DIR, RES_DIR

LEARNED = APP_DIR / "cache" / "exp_digits.json"
SEEDS = RES_DIR / "assets" / "exp_digits.json"
MIN_GAP = 0.04         # ...and at least this much closer than to any other digit
MIN_SAME = 0.92          # a shape this close to a known one, of the same size, is that digit


def _green(p):
    return p[1] > p[0] + 40 and p[1] > 120 and p[1] > p[2]


def _light(p):
    return sum(p[:3]) / 3 > 140 and not _green(p)


def _bits(cols, rows, mask):
    """The ink of one glyph, cut to its own box, as "WxH:0101..."."""
    pts = [(x, y) for x in cols for y in rows if mask(x, y)]
    if not pts:
        return None, 0
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    bits = "".join("1" if mask(x, y) else "0" for y in range(y0, y1 + 1) for x in range(x0, x1 + 1))
    return f"{x1 - x0 + 1}x{y1 - y0 + 1}:{bits}", y1 - y0 + 1


def exp_glyphs(frame, lv_line):
    """{"num": [shape, ...], "pct": [shape or ".", ...]} for the EXP text, or None if its brackets
    aren't found. Separators (the comma, the decimal point) are "." in pct and left out of num."""
    _, lx, ly, lw, lh = lv_line
    l, t = int(lx + 10 * lh), max(0, int(ly - lh))
    r, b = min(frame.width, int(lx + 75 * lh)), min(frame.height, int(ly + 2 * lh))
    if r - l < 20 or b - t < 8:
        return None
    area = frame.crop((l, t, r, b)).convert("RGB")
    px, w, h = area.load(), area.width, area.height
    green = [[_green(px[x, y]) for y in range(h)] for x in range(w)]

    def thin(x, y):     # a green pixel of an upright stroke, not of the wide bar
        return green[x][y] and not (x >= 2 and green[x - 2][y] and x + 2 < w and green[x + 2][y])
    tall = [x for x in range(w) if sum(thin(x, y) for y in range(h)) >= max(4, 0.3 * lh)]
    runs, start = [], None
    for x in range(w + 1):
        if x < w and x in tall:
            start = x if start is None else start
        elif start is not None:
            runs.append((start, x - 1))
            start = None
    marks = []       # narrow upright strokes, with their top and bottom
    for a, z in runs:
        if z - a > 3:
            continue
        ys = [y for y in range(h) if any(thin(x, y) for x in range(a, z + 1))]
        end = ys[0]
        while end + 1 in ys:            # its top stretch only: the EXP bar can start right under "["
            end += 1
        marks.append((a, z, ys[0], end))
    # HP, MP and EXP each have a green "[" and "]" of the same height on one row: the largest group
    # of strokes sharing a top and bottom are those six, and EXP's are its rightmost two. (Green
    # in the game scene right of the HUD, and the EXP bar's fill edge, don't come in such a group.)
    groups = []
    for m in marks:
        if m[3] - m[2] + 1 < 0.3 * lh:
            continue
        for g in groups:
            if abs(g[0][2] - m[2]) <= 1 and abs(g[0][3] - m[3]) <= 1:
                g.append(m)
                break
        else:
            groups.append([m])
    best = max(groups, key=len, default=[])
    pair = None
    if len(best) >= 3:
        a, b = best[-2], best[-1]
        if b[0] - a[1] > 3 * (b[3] - b[2]):
            pair = (a, b)
    if not pair:
        return None
    (o0, o1, top, bottom), (c0, *_) = pair
    bh = bottom - top + 1
    u = bh / 9                          # the bracket is 9 px tall at the 1200 px UI size
    band = range(max(0, top - 1), min(h, bottom + 2))
    light = lambda x, y: _light(px[x, y])
    ink = [x for x in range(w) if any(light(x, y) for y in band)]

    def clusters(lo, hi):
        out, cur = [], []
        for x in range(lo, hi):
            if x in ink:
                cur.append(x)
            elif cur:
                out.append(cur)
                cur = []
        if cur:
            out.append(cur)
        return out
    left = clusters(0, o0)
    num, prev = [], None
    for cl in reversed(left):            # from the bracket leftwards, up to the gap before "EXP"
        # a narrow "1" next to a faint comma leaves a wide gap inside the number: stop only at a much
        # wider one; the "EXP" letters taken by then are dropped below by their height
        if prev is not None and prev - cl[-1] - 1 >= max(6, 8 * u + 0.5):
            break
        if len(cl) > 1.6 * (bottom - top + 1):
            break                        # far wider than a digit: the bold "EXP" letters run together
        num.insert(0, cl)
        prev = cl[0]
    pct = clusters(o1 + 1, c0)[:-1]      # the last one before "]" is "%"
    big = bh * 0.45

    def shapes(cls, keep_dots):
        out = []
        for cl in cls:
            key, gh = _bits(cl, band, light)
            if key is None:
                continue
            if gh < big:
                if keep_dots:
                    out.append(".")
                continue
            out.append(key)
        return out
    num = shapes(num, False)
    if num:
        # at a small UI the gap before "EXP" is no wider than one in the number: its letters are taller
        hs = sorted(int(k.split(":")[0].split("x")[1]) for k in num)
        mid = hs[len(hs) // 2]
        while num and int(num[0].split(":")[0].split("x")[1]) > mid:
            num.pop(0)
    return {"num": num, "pct": shapes(pct, True)}


def _likeness(a, b):
    """Share of pixels two shapes have alike, or None if they can't be compared: same height, widths
    at most one column apart (the same digit lands 7 or 8 px wide), the narrower slid left or right."""
    (sa, ba), (sb, bb) = a.split(":"), b.split(":")
    wa, ha = map(int, sa.split("x"))
    wb, hb = map(int, sb.split("x"))
    if ha != hb or abs(wa - wb) > 1:
        return None
    if wa == wb:
        return sum(x == y for x, y in zip(ba, bb)) / len(ba)
    if wa < wb:
        (wa, ba), (wb, bb) = (wb, bb), (wa, ba)
    rows_a = [ba[r * wa:(r + 1) * wa] for r in range(ha)]
    rows_b = [bb[r * wb:(r + 1) * wb] for r in range(ha)]
    out = 0
    for pad in (0, 1):
        wide = ["0" * pad + r + "0" * (1 - pad) for r in rows_b]
        out = max(out, sum(x == y for ra, rb in zip(rows_a, wide) for x, y in zip(ra, rb)) / (wa * ha))
    return out


class ExpDigits:
    """Digit shapes of the HUD's EXP font: shipped ones plus learned ones."""

    def __init__(self):
        self.known = {}
        for f in (SEEDS, LEARNED):
            try:
                self.known.update(json.loads(f.read_text("utf-8")))
            except (OSError, ValueError):
                pass

    def digit(self, key):
        """The digit a shape is: a known shape exactly, else the closest one of its size, but only when
        it's clearly closer to that digit than to any other (3 and 9, 8 and 9 differ by a few pixels)."""
        if key in self.known:
            return self.known[key]
        best = {}
        for k, v in self.known.items():
            same = _likeness(key, k)
            if same is not None:
                best[v] = max(best.get(v, 0), same)
        if not best:
            return None
        ranked = sorted(best.items(), key=lambda kv: -kv[1])
        d, top = ranked[0]
        runner = ranked[1][1] if len(ranked) > 1 else 0
        return d if top >= MIN_SAME and top - runner >= MIN_GAP else None

    def text(self, shapes):
        out = ""
        for k in shapes:
            if k == ".":
                out += "."
                continue
            d = self.digit(k)
            if d is None:
                return None
            out += d
        return out

    def read(self, glyphs):
        """{"exp": int, "pct": float} or None when a digit's shape isn't known."""
        if not glyphs or not glyphs["num"]:
            return None
        n, p = self.text(glyphs["num"]), self.text(glyphs["pct"])
        if not n or not p or p.count(".") != 1 or p.startswith(".") or p.endswith("."):
            return None
        pct = float(p)
        return {"exp": int(n), "pct": pct} if pct <= 100 else None

    def learn(self, glyphs, exp, pct_int=None, save=True):
        """Learn the shapes of an EXP known to be right (CHARACTER STAT's, in the same frame). A shape
        already known as another digit is forgotten, never remapped: one of the two reads was wrong."""
        if not glyphs:
            return False
        pairs = []
        if exp is not None and len(glyphs["num"]) == len(str(exp)):
            pairs += zip(glyphs["num"], str(exp))
        whole = glyphs["pct"][:glyphs["pct"].index(".")] if "." in glyphs["pct"] else []
        if pct_int is not None and whole and len(whole) == len(str(pct_int)):
            pairs += zip(whole, str(pct_int))
        changed = False
        for k, d in pairs:
            if k not in self.known:
                self.known[k], changed = d, True
            elif self.known[k] != d:
                del self.known[k]
                changed = True
        if changed and save:
            try:
                LEARNED.parent.mkdir(parents=True, exist_ok=True)
                LEARNED.write_text(json.dumps(self.known), "utf-8")
            except OSError:
                pass
        return changed
