"""
The quick slots: 12 keys in a 4 x 3 grid at the game's bottom right. Each Use item there shows how
many you have left at the slot's bottom left; a count going down is that many drunk.

Read on the game's own pixels (native.py), where the counts are the game's ItemNo digit pictures,
exact every time (measured 2026-11-15 on frames at 1920 x 1200): each count starts at a fixed spot
in its slot, a digit is 8 px on (a "1" 5 px), so it's read left to right by matching the pictures.
A skill's own number (the zero-job speed skill's charges) sits at the slot's top right and is never
read. An empty slot keeps its item's icon and shows 0.
"""
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
