"""What the capture hands the readers: the game's window without its title bar, and in full screen on
a monitor of another shape without the black bars either (native.trim_bars)."""
import numpy as np
from PIL import Image

import capture
from test_native import boxed, nat_picture


def test_the_game_area_is_the_client_without_bars():
    nat = np.clip(nat_picture(1230, 768), 0, 255)
    shot = boxed(nat, (2560, 1440), 127.459, 2305.071)
    area = capture.game_area(shot, (0, 0), (0, 0, 2560, 1440))
    assert area.size == (2308, 1440)


def test_a_window_is_cut_to_its_client_only():
    shot = Image.new("RGB", (1936, 1239), (90, 120, 160))
    area = capture.game_area(shot, (100, 50), (108, 81, 1920, 1200))
    assert area.size == (1920, 1200)
