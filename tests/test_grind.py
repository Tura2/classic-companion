"""The grind tracker: EXP/hr, time to level and a per-map log, from the HUD's EXP."""
import pytest

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


def test_a_level_shown_before_its_exp_adds_no_extra_level(tmp_path):
    """Live, 2026-11-08: the level went 33 -> 34 a few reads before the HUD's EXP did, and the old
    level's EXP read as the new one's added a whole level (a KPQ run logged at 161,522 EXP)."""
    g = tracker(tmp_path)
    t = feed(g, [121000, 122000])
    before = g.summary(t)["gained"]
    for _ in range(4):
        g.update(122000, pct(122000), 33, 1, "Ant Tunnel I", t)    # the new level, the old EXP
        t += 2
    for _ in range(4):
        g.update(500, 0.2, 33, 1, "Ant Tunnel I", t)
        t += 2
    assert abs(g.summary(t)["gained"] - before - ((NEED - 122000) + 500)) <= NEED * 0.001


def test_the_five_minute_rate_is_over_five_minutes_of_grinding(tmp_path):
    """Live, 2026-11-08: 4 idle minutes, then one minute of 5,524 EXP showed 931K EXP/hr and
    level 35 in 8 minutes. The rate is the EXP of the last 5 minutes of grinding, over those."""
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(51)])        # 5 minutes at 60K/hr
    t = feed(g, [55000] * 40, t0=t)                           # 4 minutes idle
    t = feed(g, [55000, 60500], t0=t)                         # one big lump
    s = g.summary(t)
    assert s["exp_hr_5m"] < 2 * 60000 + 5500 / 300 * 3600    # at most the lump spread over the window
    assert s["ttl_s"] > 1500                                  # 62K to go at ~120K/hr: about half an hour


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


def test_one_misread_held_while_you_stand_still_drops_nothing(tmp_path):
    """Live, 2026-11-08: standing still between kills, one misread EXP read the same a dozen times
    'agreed' on another level EXP, replaced the right one and dropped 1,353 EXP across the gap."""
    g = tracker(tmp_path)
    t = feed(g, [60000, 60100])
    before = g.summary(t)["gained"]
    for _ in range(12):
        g.update(66100, pct(60100), 32, 1, "Ant Tunnel I", t)   # a 0 read as 6, the same every time
        t += 2
    assert abs(g.need - NEED) < NEED * 0.001
    t = feed(g, [60500], t0=t)
    assert g.summary(t)["gained"] == before + 400


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


# ---- party quests: a run from entering to leaving, its stages one run

KPQ = [(80000000 + 100 * i, f"1st Accompaniment <{s}>") for i, s in
       enumerate(["1st Stage", "2nd Stage", "3rd Stage", "4th stage", "Last Stage", "Bonus"])]


def kpq_run(g, t, exp0, gains=(800, 0, 1200, 1500, 2000, 0)):
    """One Kerning PQ run: Kerning City, then each stage with a quiet minute and a lump of EXP."""
    t = feed(g, [exp0] * 3, t0=t, map_id=103000000, name="Kerning City")
    e = exp0
    for (mid, name), gain in zip(KPQ, gains):
        t = feed(g, [e] * 10, t0=t, map_id=mid, name=name)          # a minute on the stage
        e += gain
        t = feed(g, [e] * 2, t0=t, map_id=mid, name=name)
    t = feed(g, [e] * 3, t0=t, map_id=103000000, name="Kerning City")
    return t, e


def test_pq_of_names_kerning_pq_by_its_maps():
    assert grind.pq_of("1st Accompaniment <2nd Stage>") == "Kerning PQ"
    assert grind.pq_of("1st Accompaniment <Exit>") == "Kerning PQ"
    assert grind.pq_of("Kerning City") is None
    assert grind.pq_of(None) is None


@pytest.mark.parametrize("text", ["1st Accornpanijnent", "1 st Accompaniment", "1st Accompanirnent <4tIi stage>"])
def test_pq_of_read_knows_kpq_from_a_title_cut_short(text):
    assert grind.pq_of_read(text) == "Kerning PQ"


@pytest.mark.parametrize("text", [None, "", "Kerning City", "Ant Tunnel I", "1st"])
def test_pq_of_read_leaves_other_titles(text):
    assert grind.pq_of_read(text) is None


def test_a_kpq_run_is_one_row_with_its_whole_time(tmp_path):
    g = tracker(tmp_path)
    t, _ = kpq_run(g, 0.0, 50000)
    g.flush(t)
    rows = g.history(10)
    assert len(rows) == 1                               # the stages don't split it
    r = rows[0]
    assert r["map"] == "Kerning PQ" and r["pq"] == "Kerning PQ" and r["map_id"] is None
    assert r["exp_gained"] == 5500
    assert r["active_s"] > 6 * 60                       # the quiet minutes count: a run is wall time


def test_pq_summary_counts_runs_today(tmp_path):
    g = tracker(tmp_path)
    t, e = kpq_run(g, 0.0, 50000)
    t, e = kpq_run(g, t, e)
    t = feed(g, [e] * 3, t0=t, map_id=KPQ[0][0], name=KPQ[0][1])   # the third run has just begun
    s = g.summary(t)
    assert s["map"] == "Kerning PQ"
    pq = s["pq"]
    assert pq["name"] == "Kerning PQ" and pq["stage"] == "1st Accompaniment <1st Stage>"
    assert pq["runs"] == 2 and pq["avg_exp"] == 5500
    assert abs(pq["exp_hr"] - 11000 / (pq["secs"] / 3600)) < 1
    assert pq["run_exp"] == 0 and pq["run_secs"] >= 0
    assert pq["runs_to_level"] == -(-(NEED - e) // 5500)


def test_out_of_the_pq_the_card_has_no_run(tmp_path):
    g = tracker(tmp_path)
    t, e = kpq_run(g, 0.0, 50000)
    t = feed(g, [e + 100 * i for i in range(20)], t0=t, map_id=1, name="Ant Tunnel I")
    s = g.summary(t)
    assert s["pq"] is None and s["map"] == "Ant Tunnel I"


def test_by_map_leaves_pq_runs_out(tmp_path):
    g = tracker(tmp_path)
    t, _ = kpq_run(g, 0.0, 50000)
    g.flush(t)
    assert g.by_map(min_active=0) == {}
