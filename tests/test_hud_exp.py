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
