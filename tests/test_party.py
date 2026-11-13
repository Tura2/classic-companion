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
