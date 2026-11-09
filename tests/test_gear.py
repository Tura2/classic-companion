"""Gear: the best item per slot, with what the Equip window and its tooltip need, and Overall only when it beats top + bottom."""
from types import SimpleNamespace

import gamedata


def eq(i, name, slot, dex):
    return {"id": i, "name": name, "sub_category": slot, "req_job_label": "Bowman",
            "stats": {"reqLevel": 30, "incDEX": dex, "tuc": 7}}


def gear_with(top, bottom, overall=14):
    g = object.__new__(gamedata.GameData)
    g.equips = [eq(1050010, "Robe", "Overall", overall), eq(1040042, "Armor", "Top", top), eq(1060034, "Pants", "Bottom", bottom),
                {"id": 1452004, "name": "Ryden", "sub_category": "Weapon", "weapon_type": "Bow", "req_job_label": "Bowman",
                 "attack_speed_label": "Normal", "stats": {"reqLevel": 30, "incPAD": 50, "attackSpeed": 6, "tuc": 7}}]
    g.market = SimpleNamespace(items={}, cozy=SimpleNamespace(get=lambda n: None))
    return g.gear("Hunter", 33)


def test_overall_when_it_beats_top_and_bottom():
    assert gear_with(top=5, bottom=6)["overall_instead"] is True       # 42 against 15 + 18


def test_top_and_bottom_when_they_beat_the_overall():
    assert gear_with(top=9, bottom=7)["overall_instead"] is False      # 42 against 27 + 21


def test_entries_carry_id_job_and_attack_speed():
    g = gear_with(top=5, bottom=6)
    bow = [s for s in g["slots"] if s["slot"] == "Weapon"][0]["now"][0]
    assert (bow["id"], bow["job"], bow["speed_n"]) == (1452004, "Bowman", 6)
