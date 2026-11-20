"""A captured frame (Windows Graphics Capture's BGRA buffer) into the RGB picture every reader uses,
with one copy: 2026-11-20 the old way (numpy fancy index, tobytes, convert) cost 25 ms a frame at
seven frames a second, ~14% of a core; Pillow's BGRX decoder makes the same pixels in ~7 ms."""
import numpy as np
from PIL import Image

import capture


def old_way(buf, w, h):
    return Image.frombuffer("RGBA", (w, h), buf[:, :, [2, 1, 0, 3]].tobytes()).convert("RGB")


def test_same_pixels_as_before():
    buf = (np.random.default_rng(1).random((120, 200, 4)) * 255).astype(np.uint8)
    img = capture.frame_to_rgb(buf, 200, 120)
    assert img.mode == "RGB" and img.size == (200, 120)
    assert img.tobytes() == old_way(buf, 200, 120).tobytes()


def test_padded_rows_keep_the_frame_size():
    buf = (np.random.default_rng(2).random((120, 208, 4)) * 255).astype(np.uint8)
    img = capture.frame_to_rgb(buf, 200, 120)
    assert img.size == (200, 120)
    assert img.tobytes() == old_way(np.ascontiguousarray(buf[:, :200]), 200, 120).tobytes()


def test_the_picture_owns_its_pixels():
    buf = np.full((10, 10, 4), 50, np.uint8)
    img = capture.frame_to_rgb(buf, 10, 10)
    buf[:] = 200
    assert img.getpixel((0, 0)) == (50, 50, 50)
