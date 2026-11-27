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
MOST = 4                        # kills a gain may hold to judge a split by (the Fitter)
TELL_MOST = 12                  # kills one gain can be told as: mobbing in a party, a read every ~2.5 s
                                # (live 2026-11-27: a Hunter on The Burnt Land III, reads of 504 and 518)
STEPS = 200_000                 # the search gives up after this many steps (a gain nothing explains)
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
    steps = [0]

    def walk(i, left, picked, score):
        if left == 0:
            s = score + PER_KILL * len(picked)
            if best[0] is None or s > best[0]:
                best[0], best[1] = s, list(picked)
            return
        if i == len(ts) or len(picked) == most:
            return
        v, name, who, w = ts[i]
        steps[0] += 1
        if left > (most - len(picked)) * v or steps[0] > STEPS:
            return                  # terms only get smaller from here: the kills left can't make it
        if v <= left:
            picked.append((name, who))
            walk(i, left - v, picked, score + w)          # the same kill again
            picked.pop()
        walk(i + 1, left, picked, score)
    walk(0, int(gain), [], 0.0)
    return best[1]


def tell(mobs, gain, model):
    """A gain as your kills and your party's, up to TELL_MOST kills in it; None when nothing fits."""
    return split(mobs, gain, model, most=TELL_MOST)


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
        # judged only by gains a few kills can make: a read that holds a dozen kills (mobbing) can't
        # be explained within MOST, and counted against every model it would leave none believed
        top = max((e for _, e, _ in mobs if e), default=0)
        gs = [g for g in self.gains if g <= MOST * top]
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


# ---- kills from the corner's lines. "You received EXP (+n)" is one kill's EXP: yours, or a member's
# share of theirs. Live 2026-11-27, six on Forgotten Entrance II: yours about a third of the monster's
# EXP (27 of a Raffle's 85), each member's kill about 11% (9-10), the party bonus 30% on top. The
# shares change with the party (a duo: 60% and 40%), so they're learned from the lines themselves.
LINES_MIN = 8                   # lines before any is told: the shares need a few to show
LINES_KEEP = 200                # lines remembered to learn from
LINES_TOL = 1                   # a point more or less: the damage dealt, the game's rounding
GRID = [round(0.05 + 0.005 * i, 3) for i in range(191)]     # shares tried: 5% to 100%
APART = 0.06                    # yours and a member's share are at least this far apart
SOLO_LIKE = 0.45                # one share only, this high or more: it's yours (else a member's)


def _fits(share, v, mobs):
    return any(abs(_r(share * e) - v) <= LINES_TOL for _, e, _ in mobs if e)


def _weight(share, v, mobs):
    """How well a share explains one line: by the commonest monster it fits (0: none)."""
    total = sum(c or 1 for _, _, c in mobs) or 1
    return max(((c or 1) / total for _, e, c in mobs if e and abs(_r(share * e) - v) <= LINES_TOL), default=0.0)


def _support(share, vals, mobs):
    """How well a share explains the lines (one that explains a line only by a rare monster, poorly)."""
    return sum(_weight(share, v, mobs) for v in vals)


def _middle(sup):
    """The middle of the longest run of shares with the most support: (support, share)."""
    best = max(n for n, _ in sup)
    runs, run = [], []
    for n, s in sup:
        if n == best:
            run.append(s)
        elif run:
            runs.append(run)
            run = []
    if run:
        runs.append(run)
    longest = max(runs, key=len)
    return best, longest[len(longest) // 2]


class Lines:
    """The corner's EXP lines, told as kills: which monster and whose. The shares are learned from the
    map's lines; the first few wait until there are enough."""

    def __init__(self):
        self.key, self.vals, self.pending, self.known, self.since = None, [], [], None, 0

    def shares(self, mobs):
        """(yours, a member's): either may be None when only one shows."""
        vals = self.vals
        _, s1 = _middle([(_support(s, vals, mobs), s) for s in GRID])
        # the lines the first share explains poorly: a better share would (a duo's 18 fits 59% only
        # by the map's one Axe Stump, 40% by its Wild Boars)
        best = {v: max(_weight(s, v, mobs) for s in GRID) for v in set(vals)}
        rest = [v for v in vals if _weight(s1, v, mobs) < 0.5 * best[v]]
        far = [s for s in GRID if abs(s - s1) >= APART]
        if rest and far:
            _, s2 = _middle([(_support(s, rest, mobs), s) for s in far])
            if sum(1 for v in rest if _weight(s2, v, mobs) > 0) >= max(3, 0.05 * len(vals)):
                return max(s1, s2), min(s1, s2)
        return (s1, None) if s1 >= SOLO_LIKE else (None, s1)

    def tell(self, v, mobs, shares):
        """(monster, "you"/"party") for one line, or None when neither share fits it."""
        best = None
        for share, who in zip(shares, ("you", "party")):
            if not share:
                continue
            for name, e, count in mobs:
                if not e:
                    continue
                d = abs(_r(share * e) - v)
                if d <= LINES_TOL:
                    k = (d, -(count or 1))
                    if best is None or k < best[0]:
                        best = (k, (name, who))
        return best[1] if best else None

    def take(self, v, mobs):
        """One line: the kills to count now, [(monster, "you"/"party")] (the held ones too, once known)."""
        key = tuple(n for n, _, _ in mobs)
        if key != self.key:                 # another map: its monsters, learnt afresh
            self.__init__()
            self.key = key
        self.vals = (self.vals + [int(v)])[-LINES_KEEP:]
        self.pending.append(int(v))
        if len(self.vals) < LINES_MIN:
            return []
        if self.known is None or len(self.vals) <= 30 or self.since >= 10:     # learnt anew often at first
            self.known, self.since = self.shares(mobs), 0
        self.since += 1
        out, held = [], []
        for p in self.pending:
            t = self.tell(p, mobs, self.known)
            (out if t else held).append(t or p)
        self.pending = held[-30:]           # no share fits it yet (yours, before a few showed): it waits
        return out
