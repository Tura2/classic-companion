"""
The HUD's level and EXP, read on the game's own pixels (native.py) with the game's own digit sprites.

On the game's pixels the status bar is the same picture at every resolution, in a window and in full
screen (measured 2026-11-17 on frames at 1920 x 1200 and 1920 x 1080 windowed and 1920 x 1200, 1920 x
1080 and 2560 x 1440 full screen): it hangs from the screen's middle and its bottom, so nothing has to
be learned per size, as the frame-scale readers (hudexp.py, reader.LevelDigits) must.

- The level is the orange boxes after "LV.": the UI/Basic.img/LevelNo sprites (11 x 13), the first
  box's top left 354 px left of the middle and 24 px up from the bottom, one every 12 px. The right
  digit is within ~1.5 of the sprite (mean summed RGB per pixel), any other 11 or more off.
- The EXP is "40,602 [16.88%]" after "EXP.": the UI/StatusBar.img/number sprites (5 x 7, white), the
  first digit's top left 66 px right of the middle and 28 px up from the bottom. A digit follows the
  last 6 px on, 11 past a comma, 10 past the decimal point and 12 past the bracket that opens the
  percent; "%" follows the last digit 6 px on. The sprites are the GMS v83 ones from maplestory.io,
  as assets/itemno; the game's brackets are drawn differently, so the gaps tell the parts apart.

A read that doesn't fit exactly what the game draws (something over a digit, no HUD) is None, never
a guess.
"""
import re

import numpy as np
from PIL import Image

import native
from paths import RES_DIR

LX, LY, LSTEP, LMOST = -354, 24, 12, 3     # level boxes: from the middle, from the bottom; step; at most
LEVEL_FIT = 6                               # a box is the digit whose sprite it's this close to
EX, EY = 66, 28                             # the EXP's first digit: from the middle, from the bottom
STEP, COMMA, DOT, SPLIT = 6, 11, 10, 12     # from one digit to the next: plain, past ",", ".", " ["
CLOSE = 60                                  # a pixel fits a sprite's when its R, G and B are this close, summed
INK = 0.9                                   # a digit fits when this share of its ink fits, less any light off it
LIGHT = 150                                 # off a sprite's ink, a pixel this bright counts against it
WIDE = 150                                  # the EXP text's width at most, in game pixels
FORM = re.compile(r"(\d{1,3}(?:,\d{3})*) (\d{1,3}\.\d\d)%")

_sprites = {}


def _load(folder, names):
    if folder not in _sprites:
        out = {}
        for n in names:
            a = np.asarray(Image.open(RES_DIR / "assets" / folder / f"{n}.png").convert("RGBA"), np.float32)
            out[n] = (a[..., :3], a[..., 3] >= 250)
        _sprites[folder] = out
    return _sprites[folder]


def _level_sprites():
    return _load("levelno", "0123456789")


def _status_sprites():
    return _load("statusno", list("0123456789") + ["percent"])


def _views(frame):
    """Where to look: the game's own pixels, then the frame's own (the game drew its HUD unstretched
    in frames of 2026-11-07, at the same place from the middle and the bottom)."""
    view = native.view_of(frame)
    yield view
    fw, fh = view.frame.size
    if view.size != (fw, fh):
        yield native.View(view.frame, (0.0, fw, 0.0, fh, fw, fh))


def read_level(frame):
    """The HUD's level, or None. frame: a game frame or its View."""
    return next((n for n in map(_level, _views(frame)) if n is not None), None)


def read_exp(frame):
    """The HUD's EXP as {"exp": int, "pct": float}, or None. frame: a game frame or its View."""
    return next((e for e in map(_exp, _views(frame)) if e is not None), None)


def _level(view):
    nw, nh = view.size
    x0, y0 = nw // 2 + LX, nh - LY
    a, (ox, oy) = view.rgb((x0 - 2, y0 - 2, x0 + LSTEP * LMOST + 2, y0 + 15))
    digits = ""
    for i in range(LMOST):
        x, y = x0 + LSTEP * i - ox, y0 - oy
        best = None
        for d, (pic, op) in _level_sprites().items():
            win = a[y:y + op.shape[0], x:x + op.shape[1]]
            if win.shape[:2] != op.shape:
                return None
            err = float(np.abs(win - pic).sum(-1)[op].mean())
            if best is None or err < best[0]:
                best = (err, d)
        if best[0] > LEVEL_FIT:
            break
        digits += best[1]
    return int(digits) if digits and digits[0] != "0" else None


def _fits(row, pic, op):
    """How well the sprite fits the row at each x: the share of its ink that fits, less the share of
    the rest that is light (a digit that only covers another's ink isn't that one)."""
    h, w = op.shape
    if row.shape[1] < w:
        return np.zeros(0)
    wins = np.lib.stride_tricks.sliding_window_view(row[:h], (h, w), axis=(0, 1))[0]     # (x, 3, h, w)
    wins = np.moveaxis(wins, 1, -1)                                                      # (x, h, w, 3)
    ink = ((np.abs(wins - pic).sum(-1) <= CLOSE) & op).sum((1, 2)) / op.sum()
    light = ((wins.mean(-1) > LIGHT) & ~op).sum((1, 2)) / max(1, (~op).sum())
    return ink - light


def _exp(view):
    nw, nh = view.size
    x0, y0 = nw // 2 + EX, nh - EY
    a, (ox, oy) = view.rgb((x0 - 2, y0 - 2, min(nw, x0 + WIDE), y0 + 9))
    row = a[y0 - oy:]
    fits = {k: _fits(row, pic, op) for k, (pic, op) in _status_sprites().items()}

    def at(k, x):
        f = fits[k]
        return f[x] if 0 <= x < len(f) else 0.0

    def digit(x):
        d = max("0123456789", key=lambda c: at(c, x))
        return d if at(d, x) >= INK else None

    x = x0 - ox
    text = digit(x)
    if text is None:
        return None
    while len(text) < 30:
        if at("percent", x + STEP) >= INK and at("percent", x + STEP) > max(at(c, x + STEP) for c in "0123456789"):
            text += "%"
            break
        for gap, sep in ((STEP, ""), (COMMA, ","), (DOT, "."), (SPLIT, " ")):
            d = digit(x + gap)
            if d is not None:
                text, x = text + sep + d, x + gap
                break
        else:
            return None
    m = FORM.fullmatch(text)
    if not m:
        return None
    pct = float(m.group(2))
    return {"exp": int(m.group(1).replace(",", "")), "pct": pct} if pct <= 100 else None
