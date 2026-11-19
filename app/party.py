"""
Kills in a party, told from the HUD's EXP gains (no reading of the game's corner lines).

In a party the game splits a kill's EXP. Seen live 2026-11-13 with two players on West Rocky
Mountain IV:
  your Wild Boar (46 EXP):      "You received EXP (+28)" + "Bonus EXP for PARTY (+3)"  = 31
  your partner's Wild Boar:     "You received EXP (+18)" + "Bonus EXP for PARTY (+2)"  = 20
So whoever kills gets 60% (a point more or less with the damage dealt), the others share the 40%,
and each gets a party bonus on its share. A kill with no one near is the full EXP, as solo.

A Model is the share you get of a member's kill and the bonus rate; the Fitter learns it from the
gains the solo split can't explain (two players: 0.4 and 0.1; more players share the 40% further).
split() then tells one gain as kills, each "you" or "party".
"""
import math

YOURS = 0.6                     # the share whoever made the kill gets
MEMBERS = (0.4, 0.2, 0.133, 0.1, 0.08)      # your share of a member's kill: 2 to 6 players
BONUSES = (0.05, 0.1, 0.15, 0.2)
MOST = 4                        # kills one gain can hold (a read every ~1.5 s)
PER_KILL = math.log(0.5)        # one kill more is less likely
OFF = 0.8                       # a point off your 60% (the damage you dealt) is a little less likely
SOLO = 1.0                      # in a party, a kill with no one near is less likely
NEED = 0.6                      # the share of gains a model must explain to be believed
KEEP = 60                       # gains the Fitter remembers


def _r(x):
    return int(x + 0.5)


class Model:
    def __init__(self, member, bonus):
        self.member, self.bonus = member, bonus

    def __repr__(self):
        return f"Model(member={self.member}, bonus={self.bonus})"


def terms(mobs, model):
    """[(EXP you get, monster, "you"/"party", weight)] for one kill of each monster on the map."""
    total = sum(c or 1 for _, _, c in mobs) or 1
    out = []
    for name, exp, count in mobs:
        if not exp:
            continue
        p = math.log((count or 1) / total)
        base = _r(YOURS * exp)
        for v in (base - 1, base, base + 1):
            out.append((v + _r(model.bonus * v), name, "you", p - OFF * abs(v - base)))
        v = _r(model.member * exp)
        out.append((v + _r(model.bonus * v), name, "party", p))
        out.append((exp, name, "you", p - SOLO))              # no one near: the whole kill is yours
    return sorted(out, key=lambda t: -t[0])


def split(mobs, gain, model, most=MOST):
    """One gain as [(monster, "you"/"party")], the likeliest mix of kills that adds up to it; None
    when none does."""
    ts = terms(mobs, model)
    best = [None, None]

    def walk(i, left, picked, score):
        if left == 0:
            s = score + PER_KILL * len(picked)
            if best[0] is None or s > best[0]:
                best[0], best[1] = s, list(picked)
            return
        if i == len(ts) or len(picked) == most:
            return
        v, name, who, w = ts[i]
        if v <= left:
            picked.append((name, who))
            walk(i, left - v, picked, score + w)          # the same kill again
            picked.pop()
        walk(i + 1, left, picked, score)
    walk(0, int(gain), [], 0.0)
    return best[1]


def solo_split(mobs, gain, most=MOST):
    """Whether whole kills of this map's monsters add up to the gain (no party)."""
    exps = sorted({e for _, e, _ in mobs if e}, reverse=True)

    def can(i, left, n):
        if left == 0:
            return True
        if i == len(exps) or n == most:
            return False
        e = exps[i]
        return (e <= left and can(i, left - e, n + 1)) or can(i + 1, left, n)
    return can(0, int(gain), 0)


class Fitter:
    """Learns the party's split from the gains: the Model that explains most of them, or None when
    you're solo (whole kills explain them)."""

    def __init__(self):
        self.gains = []

    def add(self, gain):
        self.gains = (self.gains + [int(gain)])[-KEEP:]

    def model(self, mobs):
        gs = self.gains
        if len(gs) < 5 or not mobs:
            return None
        solo = sum(1 for g in gs if solo_split(mobs, g))
        if solo >= NEED * len(gs):
            return None
        best, best_n = None, solo
        for member in MEMBERS:
            for bonus in BONUSES:
                m = Model(member, bonus)
                n = sum(1 for g in gs if solo_split(mobs, g) or split(mobs, g, m) is not None)
                if n > best_n:
                    best, best_n = m, n
        return best if best is not None and best_n >= NEED * len(gs) else None
