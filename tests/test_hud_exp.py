"""The HUD EXP digit shapes: never a guess, learned only from a known-right EXP."""
import hudexp


def shape(n):
    """A made-up 3x3 shape per digit, distinct enough that none is 'nearly the same' as another."""
    return "3x3:" + format(n * 37 % 512, "09b")


def glyphs(exp, pct):
    return {"num": [shape(int(c)) for c in exp], "pct": [c if c == "." else shape(int(c)) for c in pct]}


def fresh(tmp_path, monkeypatch, known=None):
    monkeypatch.setattr(hudexp, "LEARNED", tmp_path / "exp_digits.json")
    monkeypatch.setattr(hudexp, "SEEDS", tmp_path / "none.json")
    d = hudexp.ExpDigits()
    d.known = dict(known or {})
    return d


def test_unknown_shape_reads_none(tmp_path, monkeypatch):
    d = fresh(tmp_path, monkeypatch, {shape(i): str(i) for i in (7, 3, 6, 5, 0, 1)})
    assert d.read(glyphs("73665", "60.01")) == {"exp": 73665, "pct": 60.01}
    assert d.read(glyphs("73665", "60.21")) is None          # 2 not known yet: no guess


def test_learn_from_stat_then_read(tmp_path, monkeypatch):
    d = fresh(tmp_path, monkeypatch)
    g = glyphs("12849", "48.37")
    assert d.learn(g, 12849, 48)
    assert d.read(glyphs("98421", "84.12")) == {"exp": 98421, "pct": 84.12}
    assert (tmp_path / "exp_digits.json").exists()


def test_conflicting_learn_forgets(tmp_path, monkeypatch):
    d = fresh(tmp_path, monkeypatch, {shape(1): "1"})
    d.learn({"num": [shape(1)], "pct": []}, 7)           # the same shape said to be a 7: one read was wrong
    assert shape(1) not in d.known


def test_digit_count_mismatch_learns_nothing(tmp_path, monkeypatch):
    d = fresh(tmp_path, monkeypatch)
    assert not d.learn(glyphs("1234", "10.00"), 12345, 10 ** 3)
    assert d.known == {}


# HUD-only pictures of 2026-11-07 (windowed 1920x1080, level 33), the rest painted gray; git-ignored
import pytest  # noqa: E402
from pathlib import Path  # noqa: E402

CASES = Path(__file__).resolve().parent.parent / "samples" / "cases"
LV = ("LV.", 416.0, 1046.0, 29.0, 19.0)


@pytest.mark.parametrize("name,digits,pct", [("hudexp_comma_31576", 5, 5), ("hudexp_30095", 5, 5),
                                             ("hudexp_29258", 5, 5)])
def test_live_hud_splits_into_the_right_glyphs(name, digits, pct):
    """The EXP bar's fill edge isn't a bracket; a narrow 1 by a faint comma doesn't cut the number;
    the bold "EXP" letters running together aren't digits."""
    p = CASES / f"{name}.png"
    if not p.exists():
        pytest.skip("case pictures are local only")
    from PIL import Image
    g = hudexp.exp_glyphs(Image.open(p).convert("RGB"), LV)
    assert len(g["num"]) == digits and len(g["pct"]) == pct and g["pct"][2] == "."


def test_a_near_shape_between_two_digits_is_not_read(tmp_path, monkeypatch):
    """3 and 9 differ by a few pixels: a shape about as close to both is no digit."""
    base = ["1"] * 100
    nine, three, between = base[:], base[:], base[:]
    nine[10], three[20] = "0", "0"            # 9 and 3 differ in two pixels
    between[10] = "0"; between[20] = "0"; between[55] = "0"   # as close to one as to the other
    d = fresh(tmp_path, monkeypatch, {"10x10:" + "".join(nine): "9", "10x10:" + "".join(three): "3"})
    assert d.digit("10x10:" + "".join(between)) is None
    clear = nine[:]; clear[70] = "0"          # one pixel off a 9, three off a 3
    assert d.digit("10x10:" + "".join(clear)) is None   # 0.99 vs 0.97: not clear enough either
