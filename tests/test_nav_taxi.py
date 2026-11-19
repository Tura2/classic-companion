"""Town to town, Go to walks unless you ask for the cab (it costs mesos); a Beginner, who rides 90 %
off, gets the cab first. Either way the other is one button away."""
import queue

import companion
from test_router import A, H, P, bare, portal


def towns():
    """Henesys and Perion 30000 px of road apart, a cab in Henesys."""
    road = {H: [portal("r", 0, 0, A, "h")], A: [portal("h", 0, 0, H, "r"), portal("p", 30000, 0, P, "a")],
            P: [portal("a", 0, 0, A, "p")]}
    return bare({H: {"npc_positions": [{"id": 200, "x": 700, "y": 800}]}, A: {}, P: {}}, road, {200: "Regular Cab"})


def state_for(job, tmp_path, monkeypatch):
    monkeypatch.setattr(companion, "PROFILE", tmp_path / "profile.json")
    return {"profile": {"job": job, "level": 30, "current_map": H}, "queue": queue.Queue(), "nav": None}


def test_a_route_walks_and_offers_the_cab():
    nav = companion.plan(towns(), {"job": "Hunter"}, H, P)
    assert [s["id"] for s in nav["steps"]] == [H, A, P]
    assert nav["cab"] and not nav["taxi"]


def test_a_beginner_rides_first():
    nav = companion.plan(towns(), {"job": "Beginner"}, H, P)
    assert [s["id"] for s in nav["steps"]] == [H, P] and nav["taxi"] and nav["cab"]


def test_no_cab_offered_where_none_helps():
    g = towns()
    nav = companion.plan(g, {"job": "Hunter"}, A, P)       # out on the road: no cab there
    assert not nav["cab"] and not nav["taxi"]


def test_the_cab_button_switches_the_route_and_back(tmp_path, monkeypatch):
    g, state = towns(), state_for("Hunter", tmp_path, monkeypatch)
    state["nav"] = {**companion.plan(g, state["profile"], H, P), "to": {"id": P}}
    companion.choose_taxi(g, state, True)
    assert [s["id"] for s in state["nav"]["steps"]] == [H, P] and state["nav"]["taxi"]
    companion.choose_taxi(g, state, False)
    assert [s["id"] for s in state["nav"]["steps"]] == [H, A, P] and not state["nav"]["taxi"]


def test_off_the_route_it_replans_the_way_you_chose(tmp_path, monkeypatch):
    g, state = towns(), state_for("Beginner", tmp_path, monkeypatch)
    state["nav"] = {**companion.plan(g, state["profile"], H, P, taxi=False), "to": {"id": P}}
    state["profile"]["current_map"] = 99
    g.maps[99] = {"id": 99, "name": "Map 99"}
    g.portals[99] = [portal("h", 0, 0, H, "x")]
    g.graph[99] = {H: g.portals[99][0]}
    companion.set_current(g, state, 99)                     # wandered off: still walking, as chosen
    assert not state["nav"]["taxi"] and [s["id"] for s in state["nav"]["steps"]] == [99, H, A, P]


def test_arriving_ends_the_route(tmp_path, monkeypatch):
    # you got there: walking on from the destination ends the route, it doesn't send you back
    g, state = towns(), state_for("Hunter", tmp_path, monkeypatch)
    state["nav"] = {**companion.plan(g, state["profile"], H, P, taxi=False), "to": {"id": P}}
    companion.set_current(g, state, A)
    companion.set_current(g, state, P)                      # arrived
    assert state["nav"]["steps"][state["nav"]["i"]].get("arrived")
    companion.set_current(g, state, A)                      # and walked on
    assert state["nav"] is None


def test_a_quest_guide_still_replans_after_arriving(tmp_path, monkeypatch):
    # the quest guide's route follows the quest (guide_plan), so it isn't ended by walking on
    g, state = towns(), state_for("Hunter", tmp_path, monkeypatch)
    state["nav"] = {**companion.plan(g, state["profile"], H, P, taxi=False), "to": {"id": P}, "guide_to": P}
    companion.set_current(g, state, P)
    companion.set_current(g, state, A)
    assert state["nav"] is not None and state["nav"]["steps"][state["nav"]["i"]]["id"] == A
