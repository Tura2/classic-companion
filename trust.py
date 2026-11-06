"""
The gate between what a read of the game saw and what goes into your profile. Most misreads repeat
on every read of the same screen (OCR reads "Tura1" as "Tural" every time), so reads agreeing isn't
enough: each value also has to fit the game's own rules.

  level    up by one at once; any other change only after 3 reads in a row agree
  stats    base STR+DEX+INT+LUK + unspent AP = 5 x level + 20 (25 at level 1, 5 AP a level)
  skills   no skill goes down or past its max; 1st and 2nd job skills + SP left = 3 x level - 28
           from level 30 (3 x level - 29 below): 1 SP at each job advance, 3 a level
  mesos    a change of more than half needs 2 reads in a row
  name     once known, another name is another character: nothing of it is saved

A value that breaks a rule is still saved once it's been read the same 5 times in a row, for a
character the rule doesn't fit (a magician advances at level 8, not 10).
"""

LEVEL_READS, MESOS_READS, NAME_READS, ODD_READS = 3, 2, 3, 5
ONE_OR_L = str.maketrans("lI|", "111")


def same_name(a, b):
    """The same name but for a 1 read as an l, I or |: how OCR read "Tura1" before names were
    checked letter by letter, and profiles saved then still hold it."""
    return a.translate(ONE_OR_L) == b.translate(ONE_OR_L)


class Gate:
    def __init__(self, skill_max, skill_job=None):
        self.skill_max = skill_max          # skill name -> its max level
        self.skill_job = skill_job or {}    # skill name -> the job it belongs to ("Beginner" has its own SP)
        self.runs = {}                      # what -> (the value last read, how many reads in a row)
        self.other = None                   # another character's name, while it's the one on screen

    def _again(self, what, value):
        """How many reads in a row have now given this value."""
        last, n = self.runs.get(what, (None, 0))
        n = n + 1 if last == value else 1
        self.runs[what] = (value, n)
        return n

    def check(self, prof, seen):
        """The values of this read that may go into the profile, as {key: value}; "other_name" says
        another character is on screen (and then nothing else is given)."""
        out = {}
        stat, hud = seen.get("stat") or {}, seen.get("hud") or {}
        name = stat.get("name")
        if name:
            if not prof.get("name"):
                if self._again("name", name) >= NAME_READS:
                    out["name"] = name
            elif same_name(name, prof["name"]):
                self.other = None
                # a name the old reader saved misread ("Tural") is put right; never the other way
                if all(r == s or (r == "1" and s in "lI|") for r, s in zip(name, prof["name"])):
                    if name != prof["name"]:
                        out["name"] = name
            else:
                # another name on screen: none of this read is yours. Read 3 times, it's another character
                if self._again("other", name) >= NAME_READS:
                    self.other = name
                return {"other_name": self.other} if self.other else {"blocked": name}
        if self.other:
            return {"other_name": self.other}

        level = self._level(prof, stat, hud)
        if level is not None:
            out["level"] = level
        lv = level or prof.get("level")

        bases = {k: stat.get(k + "_base") for k in ("str", "dex", "int", "luk")}
        if None not in bases.values() and stat.get("ap") is not None and lv:
            fits = sum(bases.values()) + stat["ap"] == 5 * lv + 20
            if fits or self._again("stats", (tuple(bases.values()), stat["ap"])) >= ODD_READS:
                out["stats"], out["ap"] = bases, stat["ap"]

        acc = stat.get("acc")
        if acc and acc <= 40 + 6 * int(lv or 1):        # it once read 585 at level 21
            out["acc"] = acc

        mesos = (seen.get("inventory") or {}).get("mesos")
        if mesos is not None:
            before = prof.get("mesos") or 0
            big = before > 1000 and abs(mesos - before) > before / 2
            if not big or self._again("mesos", mesos) >= MESOS_READS:
                out["mesos"] = mesos

        sk = seen.get("skills") or {}
        if sk.get("levels"):
            merged = self._skills(prof, sk, lv)
            if merged is not None:
                out["skills_now"], out["sp"] = merged, sk.get("sp")
        return out

    def _level(self, prof, stat, hud):
        read = stat.get("level") or (hud.get("level") if hud.get("level_exact") else None)
        if read is None or read == prof.get("level"):
            return None
        if prof.get("level") and read == prof["level"] + 1:
            return read
        return read if self._again("level", read) >= LEVEL_READS else None

    def _skills(self, prof, sk, lv):
        """The skills with this read's tab merged in, or None while the read breaks a rule."""
        before, read, sp = prof.get("skills_now") or {}, sk["levels"], sk.get("sp")
        merged = {**before, **read}
        ok = all(v <= self.skill_max.get(k, v) and v >= before.get(k, 0) for k, v in read.items())
        if ok and sp is not None and lv:
            # 1st and 2nd job skills (Beginner skills have their own SP), once both tabs have been read
            jobs = {self.skill_job.get(k) for k in merged} - {"Beginner", None}
            if len(jobs) == (2 if lv >= 30 else 1):
                spent = sum(v for k, v in merged.items() if self.skill_job.get(k) not in ("Beginner", None))
                ok = spent + sp == 3 * lv - (28 if lv >= 30 else 29)
        if ok or self._again("skills", (tuple(sorted(read.items())), sp)) >= ODD_READS:
            return merged
        return None
