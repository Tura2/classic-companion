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
def test_learned_title_for_a_new_scale(tmp_path):
    img = frame("res_1080")
    anchors.Titles(tmp_path, res_dir=APP).learn(img, "stat", ("CHARACTER STAT", 821, 40, 113, 8), 0.9)
    assert (tmp_path / "cache" / "titles" / "s900" / "stat.png").exists()
    again = anchors.Titles(tmp_path, res_dir=APP)
    found = again.find(img, 1080 / 1200)
    assert (round(found["stat"][1]), round(found["stat"][2])) == (821, 40)
    assert again.scores["stat"] >= 0.98


def test_shrink_averages_blocks():
    a = np.arange(36, dtype=float).reshape(6, 6)
    assert np.allclose(anchors._shrink(a, 3), [[7, 10], [25, 28]])


@pytest.mark.skipif(not CASES.exists(), reason="no cases on this PC")
@pytest.mark.parametrize("case", ["fm_quest_window", "skills_1st", "hunt_moved_a"])
def test_rough_first_finds_what_the_exact_search_does(case, tmp_path, monkeypatch):
    f = frame(case)
    s = f.height / 1200
    rough = anchors.Titles(tmp_path, res_dir=APP).find(f, s, None, None)
    monkeypatch.setattr(anchors, "BIG", 10 ** 12)          # every area searched exactly, as before
    exact = anchors.Titles(tmp_path, res_dir=APP).find(f, s, None, None)
    assert {k: v[1:3] for k, v in rough.items()} == {k: v[1:3] for k, v in exact.items()}


def test_two_copies_of_a_title_find_neither(titles):
    tpl = titles.template("inventory", 1.0).astype(np.uint8)
    g = Image.new("L", (1920, 1200), 128)
    pic = Image.fromarray(tpl)
    g.paste(pic, (300, 200))
    g.paste(pic, (1200, 900))                               # the same title twice: no telling which
    assert titles._search(np.asarray(g, dtype=np.float32), titles.template("inventory", 1.0), (0, 0, 1920, 1200)) is None


def test_learned_title_keyed_by_scale(tmp_path):
    # a title learned by height before the update is never used; one learned at a scale only there
    from conftest import case_frame
    t = anchors.Titles(tmp_path, res_dir=APP)
    old = tmp_path / "cache" / "titles" / "1200" / "stat.png"
    old.parent.mkdir(parents=True)
    Image.new("L", (10, 3)).save(old)
    assert t.template("stat", 1.0).shape != (3, 10)
    f = case_frame("stat_1080_glued")
    line = t.find(f, 0.9, full={"stat"}, names={"stat"})["stat"]
    t.learn(f, "stat", line, 0.9)
    assert (tmp_path / "cache" / "titles" / "s900" / "stat.png").exists()
    assert t.template("stat", 1.0).shape != t.template("stat", 0.9).shape


def test_ncc_with_a_shared_frame_cache_is_the_same():
    # a whole-frame look shares the frame's FFT and running sums between titles (review, 2026-11-19)
    rng = np.random.default_rng(5)
    img = rng.random((300, 420)).astype(np.float32)
    cache = {}
    for th, tw in ((10, 80), (12, 76), (10, 84)):
        tpl = img[50:50 + th, 100:100 + tw].copy()
        assert np.allclose(anchors.ncc(img, tpl, cache), anchors.ncc(img, tpl))
    assert cache                                    # something was kept for the next title


@pytest.mark.skipif(not CASES.exists(), reason="no cases on this PC")
def test_whole_frame_find_same_with_shared_cache(tmp_path):
    img = frame("fm_quest_window")
    names = {"stat", "inventory", "skills", "helper", "quest"}
    a = anchors.Titles(tmp_path / "a", res_dir=APP).find(img, 1.0, None, names, names=names)
    b = anchors.Titles(tmp_path / "b", res_dir=APP)
    b.share = False                                  # the old way, title by title
    assert b.find(img, 1.0, None, names, names=names) == a


# ---- learning a title at a new UI scale only keeps what looks like the title (live 2026-11-26: at
# UI 0.64, cut from OCR's box a few px off, the inventory's and skills' titles were kept cut in half
# and the helper's as a blank patch; then the skills window was taken for the inventory, the
# inventory was found nowhere and the helper's quests flickered)

def _title_on_gray(t, name, s, at=(300, 200)):
    tpl = t.shrunk(name, s).astype(np.uint8)
    img = Image.new("L", (1200, 800), 128)
    img.paste(Image.fromarray(tpl), at)
    return img.convert("RGB"), tpl


def _line(t, name, s, x, y):
    dx, dy, lw, lh = t._offsets(name, s)
    return (t.boxes[name]["text"], x + dx, y + dy, lw, lh)


@pytest.mark.parametrize("name", ["inventory", "skills", "helper", "stat"])
def test_learn_cuts_the_title_where_it_is_when_ocr_is_a_few_px_off(name, tmp_path):
    t = anchors.Titles(tmp_path, res_dir=APP)
    img, tpl = _title_on_gray(t, name, 0.64)
    path = t.learn(img, name, _line(t, name, 0.64, 303, 198), 0.64)     # OCR's box 3 px right, 2 up
    assert path is not None and path.exists()
    kept = np.asarray(Image.open(path), dtype=np.float32)
    assert kept.shape == tpl.shape and np.allclose(kept, tpl)
    found = anchors.Titles(tmp_path, res_dir=APP).find(img, 0.64, names={name})
    assert (round(found[name][1] - t._offsets(name, 0.64)[0]), round(found[name][2] - t._offsets(name, 0.64)[1])) == (300, 200)


def test_learn_keeps_nothing_where_there_is_no_title(tmp_path):
    t = anchors.Titles(tmp_path, res_dir=APP)
    flat = Image.new("RGB", (1200, 800), (190, 190, 190))        # the helper's see-through bar: a blank patch
    assert t.learn(flat, "helper", _line(t, "helper", 0.64, 300, 200), 0.64) is None
    assert not t.learned_path("helper", 0.64).exists()
    noise = Image.fromarray(np.random.default_rng(3).integers(0, 255, (800, 1200), dtype=np.uint8)).convert("RGB")
    assert t.learn(noise, "inventory", _line(t, "inventory", 0.64, 300, 200), 0.64) is None


def test_a_bad_learned_title_kept_before_is_thrown_away(tmp_path):
    t = anchors.Titles(tmp_path, res_dir=APP)
    bad = t.learned_path("inventory", 0.64)
    bad.parent.mkdir(parents=True)
    shape = t.shrunk("inventory", 0.64).shape
    Image.new("L", shape[::-1], 200).save(bad)                    # a flat patch, kept by an older version
    assert np.allclose(t.template("inventory", 0.64), t.shrunk("inventory", 0.64))
    assert not bad.exists()                                       # so it can be learned again, right this time


def test_a_good_learned_title_is_kept(tmp_path):
    t = anchors.Titles(tmp_path, res_dir=APP)
    img, tpl = _title_on_gray(t, "stat", 0.64)
    t.learn(img, "stat", _line(t, "stat", 0.64, 300, 200), 0.64)
    again = anchors.Titles(tmp_path, res_dir=APP)
    assert again.learned_path("stat", 0.64).exists() and np.allclose(again.template("stat", 0.64), tpl)
