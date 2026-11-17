"""The grind history: every session is saved in full (its card), while it runs and when it ends."""
import json

import grind
from test_grind import NEED, feed, kpq_run, tracker


def rows(g):
    return g.db.execute("SELECT map, open, exp_gained, active_s, level_start, level_end, character FROM history").fetchall()


def data_of(g, i=0):
    return json.loads(g.db.execute("SELECT data FROM history ORDER BY id").fetchall()[i][0])


def test_a_short_walk_through_is_not_saved(tmp_path):           # 1 minute of gains, then a new map
    g = tracker(tmp_path); g.who = {"name": "Tura1", "job": "Hunter"}
    t = feed(g, [50000 + 100 * i for i in range(11)])
    feed(g, [51100], t0=t, map_id=2, name="Ant Tunnel II")
    assert rows(g) == []


def test_a_session_is_saved_while_it_runs_and_closed_on_a_new_map(tmp_path):
    g = tracker(tmp_path); g.who = {"name": "Tura1", "job": "Hunter"}
    t = feed(g, [50000 + 100 * i for i in range(41)])           # 4 minutes
    assert rows(g)[0][1] == 1                                    # saved, still open
    feed(g, [54100, 54200], t0=t, map_id=2, name="Ant Tunnel II")
    (mp, op, exp, act, l0, l1, who), = rows(g)
    assert (mp, op, exp, l0, l1, who) == ("Ant Tunnel I", 0, 4000, 32, 32, "Tura1") and act >= 120


def test_the_card_keeps_kills_loot_used_deaths_and_minutes(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(41)])
    for _ in range(3):
        g.add_kill("Jr. Wraith", t)
    g.add_kill(None, t)
    g.add_loot("Tablecloth", 2, t)
    g.add_used("Orange Potion", 1, t)
    g.add_mesos(15, t)
    g.close(t)
    data = data_of(g)
    assert data["kills"] == [{"name": "Jr. Wraith", "count": 3}, {"name": None, "count": 1}]
    assert data["loot"] == [{"name": "Tablecloth", "count": 2}] and data["used"] == [{"name": "Orange Potion", "count": 1}]
    assert data["mesos_picked"] == 15 and sum(data["minutes"]["vals"]) == 4000 and data["maps"] == ["Ant Tunnel I"]
    assert data["kills_total"] == 4 and data["deaths"] == [] and data["levelups"] == []


def test_level_ups_are_kept_with_their_time(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [NEED - 500 - 100 * (45 - i) for i in range(46)])   # 4+ minutes at level 32
    t = feed(g, [1500], t0=t, level=33)
    t = feed(g, [1000], t0=t, level=34)             # two levels in one session (a fuller bar would read as the old level's)
    g.close(t)
    assert [u["level"] for u in data_of(g)["levelups"]] == [33, 34]
    (_, _, _, _, l0, l1, _), = rows(g)
    assert (l0, l1) == (32, 34)


def test_thirty_minutes_without_exp_ends_the_session(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(41)])
    last_gain = g.last_any
    t += 1801
    t = feed(g, [54100], t0=t)                                       # the late gain
    assert g.summary(t)["gained"] == 100                             # Now restarted too
    assert len(rows(g)) == 1
    t = feed(g, [54200 + 100 * i for i in range(40)], t0=t)          # 4 more minutes: its own card
    out = g.db.execute("SELECT open, end FROM history ORDER BY id").fetchall()
    assert len(out) == 2
    assert out[0] == (0, last_gain) and out[1][0] == 1


def test_a_pq_starts_its_own_session_even_when_keeping_across_maps(tmp_path):
    g = tracker(tmp_path); g.no_reset = True
    t = feed(g, [50000 + 100 * i for i in range(41)])
    t, _ = kpq_run(g, t, 54000)
    g.close(t)
    out = g.db.execute("SELECT pq, exp_gained, active_s, start, end FROM history ORDER BY id").fetchall()
    assert [r[0] for r in out] == [None, "Kerning PQ"]
    pq, exp, active, start, end = out[1]
    assert exp == 5500 and abs(active - (end - start)) < 0.01 and active > 240   # wall time, quiet minutes too


def test_close_saves_and_a_crash_is_closed_on_next_start(tmp_path):
    g = tracker(tmp_path)
    feed(g, [50000 + 100 * i for i in range(41)])
    saved_end = g.db.execute("SELECT end FROM history").fetchone()[0]
    assert g.db.execute("SELECT open FROM history").fetchone()[0] == 1   # not closed: a crash
    g2 = grind.Grind(tmp_path / "grind.sqlite")
    assert g2.db.execute("SELECT open, end FROM history").fetchall() == [(0, saved_end)]
    assert g2.db.execute("SELECT value FROM meta WHERE key='history_since'").fetchone() is not None
