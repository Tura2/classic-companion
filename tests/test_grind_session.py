"""The grind session's tallies for Now: kills (named from the corner's EXP lines, else estimated
from the HUD), loot and mesos picked up, where the EXP bar started, the chart over the whole
session, the session before this one, and every map's EXP, kills and mesos an hour."""
from test_grind import NEED, feed, pct, tracker


def test_kills_loot_and_mesos_add_up(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(10)])
    for _ in range(3):
        g.add_kill("Jr. Wraith", t)
    g.add_kill(None, t)
    g.add_loot("Tablecloth", 1, t)
    g.add_loot("Tablecloth", 2, t)
    g.add_mesos(15, t)
    s = g.summary(t)
    assert s["kills"] == [{"name": "Jr. Wraith", "count": 3}, {"name": None, "count": 1}] and s["kills_total"] == 4
    assert s["loot"] == [{"name": "Tablecloth", "count": 3}] and s["mesos_picked"] == 15


def test_kills_fall_back_to_the_hud(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(20)])
    assert g.summary(t)["kills_total"] == 19


def test_mesos_fall_back_to_the_inventory(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(5)])
    g.mesos(1000, t)
    g.mesos(1450, t + 6)
    assert g.summary(t + 6)["mesos_picked"] == 450


def test_exp_change_across_a_level_up(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [NEED - 2000 + 500 * i for i in range(4)])
    t = feed(g, [1000], t0=t, level=33)                           # the bar starts over at level 33
    s = g.summary(t)
    assert s["start"] == {"level": 32, "pct": pct(NEED - 2000)} and s["level"] == 33


def test_the_chart_covers_the_whole_session(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(400)])            # 40 minutes
    ch = g.summary(t)["chart"]
    assert len(ch["vals"]) >= 40 and sum(ch["vals"]) == 39900


def test_a_new_map_keeps_the_last_session(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(20)])
    g.add_kill("Jr. Wraith", t)
    t = feed(g, [52000, 52000], t0=t, map_id=2, name="Kerning City")
    last = g.last_session
    assert last["map"] == "Ant Tunnel I" and last["kills_total"] == 1 and last["deaths"] == 0


def test_all_maps_has_kills_and_mesos_an_hour(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(101)])
    for _ in range(100):
        g.add_kill("Horny Mushroom", t)
    g.add_mesos(3000, t)
    g.flush(t)
    m = g.all_maps(32, min_active=60)[0]                       # ~10 minutes of grinding
    assert m["map"] == "Ant Tunnel I"
    assert m["kills_hr"] == round(100 / m["active_s"] * 3600) and m["mesos_hr"] == round(3000 / m["active_s"] * 3600)


def test_all_maps_estimates_kills_when_no_line_was_read(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(101)])            # 100 kills, no corner line
    g.flush(t)
    m = g.all_maps(32, min_active=60)[0]
    assert m["kills_hr"] == round(100 / m["active_s"] * 3600)
