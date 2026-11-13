"""Routes take the least time, not the fewest portals: the walk across each map counts, from the
portal you came out of to the way out, and a Regular Cab drives you between towns."""
import gamedata

A, B, C, D = 1, 2, 3, 4
H, P, K = 10001000, 10004000, 10003000


def bare(maps, portals, npcs=None):
    g = object.__new__(gamedata.GameData)
    g.maps = {m: {"id": m, "name": f"Map {m}", **extra} for m, extra in maps.items()}
    g.npc_names = npcs or {}
    g.portals = portals
    g.graph = {}
    for mid, ps in portals.items():
        for p in ps:
            g.graph.setdefault(mid, {})[int(p["dest_map"])] = p
    g.renders = {}
    g.prefetch_maps = lambda ids: None
    g.add_npc_rides()
    g.add_taxis()
    return g


def portal(name, x, y, to, back):
    return {"name": name, "x": x, "y": y, "dest_map": str(to), "dest_portal": back, "type": 2}


def test_a_long_walk_loses_to_one_more_portal():
    # A to D: straight through B means crossing all of B (10000 px); through C it's two short walks
    g = bare({A: {}, B: {}, C: {}, D: {}},
             {A: [portal("b", 0, 0, B, "a"), portal("c", 0, 0, C, "a")],
              B: [portal("a", 0, 0, A, "b"), portal("d", 10000, 0, D, "b")],
              C: [portal("a", 0, 0, A, "c"), portal("x", 100, 0, 5, "c"), portal("d", 200, 0, D, "c")],
              D: [portal("b", 0, 0, B, "d"), portal("c", 0, 0, C, "d")]})
    assert [s["id"] for s in g.route(A, D)] == [A, C, D]


def test_the_nearest_of_two_portals_to_the_same_map():
    g = bare({A: {}, B: {}, C: {}},
             {C: [portal("a", 50, 0, A, "c")],
              A: [portal("c", 0, 0, C, "a"), portal("b1", 5000, 0, B, "a"), portal("b2", 100, 0, B, "a")],
              B: [portal("a", 0, 0, A, "b1")]})
    steps = g.route(A, B, came_from=C)          # you stand at A's portal from C, at x 0
    assert steps[0]["portal"]["name"] == "b2"


def test_where_you_came_in_decides_the_way_out():
    g = bare({A: {}, B: {}, C: {}, D: {}},
             {A: [portal("b", 0, 0, B, "a"), portal("c", 0, 0, C, "a")],
              B: [portal("a", 0, 0, A, "b"), portal("d", 0, 0, D, "b")],
              C: [portal("a", 0, 0, A, "c"), portal("d", 0, 0, D, "c")],
              D: [portal("b", 0, 0, B, "d"), portal("c", 9000, 0, C, "d"), portal("e", 9000, 0, 5, "x")]})
    # in D, you come out of B's portal at x 0 or C's at x 9000: leave by the one you're beside
    assert [s["id"] for s in g.route(D, A, came_from=B)] == [D, B, A]
    assert [s["id"] for s in g.route(D, A, came_from=C)] == [D, C, A]


def test_a_cab_between_towns_far_apart():
    road = {H: [portal("r", 0, 0, A, "h")], A: [portal("h", 0, 0, H, "r"), portal("p", 30000, 0, P, "a")],
            P: [portal("a", 0, 0, A, "p")]}
    g = bare({H: {"npc_positions": [{"id": 200, "x": 700, "y": 800}]}, A: {}, P: {}, K: {}}, road, {200: "Regular Cab"})
    steps = g.route(H, P)
    assert [s["id"] for s in steps] == [H, P]
    cab = steps[0]
    assert cab["talk"] and cab["taxi"] and cab["npc"] == {"x": 700, "y": 800, "name": "Regular Cab"}
    assert K in g.taxis[H]                       # every other cab town, a road or not


def test_no_cab_without_one_on_the_map():
    g = bare({H: {}, P: {}}, {})
    assert g.taxis == {} and g.route(H, P) is None


def test_a_short_walk_beats_the_cab():
    g = bare({H: {"npc_positions": [{"id": 200, "x": 0, "y": 0}]}, P: {}},
             {H: [portal("p", 300, 0, P, "h")], P: [portal("h", 0, 0, H, "p")]}, {200: "Regular Cab"})
    assert not g.route(H, P)[0].get("talk")


def test_real_data_rides_a_cab_far_and_walks_near(game_reader):
    data = game_reader.data
    to_perion = data.route(H, P)
    assert [(s["name"], bool(s.get("taxi"))) for s in to_perion] == [("Henesys", True), ("Perion", False)]
    near = data.route(H, data.match_map_name("Henesys Hunting Ground I"))
    assert not any(s.get("talk") for s in near)
