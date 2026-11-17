"""The grind history: every session is saved in full (its card), while it runs and when it ends."""
import json
import time

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
    assert g.db.execute("SELECT exp_gained FROM history ORDER BY id").fetchone()[0] == 4000   # not the late gain
    assert len(rows(g)) == 1
    t = feed(g, [54200 + 100 * i for i in range(40)], t0=t)          # 4 more minutes: its own card
    out = g.db.execute("SELECT open, end FROM history ORDER BY id").fetchall()
    assert len(out) == 2
    assert out[0] == (0, last_gain) and out[1][0] == 1


def test_a_pq_starts_its_own_session_even_when_keeping_across_maps(tmp_path):
    g = tracker(tmp_path); g.no_reset = True
    t = feed(g, [50000 + 100 * i for i in range(41)])
    t_in = t + 18.0                      # kpq_run reads Kerning City for 18 s, then the first stage begins
    t, _ = kpq_run(g, t, 54000)
    t_out = t - 18.0                     # ...and its last 18 s are back in town: that read is the exit
    g.close(t)
    out = g.db.execute("SELECT pq, exp_gained, active_s, start, end, exp_hr FROM history ORDER BY id").fetchall()
    assert [r[0] for r in out] == [None, "Kerning PQ"]
    pq, exp, active, start, end, hr = out[1]
    # the run's whole time, entry to exit (not first gain to last gain), and what the run's own log row says
    assert exp == 5500 and abs(start - t_in) < 0.01 and abs(end - t_out) < 0.01 and abs(active - (t_out - t_in)) < 0.01
    run = g.db.execute("SELECT active_s FROM sessions WHERE pq='Kerning PQ'").fetchone()
    assert abs(run[0] - active) < 0.01 and abs(hr - exp / active * 3600) < 0.01


def test_a_death_that_wipes_a_saved_session_removes_its_card(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(41)])
    assert rows(g)[0][1] == 1                                       # saved while it runs
    t = feed(g, [49900], t0=t)                                      # a death costing 4,100 EXP: below zero
    assert g.summary(t)["gained"] < 0
    feed(g, [49900], t0=t, map_id=2, name="Ant Tunnel II")
    assert rows(g) == []


def test_companion_saves_the_card_when_its_window_closes(tmp_path):
    import companion
    g = tracker(tmp_path)
    feed(g, [50000 + 100 * i for i in range(41)])
    companion.close_grind({"state": {"grind": g}})
    assert [r[1] for r in rows(g)] == [0]
    companion.close_grind({})                                       # no state yet (closed during start-up)


def test_close_saves_and_a_crash_is_closed_on_next_start(tmp_path):
    g = tracker(tmp_path)
    feed(g, [50000 + 100 * i for i in range(41)])
    saved_end = g.db.execute("SELECT end FROM history").fetchone()[0]
    assert g.db.execute("SELECT open FROM history").fetchone()[0] == 1   # not closed: a crash
    g2 = grind.Grind(tmp_path / "grind.sqlite")
    assert g2.db.execute("SELECT open, end FROM history").fetchall() == [(0, saved_end)]
    assert g2.db.execute("SELECT value FROM meta WHERE key='history_since'").fetchone() is not None


def saved(g, n, who="Tura1", t0=None):
    """n saved sessions (3 minutes on map k, then a new map), the last one left running."""
    g.who = {"name": who, "job": "Hunter"}
    t = time.time() + 10 if t0 is None else t0     # after the history began, like real sessions
    for k in range(n):
        t = feed(g, [50000 + 4000 * k + 100 * i for i in range(31)], t0=t, map_id=10 + k, name=f"Map {k}")
    return t


def test_the_list_pages_eight_newest_first_without_the_open_one(tmp_path):
    g = tracker(tmp_path)
    saved(g, 11)                                    # 10 closed, the 11th still running
    p = g.history_page(0)
    assert p["total"] == 10 and p["pages"] == 2 and len(p["rows"]) == 8 and p["page"] == 0
    starts = [r["start"] for r in p["rows"]]
    assert starts == sorted(starts, reverse=True)
    open_id = g.db.execute("SELECT id FROM history WHERE open = 1").fetchone()[0]
    ids = [r["id"] for r in p["rows"]] + [r["id"] for r in g.history_page(1)["rows"]]
    assert f"h{open_id}" not in ids and len(set(ids)) == 10 and len(g.history_page(1)["rows"]) == 2


def test_old_rows_mix_in_by_time_and_walk_throughs_are_hidden(tmp_path):
    g = tracker(tmp_path)
    t = saved(g, 3)                                 # 2 closed cards, one running
    since = float(g.db.execute("SELECT value FROM meta WHERE key='history_since'").fetchone()[0])
    for start, act, exp in ((since - 5000, 600, 9000), (since - 4000, 60, 500), (since - 3000, 600, 0)):
        g.db.execute("INSERT INTO sessions (start, end, map_id, map, level_start, level_end, exp_gained, active_s)"
                     " VALUES (?,?,?,?,?,?,?,?)", (start, start + act, 1, "Old Map", 30, 30, exp, act))
    g.db.execute("UPDATE history SET start = ? WHERE id = (SELECT MIN(id) FROM history)", (since - 9000,))
    g.db.commit()
    p = g.history_page(0)
    assert p["total"] == 3
    assert [r["old"] for r in p["rows"]] == [False, True, False]      # the old one sits between by its start
    old = p["rows"][1]
    assert old["id"].startswith("s") and old["map"] == "Old Map" and old["exp_gained"] == 9000
    seen = [r["id"] for n in range(2) for r in g.history_page(n, per=2)["rows"]]
    assert sorted(seen) == sorted(r["id"] for r in p["rows"]) and len(seen) == 3


def test_multi_char_only_with_two_characters(tmp_path):
    g = tracker(tmp_path)
    t = saved(g, 3)
    assert g.history_page(0)["multi_char"] is False
    t = saved(g, 2, who="Tura4", t0=t)
    assert g.history_page(0)["multi_char"] is True


def test_the_card_is_flat_and_missing_ones_are_none(tmp_path):
    g = tracker(tmp_path)
    saved(g, 2)
    hid = g.db.execute("SELECT id FROM history WHERE open = 0").fetchone()[0]
    c = g.history_card(f"h{hid}")
    assert c["exp_gained"] == 3000 and c["minutes"]["vals"] and c["kills"] == [] and "data" not in c
    assert g.history_card("h999") is None and g.history_card("x1") is None and g.history_card("hz") is None
    open_id = g.db.execute("SELECT id FROM history WHERE open = 1").fetchone()[0]
    assert g.history_card(f"h{open_id}") is None


def test_an_old_session_card_has_the_saved_card_shape(tmp_path):
    g = tracker(tmp_path)
    g.db.execute("INSERT INTO sessions (start, end, map_id, map, level_start, level_end, exp_gained, active_s, kills,"
                 " mesos_picked, mesos_gained, deaths, exp_lost) VALUES (1,2,1,'Old Map',30,30,900,600,40,1234,999,2,50)")
    g.db.commit()
    c = g.history_card("s1")
    assert (c["kills_total"], c["mesos_picked"], c["mesos_change"], c["deaths_count"], c["exp_lost"], c["old"]) ==         (40, 1234, 999, 2, 50, True)
    assert c["kills"] == [] and c["deaths"] == [] and c["loot"] == [] and c["minutes"] is None


def test_closing_after_an_afk_ends_the_card_at_the_last_gain(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(41)])
    last, n = g.last_any, len(g._chart(t)["vals"])
    g.close(last + 8 * 3600)
    end = g.db.execute("SELECT end FROM history").fetchone()[0]
    assert end == last
    assert len(data_of(g)["minutes"]["vals"]) == n


def test_a_long_pause_never_ends_the_session(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(41)])
    g.pause(True)
    t += 40 * 60
    g.pause(False)
    t = feed(g, [54100], t0=t)
    assert g.summary(t)["gained"] == 4100                  # the earlier EXP is still in Now
    assert len(rows(g)) == 1 and rows(g)[0][1] == 1      # still the one open card


def test_a_map_session_is_titled_by_its_first_map(tmp_path):
    g = tracker(tmp_path); g.no_reset = True
    t = feed(g, [50000 + 100 * i for i in range(21)], map_id=1, name="Ant Tunnel I")
    feed(g, [52100 + 100 * i for i in range(21)], t0=t, map_id=2, name="Ant Tunnel II")
    g.close(g.last_any)
    r = g.db.execute("SELECT map, map_id FROM history").fetchall()
    assert r == [("Ant Tunnel I", 1)]
    assert data_of(g)["maps"] == ["Ant Tunnel I", "Ant Tunnel II"] and data_of(g)["map_ids"] == [1, 2]


def test_mesos_picked_is_the_corner_total_only(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(41)])
    g.s_mesos0, g.s_mesos = 1000, 1500
    g.close(g.last_any)
    d = data_of(g)
    assert d["mesos_picked"] is None and d["mesos_change"] == 500
    g2 = grind.Grind(tmp_path / "g2.sqlite")
    t = feed(g2, [50000 + 100 * i for i in range(41)])
    g2.picked = 300
    g2.close(g2.last_any)
    assert data_of(g2)["mesos_picked"] == 300


def test_a_bad_card_key_is_none(tmp_path):
    g = tracker(tmp_path)
    assert g.history_card("h\u00b2") is None and g.history_card("h" + "9" * 40) is None
