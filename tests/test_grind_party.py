"""Grind in a party: the EXP comes in shares on almost every read, so two reads in a row seldom agree
and a counted gain can come a minute or more after the one before. Reads that show the EXP still
rising are grinding all the same (seen live 2026-11-20 on The Burnt Land II: 112K/hr shown for
~80K really made)."""
import pytest

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


# ---- the corner's "Bonus EXP for PARTY" lines make a party session (Task 2)
import json
from types import SimpleNamespace

import grind
import sniper

BL2 = 10004112
NEED39 = 266857
MOBS = [("Fire Boar", 60, 19), ("Dark Axe Stump", 43, 12)]


def fake_data():
    def split(mid, gain):             # whole kills only, like gamedata.split_kills
        for k in range(1, 7):
            if gain == 60 * k:
                return ["Fire Boar"] * k
        return None
    return SimpleNamespace(maps={BL2: {"name": "The Burnt Land II"}}, split_kills=split, map_mobs=lambda mid: MOBS)


def app(tmp_path, data=None):
    return SimpleNamespace(grind=grind.Grind(tmp_path / "grind.sqlite"), data=data or fake_data())


def hud(a, prof, exp, need=NEED39, n=2):
    seen = {"hud": {"exp": exp, "exp_pct": round(exp / need * 100, 2)}}
    for _ in range(n):
        sniper.handle_grind(a, seen, prof)


def gains(a, prof, exp, steps):
    hud(a, prof, exp, n=3)
    for s in steps:
        exp += s
        hud(a, prof, exp)
    return exp


def test_party_lines_mark_the_session(tmp_path):
    a, prof = app(tmp_path), {"current_map": BL2, "level": 39}
    gains(a, prof, 20000, [60])
    sniper.handle_corner(a, [("party", 3)])
    gains(a, prof, 20060, [120, 60])
    assert a.grind.summary(1e10)["party"] is True
    a.grind.flush()
    assert [r[0] for r in a.grind.db.execute("SELECT party FROM sessions")] == [1]


def test_a_party_card_says_party(tmp_path):
    g = tracker(tmp_path)
    g.add_party_bonus(3, 0.0)
    t = feed(g, [50000 + 100 * i for i in range(40)])     # 4 minutes
    g.close(t)
    data = json.loads(g.db.execute("SELECT data FROM history").fetchone()[0])
    assert data["party"] is True


def test_in_a_party_chunks_are_not_made_up_kills(tmp_path):
    a, prof = app(tmp_path), {"current_map": BL2, "level": 39}
    sniper.handle_corner(a, [("party", 3)])
    # read live 2026-11-20, three players: the party split explains some (shares of 20%, a 20% bonus);
    # the rest, several kills' shares in one read, aren't guessed at
    live = [147, 705, 321, 415, 954, 376, 734, 68, 195, 214, 106, 206, 58, 25, 72, 28, 103, 53, 72, 108, 97, 28, 120]
    gains(a, prof, 20000, live)
    s = a.grind.summary(1e10)
    assert None not in [k["name"] for k in s["kills"]]          # no unnamed "kills" from the usual gain
    assert s["kills_total"] == sum(k["count"] for k in s["kills"])
    assert s["kills_total"] < sum(live) / 60                     # far fewer than whole Fire Boars would make it
    assert s["kills_left"] is None and s["party"] is True


def test_solo_gains_are_still_named(tmp_path):
    a, prof = app(tmp_path), {"current_map": BL2, "level": 39}
    gains(a, prof, 20000, [60, 120])
    s = a.grind.summary(1e10)
    assert s["kills"] == [{"name": "Fire Boar", "count": 3}] and s["party"] is False


def test_party_is_forgotten_after_five_minutes(tmp_path):
    g = tracker(tmp_path)
    g.add_party_bonus(3, 1000.0)
    assert g.in_party(1000.0 + 300) and not g.in_party(1000.0 + 301)


def test_a_duo_the_fitter_explains_is_still_told(tmp_path, game_reader):
    d = game_reader.data
    a, prof = app(tmp_path, d), {"current_map": d.match_map_name("West Rocky Mountain IV"), "level": 37}
    sniper.handle_corner(a, [("party", 3)])
    exp = 166000
    hud(a, prof, exp, need=122755 * 1.0, n=3)
    for gain in [62, 43, 46, 31, 31, 20, 31, 51, 30, 31, 21, 62, 31, 20, 44, 31]:      # read live, two players
        exp += gain
        hud(a, prof, exp, need=122755 * 1.0)
    s = a.grind.summary(1e10)
    yours = {k["name"]: k["count"] for k in s["kills"]}
    party = {k["name"]: k["count"] for k in s["party_kills"]}
    assert yours.get("Wild Boar", 0) >= 10 and party.get("Wild Boar", 0) >= 2


# ---- best maps keep party grinding apart from solo (Task 3)
def rows(g, *specs):
    """sessions rows: (map_id, exp, active_s, party, pq), all at level 38."""
    for i, (mid, exp, act, party, pq) in enumerate(specs):
        g.db.execute("INSERT INTO sessions (start, end, map_id, map, level_start, level_end, exp_gained, active_s,"
                     " party, pq) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (i, i + act, mid, f"Map {mid}" if mid else pq, 38, 38, exp, act, party, pq))
    g.db.commit()


def test_party_and_solo_rows_rank_apart(tmp_path):
    g = tracker(tmp_path)
    rows(g, (1, 10000, 600, 0, None), (1, 20000, 600, 1, None))
    best = g.best_maps(38)
    assert sorted((r["exp_hr"], r["party"]) for r in best if r["map_id"] == 1) == [(60000, False), (120000, True)]
    assert g.by_map()[1] == pytest.approx(60000)
    assert [r["party"] for r in g.all_maps(38) if r["map_id"] == 1].count(True) == 1


def test_old_pq_rows_are_not_party_maps(tmp_path):
    g = tracker(tmp_path)
    rows(g, (1, 10000, 600, 0, None), (None, 50000, 900, 1, "Kerning PQ"))
    assert [(r["map_id"], r["party"]) for r in g.best_maps(38)] == [(1, False)]


# ---- review fixes: misreads mustn't pass for EXP coming in
def test_a_flickering_misread_while_standing_still_isnt_grinding(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(30)])     # 3 min of grinding
    hr = g.summary(t)["exp_hr"]
    for i in range(600):                                  # 20 min standing still, the last digit flickering
        e = 52900 if i % 2 else 52908
        g.update(e, pct(e), 32, 1, "Ant Tunnel I", t)
        t += 2.0
    assert g.summary(t)["running"] is False
    t = feed(g, [53000], t0=t)                            # one kill
    assert abs(g.summary(t)["exp_hr"] - hr) / hr < 0.05


def test_a_misread_first_sighting_of_a_quest_is_still_a_lump(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(30)])     # 3 min of grinding
    hr = g.summary(t)["exp_hr"]
    t = feed(g, [52900] * 30, t0=t)                       # 3 min idle
    for e in (59912, 59920, 59920):                       # the quest's first read a few EXP off, then right
        g.update(e, pct(e), 32, 1, "Ant Tunnel I", t)
        t += 2.0
    assert abs(g.summary(t)["exp_hr"] - hr) / hr < 0.05


def test_a_party_map_has_no_kills_an_hour(tmp_path):
    g = tracker(tmp_path)
    rows(g, (1, 20000, 600, 1, None))
    g.db.execute("UPDATE sessions SET kills = 40")         # only the shares the party split could tell
    g.db.commit()
    assert [r["kills_hr"] for r in g.all_maps(38)] == [None]


def test_a_big_read_in_a_party_is_told_as_kills(tmp_path):
    a, prof = app(tmp_path), {"current_map": BL2, "level": 39}
    sniper.handle_corner(a, [("party", 3)])
    # read live 2026-11-27 on The Burnt Land III (a Hunter in a party): the small reads teach the split,
    # then one read of 518 holds a dozen kills. Up to 1.4.6 it counted none (73 kills in 24 minutes)
    exp = gains(a, prof, 20000, [110, 71, 142, 137, 168, 80, 187, 142, 170, 69])
    before = a.grind.summary(1e10)["kills_total"]
    gains(a, prof, exp, [518])
    assert a.grind.summary(1e10)["kills_total"] - before >= 8


def one_read_each(a, prof, exp, steps):
    """EXP rising on every read (mobbing): no two reads in a row agree until the last one."""
    for s in steps:
        exp += s
        hud(a, prof, exp, n=1)
    hud(a, prof, exp, n=1)        # the second read of the last value: now it's counted
    return exp


def test_rising_on_every_read_is_counted_read_by_read(tmp_path):
    a, prof = app(tmp_path), {"current_map": BL2, "level": 39}
    exp = gains(a, prof, 20000, [60])
    before = a.grind.summary(1e10)["gained"]
    one_read_each(a, prof, exp, [43, 60, 60, 48])
    assert a.grind.summary(1e10)["gained"] - before == 211
    assert a.grind.last_steps == [48]                 # each read's rise its own gain, not one chunk


def test_mobbing_in_a_party_is_told_read_by_read(tmp_path):
    a, prof = app(tmp_path), {"current_map": BL2, "level": 39}
    sniper.handle_corner(a, [("party", 3)])
    # read live 2026-11-27: EXP up on every read while mobbing, counted only as one chunk (989 at
    # once on Forgotten Entrance II); each read's step is a few kills
    exp = gains(a, prof, 20000, [110, 71, 142, 137, 168, 80, 187, 142, 170, 69])
    before = a.grind.summary(1e10)["kills_total"]
    steps = [142, 137, 168, 80, 110, 71, 187, 142]
    one_read_each(a, prof, exp, steps)
    assert a.grind.summary(1e10)["kills_total"] - before >= len(steps)


# ---- in a party, kills come from the corner's EXP lines (one line, one kill)
def fe2_app(tmp_path):
    from test_party import FE2
    data = SimpleNamespace(maps={BL2: {"name": "Forgotten Entrance II"}}, split_kills=lambda mid, gain: None,
                           map_mobs=lambda mid: FE2)
    return app(tmp_path, data)


def corner_lines(a, values, bonus=3):
    evs = []
    for v in values:
        evs += [("exp", v), ("party", bonus)]
    sniper.handle_corner(a, evs)


def test_in_a_party_kills_come_from_the_corner_lines(tmp_path):
    from test_party import FE2_LINES
    a, prof = fe2_app(tmp_path), {"current_map": BL2, "level": 40}
    gains(a, prof, 20000, [9])                      # the map is known
    sniper.handle_corner(a, [("party", 3)])
    before = a.grind.summary(1e10)
    corner_lines(a, FE2_LINES)
    s = a.grind.summary(1e10)
    assert s["kills_total"] - before["kills_total"] == 16
    assert sum(k["count"] for k in s["party_kills"]) - sum(k["count"] for k in before["party_kills"]) >= 67


def test_corner_kills_arent_counted_again_from_the_hud(tmp_path):
    a, prof = app(tmp_path), {"current_map": BL2, "level": 39}
    sniper.handle_corner(a, [("party", 3)])
    # a duo on The Burnt Land II: the HUD's gains teach its split and are told as kills...
    exp = gains(a, prof, 20000, [110, 71, 142, 137, 168, 80, 187, 142, 170, 69])
    hud_told = a.grind.summary(1e10)["kills_total"]
    assert hud_told > 0
    # ...then the corner's lines come (your Fire Boar +36, your partner's +24, your Dark Axe Stump +26)
    corner_lines(a, [36, 24, 36, 36, 24, 26, 36, 24, 36, 36], bonus=4)
    mid = a.grind.summary(1e10)["kills_total"]
    assert mid > hud_told
    gains(a, prof, exp, [142, 137, 168])         # the same kills' EXP, read off the HUD: not again
    assert a.grind.summary(1e10)["kills_total"] == mid


def test_solo_the_corner_lines_dont_count_kills(tmp_path):
    a, prof = app(tmp_path), {"current_map": BL2, "level": 39}
    gains(a, prof, 20000, [60])
    sniper.handle_corner(a, [("exp", 60)] * 10)
    assert a.grind.summary(1e10)["kills_total"] == 1          # the HUD's Fire Boar, the lines not again
