"""The game's bottom-right corner lines (EXP, mesos and items picked up), read off the game's own pixels
by their font, and turned into events each counted once though a line stays a few seconds and moves
up a row whenever a new one comes in under it.

The frames here are made the way the game makes them: the lines drawn in its font (Arial 12 px, a
dark shadow one pixel down and right) over a busy background at the game's own 1228 x 768, fading by
age, then stretched to the 1920 x 1200 window."""
import numpy as np
import pytest
from PIL import Image

import notices

NAMES = ["Wild Boar Tooth", "Orange Potion", "Firewood", "Arrows for Crossbows", "Bronze Arrows for Crossbows",
         "Bronze Arrows for Bows", "Tree Branch"]
WHITE, YELLOW = (250, 250, 250), (255, 238, 0)


def background(seed=5):
    """A busy background like the maps' rocks: blotches of light and dark sand."""
    rng = np.random.default_rng(seed)
    small = rng.integers(60, 230, (48, 77, 3)).astype(np.uint8)
    big = Image.fromarray(small).resize((1228, 768), Image.BICUBIC)
    noise = rng.integers(-18, 18, (768, 1228, 3))
    return np.clip(np.asarray(big, int) + noise, 0, 255).astype(float)


def frame(lines, bg=None):
    """A 1920 x 1200 frame showing `lines`, newest (bottom) first: each a text, or (text, alpha) for an
    older one fading, or (text, alpha, colour)."""
    font = notices.Font()
    pic = background() if bg is None else bg.copy()
    for k, ln in enumerate(lines):
        if ln is None:
            continue
        text, alpha, colour = (ln, 1.0, WHITE) if isinstance(ln, str) else (*ln, WHITE)[:3]
        m = font.mask(text)
        y, x = notices.Y0 - notices.PITCH * k, notices.XR - m.shape[1]
        shadow = np.zeros_like(m)
        shadow[1:, 1:] = m[:-1, :-1]
        shadow &= ~m
        for mask, col in ((shadow, (10, 10, 10)), (m, colour)):
            region = pic[y:y + m.shape[0], x:x + m.shape[1]]
            region[mask] = alpha * np.array(col) + (1 - alpha) * region[mask]
    return Image.fromarray(np.clip(np.rint(pic), 0, 255).astype(np.uint8)).resize((1920, 1200), Image.BILINEAR)


@pytest.fixture(scope="module")
def corner():
    c = notices.Corner()
    c.set_names(NAMES)
    return c


def test_the_font_has_every_character_a_line_uses():
    f = notices.Font()
    assert f.height == 15
    for c in "You received EXP (+1,234) Wild Boar Tooth x12 earned. (Etc) Ü'-:":
        assert c in f.glyphs
    assert f.width("You received EXP (+46)") == f.width("You received EXP (+") + f.width("46)")


def test_each_kind_of_line_is_read(corner):
    rows = corner.read(frame(["You received EXP (+46)", "You have gained mesos (+1,059)",
                              "Wild Boar Tooth x1 earned. (Etc)", "Orange Potion x12 earned. (Use)",
                              ("Bonus EXP for PARTY (+3)", 1.0, YELLOW)]))
    got = [(r.kind, r.n, r.name) for r in rows[:5]]
    assert got == [("exp", 46, None), ("mesos", 1059, None), ("item", 1, "Wild Boar Tooth"),
                   ("item", 12, "Orange Potion"), ("party", 3, None)]
    assert all(r.quality > 0.9 for r in rows[:5])
    assert rows[5] is None


def test_digits_that_share_pixels_are_told_apart(corner):
    for n in (43, 48, 49, 80, 88, 90, 33, 6, 1000):
        r = corner.read(frame([f"You received EXP (+{n})"]))[0]
        assert r.n == n


def test_a_cut_short_name_is_the_whole_name(corner):
    r = corner.read(frame(["Arrows for Cros... x28 earned. (Use)"]))[0]
    assert (r.kind, r.n, r.name) == ("item", 28, "Arrows for Crossbows")


def test_a_cut_short_name_two_items_share_goes_by_the_maps_drops(corner):
    r = corner.read(frame(["Bronze Arrows f... x5 earned. (Use)"]))[0]
    assert r.kind == "item" and r.n == 5
    assert set(r.names) == {"Bronze Arrows for Crossbows", "Bronze Arrows for Bows"}
    assert notices.pick(r, prefer={"Bronze Arrows for Bows"}) == "Bronze Arrows for Bows"
    assert notices.pick(r, prefer=set()) == "Bronze Arrows f..."       # can't tell: as the game shows it


def test_an_item_not_in_the_game_data_is_not_a_line(corner):
    r = corner.read(frame(["Shiny Rock x1 earned. (Etc)"]))[0]
    assert r is None or r.name is None


def events(corner, *frames_, t0=100.0):
    out = []
    for i, f in enumerate(frames_):
        out.append(corner.step(f, now=t0 + 0.4 * i))
    return out


def test_lines_already_showing_at_the_first_look_are_not_counted():
    c = notices.Corner()
    c.set_names(NAMES)
    assert c.step(frame(["You have gained mesos (+15)"]), now=1.0) == []


def test_a_new_line_counts_once():
    c = notices.Corner()
    c.set_names(NAMES)
    got = events(c, frame([]), frame(["Wild Boar Tooth x1 earned. (Etc)"]),
                 frame([("Wild Boar Tooth x1 earned. (Etc)", 0.8)]))
    assert got == [[], [("item", "Wild Boar Tooth", 1)], []]


def test_lines_move_up_as_new_ones_come():
    c = notices.Corner()
    c.set_names(NAMES)
    got = events(c, frame(["You received EXP (+46)"]),
                 frame(["You have gained mesos (+15)", ("You received EXP (+46)", 0.8)]),
                 frame(["Firewood x2 earned. (Etc)", "You received EXP (+43)", ("You have gained mesos (+15)", 0.8),
                        ("You received EXP (+46)", 0.6)]))
    assert got == [[], [("mesos", 15)], [("exp", 43), ("item", "Firewood", 2)]]


def test_the_same_line_again_counts_again():
    c = notices.Corner()
    c.set_names(NAMES)
    got = events(c, frame(["You have gained mesos (+15)", "You received EXP (+46)"]),
                 frame(["You received EXP (+46)", ("You have gained mesos (+15)", 0.8), ("You received EXP (+46)", 0.8)]),
                 frame(["You received EXP (+46)", ("You received EXP (+46)", 0.8), ("You have gained mesos (+15)", 0.6),
                        ("You received EXP (+46)", 0.6)]))
    assert got == [[], [("exp", 46)], [("exp", 46)]]


def test_a_line_that_comes_again_alone_counts_by_its_fade():
    """Nothing else to line up with: the fresh line is brighter than the old one had got to."""
    c = notices.Corner()
    c.set_names(NAMES)
    got = events(c, frame([]), frame(["Orange Potion x1 earned. (Use)"]),
                 frame([("Orange Potion x1 earned. (Use)", 0.75)]),
                 frame(["Orange Potion x1 earned. (Use)", ("Orange Potion x1 earned. (Use)", 0.55)]))
    assert got == [[], [("item", "Orange Potion", 1)], [], [("item", "Orange Potion", 1)]]


def test_fading_lines_are_not_new():
    c = notices.Corner()
    c.set_names(NAMES)
    got = events(c, frame(["You received EXP (+46)", "You have gained mesos (+15)"]),
                 frame([("You received EXP (+46)", 0.7), ("You have gained mesos (+15)", 0.7)]),
                 frame([("You received EXP (+46)", 0.4)]), frame([]))
    assert got == [[], [], [], []]


def test_after_a_long_gap_the_lines_showing_are_the_new_baseline():
    c = notices.Corner()
    c.set_names(NAMES)
    c.step(frame([]), now=1.0)
    assert c.step(frame(["You have gained mesos (+15)"]), now=30.0) == []


def full_screen_lines(texts, xr):
    """A 2560 x 1440 full-screen frame (the game 1230 x 768 between black bars) with `texts`, newest
    first, ending at game x xr."""
    from test_native import boxed
    import native
    font = notices.Font()
    rng = np.random.default_rng(5)
    small = rng.integers(60, 230, (48, 77, 3)).astype(np.uint8)
    pic = np.asarray(Image.fromarray(small).resize((1230, 768), Image.BICUBIC), float)
    pic[-40:] = 120 + 60 * (np.arange(1230) % 7 == 0)[None, :, None]
    for k, text in enumerate(texts):
        m = font.mask(text)
        y, x = notices.Y0 - notices.PITCH * k, xr - m.shape[1]
        shadow = np.zeros_like(m)
        shadow[1:, 1:] = m[:-1, :-1]
        shadow &= ~m
        for mask, col in ((shadow, (10, 10, 10)), (m, WHITE)):
            pic[y:y + m.shape[0], x:x + m.shape[1]][mask] = col
    return native.trim_bars(boxed(np.clip(pic, 0, 255), (2560, 1440), 127.459, 2305.071))     # as the capture does


def test_lines_a_pixel_off_are_found_and_kept_to():
    """At 1230 wide the lines end at 1223, a pixel left of 1228's and 1366's rule (width - 6; measured
    2026-11-17): the reader tries a pixel either way until a line reads for sure, then keeps to it."""
    c = notices.Corner()
    c.set_names(NAMES)
    f = full_screen_lines(["You have gained mesos (+49)", "Orange Potion x1 earned. (Use)"], 1223)
    rows = c.read(f)
    assert [(r.kind, r.n, r.name) for r in rows[:2]] == [("mesos", 49, None), ("item", 1, "Orange Potion")]
    assert c.shift == {(1230, 768): -1}


def test_full_screen_with_side_bars_reads_the_same(corner):
    """The lines end at the game picture's right edge, not the frame's: in full screen on a wider
    monitor that's before the black bar (measured 2026-11-17)."""
    from test_native import boxed
    import native
    font = notices.Font()
    rng = np.random.default_rng(5)
    small = rng.integers(60, 230, (48, 77, 3)).astype(np.uint8)
    pic = np.asarray(Image.fromarray(small).resize((1230, 768), Image.BICUBIC), float)
    pic[-40:] = 120 + 60 * (np.arange(1230) % 7 == 0)[None, :, None]
    xr, y0 = 1230 - (1228 - notices.XR), notices.Y0
    for k, text in enumerate(["You have gained mesos (+49)", "Orange Potion x1 earned. (Use)"]):
        m = font.mask(text)
        y, x = y0 - notices.PITCH * k, xr - m.shape[1]
        shadow = np.zeros_like(m)
        shadow[1:, 1:] = m[:-1, :-1]
        shadow &= ~m
        for mask, col in ((shadow, (10, 10, 10)), (m, WHITE)):
            pic[y:y + m.shape[0], x:x + m.shape[1]][mask] = col
    rows = corner.read(native.trim_bars(boxed(np.clip(pic, 0, 255), (2560, 1440), 127.459, 2305.071)))
    assert [(r.kind, r.n, r.name) for r in rows[:2]] == [("mesos", 49, None), ("item", 1, "Orange Potion")]
