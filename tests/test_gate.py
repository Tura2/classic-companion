"""The save gate: what a read may change in the profile, checked against the game's rules.
Numbers are Tura1's, measured live on 2026-11-06 (Hunter, level 32)."""
import pytest

import reader
from trust import Gate

FIRST = {"Critical Shot": 15, "The Eye of Amazon": 15, "Focus": 10, "Power Knockback": 0, "Arrow Blow": 20, "Double Shot": 1}
HUNTER = {"Bow Mastery": 5, "Amazon's Judgement": 0, "Final Attack: Bow": 0, "Bow Booster": 1, "Soul Arrow: Bow": 0, "Arrow Bomb": 1}
SKILL_MAX = {**{k: 20 for k in FIRST}, **{k: 20 for k in HUNTER}, "Three Snails": 3}
SKILL_JOB = {**{k: "Archer" for k in FIRST}, **{k: "Hunter" for k in HUNTER}, "Three Snails": "Beginner"}


def gate():
    return Gate(SKILL_MAX, SKILL_JOB)


def profile(**kw):
    return {"name": "Tura1", "level": 32, "mesos": 385973, "skills_now": dict(FIRST), **kw}


def stat(**kw):
    return {"stat": {"name": "Tura1", "level": 32, "str_base": 30, "dex_base": 142, "int_base": 4, "luk_base": 4,
                     "ap": 0, **kw}}


def test_a_misread_level_needs_three_reads():
    g, prof = gate(), profile()
    assert "level" not in g.check(prof, stat(level=132))
    assert "level" not in g.check(prof, stat(level=132))
    assert g.check(prof, stat(level=132))["level"] == 132


def test_a_level_up_counts_at_once():
    assert gate().check(profile(), stat(level=33, dex_base=147))["level"] == 33


def test_stats_that_add_up_are_saved():
    got = gate().check(profile(), stat())
    assert got["stats"] == {"str": 30, "dex": 142, "int": 4, "luk": 4} and got["ap"] == 0


def test_stats_that_dont_add_up_are_not():
    assert "stats" not in gate().check(profile(), stat(dex_base=152, ap=1))


def test_a_big_mesos_change_needs_two_reads():
    g, prof = gate(), profile()
    assert "mesos" not in g.check(prof, {"inventory": {"mesos": 61}})
    assert g.check(prof, {"inventory": {"mesos": 61}})["mesos"] == 61


def test_another_name_is_not_written_and_blocks_the_rest():
    g, prof = gate(), profile()
    for _ in range(2):
        g.check(prof, stat(name="Offir"))
    got = g.check(prof, stat(name="Offir"))
    assert got.get("other_name") == "Offir"
    assert "name" not in got and "stats" not in got and "level" not in got


def test_a_right_name_is_never_put_wrong():
    got = gate().check(profile(), stat(name="Tural"))      # "Tura1" saved, a 1 read as l
    assert "name" not in got and "blocked" not in got


def test_skills_that_add_up_are_saved():
    got = gate().check(profile(), {"skills": {"levels": dict(HUNTER), "sp": 0}})
    assert got["skills_now"] == {**FIRST, **HUNTER} and got["sp"] == 0


def test_skills_that_dont_add_up_are_not():
    assert "skills_now" not in gate().check(profile(), {"skills": {"levels": {**HUNTER, "Bow Mastery": 8}, "sp": 0}})


def test_a_skill_never_goes_down_or_past_its_max():
    assert "skills_now" not in gate().check(profile(), {"skills": {"levels": {"Arrow Blow": 2}, "sp": 0}})
    assert "skills_now" not in gate().check(profile(), {"skills": {"levels": {"Arrow Blow": 21}, "sp": 0}})


def test_a_character_the_rule_doesnt_fit_is_saved_after_five_reads():
    g, prof = gate(), profile()
    read = {"skills": {"levels": dict(HUNTER), "sp": 3}}        # off by 3: a magician's job advance is at 8
    for _ in range(4):
        assert "skills_now" not in g.check(prof, read)
    assert g.check(prof, read)["sp"] == 3


def test_a_learned_digit_shape_is_never_remapped(tmp_path, monkeypatch):
    from PIL import Image
    monkeypatch.setattr(reader, "DIGITS_FILE", tmp_path / "digits.json")
    d = reader.LevelDigits()
    shape = Image.new("L", (10, 11), 255)
    d.learn([shape], 9)
    d.learn([shape], 8)
    assert reader._bits(shape) not in d.known


def test_a_shape_a_pixel_off_reads_as_the_learned_digit(tmp_path, monkeypatch):
    from PIL import Image, ImageDraw
    monkeypatch.setattr(reader, "DIGITS_FILE", tmp_path / "digits.json")
    d = reader.LevelDigits()
    nine = Image.new("L", (10, 11), 255)
    ImageDraw.Draw(nine).ellipse((1, 0, 8, 6), outline=0)
    ImageDraw.Draw(nine).line((8, 3, 8, 10), fill=0)
    d.learn([nine], 9)
    near = nine.copy()
    near.putpixel((0, 10), 0)                # the game draws the same digit a pixel differently
    assert d.read([near]) == (9, True)


def test_nothing_is_saved_while_another_name_shows():
    got = gate().check(profile(), {**stat(name="Offir", level=10), "inventory": {"mesos": 500}})
    assert not ({"level", "stats", "mesos", "acc", "skills_now"} & set(got))


def test_a_name_saved_misread_by_the_old_reader_is_put_right():
    # profiles saved before this fix hold "Tural": the new read "Tura1" is the same character
    g, prof = gate(), profile(name="Tural")
    got = g.check(prof, stat())
    assert got.get("name") == "Tura1" and "blocked" not in got and "stats" in got


def test_learn_level_ignores_digits_from_an_older_read(tmp_path, monkeypatch):
    import gamedata  # noqa: F401  (Reader needs no data for this)
    from PIL import Image
    monkeypatch.setattr(reader, "DIGITS_FILE", tmp_path / "digits.json")
    r = reader.Reader.__new__(reader.Reader)
    r.digits, r.last_glyphs = reader.LevelDigits(), [Image.new("L", (10, 11), 255)] * 2
    r.start_read()                       # a new read that doesn't see the HUD
    r.learn_level(33)
    assert r.digits.known == {}
