"""The HUD's level and EXP read on the game's own pixels with its own digit sprites: the same at every
resolution, in a window and in full screen, with nothing to learn."""
import numpy as np
from PIL import Image

import hudnative
import native
from paths import RES_DIR
from test_native import boxed, stretched

HUD_BG = (62, 71, 76)


def sprite(folder, name):
    return np.asarray(Image.open(RES_DIR / "assets" / folder / f"{name}.png").convert("RGBA"), np.float64)


def put(pic, a, x, y):
    h, w = a.shape[:2]
    alpha = a[..., 3:] / 255
    pic[y:y + h, x:x + w] = pic[y:y + h, x:x + w] * (1 - alpha) + a[..., :3] * alpha


def hud(nw, level, exp_text, nh=768):
    """A native picture with the HUD's level boxes and EXP text drawn as the game draws them:
    exp_text like "40,602 [16.88%]"."""
    pic = np.zeros((nh, nw, 3))
    pic[:] = (90, 120, 60)                                  # the map
    pic[nh - 40:] = HUD_BG                                  # the status bar
    pic[nh - 5:, ::7] = 140                                 # its sharp bottom, that full screen's width is told by
    m = nw // 2
    for i, d in enumerate(str(level)):
        put(pic, sprite("levelno", d), m - 354 + 12 * i, nh - 24)
    x, y = m + 66, nh - 28
    for ch in exp_text:
        if ch.isdigit():
            put(pic, sprite("statusno", ch), x, y)
            x += 6
        elif ch == ",":
            pic[y + 6:y + 8, x:x + 1] = 230
            x += 5
        elif ch == ".":
            pic[y + 6, x + 1] = 230
            x += 4
        elif ch == " ":
            x += 2
        elif ch == "[":
            pic[y - 1:y + 8, x + 2:x + 3] = (153, 204, 51)
            x += 4
        elif ch == "%":
            put(pic, sprite("statusno", "percent"), x, y)
            x += 8
    return pic


def test_level_and_exp_in_a_window_at_both_shapes():
    for size, nw in (((1920, 1200), 1228), ((1920, 1080), 1366)):
        v = native.game_view(stretched(hud(nw, 38, "40,602 [16.88%]"), size))
        assert hudnative.read_level(v) == 38
        assert hudnative.read_exp(v) == {"exp": 40602, "pct": 16.88}


def test_level_and_exp_in_full_screen_between_bars():
    nat = hud(1230, 33, "32,994 [23.79%]")
    v = native.game_view(native.trim_bars(boxed(nat, (2560, 1440), 127.459, 2305.071)))
    assert v.size == (1230, 768)
    assert hudnative.read_level(v) == 33
    assert hudnative.read_exp(v) == {"exp": 32994, "pct": 23.79}


def test_numbers_of_other_lengths():
    v = native.game_view(stretched(hud(1366, 7, "512 [3.05%]"), (1920, 1080)))
    assert hudnative.read_level(v) == 7
    assert hudnative.read_exp(v) == {"exp": 512, "pct": 3.05}
    v = native.game_view(stretched(hud(1366, 120, "1,234,567 [100.00%]"), (1920, 1080)))
    assert hudnative.read_level(v) == 120
    assert hudnative.read_exp(v) == {"exp": 1234567, "pct": 100.0}


def test_no_hud_reads_nothing():
    pic = np.zeros((768, 1228, 3))
    pic[:] = (90, 120, 60)
    pic[-40:] = HUD_BG
    v = native.game_view(stretched(pic, (1920, 1200)))
    assert hudnative.read_level(v) is None and hudnative.read_exp(v) is None


def test_a_covered_digit_reads_nothing_not_a_wrong_number():
    nat = hud(1228, 38, "40,602 [16.88%]")
    nat[768 - 28:768 - 20, 614 + 66 + 17:614 + 66 + 23] = (250, 250, 250)    # something over the third digit
    v = native.game_view(stretched(nat, (1920, 1200)))
    assert hudnative.read_exp(v) is None
    assert hudnative.read_level(v) == 38


def test_a_whole_frame_works_as_well_as_its_view():
    frame = stretched(hud(1228, 38, "40,602 [16.88%]"), (1920, 1200))
    assert hudnative.read_level(frame) == 38
    assert hudnative.read_exp(frame) == {"exp": 40602, "pct": 16.88}


def test_a_game_drawn_one_to_one_reads_too():
    """Frames of 2026-11-07 show the game drawing its HUD at the window's own size (no stretch), at the
    same place from the middle and the bottom."""
    frame = Image.fromarray(hud(1920, 32, "73,665 [60.01%]", nh=1080).astype(np.uint8))
    assert hudnative.read_level(frame) == 32
    assert hudnative.read_exp(frame) == {"exp": 73665, "pct": 60.01}


def test_the_full_read_gives_them_exact(game_reader):
    """Reader.read takes the HUD's level and EXP from here: exact, so the app counts kills by it and
    trusts the level, at every resolution."""
    frame = native.trim_bars(boxed(hud(1230, 38, "41,476 [17.25%]"), (2560, 1440), 127.459, 2305.071))
    hud_seen = game_reader.read(frame)["hud"]
    assert (hud_seen["level"], hud_seen["level_exact"]) == (38, True)
    assert (hud_seen["exp"], hud_seen["exp_pct"]) == (41476, 17.25)
