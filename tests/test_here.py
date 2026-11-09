"""The map you're on: its monsters, what they drop (most valuable first), its NPCs and portals."""
from types import SimpleNamespace
from unittest.mock import ANY

import gamedata

ANT1, HENESYS = 10005060, 10001000
CLAW = "Claw Attack Scroll: Intermediate"


def bare(**over):
    g = object.__new__(gamedata.GameData)
    g.maps = {ANT1: {"id": ANT1, "name": "Ant Tunnel I", "street_name": "Dungeon", "map_mark": "Dungeon"},
              HENESYS: {"id": HENESYS, "name": "Henesys", "street_name": "Victoria Road", "map_mark": "Henesys",
                        "is_town": True, "npc_positions": [{"id": 202, "x": 4166, "y": 719}]}}
    g.monsters = [{"id": 21, "name": "Zombie Mushroom", "level": 24, "exp": 45, "thumbnail": "zm",
                   "maps": [{"id": ANT1, "name": "Ant Tunnel I", "count": 11}]},
                  {"id": 19, "name": "Horny Mushroom", "level": 22, "exp": 41, "thumbnail": "hm",
                   "maps": [{"id": ANT1, "name": "Ant Tunnel I", "count": 15}]}]
    g.drops_by_mob = {21: [{"item": CLAW, "rate": None}, {"item": "Orange Potion", "rate": 3.5}],
                      19: [{"item": "Cutlus", "rate": None}]}
    g.market = SimpleNamespace(items={CLAW: {"p": 449999}, "Cutlus": {"p": 9999}})
    g.scroll_rates = {CLAW: 60}
    g.item_ids = {CLAW: 2044701, "Orange Potion": 2000001, "Cutlus": 1302010}
    g.portals = {ANT1: [{"x": 543, "y": 427, "dest_map": str(HENESYS), "type": 2}]}
    g.quest_list = [{"id": "1", "name": "A Chief's Errand", "npc_id": 202}]
    g.npc_names = {202: "Chief Stan"}
    for k, v in over.items():
        setattr(g, k, v)
    return g


def test_load_drops_keys_by_monster_id():
    guide = {"items": {CLAW: {"d": [["Zombie Mushroom", 24, None, 0, "Ant Tunnel I", 0, 21]]},
                       "Orange Potion": {"d": [["Zombie Mushroom", 24, 3.5, 200, "Ant Tunnel I", 0, 21]]}}}
    d = gamedata.load_drops(guide)
    assert {x["item"] for x in d[21]} == {CLAW, "Orange Potion"}
    assert [x["rate"] for x in d[21] if x["item"] == "Orange Potion"] == [3.5]


def test_drops_most_valuable_first_with_scroll_rate():
    h = bare().here(ANT1)
    assert h["drops"][0] == {"item": CLAW, "from": "Zombie Mushroom", "rate": None, "price": 449999,
                             "success": 60, "img": ANY}
    assert [d["item"] for d in h["drops"]] == [CLAW, "Cutlus", "Orange Potion"]   # unpriced last
    assert [m["name"] for m in h["mobs"]] == ["Zombie Mushroom", "Horny Mushroom"] and h["drops_ok"]
    assert h["mobs"][0] == {"id": 21, "name": "Zombie Mushroom", "level": 24, "count": 11, "exp": 45, "img": ANY}
    assert h["portals"] == [{"x": 543, "y": 427, "to": "Henesys", "to_id": HENESYS}]
    assert h["mark"].endswith("map_marks/Dungeon.png") and h["town"] is False


def test_no_drop_file_still_starts():
    h = bare(drops_by_mob={}).here(ANT1)
    assert h["drops"] == [] and h["drops_ok"] is False and len(h["mobs"]) == 2


def test_town_has_npcs_no_drops():
    h = bare().here(HENESYS)
    assert h["town"] and h["mobs"] == [] and h["drops"] == []
    assert {"id": 202, "name": "Chief Stan", "x": 4166, "y": 719, "role": "Quests", "img": ANY} in h["npcs"]
