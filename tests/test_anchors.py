"""Finding windows by their title picture (anchors.py), on the real game cases."""
import numpy as np
import pytest
from PIL import Image, ImageDraw

from casekit import APP, CASES

import anchors

# where a clean OCR read of each case puts each title (x, y), at the size the case was taken
WHERE = {
    ("fm_quest_window", "stat"): (778, 662), ("fm_tooltip", "stat"): (778, 662),
    ("fm_title_glued", "stat"): (778, 662),     # OCR glued a tooltip's edge on: (771, 660)
    ("hunt_moved_a", "stat"): (827, 46), ("hunt_moved_b", "stat"): (827, 46), ("hunt_popup", "stat"): (827, 46),
    ("fm_quest_window", "inventory"): (386, 636), ("fm_quest_window", "quest"): (250, 17),
    ("fm_quest_window", "minimap"): (12, 15), ("hunt_moved_a", "helper"): (1435, 65),
    ("skills_1st", "skills"): (1068, 87), ("skills_1st", "minibar"): (455, 109),
}


def frame(case):
    return Image.open(CASES / f"{case}.png").convert("RGB")


@pytest.fixture
def titles(tmp_path):
    return anchors.Titles(tmp_path, res_dir=APP)


def test_ncc_matches_its_definition():
    rng = np.random.default_rng(1)
    img, tpl = rng.random((20, 30)), rng.random((5, 7))
    got = anchors.ncc(img, tpl)
    t = tpl - tpl.mean()
    want = np.empty((16, 24))
    for y in range(16):
        for x in range(24):
            w = img[y:y + 5, x:x + 7] - img[y:y + 5, x:x + 7].mean()
            want[y, x] = (w * t).sum() / np.sqrt((w * w).sum() * (t * t).sum())
    assert np.allclose(got, want, atol=1e-4)


@pytest.mark.skipif(not CASES.exists(), reason="no cases on this PC")
@pytest.mark.parametrize("case,name", sorted(WHERE))
def test_title_found_where_a_clean_read_puts_it(titles, case, name):
    found = titles.find(frame(case), 1.0)
    assert name in found
    # within a pixel: OCR's box moves a pixel with how the game draws the text where the window sits
    assert abs(found[name][1] - WHERE[case, name][0]) <= 1 and abs(found[name][2] - WHERE[case, name][1]) <= 1


@pytest.mark.skipif(not CASES.exists(), reason="no cases on this PC")
def test_stat_found_at_1080_with_titles_cut_at_1200(titles):
    found = titles.find(frame("res_1080"), 1080 / 1200)
    assert abs(found["stat"][1] - 821) <= 2 and abs(found["stat"][2] - 40) <= 2


@pytest.mark.skipif(not CASES.exists(), reason="no cases on this PC")
def test_half_covered_title_is_not_found(titles):
    img = frame("fm_quest_window")
    ImageDraw.Draw(img).rectangle((775, 659, 841, 674), fill=(128, 128, 128))
    assert "stat" not in titles.find(img, 1.0)


def test_plain_frame_finds_nothing(titles):
    assert titles.find(Image.new("RGB", (1920, 1200), (128, 128, 128)), 1.0) == {}


@pytest.mark.skipif(not CASES.exists(), reason="no cases on this PC")
def test_learned_title_for_a_new_height(tmp_path):
    img = frame("res_1080")
    anchors.Titles(tmp_path, res_dir=APP).learn(img, "stat", ("CHARACTER STAT", 821, 40, 113, 8))
    assert (tmp_path / "cache" / "titles" / "1080" / "stat.png").exists()
    again = anchors.Titles(tmp_path, res_dir=APP)
    found = again.find(img, 1080 / 1200)
    assert (round(found["stat"][1]), round(found["stat"][2])) == (821, 40)
    assert again.scores["stat"] >= 0.98
