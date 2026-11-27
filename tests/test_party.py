"""Kills in a party, from the HUD's EXP gains. In a party the game splits a kill's EXP: whoever killed
it gets about 60%, the others share the rest, and each gets a party bonus on top (seen 2026-11-13 on
West Rocky Mountain IV, two players: "You received EXP (+28)" + "Bonus EXP for PARTY (+3)" for a
Wild Boar you killed, "(+18)" + "(+2)" for one your partner killed). The split is learned from the
gains, and each gain is told as your kills and your party's kills."""
import party

# West Rocky Mountain IV: (name, EXP, how many spawn)
WRM4 = [("Axe Stump", 32, 1), ("Dark Axe Stump", 43, 14), ("Wild Boar", 46, 15), ("Lupin", 75, 3)]
DUO = party.Model(member=0.4, bonus=0.1)
# the gains read live 2026-11-13 (two players), in order
LIVE = [62, 43, 46, 31, 31, 20, 31, 51, 30, 31, 21, 62, 50, 31, 31, 31, 30, 20, 51, 31, 20, 44, 31, 31, 51, 14, 14,
        30, 31, 30, 31]


def test_your_kill_and_your_partners():
    assert party.split(WRM4, 31, DUO) == [("Wild Boar", "you")]
    assert party.split(WRM4, 30, DUO) == [("Wild Boar", "you")]          # a point less damage: still yours
    assert party.split(WRM4, 20, DUO) == [("Wild Boar", "party")]
    assert party.split(WRM4, 21, DUO) == [("Axe Stump", "you")]
    assert party.split(WRM4, 14, DUO) == [("Axe Stump", "party")]


def test_two_kills_in_one_read():
    assert sorted(party.split(WRM4, 51, DUO)) == [("Wild Boar", "party"), ("Wild Boar", "you")]
    assert party.split(WRM4, 62, DUO) == [("Wild Boar", "you"), ("Wild Boar", "you")]
    assert sorted(party.split(WRM4, 44, DUO)) == [("Axe Stump", "party"), ("Wild Boar", "you")]


def test_a_gain_nothing_explains():
    assert party.split(WRM4, 7, DUO) is None


def test_the_split_is_learned_from_the_gains():
    fit = party.Fitter()
    for g in LIVE:
        fit.add(g)
    m = fit.model(WRM4)
    assert (m.member, m.bonus) == (0.4, 0.1)


def test_solo_gains_teach_no_party():
    fit = party.Fitter()
    for g in [46, 43, 32, 46, 75, 46, 89, 43, 46, 32, 46]:      # full EXP: nobody to share with
        fit.add(g)
    assert fit.model(WRM4) is None


# The Burnt Land III, read live 2026-11-27: a Hunter in a party, kills told by Companion 73 in 24
# minutes against ~1,200 EXP a minute. A read every ~2.5 s holds many kills when you mob a map.
BL3 = [("Dark Axe Stump", 43, 13), ("Fire Boar", 60, 24)]
LIVE_1127 = [187, 142, 170, 69, 38, 100, 43, 44, 12, 28, 145, 114, 12, 64, 175, 504, 53,
             110, 71, 142, 137, 168, 518, 80]
# reads like the 504 and 518 above: a dozen kills in one read
BIG = [466, 390, 612, 433, 487, 551, 402, 377, 529, 445, 498, 421]


def test_a_big_read_is_told_as_many_kills():
    m = party.Model(member=0.4, bonus=0.05)
    told = party.tell(BL3, 518, m)
    assert told is not None and 10 <= len(told) <= party.TELL_MOST
    assert party.tell(BL3, 504, m) is not None


def test_big_reads_dont_hide_the_split():
    reads = LIVE_1127 + BIG + BIG            # a stretch of mobbing: half the reads hold many kills
    fit = party.Fitter()
    for g in reads:
        fit.add(g)
    m = fit.model(BL3)
    assert m is not None
    told = [party.tell(BL3, g, m) for g in reads]
    assert sum(1 for t in told if t) >= 0.9 * len(told)


def test_big_reads_alone_teach_nothing():
    fit = party.Fitter()
    for g in BIG:
        fit.add(g)
    assert fit.model(BL3) is None          # nothing small enough to judge a split by


def test_a_read_nothing_explains_gives_up_fast():
    import time
    t = time.process_time()
    assert party.tell(WRM4, 997, DUO) is None or len(party.tell(WRM4, 997, DUO)) <= party.TELL_MOST
    party.tell(WRM4, 9973, DUO)
    assert time.process_time() - t < 2.0


# ---- kills from the corner's lines: "You received EXP (+n)" is one kill's EXP, yours or a member's
# Forgotten Entrance II, read live 2026-11-27 over 40 s, a party of six: 16 lines of 26-27 (your
# kills, about a third of the monster's EXP) and 69 of 8-12 (the five others' kills, about 11%)
FE2 = [("Lupin", 75, 6), ("Glowshroom", 82, 12), ("Raffle", 85, 14)]
FE2_LINES = [10, 9, 27, 9, 27, 8, 10, 9, 9, 10, 10, 27, 9, 10, 8, 10, 9, 9, 9, 27, 9, 10, 9, 8, 26, 8, 26, 9, 9, 9,
             27, 10, 10, 10, 10, 8, 9, 26, 10, 9, 8, 10, 8, 9, 10, 9, 26, 9, 10, 8, 10, 27, 8, 9, 9, 9, 8, 27, 8, 10,
             10, 27, 10, 9, 27, 26, 10, 8, 9, 9, 10, 10, 10, 9, 11, 12, 8, 9, 27, 8, 10, 9, 9, 9, 26]


def take_all(lines, mobs, values):
    told = []
    for v in values:
        told += lines.take(v, mobs)
    return told


def test_six_in_a_party_lines_tell_yours_and_theirs():
    lines = party.Lines()
    told = take_all(lines, FE2, FE2_LINES)
    yours = [n for n, who in told if who == "you"]
    assert len(yours) == 16 and len(told) - len(yours) >= 67
    assert sorted(lines.pending) == [11, 12]       # the two odd lines (a member at another level?) wait
    assert set(n for n, _ in told) <= {"Lupin", "Glowshroom", "Raffle"}
    you, member = lines.shares(FE2)
    assert 0.29 <= you <= 0.35 and 0.10 <= member <= 0.13


def test_a_duo_s_lines():
    # West Rocky Mountain IV, two players (2026-11-13): your Wild Boar +28, your partner's +18
    lines = party.Lines()
    told = take_all(lines, WRM4, [28, 18, 28, 28, 18, 26, 28, 17, 28, 18, 28, 28])
    assert [w for _, w in told].count("party") == 4
    assert all(n in ("Wild Boar", "Dark Axe Stump") for n, _ in told)


def test_lines_wait_for_enough_to_learn_from():
    lines = party.Lines()
    assert take_all(lines, FE2, FE2_LINES[:5]) == []        # too few to tell whose
    first = take_all(lines, FE2, FE2_LINES[5:10])            # then the ones held are told too...
    assert len(first) >= 8 and all(w == "party" for _, w in first)
    later = take_all(lines, FE2, FE2_LINES[10:])             # ...and yours, once a few of them show
    assert len(first) + len(later) + len(lines.pending) == len(FE2_LINES)
    assert sum(1 for _, w in first + later if w == "you") == 16


def test_a_new_map_starts_afresh():
    lines = party.Lines()
    take_all(lines, FE2, FE2_LINES)
    assert lines.take(28, WRM4) == []                       # other monsters: learnt again
