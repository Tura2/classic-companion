"""Florina Beach is reached by no portal: Pason in Lith Harbor takes you there, and Pison on the
beach sends you back. A route through them says to talk to them, with the NPC circled."""
import gamedata
import overlay_art

LITH, HENESYS, FLORINA, SHED = 10000000, 10001000, 10007000, 10007010


def bare():
    g = object.__new__(gamedata.GameData)
    g.maps = {LITH: {"id": LITH, "name": "Lith Harbor", "is_town": True,
                     "npc_positions": [{"id": 112, "x": 2750, "y": 1888}, {"id": 104, "x": 2907, "y": 1108}]},
              HENESYS: {"id": HENESYS, "name": "Henesys", "is_town": True},
              FLORINA: {"id": FLORINA, "name": "Florina Beach", "is_town": True,
                        "npc_positions": [{"id": 801, "x": 955, "y": 1076}]},
              SHED: {"id": SHED, "name": "A Look-Out Shed Around the Beach"}}
    g.npc_names = {112: "Pason", 801: "Pison", 104: "VIP Cab"}
    g.portals = {LITH: [{"x": 100, "y": 1800, "name": "west00"}, {"x": 5000, "y": 1700, "name": "east00"}],
                 FLORINA: [{"x": 1860, "y": 700, "name": "east00"}]}
    g.graph = {LITH: {HENESYS: {"x": 100, "y": 1800, "name": "west00"}},
               HENESYS: {LITH: {"x": 0, "y": 0, "name": "east00"}},
               FLORINA: {SHED: {"x": 1860, "y": 700, "name": "east00"}},
               SHED: {FLORINA: {"x": -1921, "y": 177, "name": "west00"}}}
    g.renders = {}
    g.prefetch_maps = lambda ids: None
    g.add_npc_rides()
    return g


def test_henesys_to_the_beach_goes_through_pason():
    steps = bare().route(HENESYS, SHED)
    assert [s["name"] for s in steps] == ["Henesys", "Lith Harbor", "Florina Beach", "A Look-Out Shed Around the Beach"]
    pason = steps[1]
    assert pason["talk"] and pason["portal"] is None
    assert pason["npc"] == {"x": 2750, "y": 1888, "name": "Pason"}
    assert pason["to"]["name"] == "Florina Beach" and pason["hint"]["arrow"]
    assert "talk" not in steps[0] and steps[0]["portal"]


def test_back_from_the_beach_through_pison():
    steps = bare().route(SHED, HENESYS)
    assert [s["name"] for s in steps] == ["A Look-Out Shed Around the Beach", "Florina Beach", "Lith Harbor", "Henesys"]
    assert steps[1]["talk"] and steps[1]["npc"]["name"] == "Pison"


def test_no_ride_without_the_npc_on_the_map():
    g = bare()
    g.maps[LITH]["npc_positions"] = []
    g.graph = {LITH: {HENESYS: {}}, HENESYS: {LITH: {}}, FLORINA: {SHED: {}}, SHED: {FLORINA: {}}}
    g.add_npc_rides()
    assert FLORINA not in g.graph[LITH]


def test_the_card_on_the_game_says_talk_to_pason():
    steps = bare().route(HENESYS, FLORINA)
    img = overlay_art.route_strip({"steps": steps, "i": 1, "to": {"name": "Florina Beach"}})
    assert img.size[0] > 0


def test_real_data_reaches_florina_road(game_reader):
    data = game_reader.data
    steps = data.route(HENESYS, SHED)
    assert steps, "no route from Henesys to the Look-Out Shed"
    talks = [s for s in steps if s.get("talk") and not s.get("taxi")]     # the cab to Lith Harbor aside
    assert [(s["name"], s["npc"]["name"], s["to"]["name"]) for s in talks] == [("Lith Harbor", "Pason", "Florina Beach")]
    back = data.route(SHED, HENESYS)
    assert [(s["name"], s["npc"]["name"]) for s in back if s.get("talk") and not s.get("taxi")] == [("Florina Beach", "Pison")]
