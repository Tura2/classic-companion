"""Grind in a party: the EXP comes in shares on almost every read, so two reads in a row seldom agree
and a counted gain can come a minute or more after the one before. Reads that show the EXP still
rising are grinding all the same (seen live 2026-11-20 on The Burnt Land II: 112K/hr shown for
~80K really made)."""
from test_grind import feed, pct, tracker


def rising(g, t0, exp0, holds, step=2.0, per_read=20, per_hold=45, level=32, map_id=1, name="Ant Tunnel I"):
    """`holds` blocks of reads `step` s apart, each read `per_read` EXP up on the last, so no two agree;
    each block ends on one more read shown twice, which agree. Returns (time, EXP) at the end."""
    t, e = t0, exp0
    for _ in range(holds):
        for _ in range(per_hold - 1):
            e += per_read
            g.update(e, pct(e), level, map_id, name, t)
            t += step
        e += per_read
        for _ in range(2):
            g.update(e, pct(e), level, map_id, name, t)
            t += step
    return t, e


def test_rising_reads_count_as_grinding_time(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 20 * i for i in range(5)])      # agreed reads first: the clock has started
    s0 = g.summary(t)
    t1, _ = rising(g, t, 50080, holds=7)                  # ~630 s, two reads agree only every ~90 s
    s = g.summary(t1)
    active = s["active_s"] - s0["active_s"]
    assert active >= 0.9 * (t1 - t)
    rate = (s["gained"] - s0["gained"]) / active * 3600
    assert abs(rate - 36000) / 36000 < 0.10               # 20 EXP every 2 s


def test_a_quest_after_a_break_is_still_a_lump(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(30)])     # 3 min of grinding
    hr = g.summary(t)["exp_hr"]
    t = feed(g, [52900] * 30, t0=t)                       # 3 min idle
    t = feed(g, [52900 + 7020] * 2, t0=t)                 # a quest: one jump, its first read not agreed yet
    s = g.summary(t)
    assert s["gained"] == 2900 + 7020
    assert abs(s["exp_hr"] - hr) / hr < 0.05


def test_rising_reads_while_paused_dont_count(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 20 * i for i in range(5)])
    t, exp = rising(g, t, 50080, holds=1)
    g.pause(True)
    before = g.summary(t)["active_s"]
    t, _ = rising(g, t, exp, holds=3)
    assert g.summary(t)["active_s"] == before
