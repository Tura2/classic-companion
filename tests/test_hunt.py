"""Train's monster search: find a monster by name, then the maps it lives on, nearest to you first."""
import gamedata

HENESYS, FIELD, ANT1, ANT2, ISLAND = 1, 2, 3, 4, 5


def bare():
    g = object.__new__(gamedata.GameData)
    g.maps = {i: {"id": i, "name": n, "street_name": "Victoria Road"} for i, n in
              [(HENESYS, "Henesys"), (FIELD, "Henesys Hunting Ground I"), (ANT1, "Ant Tunnel I"),
               (ANT2, "Ant Tunnel II"), (ISLAND, "Snail Hunting Ground I")]}
    # Henesys -> Field -> Ant Tunnel I -> Ant Tunnel II; the island can't be walked to
    g.graph = {HENESYS: {FIELD: {}}, FIELD: {HENESYS: {}, ANT1: {}}, ANT1: {FIELD: {}, ANT2: {}}, ANT2: {ANT1: {}}}
    g.renders = {}
    g.monsters = [
        {"id": 21, "name": "Zombie Mushroom", "level": 24, "hp": 1000, "exp": 45, "thumbnail": "zm",
         "maps": [{"id": ANT2, "count": 20}, {"id": ANT1, "count": 6}, {"id": ISLAND, "count": 30}]},
        {"id": 22, "name": "Zombie Mushroom", "level": 24, "hp": 1000, "exp": 45, "special": True,
         "maps": [{"id": FIELD, "count": 50}]},                        # a party quest copy: not a hunting spot
        {"id": 19, "name": "Horny Mushroom", "level": 22, "hp": 800, "exp": 41, "maps": [{"id": ANT1, "count": 15}]},
        {"id": 99, "name": "Zombie Lupin", "level": 33, "hp": 2000, "exp": 80, "maps": []},   # spawns nowhere
    ]
    return g


def test_find_mobs_by_name_once_each():
    hits = bare().find_mobs("zombie mush")
    assert [h["name"] for h in hits] == ["Zombie Mushroom"]
    assert hits[0]["level"] == 24 and hits[0]["img"].endswith("monsters/zm.png")


def test_find_mobs_equal_matches_nearest_your_level_first():
    g = bare()
    g.monsters.append({"id": 30, "name": "Zombie Mushmom", "level": 55, "maps": [{"id": ANT2, "count": 1}]})
    assert [h["name"] for h in g.find_mobs("zombie mush", level=35)][:2] == ["Zombie Mushroom", "Zombie Mushmom"]


def test_find_mobs_skips_monsters_that_spawn_nowhere():
    assert [h["name"] for h in bare().find_mobs("Zombie")] == ["Zombie Mushroom"]


def test_hunt_nearest_first_then_unreachable_last():
    h = bare().hunt("Zombie Mushroom", HENESYS)
    assert h["mob"]["name"] == "Zombie Mushroom" and h["mob"]["exp"] == 45
    assert [(m["id"], m["hops"], m["count"]) for m in h["maps"]] == [(ANT1, 2, 6), (ANT2, 3, 20), (ISLAND, None, 30)]
    assert h["maps"][0]["name"] == "Ant Tunnel I"


def test_hunt_ignores_party_quest_copies():
    assert FIELD not in [m["id"] for m in bare().hunt("Zombie Mushroom", HENESYS)["maps"]]


def test_hunt_you_are_there():
    assert bare().hunt("Horny Mushroom", ANT1)["maps"][0]["hops"] == 0


def test_hunt_without_a_current_map_busiest_first():
    h = bare().hunt("Zombie Mushroom", None)
    assert [(m["id"], m["hops"]) for m in h["maps"]] == [(ISLAND, None), (ANT2, None), (ANT1, None)]


def test_hunt_unknown_monster():
    assert bare().hunt("Nope", HENESYS) is None
