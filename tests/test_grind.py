"""The grind tracker: EXP/hr, time to level and a per-map log, from the HUD's EXP."""
import grind

NEED = 122755          # EXP for level 32 (73,665 at 60.01%)


def pct(exp, need=NEED):
    return round(exp / need * 100, 2)


def tracker(tmp_path):
    return grind.Grind(tmp_path / "grind.sqlite")


def feed(g, exps, t0=0.0, step=6.0, level=32, map_id=1, name="Ant Tunnel I"):
    t = t0
    for e in exps:
        for _ in range(3):             # the app reads every 1.5-2 s; two reads agree before a change counts
            g.update(e, pct(e), level, map_id, name, t)
            t += step / 3
    return t


def test_ten_minutes_at_steady_pace(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(101)])     # +100 EXP every 6 s for 10 minutes
    s = g.summary(t)
    assert abs(s["exp_hr"] - 60000) / 60000 < 0.02
    assert abs(s["exp_hr_5m"] - 60000) / 60000 < 0.02
    assert s["ttl_s"] is not None and abs(s["ttl_s"] - (NEED - 60000) / 60000 * 3600) < 60


def test_time_to_level_waits_for_a_minute(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(8)])        # 42 seconds
    assert g.summary(t)["ttl_s"] is None


def test_fifteen_idle_seconds_pause(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(11)])       # a minute of grinding
    active = g.summary(t)["active_s"]
    t = feed(g, [51000] * 20, t0=t)                         # two minutes in town: no gains
    assert g.summary(t)["running"] is False
    assert g.summary(t)["active_s"] - active <= 16


def test_map_change_starts_a_new_segment_in_the_log(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(30)])
    t = feed(g, [53000 + 100 * i for i in range(30)], t0=t, map_id=2, name="Ant Tunnel II")
    g.flush(t)
    rows = g.history(10)
    assert [r["map_id"] for r in rows] == [2, 1]
    assert all(r["exp_gained"] > 0 for r in rows)
    assert g.summary(t)["map"] == "Ant Tunnel II"


def test_level_up_keeps_counting(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [122000, 122000])
    before = g.summary(t)["gained"]
    for _ in range(4):
        g.update(500, 0.2, 33, 1, "Ant Tunnel I", t)
        t += 2
    # the level's EXP is worked out from the HUD's two-decimal percent: right to about a thousandth
    assert abs(g.summary(t)["gained"] - before - ((NEED - 122000) + 500)) <= NEED * 0.001


def test_a_lone_lower_read_is_ignored(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [60000, 60100])
    g.update(6010, pct(6010), 32, 1, "Ant Tunnel I", t)      # a digit dropped, once
    t = feed(g, [60200], t0=t + 3)
    assert g.summary(t)["gained"] == 200


def test_exp_going_down_twice_without_level_up_is_still_dropped(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [60000, 60100, 30000, 30000])
    assert g.summary(t)["gained"] == 100


def test_real_exp_per_map_from_the_log(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(101)])
    g.flush(t)
    assert abs(tracker(tmp_path).by_map()[1] - 60000) / 60000 < 0.02


def test_mesos_per_hour(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(21)])
    g.mesos(100000, 1.0)
    g.mesos(110000, t)
    assert abs(g.summary(t)["mesos_hr"] - 10000 / g.summary(t)["active_s"] * 3600) < 1


def test_reset_starts_over(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(11)])
    g.reset(t)
    assert g.summary(t)["gained"] == 0


def test_a_percent_that_disagrees_with_the_exp_is_a_misread(tmp_path):
    """Live, 2026-11-07: 29,977 [21.62%] read as 29,877 [21.62%] twice; and 30,420 [21.94%] as 21.34."""
    g = tracker(tmp_path)
    t = feed(g, [29500, 29600])
    before = g.summary(t)["gained"]
    for _ in range(3):
        g.update(29877, 21.62, 32, 1, "Ant Tunnel I", t)
        t += 2
    for _ in range(3):
        g.update(30420, 21.34, 32, 1, "Ant Tunnel I", t)
        t += 2
    assert g.summary(t)["gained"] == before
    t = feed(g, [30447], t0=t)
    assert g.summary(t)["gained"] == before + 847


def test_the_levels_exp_needs_three_reads_that_agree(tmp_path):
    g = tracker(tmp_path)
    g.update(50000, pct(50000), 32, 1, "Ant Tunnel I", 0)
    g.update(50000, pct(50000), 32, 1, "Ant Tunnel I", 2)
    assert g.need is None
    g.update(50000, pct(50000), 32, 1, "Ant Tunnel I", 4)
    assert abs(g.need - NEED) < NEED * 0.001


def test_a_level_exp_set_by_misreads_is_replaced(tmp_path):
    """Live, 2026-11-07: right after a start, "96 [22.5%]" read three times set the level's EXP to 427."""
    g = tracker(tmp_path)
    for i in range(3):
        g.update(96, 22.5, 32, 1, "Ant Tunnel I", i * 2)
    t = feed(g, [50000 + 100 * i for i in range(6)], t0=10)
    assert abs(g.need - NEED) < NEED * 0.001
    before = g.summary(t)["gained"]
    assert before < 600                       # nothing counted from 96 up to 50,000
    t = feed(g, [50600, 50700], t0=t)
    assert g.summary(t)["gained"] == before + 200


def test_a_misread_level_doesnt_stop_counting(tmp_path):
    g = tracker(tmp_path)
    for i in range(3):
        g.update(96, 22.5, 23, 1, "Ant Tunnel I", i * 2)      # the HUD's level misread too
    t = feed(g, [50000 + 100 * i for i in range(4)], t0=10)
    assert g.summary(t)["gained"] > 0


def test_summary_feeds_the_card(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(21)], t0=6000.0)     # two minutes, +100 every 6 s
    s = g.summary(t)
    assert s["level"] == 32 and abs(s["need"] - NEED) < NEED * 0.001
    assert s["left"] == s["need"] - 52000
    assert len(s["spark"]) == grind.SPARK_MINUTES and sum(s["spark"]) == s["gained"] == 2000
    assert s["since"] is not None and s["since"] >= 6000.0
