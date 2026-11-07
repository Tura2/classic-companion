"""
Grind tracker: EXP per hour, time to the next level and mesos per hour, from the HUD's EXP ("73,665
[60.01%]", read by reader/hudexp) and the inventory's mesos. Kept per map in grind.sqlite, so over
time it says which map really pays best for you.

A session runs while EXP comes in: 15 s without a gain pauses it (and the clock), the next gain
resumes it. Each map is its own segment in the log; on the dashboard a map change starts the
numbers over unless "No reset" is on. One misread never counts: a new EXP needs two reads in a row,
and EXP going down without a level-up is dropped. The EXP a level needs is exp / pct, so no EXP
table is needed; a level-up adds what was left of the old level plus the new EXP.
"""
import sqlite3
import time

IDLE = 15.0             # seconds without a gain before the clock stops
WINDOW = 300.0          # "last 5 minutes" rate
MIN_TTL_DATA = 60.0     # seconds of active time before time-to-level is shown
MAX_GAIN_SHARE = 0.6    # one step gaining more than this share of a level is a misread
NEED_READS = 3          # reads that agree on the level's EXP (exp / pct) before any is trusted


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
        self.db.commit()
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
        self.events = []             # (ts, gain, active seconds before it), for the 5-minute rate
        self.last_gain = None
        self.last_tick = now

    def _new_segment(self, now, level):
        self.seg = {"id": None, "start": now, "map_id": self.map_id, "map": self.map, "level_start": level,
                    "level_end": level, "exp": 0, "active": 0.0, "mesos0": None, "mesos": None}

    def _save_segment(self, now):
        g = self.seg
        if not g or g["exp"] <= 0:
            return
        row = (g["start"], now, g["map_id"], g["map"], g["level_start"], g["level_end"], g["exp"], g["active"],
               (g["mesos"] - g["mesos0"]) if g["mesos0"] is not None and g["mesos"] is not None else None, None, 0)
        if g["id"] is None:
            cur = self.db.execute("INSERT INTO sessions (start, end, map_id, map, level_start, level_end, exp_gained,"
                                  " active_s, mesos_gained, potions_cost, party) VALUES (?,?,?,?,?,?,?,?,?,?,?)", row)
            g["id"] = cur.lastrowid
        else:
            self.db.execute("UPDATE sessions SET start=?, end=?, map_id=?, map=?, level_start=?, level_end=?,"
                            " exp_gained=?, active_s=?, mesos_gained=?, potions_cost=?, party=? WHERE id=?", row + (g["id"],))
        self.db.commit()

    def flush(self, now=None):
        self._save_segment(now or time.time())

    # ---- reads
    def _tick(self, now):
        """Advance the clock: active time counts only while gains keep coming."""
        if self.last_tick is not None and self.last_gain is not None and not self.paused:
            dt = max(0.0, min(now, self.last_gain + IDLE) - max(self.last_tick, self.last_gain - IDLE))
            dt = max(0.0, min(dt, now - self.last_tick))
            self.s_active += dt
            if self.seg:
                self.seg["active"] += dt
        self.last_tick = now

    def update(self, exp, pct, level, map_id, map_name, now):
        """One read of the HUD's EXP. Returns the EXP it counted (0 for none)."""
        if exp is None or pct is None:
            return 0
        if map_id is not None and map_id != self.map_id:
            self._save_segment(now)
            self.map_id, self.map = map_id, map_name
            self._new_segment(now, level)
            if not self.no_reset:
                self._new_session(now)
        elif self.seg is None:
            self._new_segment(now, level)
        self._tick(now)
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
        if gain is None:
            return 0                      # a misread: keep what we had
        self.last = read
        if gain <= 0 or self.paused:
            return 0
        if self.last_gain is None or now - self.last_gain > IDLE:
            self.last_tick = now           # resuming: the idle time doesn't count
        self.events.append((now, gain, self.s_active))
        self.events = [e for e in self.events if e[0] >= now - WINDOW - 60]
        self.last_gain = now
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
        new_level = level != self.need_level or (self.need is not None and self.last is not None
                                                 and pct + 50 < self.last[1])
        if self.need is not None and not new_level:
            return abs(need - self.need) <= self.need * need_tol(pct)
        if new_level:
            self.need, self.need_level, self.need_seen = None, level, []
        self.need_seen = (self.need_seen + [(need, pct)])[-NEED_READS:]
        if len(self.need_seen) < NEED_READS:
            return False
        ref = sorted(n for n, _ in self.need_seen)[NEED_READS // 2]
        if all(abs(n - ref) <= ref * need_tol(p) for n, p in self.need_seen):
            self.need = ref
            return True
        return False

    @staticmethod
    def _gain(old, new):
        e0, p0, l0 = old
        e1, p1, l1 = new
        need0 = e0 / (p0 / 100) if p0 else None
        up = (l0 is not None and l1 is not None and l1 == l0 + 1) or (l0 is None or l1 is None) and p1 + 50 < p0
        if up:
            if not need0:
                return None
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

    def reset(self, now):
        self._save_segment(now)
        self._new_segment(now, self.last[2] if self.last else None)
        self._new_session(now)

    def summary(self, now):
        self._tick(now)
        running = self.last_gain is not None and now - self.last_gain <= IDLE and not self.paused
        hr = self.s_gained / self.s_active * 3600 if self.s_active >= 1 else None
        recent = [e for e in self.events if e[0] >= now - WINDOW]
        hr5 = None
        if recent:
            start = [e for e in self.events if e[0] < now - WINDOW]
            act0 = start[-1][2] if start else (recent[0][2] if len(recent) > 1 else 0)
            gained = sum(e[1] for e in recent if e[2] >= act0) if start else sum(e[1] for e in recent[1:])
            span = self.s_active - act0
            hr5 = gained / span * 3600 if span >= 1 else None
        ttl = None
        if self.last and self.s_active >= MIN_TTL_DATA and hr5:
            e, p, _ = self.last
            if p:
                ttl = (e / (p / 100) - e) / (hr5 / 3600)
        mhr = None
        if self.s_mesos0 is not None and self.s_mesos is not None and self.s_active >= 60:
            mhr = (self.s_mesos - self.s_mesos0) / self.s_active * 3600
        return {"running": running, "paused": self.paused, "no_reset": self.no_reset, "gained": self.s_gained,
                "active_s": round(self.s_active, 1), "exp_hr": hr, "exp_hr_5m": hr5, "ttl_s": ttl, "mesos_hr": mhr,
                "map": self.map, "map_id": self.map_id,
                "exp": self.last[0] if self.last else None, "pct": self.last[1] if self.last else None}

    def history(self, limit=20):
        cur = self.db.execute("SELECT start, end, map_id, map, level_start, level_end, exp_gained, active_s,"
                              " mesos_gained FROM sessions ORDER BY start DESC LIMIT ?", (limit,))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def by_map(self, min_active=120):
        """{map_id: your real EXP per hour there}, from at least min_active seconds of grinding."""
        rows = self.db.execute("SELECT map_id, SUM(exp_gained), SUM(active_s) FROM sessions GROUP BY map_id")
        return {m: e / a * 3600 for m, e, a in rows if m is not None and a and a >= min_active}
