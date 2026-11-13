"""
The counts the game draws on an item slot (the inventory's slots, the quick slots): small digits in
the slot's bottom left, a dark outline with a light fill, the icon showing through their middle.

They're a pixel font drawn the same every time, so each digit is a template of which pixels are dark
(the outline) and which are light (the fill), the rest "don't care" (the icon behind). A count is
read left to right: the digit whose dark and light pixels agree best at the next place, until none
agrees well. Templates are learned from slots whose counts are known (tools/learn_slot_digits.py)
and kept in assets/slot_digits.json, at a 1200 px tall game.
"""
import json
from pathlib import Path

import numpy as np

DARK, LIGHT = 1, 2
TOP, ROWS = 30, 20           # the band of a 50 px slot the count is drawn in, from the slot's top
START = 4                    # how far right of the slot's left edge the first digit may start
GOOD = 0.72                  # a digit agrees at least this well (the game scales its 8 x 11 digits unevenly)
FILE = Path(__file__).resolve().parent / "assets" / "slot_digits.json"


def classes(rgb):
    """Each pixel's class: dark (the outline), light (the fill), or 0."""
    a = np.asarray(rgb, dtype=int)
    hi, lo = a.max(2), a.min(2)
    out = np.zeros(a.shape[:2], np.uint8)
    out[hi <= 70] = DARK
    # the fill is a neutral grey-white or a light blue; the slot behind is a warm beige (225,223,213)
    out[((lo >= 150) & (hi - lo <= 5)) | ((a[..., 2] >= 200) & (a[..., 2] - a[..., 0] >= 25))] = LIGHT
    return out


def band(slot_rgb):
    """The count's band of a slot picture (50 x 50 at the 1200 px size)."""
    return classes(np.asarray(slot_rgb)[TOP:TOP + ROWS])


def fit(cls, tpl, x):
    """(share of tpl's pixels found at column x, matches - 2 x mismatches) at its best row: the share
    says whether it's there at all, the count which of two digits that are both there is (a 3's
    pixels are all inside an 8: the 8 has more)."""
    h, w = tpl.shape
    if x < 0 or x + w > cls.shape[1]:
        return 0.0, -1e9
    care = tpl > 0
    n = int(care.sum())
    if not n:
        return 0.0, -1e9
    best = (0.0, -1e9)
    for y in range(0, cls.shape[0] - h + 1):
        m = int((cls[y:y + h, x:x + w][care] == tpl[care]).sum())
        best = max(best, (m / n, m - 2 * (n - m)))
    return best


def score(cls, tpl, x):
    """How well template tpl agrees with the band at column x: the share of its dark and light pixels
    found there (0 when it doesn't fit)."""
    h, w = tpl.shape
    if x < 0 or x + w > cls.shape[1]:
        return 0.0
    care = tpl > 0
    n = care.sum()
    if not n:
        return 0.0
    best = 0.0
    for y in range(0, cls.shape[0] - h + 1):          # the digits sit a row or two lower in some slots
        win = cls[y:y + h, x:x + w]
        best = max(best, float((win[care] == tpl[care]).sum() / n))
    return best


class Digits:
    def __init__(self, path=FILE):
        raw = json.loads(Path(path).read_text("utf-8")) if Path(path).exists() else {}
        self.tpl = {d: np.array(t, np.uint8) for d, t in raw.items()}

    def read(self, slot_rgb):
        """The count on a slot, or None when no digit is there (an equip shows none... or 1)."""
        if not self.tpl:
            return None
        cls = band(slot_rgb)
        lo, hi, out = 0, START, ""
        while len(out) < 4:
            best = (-1e9, None, None)
            for d, t in self.tpl.items():
                for xx in range(max(0, lo), hi + 1):
                    share, net = fit(cls, t, xx)
                    if share >= GOOD and net > best[0]:
                        best = (net, d, xx)
            if best[1] is None:
                break
            out += best[1]
            end = best[2] + self.tpl[best[1]].shape[1]
            lo, hi = end - 3, end + 1          # the next digit: right after, maybe sharing an edge
        return int(out) if out else None
