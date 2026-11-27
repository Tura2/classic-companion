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


def test_another_unread_title_ends_the_guess(tmp_path):
    a, prof = app(tmp_path), {"current_map": KC, "level": 33}
    read(a, prof, 50000, "Kerning City")
    read(a, prof, 50000, missed="1st Accornpanijnent")
    read(a, prof, 50500)
    assert a.grind.pq == "Kerning PQ"
    read(a, prof, 50600, missed="Kerning")             # back in town, its title read short
    assert a.grind.pq is None and a.grind.map == "Kerning City"


def test_other_unread_titles_dont_start_a_run(tmp_path):
    a, prof = app(tmp_path), {"current_map": KC, "level": 33}
    read(a, prof, 50000, "Kerning City")
    read(a, prof, 50100, missed="Kerning Ciy Pharmcy")
    assert a.grind.pq is None and a.grind.map == "Kerning City"


def test_a_valuable_pickup_is_shared_and_a_cheap_one_isnt(tmp_path):
    a = app(tmp_path)
    shared = []
    a.state = {"discord_share": lambda kind, data, key: shared.append((kind, data, key)) or True}
    a.data = SimpleNamespace(maps=MAPS, item_ids={"Work Gloves": 1082002},
                             market=SimpleNamespace(items={"Work Gloves": {"p": 120000}, "Snail Shell": {"p": 50}}))
    sniper.handle_corner(a, [("item", "Work Gloves", 1), ("item", "Snail Shell", 4), ("item", "Mystery Box", 1)])
    assert [(k, d["item"], d["item_id"], d["median"]) for k, d, _ in shared] == [("drop", "Work Gloves", 1082002, 120000)]
    assert shared[0][2].startswith("drop:") and "Work Gloves" in shared[0][2]
    assert a.grind.loot == {"Work Gloves": 1, "Snail Shell": 4, "Mystery Box": 1}


def test_pickups_without_discord_are_only_counted(tmp_path):
    a = app(tmp_path)
    sniper.handle_corner(a, [("item", "Work Gloves", 1)])
    assert a.grind.loot == {"Work Gloves": 1}


def test_a_finished_grind_card_is_shared_once_by_its_key(tmp_path):
    shared = []
    a = SimpleNamespace(state={"discord_share": lambda kind, data, key: shared.append((kind, data, key)) or True})
    card = {"id": 7, "start": 1000.0, "map": "Ant Tunnel I", "pq": None, "active_s": 660.0, "exp_gained": 5,
            "exp_hr": 100.0, "level_start": 40, "level_end": 40, "job": None, "data": {}}
    sniper.share_grind(a, card)
    sniper.share_grind(a, dict(card, active_s=100.0))     # too short: nothing
    assert [(k, d["map"], key) for k, d, key in shared] == [("grind", "Ant Tunnel I", "grind:7:1000")]
