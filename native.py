"""
The game's own pixels, from the window's picture.

MapleStory Classic draws everything at 768 px tall (1228 x 768 for a 1920 x 1200 window, 1366 x 768
for 16:9 ones) and the window shows that picture stretched, smoothly: each pixel of the frame is a
blend of the two or four game pixels nearest it (bilinear, pixel centres lined up). Measured
2026-11-14 on frames at 1920 x 1200, 1920 x 1080 and 2560 x 1440: undoing that stretch gives the game's
picture back to within rounding, anywhere in the frame (the map, the windows, the corner's lines).

The stretch is the same small sum for every row and column, so it's undone by least squares, one
matrix for the columns and one for the rows of the area wanted (kept per area: they don't change).
On the game's own pixels its fonts and digits are exact little pictures again, drawn the same way
every time, so they're told apart by matching, not by guessing like OCR.
"""
from functools import lru_cache

import numpy as np

NATIVE_H = 768
LUM = np.array([0.299, 0.587, 0.114], np.float32)


def native_size(w, h):
    """The game's own size for a game area of w x h: 768 tall, the width to the nearest even number
    (1920 x 1200 -> 1228, 1920 x 1080 and 2560 x 1440 -> 1366). Up to 768 tall it isn't stretched."""
    if h <= NATIVE_H:
        return w, h
    return 2 * round(w * NATIVE_H / h / 2), NATIVE_H


def _stretch(lo, hi, frame_len, native_len):
    """How frame pixels lo..hi-1 blend the game's pixels along one side: (matrix, first game pixel).
    Past the picture's edge the edge pixel is used again."""
    x = np.arange(lo, hi)
    u = (x + 0.5) * native_len / frame_len - 0.5
    i0 = np.floor(u).astype(int)
    f = u - i0
    left, right = np.clip(i0, 0, native_len - 1), np.clip(i0 + 1, 0, native_len - 1)
    first = int(left.min())
    a = np.zeros((len(x), int(right.max()) - first + 1))
    np.add.at(a, (np.arange(len(x)), left - first), 1 - f)
    np.add.at(a, (np.arange(len(x)), right - first), f)
    return a, first


BAND = 10       # each game pixel is worked out from the 2 x 10 + 1 frame pixels around it (off by < 0.1)


@lru_cache(maxsize=32)
def _undo(lo, hi, frame_len, native_len):
    """How to get game pixels back along one side: (frame pixels to use, their weights), each
    (game pixels, 2 * BAND + 1), and the first game pixel. The least-squares answer's weights fall
    off fast away from a pixel, so only the nearest ones are kept: plain sums, no matrix library
    (whose threads cost more than the sums for areas this small)."""
    a, first = _stretch(lo, hi, frame_len, native_len)
    p = np.linalg.pinv(a)
    n = p.shape[0]
    centre = np.rint((np.arange(first, first + n) + 0.5) * frame_len / native_len - 0.5).astype(int) - lo
    idx = centre[:, None] + np.arange(-BAND, BAND + 1)[None, :]
    ok = (idx >= 0) & (idx < hi - lo)
    idx = np.clip(idx, 0, hi - lo - 1)
    w = np.where(ok, p[np.arange(n)[:, None], idx], 0)
    return idx, w.astype(np.float32), first


def frame_box(size, nbox, margin=2):
    """The frame area (x0, y0, x1, y1) to un-stretch for the game area nbox (in game pixels), a few
    pixels bigger so the edges come back sharp."""
    w, h = size
    nw, nh = native_size(w, h)
    sx, sy = w / nw, h / nh
    x0, y0, x1, y1 = nbox
    return (max(0, int(x0 * sx) - margin), max(0, int(y0 * sy) - margin),
            min(w, int(np.ceil(x1 * sx)) + margin), min(h, int(np.ceil(y1 * sy)) + margin))


def _native(a, size, box):
    """Frame pixels a (rows, columns[, channels]) under box, back to the game's own: (array, (x, y))."""
    w, h = size
    nw, nh = native_size(w, h)
    x0, y0, x1, y1 = box
    if (nw, nh) == (w, h):
        return a, (x0, y0)
    ix, wx, fx = _undo(x0, x1, w, nw)
    iy, wy, fy = _undo(y0, y1, h, nh)
    if a.ndim == 3:
        wx, wy = wx[:, :, None], wy[:, :, None, None]
        a = (a[:, ix] * wx).sum(2)               # columns back to the game's
        return (a[iy, :] * wy).sum(1), (fx, fy)  # then rows
    a = (a[:, ix] * wx).sum(-1)
    a = (a[iy, :] * wy[:, :, None]).sum(1)
    return a, (fx, fy)


def lum(frame, box):
    """The brightness of the game's own pixels under the frame area box (x0, y0, x1, y1): (2-D array,
    (game x, game y) of its top-left pixel). Its outermost pixel all round is less sure."""
    return _native(np.asarray(frame.crop(box).convert("RGB"), np.float32) @ LUM, frame.size, box)


def rgb(frame, box):
    """The game's own colours under the frame area box, like lum: ((rows, columns, 3) array, (x, y))."""
    return _native(np.asarray(frame.crop(box).convert("RGB"), np.float32), frame.size, box)
