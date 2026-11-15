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
