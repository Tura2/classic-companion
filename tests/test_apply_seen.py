"""What the app saves from a read (sniper.App.apply_seen), through the save gate, on a stand-in app."""
from types import SimpleNamespace

import sniper
from trust import Gate


def app(profile):
    saved = []
    state = {"profile": profile, "nav": None, "guide": None, "save_profile": lambda: saved.append(dict(profile))}
    return SimpleNamespace(
        state=state, saved=saved, gate=Gate({"Arrow Blow": 20}, {"Arrow Blow": "Archer"}),
        agree=sniper.Agree(), notice=sniper.Agree(2), counts=sniper.SteadyCounts(),
        reader=SimpleNamespace(quests_by_name={}, learn_level=lambda level: None),
        data=SimpleNamespace(chains={}, quest_list=[]), shop_rows=[], overlay=SimpleNamespace(region=None),
        drawing=lambda: False, publish=lambda: None, apply_map=lambda seen, prof: None)


def stat(**kw):
    return {"stat": {"name": "Tura1", "job": "Hunter", "level": 32, "str_base": 30, "dex_base": 142, "int_base": 4,
                     "luk_base": 4, "ap": 0, "acc": 72, **kw}, "windows": {}}


def test_a_misread_level_is_not_saved():
    a = app({"name": "Tura1", "job": "Hunter", "level": 32, "mesos": 385973})
    sniper.App.apply_seen(a, stat(level=132), None)
    assert a.state["profile"]["level"] == 32


def test_stats_that_add_up_are_saved():
    a = app({"name": "Tura1", "job": "Hunter", "level": 32})
    sniper.App.apply_seen(a, stat(), None)
    assert a.state["profile"]["stats"] == {"str": 30, "dex": 142, "int": 4, "luk": 4}


def test_another_character_changes_nothing():
    a = app({"name": "Tura1", "job": "Hunter", "level": 32, "mesos": 385973})
    for _ in range(3):
        sniper.App.apply_seen(a, {**stat(name="Offir", job="Beginner", level=10), "inventory": {"mesos": 500}}, None)
    p = a.state["profile"]
    assert (p["name"], p["job"], p["level"], p["mesos"]) == ("Tura1", "Hunter", 32, 385973)
    assert a.state["game"]["other_name"] == "Offir"
