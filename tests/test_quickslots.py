"""The quick slots (12, in a 4 x 3 grid at the game's bottom right): each slot's count read by the
game's own digit pictures (ItemNo), its item told by its icon, and potions drunk counted from
counts going down.

The frames here are made the way the game makes them: digits and icons drawn at the game's own
1228 x 768 over a busy background, then stretched to the 1920 x 1200 window."""
import numpy as np
from PIL import Image

import native
import quickslots

NW, NH = 1228, 768


def background(seed=7):
    """A busy background, like the slots' own art and the map behind them."""
    rng = np.random.default_rng(seed)
    small = rng.integers(60, 230, (48, 77, 3)).astype(np.uint8)
    big = Image.fromarray(small).resize((NW, NH), Image.BICUBIC)
    noise = rng.integers(-18, 18, (NH, NW, 3))
    return np.clip(np.asarray(big, int) + noise, 0, 255).astype(float)


def sprite(d):
    a = np.asarray(Image.open(quickslots.DIGIT_DIR / f"{d}.png").convert("RGBA"), float)
    return a[..., :3], a[..., 3:] / 255


def paste(pic, rgba, x, y):
    rgb, al = rgba
    h, w = rgb.shape[:2]
    region = pic[y:y + h, x:x + w]
    region[:] = al * rgb + (1 - al) * region


def draw_count(pic, slot, n):
    _, x, y = quickslots.count_spots((NW, NH))[slot]
    for ch in str(n):
        paste(pic, sprite(int(ch)), x, y)
        x += quickslots.ADV[int(ch)]


def stretch(pic):
    return Image.fromarray(np.clip(np.rint(pic), 0, 255).astype(np.uint8)).resize((1920, 1200), Image.BILINEAR)


def frame(counts, bg=None, extra=None):
    """A 1920 x 1200 frame with `counts` {slot: count} drawn at their spots."""
    pic = background() if bg is None else bg.copy()
    for slot, n in counts.items():
        draw_count(pic, slot, n)
    if extra:
        extra(pic)
    return stretch(pic)


def read_all(f):
    return quickslots.Digits().read_all(f)


def test_reads_counts_at_each_spot():
    want = {0: 93, 1: 145, 3: 52, 5: 65, 7: 0, 11: 1203}
    got = read_all(frame(want))
    assert got == [want.get(s) for s in range(12)]


def test_one_is_narrow():
    got = read_all(frame({2: 111, 6: 1203, 9: 10}))
    assert (got[2], got[6], got[9]) == (111, 1203, 10)


def test_a_covered_first_digit_reads_none():
    def cover(pic):
        _, x, y = quickslots.count_spots((NW, NH))[5]
        pic[y - 1:y + 12, x - 1:x + 5] = 128           # the "1" of 145 under something flat and grey
    got = read_all(frame({5: 145}, extra=cover))
    assert got[5] in (None, 45)
    assert got[5] is None              # recorded 2026-11-15: a covered first digit reads nothing


def test_the_spots_sit_where_measured():
    spots = quickslots.count_spots((NW, NH))
    assert [s[0] for s in spots] == list(range(12))
    assert spots[4][1:] == (871, 649) and spots[5][1:] == (906, 649) and spots[7][1:] == (976, 649)
    assert spots[9][1:] == (906, 683)


def test_reading_twelve_slots_is_quick():
    import time
    f, d = frame({0: 93, 1: 145, 3: 52, 5: 65}), quickslots.Digits()
    d.read_all(f)
    t = time.perf_counter()
    for _ in range(5):
        d.read_all(f)
    assert (time.perf_counter() - t) / 5 < 0.010
