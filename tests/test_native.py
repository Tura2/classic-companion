"""The game draws at 768 px tall and the window shows that picture stretched, smoothly (bilinear);
native.py undoes the stretch to get the game's own pixels back."""
import numpy as np
from PIL import Image

import native


def stretched(nat, size):
    """What the window shows of a native picture: stretched the way the game does (bilinear,
    pixel centres lined up), as a frame of `size`."""
    return Image.fromarray(nat.astype(np.uint8)).resize(size, Image.BILINEAR)


def test_native_size():
    assert native.native_size(1920, 1200) == (1228, 768)
    assert native.native_size(1920, 1080) == (1366, 768)
    assert native.native_size(2560, 1440) == (1366, 768)
    assert native.native_size(1024, 768) == (1024, 768)      # 768 tall and under: not stretched


def test_the_stretch_is_undone_exactly():
    rng = np.random.default_rng(3)
    nat = rng.integers(0, 256, (768, 1228, 3))
    frame = stretched(nat, (1920, 1200))
    lum, (x0, y0) = native.lum(frame, (1500, 800, 1920, 1000))
    want = nat @ np.array([0.299, 0.587, 0.114])
    got = want[y0:y0 + lum.shape[0], x0:x0 + lum.shape[1]]
    assert lum.shape[0] > 100 and lum.shape[1] > 200
    assert np.abs(lum - got)[1:-1, 1:-1].max() < 1.5        # rounding to whole numbers in the frame
    assert x0 == int((1500 + 0.5) * 1228 / 1920 - 0.5) and y0 == int((800 + 0.5) * 768 / 1200 - 0.5)


def test_native_box_for_a_native_area():
    """The frame area to un-stretch for a wanted native area, and the native area it gives back."""
    box = native.frame_box((1920, 1200), (980, 500, 1228, 620))
    lum, (x0, y0) = native.lum(stretched(np.zeros((768, 1228, 3)), (1920, 1200)), box)
    assert x0 <= 980 and y0 <= 500
    assert x0 + lum.shape[1] >= 1228 - 1 and y0 + lum.shape[0] >= 620


def test_rgb_gives_the_colours_back_and_matches_lum():
    rng = np.random.default_rng(4)
    nat = rng.integers(0, 256, (768, 1228, 3))
    frame = stretched(nat, (1920, 1200))
    box = (1300, 900, 1700, 1100)
    rgb, (x0, y0) = native.rgb(frame, box)
    lum, at = native.lum(frame, box)
    assert at == (x0, y0) and rgb.shape == lum.shape + (3,)
    assert np.abs(rgb @ native.LUM - lum).max() < 0.01
    got = nat[y0:y0 + rgb.shape[0], x0:x0 + rgb.shape[1]]
    assert np.abs(rgb - got)[1:-1, 1:-1].max() < 3     # one channel: its rounding isn't averaged like lum's


# ---- full screen: the game keeps its own shape and the rest is black bars

def boxed(nat, size, left, width, top=0.0, height=None):
    """A frame of `size` showing the native picture stretched over [left, left + width) x [top, top +
    height) (fractions of a pixel too) and black around it, the way full screen on a wider (or
    narrower) monitor shows the game. Edge pixels the picture only partly covers are partly black."""
    fw, fh = size
    height = fh if height is None else height

    def side(n_frame, lo, length, n_nat):
        x = np.arange(n_frame)
        u = np.clip((x + 0.5 - lo) * n_nat / length - 0.5, 0, n_nat - 1)
        i0 = np.floor(u).astype(int)
        f = u - i0
        a = np.zeros((n_frame, n_nat))
        a[x, i0] += 1 - f
        a[x, np.minimum(i0 + 1, n_nat - 1)] += f
        cover = np.clip(np.minimum(x + 1, lo + length) - np.maximum(x, lo), 0, 1)
        return a * cover[:, None]
    ax, ay = side(fw, left, width, nat.shape[1]), side(fh, top, height, nat.shape[0])
    out = np.stack([ay @ nat[..., k] @ ax.T for k in range(3)], -1)
    return Image.fromarray(np.clip(np.rint(out), 0, 255).astype(np.uint8))


def nat_picture(w, h, seed=8):
    rng = np.random.default_rng(seed)
    small = rng.integers(40, 250, (h // 16, w // 16, 3)).astype(np.uint8)
    pic = np.asarray(Image.fromarray(small).resize((w, h), Image.BICUBIC), float)
    pic[-40:] = 120 + 60 * (np.arange(w) % 7 == 0)[None, :, None]      # a HUD bar along the bottom, sharp
    return pic + rng.integers(-12, 12, pic.shape)


def test_a_window_without_bars_is_the_whole_frame():
    frame = stretched(np.clip(nat_picture(1228, 768), 0, 255), (1920, 1200))
    v = native.game_view(frame)
    assert (v.x0, v.w, v.y0, v.h, v.size) == (0, 1920, 0, 1200, (1228, 768))
    a, at = v.lum((1000, 600, 1200, 700))
    b, bt = native.lum(frame, native.frame_box(frame.size, (1000, 600, 1200, 700)))
    assert at == bt and np.array_equal(a, b)


def test_full_screen_side_bars_are_found_to_a_fraction_of_a_pixel():
    nat = np.clip(nat_picture(1230, 768), 0, 255)
    frame = boxed(nat, (2560, 1440), 127.459, 2305.071)        # measured 2026-11-17, 1920 x 1200 full screen
    v = native.game_view(native.trim_bars(frame))                # cut at x 126: the picture from 1.459
    assert abs(v.x0 - 1.459) < 0.05 and abs(v.w - 2305.071) < 0.1 and (v.y0, v.h) == (0, 1440)
    assert v.size == (1230, 768)                                 # not 1229: told by the picture, not by the ratio
    lum, (x, y) = v.lum((900, 600, 1220, 760))
    want = (nat @ native.LUM)[y:y + lum.shape[0], x:x + lum.shape[1]]
    assert np.abs(lum - want)[2:-2, 2:-2].max() < 3


def test_bars_above_and_below_are_found_too():
    nat = np.clip(nat_picture(1228, 768), 0, 255)
    frame = boxed(nat, (1920, 1440), 0, 1920, 119.6, 1200.8)
    v = native.game_view(native.trim_bars(frame))                # cut at y 118: the picture from 1.6
    assert abs(v.y0 - 1.6) < 0.05 and abs(v.h - 1200.8) < 0.1 and v.size == (1228, 768)


def test_a_frame_the_capture_left_whole_is_the_game_picture_whole():
    """A window (or a recording, a test frame): its black sides are the game's (a small map), not bars."""
    nat = np.clip(nat_picture(1228, 768), 0, 255)
    nat[:, :60] = 0                                                   # a small map: black at its sides
    nat[:, -60:] = 0
    v = native.game_view(stretched(nat, (1920, 1200)))
    assert (v.x0, v.w, v.size) == (0, 1920, (1228, 768))


def test_trimming_the_bars_leaves_the_game_picture_for_every_reader():
    """The capture cuts full screen's bars off, so readers that work on frame pixels (the HUD, the
    mini map, windows) see the game's picture as in a window. A dark pixel is kept each side so the
    precise readers still find the picture's edge to a fraction of a pixel."""
    nat = np.clip(nat_picture(1230, 768), 0, 255)
    frame = boxed(nat, (2560, 1440), 127.459, 2305.071)
    cut = native.trim_bars(frame)
    assert cut.size == (2308, 1440)
    v = native.game_view(cut)
    assert abs(v.x0 - 1.459) < 0.05 and abs(v.w - 2305.071) < 0.1 and v.size == (1230, 768)


def test_a_frame_without_bars_is_not_cut():
    frame = stretched(np.clip(nat_picture(1228, 768), 0, 255), (1920, 1200))
    assert native.trim_bars(frame) is frame
    assert native.trim_bars(Image.new("RGB", (1920, 1200))).size == (1920, 1200)     # all black: as it is


def test_the_bars_edge_stays_put_while_it_only_wobbles():
    """Live frames measure the same edge a few thousandths of a pixel apart (127.4646 then 127.4595,
    2026-11-17). Each new edge is new un-stretch sums and a new width check, every look, all of it
    heavy, so an edge that hardly moved is the one already known; a real move is taken."""
    native._bars.clear()
    nat = np.clip(nat_picture(1230, 768), 0, 255)
    first = native.trim_bars(boxed(nat, (2560, 1440), 127.4646, 2305.0708)).info[native.AREA]
    again = native.trim_bars(boxed(np.clip(nat_picture(1230, 768, seed=9), 0, 255), (2560, 1440),
                                   127.4595, 2305.081)).info[native.AREA]
    assert again == first
    moved = native.trim_bars(boxed(np.clip(nat_picture(1228, 768), 0, 255), (2560, 1440), 240, 2080)).info[native.AREA]
    assert abs(moved[0] - 1) < 0.05 and abs(moved[1] - 2080) < 0.1
