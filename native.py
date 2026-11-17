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
from PIL import Image

NATIVE_H = 768
LUM = np.array([0.299, 0.587, 0.114], np.float32)


def native_size(w, h):
    """The game's own size for a game area of w x h: 768 tall, the width to the nearest even number
    (1920 x 1200 -> 1228, 1920 x 1080 and 2560 x 1440 -> 1366). Up to 768 tall it isn't stretched."""
    if h <= NATIVE_H:
        return w, h
    return 2 * round(w * NATIVE_H / h / 2), NATIVE_H


def _stretch(lo, hi, frame_len, native_len, off=0.0):
    """How frame pixels lo..hi-1 blend the game's pixels along one side: (matrix, first game pixel).
    The game's picture covers frame_len pixels from off (fractions too: full screen's black bars).
    Past the picture's edge the edge pixel is used again; a frame pixel the picture only partly
    covers is that much of it (the rest is the bar's black)."""
    x = np.arange(lo, hi)
    u = (x + 0.5 - off) * native_len / frame_len - 0.5
    i0 = np.floor(u).astype(int)
    f = u - i0
    left, right = np.clip(i0, 0, native_len - 1), np.clip(i0 + 1, 0, native_len - 1)
    first = int(left.min())
    a = np.zeros((len(x), int(right.max()) - first + 1))
    np.add.at(a, (np.arange(len(x)), left - first), 1 - f)
    np.add.at(a, (np.arange(len(x)), right - first), f)
    cover = np.clip(np.minimum(x + 1, off + frame_len) - np.maximum(x, off), 0, 1)
    return a * cover[:, None], first


BAND = 10       # each game pixel is worked out from the 2 x 10 + 1 frame pixels around it (off by < 0.1)


@lru_cache(maxsize=32)
def _undo(lo, hi, frame_len, native_len, off=0.0):
    """How to get game pixels back along one side: (frame pixels to use, their weights), each
    (game pixels, 2 * BAND + 1), and the first game pixel. The least-squares answer's weights fall
    off fast away from a pixel, so only the nearest ones are kept: plain sums, no matrix library
    (whose threads cost more than the sums for areas this small)."""
    a, first = _stretch(lo, hi, frame_len, native_len, off)
    p = np.linalg.pinv(a)
    n = p.shape[0]
    centre = np.rint((np.arange(first, first + n) + 0.5) * frame_len / native_len - 0.5 + off).astype(int) - lo
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


def _native(a, size, box, area=None):
    """Frame pixels a (rows, columns[, channels]) under box, back to the game's own: (array, (x, y)).
    area: where the game's picture is in the frame and its own size, (x0, w, y0, h, nw, nh); the
    whole frame when None."""
    w, h = size
    x0, y0, x1, y1 = box
    if area is None:
        area = (0.0, w, 0.0, h, *native_size(w, h))
    ax, aw, ay, ah, nw, nh = area
    if (nw, nh) == (w, h) and (ax, ay, aw, ah) == (0, 0, w, h):
        return a, (x0, y0)
    ix, wx, fx = _undo(x0, x1, aw, nw, ax)
    iy, wy, fy = _undo(y0, y1, ah, nh, ay)
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


# ---- where the game's picture is. In full screen on a monitor of another shape the game keeps its
# own (16:10 for 1920 x 1200) and the rest is black bars. Measured 2026-11-17, 1920 x 1200 full screen
# on a 2560 x 1440 monitor: the picture covers x 127.46..2432.53 (bars of 127 px, the edge pixels half
# covered), and the game draws 1230 x 768 there, not the 1229 its shape gives. So its width is told by
# the picture (the width whose stretch rebuilds the HUD's sharp bottom bar best), not worked out.

DARK = 8            # a frame column (or row) no brighter than this anywhere is part of a bar
_views = {}         # frame size -> the last area found there (x0, w, y0, h, nw, nh)


class View:
    """The game's picture in one frame: its place (x0, w, y0, h, in frame pixels, fractions too) and
    its own size (nw, nh), and the game's own pixels under any of its areas."""

    def __init__(self, frame, area):
        self.frame = frame
        self.area = area
        self.x0, self.w, self.y0, self.h, self.nw, self.nh = area

    @property
    def size(self):
        return self.nw, self.nh

    def box(self, nbox, margin=2):
        """The frame area to un-stretch for the game area nbox (in game pixels)."""
        fw, fh = self.frame.size
        sx, sy = self.w / self.nw, self.h / self.nh
        x0, y0, x1, y1 = nbox
        return (max(0, int(self.x0 + x0 * sx) - margin), max(0, int(self.y0 + y0 * sy) - margin),
                min(fw, int(np.ceil(self.x0 + x1 * sx)) + margin), min(fh, int(np.ceil(self.y0 + y1 * sy)) + margin))

    def lum(self, nbox):
        """The game's own brightness under nbox (game pixels): (array, (game x, game y) of its corner)."""
        box = self.box(nbox)
        a = np.asarray(self.frame.crop(box).convert("RGB"), np.float32) @ LUM
        return _native(a, self.frame.size, box, self.area)

    def rgb(self, nbox):
        """The game's own colours under nbox, like lum."""
        box = self.box(nbox)
        return _native(np.asarray(self.frame.crop(box).convert("RGB"), np.float32), self.frame.size, box, self.area)


def _edges(peak, mean):
    """Where the picture starts and ends along one side, from each frame line's brightest pixel (peak)
    and its mean: (start, end) in frame pixels, fractions too, or None when it's all dark."""
    lit = np.where(peak > DARK)[0]
    if not len(lit):
        return None
    a, b = int(lit[0]), int(lit[-1])
    start, end = float(a), float(b + 1)
    if a > 0 and a + 1 < len(mean) and mean[a + 1] > 0:
        start = a + 1 - min(1.0, mean[a] / mean[a + 1])         # a half-covered edge pixel is half bright
    if b + 1 < len(mean) and b > 0 and mean[b - 1] > 0:
        end = b + min(1.0, mean[b] / mean[b - 1])
    return start, end


def _width(frame, x0, w, y0, h, nh):
    """The game's own width for its picture w x h at (x0, y0): the one whose stretch rebuilds the
    HUD's bottom bar (sharp, always drawn) best, of the few its shape allows."""
    base = round(w * nh / h)
    rows = (int(y0 + h) - max(8, round(h / 14)), int(y0 + h) - 1)
    cols = (max(int(x0) + 1, int(x0 + w) - round(0.37 * w)), int(x0 + w) - 1)
    sub = np.asarray(frame.crop((cols[0], rows[0], cols[1], rows[1])).convert("RGB"), np.float32) @ LUM
    ay, _ = _stretch(*rows, h, nh, y0)
    iay = np.linalg.pinv(ay)
    best = None
    for nw in range(base - 3, base + 4):
        ax, _ = _stretch(*cols, w, nw, x0)
        back = ay @ (iay @ sub @ np.linalg.pinv(ax).T) @ ax.T
        err = float(np.abs(back - sub)[2:-2, 2:-2].mean())
        if best is None or err < best[0]:
            best = (err, nw)
    return best[1]


def _lines(frame):
    """Each frame column's and row's brightest pixel and mean (every 4th row or column: a quarter of
    the work): ((column peaks, column means), (row peaks, row means))."""
    fw, fh = frame.size
    by_col = np.asarray(frame.resize((fw, max(1, fh // 4)), Image.NEAREST).convert("L"), np.float32)
    by_row = np.asarray(frame.resize((max(1, fw // 4), fh), Image.NEAREST).convert("L"), np.float32)
    return (by_col.max(0), by_col.mean(0)), (by_row.max(1), by_row.mean(1))


def trim_bars(frame):
    """The frame without full screen's black bars (one dark pixel kept each side, so the picture's
    edge can still be found to a fraction of a pixel); the frame itself when it has none, or is all
    dark (a map loading)."""
    fw, fh = frame.size
    (cp, cm), (rp, rm) = _lines(frame)
    cols, rows = _edges(cp, cm), _edges(rp, rm)
    if cols is None or rows is None:
        return frame
    x0, x1 = max(0, int(cols[0]) - 1), min(fw, int(np.ceil(cols[1])) + 1)
    y0, y1 = max(0, int(rows[0]) - 1), min(fh, int(np.ceil(rows[1])) + 1)
    if x1 - x0 >= fw - 2 and y1 - y0 >= fh - 2:
        return frame
    return frame.crop((x0, y0, x1, y1))


def view_of(frame):
    """A View of the frame, or the View itself when given one (worked out once a look, shared)."""
    return frame if isinstance(frame, View) else game_view(frame)


def game_view(frame):
    """Where the game's picture is in a frame and its own size, as a View: the whole frame in a
    window, the part between the black bars in full screen on a monitor of another shape."""
    fw, fh = frame.size
    (cp, cm), (rp, rm) = _lines(frame)
    cols, rows = _edges(cp, cm), _edges(rp, rm)
    last = _views.get((fw, fh))
    if cols is None or rows is None:                      # all black (a map loading): as last time
        return View(frame, last or (0.0, fw, 0.0, fh, *native_size(fw, fh)))
    (x0, x1), (y0, y1) = cols, rows
    if x0 < 0.5 and y0 < 0.5 and x1 > fw - 0.5 and y1 > fh - 0.5:     # no bars: the whole frame
        area = (0.0, fw, 0.0, fh, *native_size(fw, fh))
    elif last and abs(last[0] - x0) < 0.2 and abs(last[1] - (x1 - x0)) < 0.3 \
            and abs(last[2] - y0) < 0.2 and abs(last[3] - (y1 - y0)) < 0.3:
        area = last                                       # the same place as before: its width is known
    else:
        w, h = x1 - x0, y1 - y0
        nh = NATIVE_H if h > NATIVE_H else round(h)
        area = (x0, w, y0, h, _width(frame, x0, w, y0, h, nh), nh)
    _views[(fw, fh)] = area
    return View(frame, area)
