"""What the capture hands the readers: the game's window without its title bar, and in full screen on
a monitor of another shape without the black bars either (native.trim_bars)."""
import numpy as np
from PIL import Image

import capture
from test_native import boxed, nat_picture  # noqa: F401


def test_the_game_area_is_the_client_without_bars():
    nat = np.clip(nat_picture(1230, 768), 0, 255)
    shot = boxed(nat, (2560, 1440), 127.459, 2305.071)
    area = capture.game_area(shot, (0, 0), (0, 0, 2560, 1440), full=True)
    assert area.size == (2308, 1440) and abs(area.info["game_area"][0] - 1.459) < 0.05


def test_a_window_is_cut_to_its_client_only():
    shot = Image.new("RGB", (1936, 1239), (90, 120, 160))
    area = capture.game_area(shot, (100, 50), (108, 81, 1920, 1200))
    assert area.size == (1920, 1200)


def test_a_window_with_black_sides_is_never_cut():
    """A small map leaves black at the screen's sides in a window: that's the game's picture."""
    nat = np.clip(nat_picture(1228, 768), 0, 255)
    nat[:, :60] = 0
    nat[:, -60:] = 0
    shot = boxed(nat, (1920, 1200), 0, 1920)
    area = capture.game_area(shot, (0, 0), (0, 0, 1920, 1200), full=False)
    assert area.size == (1920, 1200) and "game_area" not in area.info


def test_full_screen_is_the_client_covering_its_monitor():
    assert capture.covers((0, 0, 2560, 1440), (0, 0, 2560, 1440))
    assert capture.covers((2560, 0, 1920, 1200), (2560, 0, 4480, 1200))          # a second monitor
    assert not capture.covers((8, 31, 1920, 1200), (0, 0, 2560, 1440))           # a window on it
    assert not capture.covers((0, 0, 2560, 1440), None)                           # monitor unknown
