"""
The game's bottom-right corner lines, as events for the grind session:
    You received EXP (+46)              -> ("exp", 46)       (kills come from the HUD's EXP instead)
    Bonus EXP for PARTY (+3)            -> ("party", 3)
    You have gained mesos (+59)         -> ("mesos", 59)
    Wild Boar Tooth x1 earned. (Etc)    -> ("item", "Wild Boar Tooth", 1)

How they're read (worked out 2026-11-14 on 240 frames of play, see tools/check_corner.py):
- On the game's own pixels (native.py) the lines are Arial 12 px drawn by Windows without smoothing,
  in white (yellow for a party's EXP), with a dark shadow one pixel down and right. So a line is known
  exactly from its text: tools/make_corner_font.py keeps each character's picture.
- Every pixel of a letter is brighter than its shadow pixel, whatever the map behind. A candidate
  line scores how many of its letter pixels are; the best candidate is the line. The line's end is
  always the same spot, so each character's place follows from the ones after it: read right to
  left, the number in brackets, then the words before it. An item's name is every game item's name
  tried at once (cut short with "..." too, as the game does long ones); a line that is none of the
  four kinds, or names no known item, isn't counted.
- Lines stack up, newest at the bottom, 14 px apart, fading out in 2-3 s; a new line pushes the
  others up a row. Each look lines the rows up with the last look's lines (the same text, a row or
  more up, and no brighter: lines only fade), and only lines new at the bottom count.
"""
import json
from collections import namedtuple

import numpy as np

import native
from paths import RES_DIR

FONT_FILE = RES_DIR / "assets" / "corner_font.json"

# where the lines are, in the game's own pixels at 1228 x 768 (they keep to the bottom-right corner)
XR, Y0 = 1222, 603          # where every line ends; the newest line's top
PITCH, ROWS = 14, 7         # rows apart; rows looked at
WIDE = 260                  # the longest line's width
LINE, SURE = 0.8, 0.95      # a row has a line at this quality; it's read for sure at this one
NAME_OK = 0.85              # an item name agrees at least this well, or it's no known item
FORGET = 3.0                # seconds between looks after which the lines showing start afresh
CUTS = range(10, 21)        # the game shows a long item name's first this many characters, then "..."
SHIFTS = (0, -1, 1)         # where a size's lines may end, off the width - 6 rule, until one reads for sure

PREFIX = {"exp": "You received EXP (+", "party": "Bonus EXP for PARTY (+", "mesos": "You have gained mesos (+"}
TABS = ("Etc", "Use", "Equip", "Setup", "Set-up", "Install", "Cash")
DIGITS = "0123456789,"

Line = namedtuple("Line", "kind n name names text quality contrast")


class Font:
    """The corner lines' font: each character's picture (15 px tall) and width."""

    def __init__(self, raw=None):
        raw = raw or json.loads(FONT_FILE.read_text("utf-8"))
        self.height = raw["height"]
        self.glyphs = {}
        for c, (adv, x0, rows) in raw["glyphs"].items():
            m = np.array([[ch == "#" for ch in r] for r in rows], bool).reshape(self.height, -1)
            below = np.zeros_like(m)
            below[:-1, :-1] = m[1:, 1:]
            ys, xs = np.nonzero(m & ~below)           # letter pixels whose shadow pixel shows
            self.glyphs[c] = (adv, x0, m, ys, xs + x0)

        self._laid = {}

    def width(self, text):
        return sum(self.glyphs[c][0] for c in text)

    def laid_out(self, text):
        """The letter pixels (rows, columns) whose shadow shows, of text ending at column 0."""
        got = self._laid.get(text)
        if got is None:
            ys, xs, x = [], [], -self.width(text)
            for c in text:
                adv, _, _, gy, gx = self.glyphs[c]
                ys.append(gy)
                xs.append(gx + x)
                x += adv
            got = self._laid[text] = (np.concatenate(ys) if ys else np.zeros(0, int),
                                      np.concatenate(xs) if xs else np.zeros(0, int))
        return got

    def mask(self, text, pad=0):
        """The line's letter pixels, the text starting `pad` pixels in."""
        out = np.zeros((self.height, self.width(text) + 2 * pad), bool)
        x = pad
        for c in text:
            adv, x0, m, _, _ = self.glyphs[c]
            lo, hi = x + x0, x + x0 + m.shape[1]
            a, b = max(lo, 0), min(hi, out.shape[1])
            if b > a:
                out[:, a:b] |= m[:, a - lo:b - lo]
            x += adv
        return out


class Names:
    """Every item name, laid out for scoring them all at once at one spot of a line."""

    def __init__(self, names, font):
        names = sorted({n for n in names if n and all(c in font.glyphs for c in n)})
        self.names = names
        chars = sorted({c for n in names for c in n})
        self.chars = chars
        idx = {c: i for i, c in enumerate(chars)}
        longest = max((len(n) for n in names), default=1)
        self.ci = np.full((len(names), longest), -1, np.int32)        # each name's characters
        self.at = np.zeros((len(names), longest + 1), np.int32)      # where each starts; [len]: width
        self.lens = np.array([len(n) for n in names], np.int32)
        for i, n in enumerate(names):
            x = 0
            for j, c in enumerate(n):
                self.ci[i, j], self.at[i, j] = idx[c], x
                x += font.glyphs[c][0]
            self.at[i, len(n):] = x


class _Row:
    """One row's evidence: for each pixel, how much it looks like a letter pixel over its shadow."""

    def __init__(self, lum, y, contrast=None):
        h = lum.shape[0]
        self.y = y
        band = np.full((16, lum.shape[1]), -1.0, np.float32)
        top, bot = max(y, 0), min(y + 16, h - 1)
        if bot > top:
            d = lum[top:bot, :-1] - lum[top + 1:bot + 1, 1:]
            if contrast:                  # tuned to this line's own brightness over its shadow
                ev = np.clip((d - 0.45 * contrast) / (0.25 * contrast), -1, 1)
            else:
                ev = np.clip((d - 25) / 40, -1, 1)
            band[top - y:bot - y, :-1] = ev
        self.ev = band

    def char(self, font, c, x):
        """(score, pixels) of character c whose box starts at column x."""
        _, _, _, ys, xs = font.glyphs[c]
        xs = xs + x
        ok = (xs >= 0) & (xs < self.ev.shape[1])
        return float(self.ev[ys[ok], xs[ok]].sum()) - float((~ok).sum()), len(ys)

    def text(self, font, s, xr):
        """(score, pixels, where it starts) of text s ending at column xr."""
        ys, xs = font.laid_out(s)
        xs = xs + xr
        ok = (xs >= 0) & (xs < self.ev.shape[1])
        return float(self.ev[ys[ok], xs[ok]].sum()) - float((~ok).sum()), len(ys), xr - font.width(s)

    def busy(self, lo, hi):
        """How many pixels between columns lo and hi look like a letter over its shadow."""
        return int((self.ev[:, max(lo, 0):max(hi, 0)] > 0.5).sum())

    def table(self, font, chars, lo, hi):
        """Every character's score at every column lo..hi-1: (len(chars), hi - lo)."""
        out = np.full((len(chars), max(hi - lo, 0)), -50.0, np.float32)
        cols = np.arange(lo, hi)
        for i, c in enumerate(chars):
            _, _, _, ys, xs = font.glyphs[c]
            if not len(ys):
                out[i] = 0
                continue
            x = xs[:, None] + cols[None, :]
            ok = (x >= 0) & (x < self.ev.shape[1])
            v = np.where(ok, self.ev[ys[:, None], np.clip(x, 0, self.ev.shape[1] - 1)], -1.0)
            out[i] = v.sum(0)
        return out


def _numbers(row, font, xr, sure=0.8, most=9):
    """Every run of digits that could end at xr: (text, score, pixels, where it starts)."""
    out = []

    def grow(x, txt, tot, n):
        if txt and txt[0] != ",":
            out.append((txt, tot, n, x))
        if len(txt) >= most:
            return
        fits = []
        for c in DIGITS:
            a, b = row.char(font, c, x - font.glyphs[c][0])
            if b and a / b >= sure:
                fits.append((a, b, c))
        for a, b, c in sorted(fits, reverse=True)[:2]:
            grow(x - font.glyphs[c][0], c + txt, tot + a, n + b)

    grow(xr, "", 0.0, 0)
    return out


def _name(row, font, names, xr):
    """The item name best ending at column xr: (score, pixels, shown text, [full names]) or None."""
    if not names.names:
        return None
    lo = xr - int(names.at[:, -1].max()) - 2
    tab = row.table(font, names.chars, lo, xr)
    pix = np.array([len(font.glyphs[c][3]) for c in names.chars] + [0], np.int32)

    def score(ends_at, k):
        """Every name's first k characters (k: per name) laid out to end at ends_at."""
        j = np.arange(names.ci.shape[1])[None, :]
        use = j < k[:, None]
        start = ends_at - names.at[np.arange(len(k)), k]
        col = np.clip(start[:, None] + names.at[:, :-1] - lo, 0, tab.shape[1] - 1)
        ci = np.where(use, names.ci, 0)
        s = np.where(use, tab[ci, col], 0).sum(1)
        n = np.where(use, pix[ci], 0).sum(1)
        return s, n

    s, n = score(xr, names.lens)
    best = int(np.argmax(s))
    found = (float(s[best]), int(n[best]), names.names[best], [names.names[best]])
    dots, dn, x_dots = row.text(font, "...", xr)
    if dn and dots / dn >= 0.6:
        for k in CUTS:
            longer = names.lens > k
            if not longer.any():
                continue
            s, n = score(x_dots, np.where(longer, k, names.lens))
            s = np.where(longer, s + dots, -1e9)
            i = int(np.argmax(s))
            if s[i] > found[0]:
                shown = names.names[i][:k]
                full = [nm for nm, ln in zip(names.names, names.lens) if ln > k and nm.startswith(shown)]
                found = (float(s[i]), int(n[i]) + dn, shown + "...", full)
    return found


def read_row(lum, y, font, names, xr, contrast=None):
    """The line on the row whose top is y, as a Line, or None."""
    row = _Row(lum, y, contrast)
    if row.busy(xr - 40, xr) < 25:          # not even the end of a line here
        return None
    cands = []
    a, b, x = row.text(font, ")", xr)
    for digits, ta, tb, x2 in _numbers(row, font, x):
        for kind, p in PREFIX.items():
            pa, pb, _ = row.text(font, p, x2)
            cands.append((a + ta + pa, b + tb + pb, kind, digits, None, [], p + digits + ")"))
    (ea, eb, x), tab = max((row.text(font, f" earned. ({t})", xr), t) for t in TABS)
    if eb and ea / eb > 0.6:
        for digits, ta, tb, x2 in _numbers(row, font, x):
            xa, xb, x3 = row.text(font, " x", x2)
            if xa / xb < 0.6:
                continue
            got = _name(row, font, names, x3)
            if got is None:
                continue
            na, nb, shown, full = got
            if na / max(nb, 1) < NAME_OK:
                cands.append((ea + ta + xa, eb + tb + xb + nb, "item", digits, None, [], None))
                continue
            cands.append((ea + ta + xa + na, eb + tb + xb + nb, "item", digits, shown, full,
                          f"{shown} x{digits} earned. ({tab})"))
    if not cands:
        return None
    tot, n, kind, digits, shown, full, text = max(cands, key=lambda c: c[0])
    q = tot / n
    if q < LINE:
        return None
    name = full[0] if len(full) == 1 else None
    return Line(kind, int(digits.replace(",", "")), name, full, text, q, _contrast(lum, y, font, text, xr))


def _contrast(lum, y, font, text, xr):
    """How much brighter the line's letters are than their shadows (it falls as the line fades)."""
    if not text:
        return 0.0
    m = font.mask(text)
    below = np.zeros_like(m)
    below[:-1, :-1] = m[1:, 1:]
    ys, xs = np.nonzero(m & ~below)
    ys, xs = ys + y, xs + xr - m.shape[1]
    ok = (ys >= 0) & (ys + 1 < lum.shape[0]) & (xs >= 0) & (xs + 1 < lum.shape[1])
    if not ok.any():
        return 0.0
    return float(np.median(lum[ys[ok], xs[ok]] - lum[ys[ok] + 1, xs[ok] + 1]))


def pick(line, prefer=()):
    """The item a line names: its one item, or of the items a cut-short name could be, the one this
    map drops; else the name as the game shows it."""
    if line.name:
        return line.name
    mine = [n for n in line.names if n in prefer]
    if len(mine) == 1:
        return mine[0]
    return line.text.split(" x", 1)[0] if line.text else None


def _event(line, prefer):
    if line.kind == "item":
        name = pick(line, prefer)
        return ("item", name, line.n) if name else None
    return (line.kind, line.n)


class Corner:
    """Reads the corner's lines and counts each new one once."""

    def __init__(self, font=None):
        self.font = font or Font()
        self.names = Names([], self.font)
        self.lines = []           # the lines last seen, newest first: dicts with text, contrast, done
        self.last = None          # when the last look was
        self.shift = {}           # the game's size -> how far its lines end off the width - 6 rule

    def set_names(self, names):
        self.names = Names(names, self.font)

    def _place(self, frame):
        view = native.view_of(frame)          # the game's picture: between black bars in full screen
        nw, nh = view.size
        xr, y0 = nw - (1228 - XR), nh - (768 - Y0)
        top = y0 - PITCH * (ROWS - 1) - 2
        lum, (x0, y0n) = view.lum((xr - WIDE - 1, top, nw, y0 + 17))
        return lum, xr - x0, [y0 - PITCH * k - y0n for k in range(ROWS)], view.size

    def _look(self, frame):
        """The rows read where this size's lines end: (lum, xr, ys, lines). The lines end at the
        game's width - 6 at 1228 and 1366 but at 1223 at 1230 (full screen between bars, measured
        2026-11-17), so until a line reads for sure a size tries a pixel either way too, and keeps
        to the place that read it."""
        lum, xr, ys, size = self._place(frame)
        known = self.shift.get(size)
        best = None
        for d in (known,) if known is not None else SHIFTS:
            cur = [self._read(lum, y, xr + d) for y in ys]
            sure = sum(1 for c in cur if c and c.quality >= SURE)
            if best is None or sure > best[0]:
                best = (sure, d, cur)
            if known is None and d == 0 and (sure or not any(_Row(lum, y).busy(xr - 42, xr + 2) >= 25 for y in ys)):
                break                         # read for sure where expected, or no line's end showing at all
        sure, d, cur = best
        if known is None and sure:
            self.shift[size] = d
        return lum, xr + d, ys, cur

    def read(self, frame):
        """Each row's line, newest (bottom) first: a Line, or None where none reads."""
        return self._look(frame)[3]

    def _read(self, lum, y, xr):
        first = read_row(lum, y, self.font, self.names, xr)
        if first and first.text and first.contrast >= 30:
            tuned = read_row(lum, y, self.font, self.names, xr, first.contrast)
            if tuned and tuned.quality >= 0.6:
                return tuned
        return first

    def step(self, frame, now, prefer=()):
        """The events from lines new since the last look, oldest first. At the first look (or after a
        long gap) the lines showing are only taken note of."""
        lum, xr, ys, cur = self._look(frame)
        fresh = self.last is None or now - self.last > FORGET
        self.last = now
        if fresh:
            self.lines = [{"text": c.text, "contrast": c.contrast, "line": c, "done": True} if c else None
                          for c in cur]
            while self.lines and self.lines[-1] is None:
                self.lines.pop()
            return []

        rows = [_Row(lum, y) for y in ys]

        def check(old, r):
            """+1: the old line is on row r; -1: another line is; 0: can't tell (faded, covered)."""
            if old is None or not old["text"]:
                return 0
            c = cur[r]
            if c and c.quality >= SURE:
                if c.text != old["text"]:
                    return -1
                return 1 if c.contrast <= old["contrast"] * 1.08 + 4 else -1
            a, b, _ = rows[r].text(self.font, old["text"], xr)
            if b and a / b >= 0.75:
                return 1 if _contrast(lum, ys[r], self.font, old["text"], xr) <= old["contrast"] * 1.08 + 4 else -1
            return 0

        best = None
        for s in range(ROWS + 1):
            score = -sum(1 for k in range(min(s, ROWS)) if cur[k] is None)       # a new line shows
            score += sum(check(old, j + s) for j, old in enumerate(self.lines) if j + s < ROWS)
            # above the lines already known there's nothing new: a line read for sure there is wrong
            score -= sum(1 for r in range(len(self.lines) + s, ROWS) if cur[r] and cur[r].quality >= SURE)
            if best is None or score > best[0]:
                best = (score, s)
        s = best[1]

        kept = []
        for j, old in enumerate(self.lines):
            r = j + s
            if r >= ROWS:
                break
            c = cur[r]
            if old is None:
                kept.append(None)
                continue
            if c and not old["done"] and (old["text"] is None or (c.text == old["text"] and c.quality > old["line"].quality)):
                old.update(text=c.text, line=c)
            if c and c.text == old["text"]:
                old["contrast"] = min(old["contrast"], c.contrast)
            elif not c and check(old, r) <= 0:
                break                     # faded away: it and every older line are gone
            kept.append(old)
        new = [{"text": c.text, "contrast": c.contrast, "line": c, "done": False} if c else
               {"text": None, "contrast": 1e9, "line": None, "done": False} for c in cur[:s]]
        self.lines = new + kept
        out = []
        for old in reversed(self.lines):              # oldest first
            if old and not old["done"] and old["line"] and old["line"].quality >= SURE:
                old["done"] = True
                ev = _event(old["line"], prefer)
                if ev:
                    out.append(ev)
        return out
