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


# ---- naming a slot's item by its icon

def shape_icon(kind, colour, h=30, w=27):
    """A made-up icon: a filled potion-ish blob (kind "round") or a box with a stripe ("box")."""
    a = np.zeros((h, w, 4))
    yy, xx = np.mgrid[:h, :w]
    if kind == "round":
        inside = (yy - h * 0.6) ** 2 / (h * 0.4) ** 2 + (xx - w / 2) ** 2 / (w * 0.45) ** 2 <= 1
        inside |= (np.abs(xx - w / 2) < 3) & (yy < h * 0.3)
    else:
        inside = (yy > 3) & (yy < h - 2) & (xx > 2) & (xx < w - 3)
    a[inside, :3] = colour
    edge = inside & ~np.roll(inside, 1, 0) | inside & ~np.roll(inside, 1, 1)
    a[edge, :3] = (20, 20, 20)
    a[inside, 3] = 255
    a[(yy % 7 == 3) & inside, :3] = (240, 240, 240)       # a shine stripe, so it isn't flat
    return a


ICONS = {2000001: ("Orange Potion", shape_icon("round", (240, 140, 30))),
         2000000: ("Red Potion", shape_icon("round", (220, 30, 30))),
         2000003: ("Blue Potion", shape_icon("round", (30, 50, 220))),
         2010000: ("Apple", shape_icon("box", (120, 200, 60), 26, 26))}


def icon_files(tmp_path, icons=ICONS):
    for iid, (_, a) in icons.items():
        Image.fromarray(a.astype(np.uint8), "RGBA").save(tmp_path / f"{iid}.png")
    return quickslots.Icons([(iid, name) for iid, (name, _) in icons.items()],
                            lambda iid: (tmp_path / f"{iid}.png") if (tmp_path / f"{iid}.png").exists() else None)


def draw_icon(pic, slot, a):
    x, y = quickslots.icon_spot((NW, NH), slot, a.shape[:2])
    paste(pic, (a[..., :3], a[..., 3:] / 255), x, y)


def slot_frame(icons_by_slot, counts=None, extra=None):
    pic = background()
    for slot, a in icons_by_slot.items():
        draw_icon(pic, slot, a)
    for slot, n in (counts or {}).items():
        draw_count(pic, slot, n)
    if extra:
        extra(pic)
    return stretch(pic)


def names(icons, f):
    return quickslots.slot_names(icons, f)


def test_names_the_icon_in_a_slot(tmp_path):
    icons = icon_files(tmp_path)
    icons.load()
    assert icons.ready
    for iid, (name, a) in ICONS.items():
        assert names(icons, slot_frame({5: a}))[5] == name


def test_same_shape_other_colour_is_told_apart(tmp_path):
    icons = icon_files(tmp_path)
    icons.load()
    got = names(icons, slot_frame({4: ICONS[2000001][1], 5: ICONS[2000000][1], 9: ICONS[2000003][1]}))
    assert (got[4], got[5], got[9]) == ("Orange Potion", "Red Potion", "Blue Potion")


def test_a_skill_or_empty_slot_is_none(tmp_path):
    icons = icon_files(tmp_path)
    icons.load()
    skill = shape_icon("box", (200, 200, 200), 30, 30)
    skill[10:20, 5:25, :3] = (90, 60, 160)
    got = names(icons, slot_frame({3: skill}))
    assert got[3] is None and got[0] is None


def test_label_and_count_over_the_icon_still_name_it(tmp_path):
    icons = icon_files(tmp_path)
    icons.load()

    def label(pic):
        x, y = quickslots.slot_origin((NW, NH), 9)
        pic[y + 1:y + 9, x + 2:x + 22] = (235, 235, 245)           # a key's name, "Shift", over the top left
    got = names(icons, slot_frame({9: ICONS[2000001][1]}, counts={9: 145}, extra=label))
    assert got[9] == "Orange Potion"


def test_nothing_is_named_before_the_icons_load(tmp_path):
    icons = icon_files(tmp_path)
    assert not icons.ready
    assert names(icons, slot_frame({5: ICONS[2000001][1]})) == [None] * 12


def test_a_slot_looking_the_same_is_not_matched_again(tmp_path):
    icons = icon_files(tmp_path)
    icons.load()
    pic = background()
    draw_icon(pic, 5, ICONS[2000001][1])
    rng = np.random.default_rng(1)
    names(icons, stretch(pic))
    done = icons.work
    again = names(icons, stretch(pic + rng.integers(-3, 4, pic.shape)))     # a little noise, as frame to frame
    assert again[5] == "Orange Potion" and icons.work == done
