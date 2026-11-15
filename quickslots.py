"""
The quick slots: 12 keys in a 4 x 3 grid at the game's bottom right. Each Use item there shows how
many you have left at the slot's bottom left; a count going down is that many drunk.

Read on the game's own pixels (native.py), where the counts are the game's ItemNo digit pictures,
exact every time (measured 2026-11-15 on frames at 1920 x 1200): each count starts at a fixed spot
in its slot, a digit is 8 px on (a "1" 5 px), so it's read left to right by matching the pictures.
A skill's own number (the zero-job speed skill's charges) sits at the slot's top right and is never
read. An empty slot keeps its item's icon and shows 0.

A slot's item is told by its icon, at the game's own size: the game sets an icon's bottom on the
slot's row 31 and centres it on column 18 (measured on Blue Potion, Lemon, Pet Food and Orange
Potion), so each Use item's icon is tried there, a pixel either way. The key's name over the top left
and the count over the bottom left cover part of it: the real item still fits 0.64-0.68 of its
pixels, any other at most 0.33.
"""
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

import native
from paths import RES_DIR

DIGIT_DIR = RES_DIR / "assets" / "itemno"
ADV = {d: 5 if d == 1 else 8 for d in range(10)}     # how far the next digit starts
ROWS, COLS = 3, 4
CX, CY = 357, 153       # slot (0, 0)'s count from the game's right and bottom edges: x = NW - CX, y = NH - CY
PX, PY = 35, 34         # from one slot to the next
TOL, SHARE = 6, 0.85    # a digit fits when this share of its pixels is within TOL levels
MOST = 5                # digits in a count, at most
SX, SY = 358, 172       # slot (0, 0)'s top left from the game's right and bottom edges
CH, CW = 34, 36         # an icon's place: the slot's rows -2..31 and columns 0..35
FIT, BEATS = 0.5, 0.15  # an item is named when this share of its icon fits, this much better than any other
CLOSE = 30              # a pixel fits when its R, G and B are this close, summed
SHORT = 8               # icons tried a pixel off their place too
SAME = 4                # a slot whose top differs from its last look by less than this (mean) is the same


def count_spots(nsize):
    """[(slot, x, y)]: where each slot's count starts (its first digit's top left), in game pixels,
    slots numbered left to right, top to bottom, from 0."""
    nw, nh = nsize
    return [(r * COLS + c, nw - CX + PX * c, nh - CY + PY * r) for r in range(ROWS) for c in range(COLS)]


class Digits:
    """The game's ItemNo digits, and counts read with them."""

    def __init__(self):
        self.pics = []
        for d in range(10):
            a = np.asarray(Image.open(DIGIT_DIR / f"{d}.png").convert("RGBA"), np.float32)
            self.pics.append((d, a[..., :3] @ native.LUM, a[..., 3] >= 250))

    def _digit(self, L, x, y, reach=0):
        """The digit best fitting at (x, y), or up to reach px off it: (share, pixels, d, x, y), or None."""
        best = None
        for d, pic, op in self.pics:
            h, w = pic.shape
            y0, x0 = max(0, y - reach), max(0, x - reach)
            area = L[y0:y + reach + h, x0:x + reach + w]
            if area.shape[0] < h or area.shape[1] < w:
                continue
            wins = np.lib.stride_tricks.sliding_window_view(area, (h, w))      # every place at once
            share = ((np.abs(wins - pic) <= TOL) & op).sum((-1, -2)) / op.sum()
            i, j = np.unravel_index(int(share.argmax()), share.shape)
            cand = (float(share[i, j]), int(op.sum()), d, x0 + j, y0 + i)
            if cand[0] >= SHARE and (best is None or cand[:2] > best[:2]):
                best = cand
        return best

    def read(self, L, x, y):
        """The count whose first digit's top left is at (x, y) of L (game pixels), or None. The first
        digit may sit a pixel off; the rest follow it exactly."""
        first = self._digit(L, x, y, reach=1)
        if first is None:
            return None
        _, _, d, x, y = first
        text = str(d)
        x += ADV[d]
        while len(text) < MOST:
            nxt = self._digit(L, x, y)
            if nxt is None:
                break
            text += str(nxt[2])
            x += ADV[nxt[2]]
        return int(text)

    def read_all(self, frame):
        """Every slot's count, slot 0 to 11 (None where none is read), from a game frame."""
        size = native.native_size(*frame.size)
        spots = count_spots(size)
        xs, ys = [s[1] for s in spots], [s[2] for s in spots]
        nbox = (min(xs) - 2, min(ys) - 2, max(xs) + 8 * MOST + 2, max(ys) + 14)
        L, (ox, oy) = native.lum(frame, native.frame_box(frame.size, nbox))
        return [self.read(L, x - ox, y - oy) for _, x, y in spots]


def slot_origin(nsize, slot):
    """A slot's top left in game pixels."""
    nw, nh = nsize
    r, c = divmod(slot, COLS)
    return nw - SX + PX * c, nh - SY + PY * r


def icon_spot(nsize, slot, hw):
    """Where the game draws an icon of size (h, w) in a slot: its top left, in game pixels."""
    x, y = slot_origin(nsize, slot)
    h, w = hw
    return x + (CW - w) // 2, y + 31 - h


class Icons:
    """The Use items' icons, and a slot's item told by them. items: [(id, name)]; icon_path(id): the
    icon's file (downloaded if need be), or None. load() is slow the first time (downloads), so it
    runs on its own thread; until it's done nothing is named."""

    def __init__(self, items, icon_path):
        self.items, self.icon_path = list(items), icon_path
        self.ready = False
        self.last = {}          # slot -> (its top as last matched, the item named then)
        self.work = 0           # slots matched against every icon (the costly part), for the tests

    def load(self):
        names, pics, masks = [], [], []
        with ThreadPoolExecutor(16) as ex:                  # the first time, they're downloaded
            paths = list(ex.map(lambda it: self.icon_path(it[0]), self.items))
        for (iid, name), path in zip(self.items, paths):
            if path is None:
                continue
            try:
                a = np.asarray(Image.open(path).convert("RGBA"), np.float32)
            except OSError:
                continue
            h, w = a.shape[:2]
            canvas, mask = np.zeros((CH, CW, 3), np.float32), np.zeros((CH, CW), bool)
            top, left = CH - 1 - h, (CW - w) // 2                      # bottom on row 31 = canvas row 33
            ys, xs = slice(max(0, top), top + h), slice(max(0, left), min(CW, left + w))
            src = a[max(0, -top):, max(0, -left):][:ys.stop - ys.start, :xs.stop - xs.start]
            canvas[ys, xs], mask[ys, xs] = src[..., :3], src[..., 3] >= 250
            if mask.sum() >= 20:
                names.append(name)
                pics.append(canvas)
                masks.append(mask)
        self.names, self.pics, self.masks = names, np.array(pics), np.array(masks)
        self.counts = self.masks.sum((1, 2)) if len(names) else np.zeros(0)
        self.ready = True

    def _fit(self, win, dy, dx, which):
        """The share of each icon's pixels (those picked by which) fitting the slot moved by (dy, dx)."""
        w = win[1 + dy:1 + dy + CH, 1 + dx:1 + dx + CW]
        fits = (np.abs(self.pics[which] - w).sum(-1) <= CLOSE) & self.masks[which]
        return fits.sum((1, 2)) / self.counts[which]

    def name(self, win, slot=None):
        """The Use item in a slot, or None. win: the game's colours over the slot's rows -3..32 and
        columns -1..36 (one pixel more all round than an icon's place). A slot that looks as it did
        last time (above its count, which changes) keeps what it was named then."""
        if not self.ready or not len(self.names):
            return None
        top = win[:21]
        if slot in self.last and np.abs(self.last[slot][0] - top).mean() < SAME:
            return self.last[slot][1]
        self.work += 1
        best = self._fit(win, 0, 0, slice(None))                 # every icon at its place, then
        short = np.argsort(-best)[:SHORT]                         # the best few a pixel either way too
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    best[short] = np.maximum(best[short], self._fit(win, dy, dx, short))
        by_name = {}
        for n, v in zip(self.names, best):
            by_name[n] = max(v, by_name.get(n, 0))
        ranked = sorted(by_name.items(), key=lambda kv: -kv[1])
        first, second = ranked[0], (ranked[1] if len(ranked) > 1 else (None, 0))
        out = first[0] if first[1] >= FIT and first[1] - second[1] >= BEATS else None
        if slot is not None:
            self.last[slot] = (top.copy(), out)
        return out


def slot_names(icons, frame):
    """Each slot's Use item (None: not one, or not known), slot 0 to 11, from a game frame."""
    if not icons.ready:
        return [None] * (ROWS * COLS)
    size = native.native_size(*frame.size)
    spots = [slot_origin(size, s) for s in range(ROWS * COLS)]
    xs, ys = [p[0] for p in spots], [p[1] for p in spots]
    R, (ox, oy) = native.rgb(frame, native.frame_box(frame.size, (min(xs) - 2, min(ys) - 4, max(xs) + CW + 3, max(ys) + 34)))
    return [icons.name(R[y - 3 - oy:y + 33 - oy, x - 1 - ox:x + CW + 1 - ox], s) for s, (x, y) in enumerate(spots)]


MAX_DROP = 20       # a count falling more than this between two looks isn't counted (something covers a digit)


class QuickSlots:
    """Potions drunk from the quick slots: step(frame, now) -> [("used", name, n)], each counted once.

    Per slot: the first look sets a baseline (item, count). A new count counts once the next look
    reads it too; falling by 1..MAX_DROP is that many drunk, rising (a pickup) isn't counted. The
    item changing, or a look that can't read the slot, sets the baseline again: nothing is counted
    then, since a wrong count is worse than a missed one."""

    def __init__(self, icons, digits=None):
        self.icons, self.digits = icons, digits or Digits()
        self.base = {}          # slot -> (name, count)
        self.pending = {}       # slot -> a new count seen once

    def step(self, frame, now):
        if not self.icons.ready:
            self.base, self.pending = {}, {}
            return []
        counts, names = self.digits.read_all(frame), slot_names(self.icons, frame)
        out = []
        for slot, (name, n) in enumerate(zip(names, counts)):
            base = self.base.get(slot)
            if name is None or n is None or base is None or base[0] != name:
                self.base[slot] = (name, n) if name is not None and n is not None else None
                self.pending.pop(slot, None)
                continue
            if n == base[1]:
                self.pending.pop(slot, None)
            elif self.pending.get(slot) != n:
                self.pending[slot] = n
            else:
                del self.pending[slot]
                if 1 <= base[1] - n <= MAX_DROP:
                    out.append(("used", name, base[1] - n))
                self.base[slot] = (name, n)
        return out
