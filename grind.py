"""
Grind tracker: EXP per hour, time to the next level and mesos per hour, from the HUD's EXP ("73,665
[60.01%]", read by reader/hudexp) and the inventory's mesos. Kept per map in grind.sqlite, so over
time it says which map really pays best for you.

A session runs while EXP comes in. Its grinding time is the waits between gains (respawns,
walking) up to a minute each; a longer wait is a break and isn't counted, and EXP/hr is the
session's EXP over that time. Each map is its own segment in the log; on the dashboard a map change starts the
numbers over unless "No reset" is on. One misread never counts: a new EXP needs two reads in a row,
and EXP going down without a level-up is dropped. The EXP a level needs is exp / pct, so no EXP
table is needed; a level-up adds what was left of the old level plus the new EXP.

A party quest is counted by the run instead: entering any of its maps starts a run, its stages
are the same run, and leaving ends it. A run's time is all of it, the quiet puzzle minutes too, so
"EXP per hour" there is what the PQ really pays for the time it takes.
"""
import math
import sqlite3
import time

# Party quests: every map whose name starts with the prefix belongs to it (stages, bonus, exit).
PQS = (("Kerning PQ", "1st Accompaniment"),)


def pq_of(map_name):
    """The party quest this map belongs to, or None."""
    if not map_name:
        return None
    return next((pq for pq, prefix in PQS if map_name.lower().startswith(prefix.lower())), None)


PQ_READ_CUTOFF = 85


def pq_of_read(text):
    """The party quest a mini map title belongs to, from a read too poor to name the map
    ("1st Accornpanijnent", the stage cut off): its start is close to the PQ's prefix."""
    if not text or len(text) < 6:
        return None
    from rapidfuzz import fuzz
    low = text.lower().replace("rn", "m").replace("jn", "m")     # OCR reads an "m" as "rn" or "jn"
    for pq, prefix in PQS:
        p = prefix.lower()
        if max(fuzz.ratio(p, low[:len(p) + d]) for d in (-1, 0, 1, 2)) >= PQ_READ_CUTOFF:
            return pq
    return None


def day_start(now):
    """Local midnight before `now`."""
    t = time.localtime(now)
    return math.floor(now) - (t.tm_hour * 3600 + t.tm_min * 60 + t.tm_sec)

BREAK = 60.0            # a wait between gains longer than this is a break: it isn't grinding time at all
WINDOW = 300.0          # "last 5 minutes" rate
CLOCK_WINDOW = 900.0    # time to level: the clock pace over the last 15 minutes, idle included
LUMP_SHARE = 0.01       # a gain after a break bigger than this share of the level (a quest) isn't killing pace
MIN_TTL_DATA = 60.0     # seconds of active time before time-to-level is shown
MAX_GAIN_SHARE = 0.6    # one step gaining more than this share of a level is a misread
SPARK_MINUTES = 30      # the chart: EXP per minute over this many minutes
NEED_READS = 3          # reads that agree on the level's EXP (exp / pct) before any is trusted
RETHINK_VALUES = 3      # different EXPs in a row agreeing on another level EXP replace one set by misreads


def need_of(exp, pct):
    """The EXP the level needs, from the HUD's EXP and its two-decimal percent."""
    return exp * 100 / pct if pct else None


def need_tol(pct):
    """How far exp / pct may stray from the level's EXP: the percent is shown to 0.01."""
    return 0.011 / pct + 0.0003


class Grind:
    def __init__(self, db_path):
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.execute("""CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY, start REAL, end REAL,
            map_id INTEGER, map TEXT, level_start INTEGER, level_end INTEGER, exp_gained INTEGER, active_s REAL,
            mesos_gained INTEGER, potions_cost INTEGER, party INTEGER)""")
        try:
            self.db.execute("ALTER TABLE sessions ADD COLUMN pq TEXT")   # logs from before PQ runs
        except sqlite3.OperationalError:
            pass
        self.db.commit()
        self.pq = None               # the party quest you're in, if any
        self.no_reset = False
        self.paused = False          # paused by hand from the dashboard
        self.last = None             # the last accepted (exp, pct, level)
        self.raw = None              # the last read, for the two-reads rule
        self.map_id = self.map = None
        self.need = None             # the level's EXP, once NEED_READS reads agree on it
        self.need_level = None
        self.need_seen = []          # exp / pct of recent reads, while the level's EXP isn't known yet
        self.seg = None
        self._new_session(None)

    # ---- state
    def _new_session(self, now):
        self.s_gained, self.s_active, self.s_mesos0, self.s_mesos = 0, 0.0, None, None
        self.s_paced = 0             # EXP gained by killing: one-off lumps after a break left out
        self.s_start = None          # the session's first gain
        self.s_t0 = now              # when the session began watching, for the clock pace
        self.minutes = {}            # minute (epoch // 60) -> EXP gained in it, for the chart
        self.events = []             # (ts, gain, active seconds before it, lump), for the rates
        self.last_gain = None        # the last gain that counted as killing (runs the clock)
        self.last_any = None         # the last gain of any kind, lumps too (tells a break)

    def _new_segment(self, now, level):
        """A map's stretch in the log, or a whole party quest run (map_id None, map the PQ's name)."""
        self.seg = {"id": None, "start": now, "map_id": None if self.pq else self.map_id, "map": self.pq or self.map,
                    "pq": self.pq, "stage": self.map, "level_start": level, "level_end": level, "exp": 0,
                    "active": 0.0, "mesos0": None, "mesos": None}

    def _save_segment(self, now):
        g = self.seg
        if not g or g["exp"] <= 0:
            return
        active = now - g["start"] if g["pq"] else g["active"]      # a run counts all its time
        row = (g["start"], now, g["map_id"], g["map"], g["level_start"], g["level_end"], g["exp"], active,
               (g["mesos"] - g["mesos0"]) if g["mesos0"] is not None and g["mesos"] is not None else None, None,
               1 if g["pq"] else 0, g["pq"])
        if g["id"] is None:
            cur = self.db.execute("INSERT INTO sessions (start, end, map_id, map, level_start, level_end, exp_gained,"
                                  " active_s, mesos_gained, potions_cost, party, pq) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", row)
            g["id"] = cur.lastrowid
        else:
            self.db.execute("UPDATE sessions SET start=?, end=?, map_id=?, map=?, level_start=?, level_end=?,"
                            " exp_gained=?, active_s=?, mesos_gained=?, potions_cost=?, party=?, pq=? WHERE id=?",
                            row + (g["id"],))
        self.db.commit()

    def flush(self, now=None):
        self._save_segment(now or time.time())

    # ---- reads
    def _open_gap(self, now):
        """Seconds since the last gain while they still count as grinding (not yet a break)."""
        if self.last_gain is None or self.paused:
            return 0.0
        gap = now - self.last_gain
        return gap if 0 <= gap <= BREAK else 0.0

    def update(self, exp, pct, level, map_id, map_name, now):
        """One read of the HUD's EXP. Returns the EXP it counted (0 for none)."""
        if exp is None or pct is None:
            return 0
        if map_id is not None and map_id != self.map_id:
            pq = pq_of(map_name)
            self.map_id, self.map = map_id, map_name
            if pq is not None and pq == self.pq and self.seg:
                self.seg["stage"] = map_name      # the next stage: the same run
            else:
                self._save_segment(now)
                self.pq = pq
                self._new_segment(now, level)
                if not self.no_reset:
                    self._new_session(now)
        elif self.seg is None:
            self._new_segment(now, level)
        if self.s_t0 is None:
            self.s_t0 = now
        read = (exp, pct, level)
        agreed = self.raw == read
        self.raw = read
        fits = self._fits_level(exp, pct, level)
        if not agreed or not fits:
            return 0                      # one read alone, or its EXP and percent disagree on the level's EXP
        if self.last is None:
            self.last = read
            return 0
        gain = self._gain(self.last, read)
        fresh, self.need_fresh = getattr(self, "need_fresh", False), False
        if gain is None:
            if fresh:
                self.last = read          # a level EXP just settled that the old read can't lead to: start here
            return 0                      # a misread: keep what we had
        self.last = read
        if gain <= 0 or self.paused:
            return 0
        # a break is measured from the last gain of any kind: at a low level every kill is over
        # LUMP_SHARE of the level, and measured from the last killing gain each kill would be a
        # lump after a "break", so the clock never started (0 s, no EXP/hr). Now only the first
        # gain after a real break can be a lump.
        resumed = self.last_any is None or now - self.last_any > BREAK
        self.last_any = now
        need = self.need or need_of(exp, pct) or 0
        lump = resumed and gain > LUMP_SHARE * need     # a quest turned in, not a kill
        if not lump:                       # a lump isn't grinding: it doesn't start the clock either
            dt = self._open_gap(now)       # the wait since the last gain is grinding time, unless a break
            self.s_active += dt
            self.seg["active"] += dt
            self.s_paced += gain
            self.last_gain = now
        self.events.append((now, gain, self.s_active, lump))
        self.events = [e for e in self.events
                       if e[2] >= self.s_active - WINDOW - 60 or e[0] >= now - CLOCK_WINDOW - 60]
        if self.s_start is None:
            self.s_start = now
        m = int(now // 60)
        self.minutes[m] = self.minutes.get(m, 0) + gain
        for old in [k for k in self.minutes if k < m - SPARK_MINUTES]:
            del self.minutes[old]
        self.s_gained += gain
        self.seg["exp"] += gain
        self.seg["level_end"] = level
        if self.seg["exp"] and now - (self.seg.get("saved") or 0) > 60:
            self.seg["saved"] = now
            self._save_segment(now)
        return gain

    def _fits_level(self, exp, pct, level):
        """True if exp / pct is this level's EXP. A new level (or the percent wrapping round) starts
        over: the first NEED_READS reads that agree among themselves set it."""
        need = need_of(exp, pct)
        if not need:
            return False
        if self.last and level is not None and self.last[2] is not None and level == self.last[2] + 1 \
                and pct >= self.last[1]:
            return False                  # the new level shows before its EXP: the old level's EXP still
        new_level =level != self.need_level or (self.need is not None and self.last is not None
                                                 and pct + 50 < self.last[1])
        if self.need is not None and not new_level:
            if abs(need - self.need) <= self.need * need_tol(pct):
                self.need_other = []
                return True
            # a wrong level EXP set by repeated misreads would shut out every right read after it:
            # RETHINK_VALUES different EXPs in a row that agree among themselves on another one
            # replace it. Different ones: standing still, one misread comes back the same every
            # read and would "agree" with itself (2026-11-08, it dropped 1,353 EXP)
            other = getattr(self, "need_other", [])
            if not other or other[-1][2] != exp:
                self.need_other = (other + [(need, pct, exp)])[-RETHINK_VALUES:]
            ref = sorted(n for n, _, _ in self.need_other)[len(self.need_other) // 2]
            if len(self.need_other) == RETHINK_VALUES and all(abs(n - ref) <= ref * need_tol(p)
                                                              for n, p, _ in self.need_other):
                self.need, self.need_other = ref, []
                self.last = None          # start again from here: no gain across the bad stretch
            return False
        if new_level:
            self.need, self.need_level, self.need_seen = None, level, []
        self.need_seen = (self.need_seen + [(need, pct)])[-NEED_READS:]
        if len(self.need_seen) < NEED_READS:
            return False
        ref = sorted(n for n, _ in self.need_seen)[NEED_READS // 2]
        if all(abs(n - ref) <= ref * need_tol(p) for n, p in self.need_seen):
            self.need, self.need_fresh = ref, True
            return True
        return False

    @staticmethod
    def _gain(old, new):
        e0, p0, l0 = old
        e1, p1, l1 = new
        need0 = e0 / (p0 / 100) if p0 else None
        up = (l0 is not None and l1 is not None and l1 == l0 + 1) or (l0 is None or l1 is None) and p1 + 50 < p0
        if up:
            if not need0 or p1 >= p0:
                return None               # a level-up starts the bar over: a fuller bar is the old level's
            return round(need0 - e0) + e1
        if l0 is not None and l1 is not None and l1 != l0:
            return None
        if e1 < e0:
            return None                   # EXP doesn't go down without a level-up (a death's loss is ignored too)
        if need0 and e1 - e0 > MAX_GAIN_SHARE * need0:
            return None
        return e1 - e0

    def mesos(self, mesos, now):
        """A read of your mesos (the inventory, while it's open)."""
        if mesos is None:
            return
        if self.s_mesos0 is None:
            self.s_mesos0 = mesos
        self.s_mesos = mesos
        if self.seg:
            if self.seg["mesos0"] is None:
                self.seg["mesos0"] = mesos
            self.seg["mesos"] = mesos

    # ---- dashboard
    def pause(self, on):
        self.paused = bool(on)
        if self.paused:
            self.last_gain = None          # the paused time isn't grinding time

    def reset(self, now):
        self._save_segment(now)
        self._new_segment(now, self.last[2] if self.last else None)
        self._new_session(now)

    def summary(self, now):
        running = self.last_gain is not None and now - self.last_gain <= BREAK and not self.paused
        # EXP/hr is cumulative over the session's grinding time: every wait between gains up to
        # BREAK counts (respawns, walking), longer ones are breaks and don't. One-off lumps (quests)
        # are left out. Counting only 15 s after each gain showed ~100K/hr against ~66K
        # really made (2026-11-11). The last WINDOW seconds of grinding give the recent rate.
        active = self.s_active + self._open_gap(now)
        hr = self.s_paced / active * 3600 if active >= 1 else None
        span = min(WINDOW, active)
        hr5 = None
        if span >= MIN_TTL_DATA:
            gained = sum(e[1] for e in self.events if e[2] > active - span and not e[3])
            hr5 = gained / span * 3600
        # time to level goes by the clock: everything gained over the last CLOCK_WINDOW, idle included
        t0 = self.s_t0 if self.s_t0 is not None else self.s_start
        clock_hr = None
        if t0 is not None and self.s_start is not None:
            wall = min(CLOCK_WINDOW, now - t0)
            if wall >= MIN_TTL_DATA:
                clock_hr = sum(e[1] for e in self.events if e[0] > now - wall) / wall * 3600
        ttl = None
        if self.last and clock_hr:
            e, p, _ = self.last
            if p:
                ttl = (e / (p / 100) - e) / (clock_hr / 3600)
        mhr = None
        if self.s_mesos0 is not None and self.s_mesos is not None and active >= 60:
            mhr = (self.s_mesos - self.s_mesos0) / active * 3600
        now_m = int(now // 60)
        spark = [self.minutes.get(m, 0) for m in range(now_m - SPARK_MINUTES + 1, now_m + 1)]
        level = self.last[2] if self.last else None
        need = self.need if self.need is not None else (need_of(self.last[0], self.last[1]) if self.last else None)
        return {"running": running, "paused": self.paused, "no_reset": self.no_reset, "gained": self.s_gained,
                "level": level, "need": round(need) if need else None,
                "left": round(need - self.last[0]) if need and self.last else None,
                "since": self.s_start, "spark": spark,
                "active_s": round(active, 1), "exp_hr": hr, "exp_hr_5m": hr5, "exp_hr_clock": clock_hr,
                "ttl_s": ttl, "mesos_hr": mhr,
                "map": self.pq or self.map, "map_id": self.map_id,
                "pq": self.pq_summary(now, need - self.last[0] if need and self.last else None) if self.pq else None,
                "exp": self.last[0] if self.last else None, "pct": self.last[1] if self.last else None}

    def pq_summary(self, now, left=None):
        """The run you're in, and today's finished runs of the same party quest."""
        g = self.seg or {}
        cur_id = g.get("id") or -1
        rows = self.db.execute("SELECT exp_gained, active_s FROM sessions WHERE pq=? AND start>=? AND id!=?",
                               (self.pq, day_start(now), cur_id)).fetchall()
        runs, exp, secs = len(rows), sum(r[0] for r in rows), sum(r[1] or 0 for r in rows)
        avg = round(exp / runs) if runs else None
        return {"name": self.pq, "stage": g.get("stage"), "run_exp": g.get("exp", 0),
                "run_secs": round(now - g["start"]) if g.get("start") is not None else 0,
                "runs": runs, "exp": exp, "secs": round(secs), "avg_exp": avg,
                "avg_secs": round(secs / runs) if runs else None,
                "exp_hr": exp / secs * 3600 if secs >= 1 else None,
                "runs_to_level": math.ceil(left / avg) if avg and left and left > 0 else None}

    def history(self, limit=20):
        cur = self.db.execute("SELECT start, end, map_id, map, level_start, level_end, exp_gained, active_s,"
                              " mesos_gained, pq FROM sessions ORDER BY start DESC LIMIT ?", (limit,))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def best_maps(self, level, levels_back=5, min_active=600, limit=3):
        """Your best maps by killing EXP an hour in your last few levels (it falls as you level), each with
        at least min_active seconds of grinding. Party quests aren't maps you'd go back to grind."""
        rows = self.db.execute(
            "SELECT map_id, map, MIN(level_start), MAX(level_end), SUM(exp_gained), SUM(active_s) FROM sessions"
            " WHERE pq IS NULL AND map_id IS NOT NULL AND level_end >= ? GROUP BY map_id",
            (int(level) - levels_back + 1,)).fetchall()
        out = [{"map_id": m, "map": name, "level_lo": lo, "level_hi": hi, "active_s": a, "exp_hr": round(e / a * 3600)}
               for m, name, lo, hi, e, a in rows if a and a >= min_active]
        return sorted(out, key=lambda r: -r["exp_hr"])[:limit]

    def by_map(self, min_active=120):
        """{map_id: your real EXP per hour there}, from at least min_active seconds of grinding."""
        rows = self.db.execute("SELECT map_id, SUM(exp_gained), SUM(active_s) FROM sessions GROUP BY map_id")
        return {m: e / a * 3600 for m, e, a in rows if m is not None and a and a >= min_active}
