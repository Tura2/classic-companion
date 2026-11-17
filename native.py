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
# covered, the picture centred to 0.01 px), and the game draws 1230 x 768 there, not the 1229 its shape
# gives. So its width is told by the picture (the width whose stretch rebuilds the HUD's sharp bottom
# best), not worked out.
#
# Bars are looked for only in full screen (the capture says so: the game covers its whole monitor).
# In a window a small map leaves black at the screen's sides too, and that is the game's picture.
# The picture's edge is measured on the HUD's bottom left (the status bar, drawn on every map at the
# picture's very edge); the far side mirrors it. The capture cuts the bars off and puts where the
# picture is in the frame's info, so every reader gets the game as in a window; a frame without it
# (a window, a recording, a test) is the game's picture whole.

DARK = 8            # a frame pixel no brighter than this is a bar's
HUD_BAND = 0.04     # the bottom (and left) share of the frame the HUD's edge is measured on
AREA = "game_area"  # frame.info key: (x0, w, y0, h), the game's picture in the frame (fractions too)
_widths = {}        # (rounded area, frame size) -> the game's own width there


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


def _edge(line):
    """Where a line of brightness (from the frame's edge inwards) stops being a bar: in pixels,
    fractions too (a half-covered pixel is half as bright as the next), or None when it never does."""
    lit = np.where(line > DARK)[0]
    if not len(lit):
        return None
    a = int(lit[0])
    if a == 0:
        return 0.0
    nxt = line[a + 1] if a + 1 < len(line) else 0
    return a + 1 - min(1.0, line[a] / nxt) if nxt > 0 else float(a)


def find_bars(frame):
    """Full screen's bars round the game's picture: (x0, w, y0, h) of the picture in the frame, or
    None when there are none. Measured on the HUD's bottom left; the far sides mirror it."""
    fw, fh = frame.size
    bh, bw = max(4, round(fh * HUD_BAND)), max(4, round(fw * HUD_BAND))

    def strip(box):                     # only the strips the edges are measured on: the frame is big
        return np.asarray(frame.crop(box).convert("L"), np.float32)
    x0 = _edge(strip((0, fh - bh, fw, fh)).mean(0))                   # the bottom, from the left
    if x0 is not None:                                                # bars at the sides (or none)
        if x0 > fw * 0.3:
            return None
        y0 = _edge(strip((int(x0) + 2, 0, int(x0) + 2 + bw, fh)).mean(1)[::-1])    # the left, from the bottom
    else:                                                             # the bottom is a bar: above and below
        y0 = _edge(strip((0, 0, bw, fh)).mean(1)[::-1])
        if y0 is None or y0 > fh * 0.3:
            return None
        hud = int(fh - y0) - 2                                         # the HUD's bottom, just above the bar
        x0 = _edge(strip((0, hud - bh, fw, hud)).mean(0))
    if x0 is None or y0 is None or y0 > fh * 0.3 or (x0 < 0.5 and y0 < 0.5):
        return None
    return x0, fw - 2 * x0, y0, fh - 2 * y0


def trim_bars(frame):
    """A full-screen frame without its black bars (one dark pixel kept each side) and the game's
    picture's place in it in its info; the frame itself when it has none."""
    found = find_bars(frame)
    if found is None:
        return frame
    x0, w, y0, h = found
    fw, fh = frame.size
    cx, cy = max(0, int(x0) - 1), max(0, int(y0) - 1)
    cut = frame.crop((cx, cy, min(fw, int(np.ceil(x0 + w)) + 1), min(fh, int(np.ceil(y0 + h)) + 1)))
    cut.info[AREA] = (x0 - cx, w, y0 - cy, h)
    return cut


def _width(frame, x0, w, y0, h, nh):
    """The game's own width for its picture w x h at (x0, y0): the one whose stretch rebuilds the
    HUD's bottom (sharp, always drawn) best, of the few its shape allows."""
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


def view_of(frame):
    """A View of the frame, or the View itself when given one (worked out once a look, shared)."""
    return frame if isinstance(frame, View) else game_view(frame)


def game_view(frame):
    """Where the game's picture is in a frame and its own size, as a View: what the capture put in
    the frame's info (full screen, its bars cut), else the whole frame (a window)."""
    fw, fh = frame.size
    area = frame.info.get(AREA)
    if area is None:
        return View(frame, (0.0, fw, 0.0, fh, *native_size(fw, fh)))
    x0, w, y0, h = area
    key = (round(x0, 1), round(w, 1), round(y0, 1), round(h, 1), fw, fh)
    nh = NATIVE_H if h > NATIVE_H else round(h)
    if key not in _widths:
        _widths[key] = _width(frame, x0, w, y0, h, nh)
    return View(frame, (x0, w, y0, h, _widths[key], nh))
