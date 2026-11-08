"""The grind tracker fed from the app's reads: where you are comes from the mini map, and a party
quest title read too badly to name its stage still counts as that party quest."""
from types import SimpleNamespace

import grind
import sniper

KC = 103000000
MAPS = {KC: {"name": "Kerning City"}, 80000100: {"name": "1st Accompaniment <2nd Stage>"}}


def app(tmp_path):
    return SimpleNamespace(grind=grind.Grind(tmp_path / "grind.sqlite"), data=SimpleNamespace(maps=MAPS))


def read(a, prof, exp, map_name=None, missed=None):
    seen = {"hud": {"exp": exp, "exp_pct": round(exp / 1000, 2)}}
    if map_name:
        seen["map"] = {"name": map_name}
    if missed:
        seen["map_missed"] = missed
    for _ in range(3):
        sniper.handle_grind(a, seen, prof)


def test_a_cut_short_kpq_title_starts_the_run(tmp_path):
    a, prof = app(tmp_path), {"current_map": KC, "level": 33}
    read(a, prof, 50000, "Kerning City")
    read(a, prof, 50000, missed="1st Accornpanijnent")   # the stage can't be read: still Kerning City in the profile
    assert a.grind.pq == "Kerning PQ"
    read(a, prof, 50500)                                   # no title at all this time: still in the run
    assert a.grind.pq == "Kerning PQ"
    prof["current_map"] = 80000100                         # then a stage is read
    read(a, prof, 51000, "1st Accompaniment <2nd Stage>")
    assert a.grind.pq == "Kerning PQ"
    prof["current_map"] = KC                               # out again
    read(a, prof, 51000, "Kerning City")
    assert a.grind.pq is None
    a.grind.flush()
    rows = a.grind.history(10)
    assert [r["pq"] for r in rows] == ["Kerning PQ"]       # one run, its EXP all in it
    assert rows[0]["exp_gained"] == 1000


def test_other_unread_titles_dont_start_a_run(tmp_path):
    a, prof = app(tmp_path), {"current_map": KC, "level": 33}
    read(a, prof, 50000, "Kerning City")
    read(a, prof, 50100, missed="Kerning Ciy Pharmcy")
    assert a.grind.pq is None and a.grind.map == "Kerning City"
