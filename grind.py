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
DEATH_MAX = 0.10        # a death costs up to this share of the level's EXP (LUK lowers it)
DEATH_MIN = 0.005       # ...and at least this: a HUD digit misread that still fits the level is far less
STALL_AFTER = 300.0     # "no EXP" note: only after this much grinding on the map you're still on
KILL_SAMPLE = 30        # kills to level: the typical gain over this many recent ones
KILL_MIN = 5            # ... once there are at least this many
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
        for col in ("pq TEXT", "deaths INTEGER", "exp_lost INTEGER", "kills INTEGER", "mesos_picked INTEGER"):     # logs from before these
            try:
                self.db.execute(f"ALTER TABLE sessions ADD COLUMN {col}")
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
        self.last_session = None     # the session before this one, for Now in a town
        self.s_start = None
        self._new_session(None)

    # ---- state
    def _new_session(self, now):
        if getattr(self, "s_start", None) is not None:
            self.last_session = self._session_brief(now)
        self.s_gained, self.s_active, self.s_mesos0, self.s_mesos = 0, 0.0, None, None
        self.s_paced = 0             # EXP gained by killing: one-off lumps after a break left out
        self.s_start = None          # the session's first gain
        self.s_t0 = now              # when the session began watching, for the clock pace
        self.minutes = {}            # minute (epoch // 60) -> EXP gained in it, for the chart
        self.events = []             # (ts, gain, active seconds before it, lump), for the rates
        self.last_gain = None        # the last gain that counted as killing (runs the clock)
        self.last_any = None         # the last gain of any kind, lumps too (tells a break)
        self.deaths = []             # {"ts", "lost", "map"}: EXP drops of up to DEATH_MAX of the level
        self.kills = {}              # monster name (None: not named) -> your kills, from the EXP gains
        self.party_kills = {}        # monster name -> kills your party made (their share of the EXP came to you)
        self.loot = {}               # item name -> how many picked up, from the corner's lines
        self.picked = 0              # mesos picked up, from the corner's lines
        self.s_first = None          # {"level", "pct"} where the session's EXP bar started
        self.s_map = None            # the map the session's EXP came on

    def _new_segment(self, now, level):
        """A map's stretch in the log, or a whole party quest run (map_id None, map the PQ's name)."""
        self.seg = {"id": None, "start": now, "map_id": None if self.pq else self.map_id, "map": self.pq or self.map,
                    "pq": self.pq, "stage": self.map, "level_start": level, "level_end": level, "exp": 0,
                    "active": 0.0, "mesos0": None, "mesos": None, "deaths": 0, "exp_lost": 0, "kills": None,
                    "picked": None}

    def _save_segment(self, now):
        g = self.seg
        if not g or (g["exp"] <= 0 and not g.get("deaths")):     # a stretch with a death is kept, net below 0 too
            return
        active = now - g["start"] if g["pq"] else g["active"]      # a run counts all its time
        if g.get("kills") is None and not g["pq"]:      # no corner line read: kills worked out from the EXP
            k = self.per_kill()
            killed = g["exp"] + g.get("exp_lost", 0)
            g["kills_est"] = round(killed / k) if k and killed > 0 else None
        row = (g["start"], now, g["map_id"], g["map"], g["level_start"], g["level_end"], g["exp"], active,
               (g["mesos"] - g["mesos0"]) if g["mesos0"] is not None and g["mesos"] is not None else None, None,
               1 if g["pq"] else 0, g["pq"], g.get("deaths", 0), g.get("exp_lost", 0),
               g.get("kills") if g.get("kills") is not None else g.get("kills_est"), g.get("picked"))
        if g["id"] is None:
            cur = self.db.execute("INSERT INTO sessions (start, end, map_id, map, level_start, level_end, exp_gained,"
                                  " active_s, mesos_gained, potions_cost, party, pq, deaths, exp_lost, kills, mesos_picked)"
                                  " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
            g["id"] = cur.lastrowid
        else:
            self.db.execute("UPDATE sessions SET start=?, end=?, map_id=?, map=?, level_start=?, level_end=?,"
                            " exp_gained=?, active_s=?, mesos_gained=?, potions_cost=?, party=?, pq=?, deaths=?,"
                            " exp_lost=?, kills=?, mesos_picked=? WHERE id=?", row + (g["id"],))
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
            self.s_first = self.s_first or {"level": level, "pct": pct}
            return 0
        if self.s_first is None:
            self.s_first = {"level": self.last[2], "pct": self.last[1]}
        gain = self._gain(self.last, read)
        fresh, self.need_fresh = getattr(self, "need_fresh", False), False
        if gain is None:
            lost = self._death_loss(self.last, read)
            if lost:
                self._died(lost, read, now)
                return 0
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
        self.last_lump = lump
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
        self.minutes[m] = self.minutes.get(m, 0) + gain     # the whole session: Now's chart
        self.s_map = self.pq or self.map
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

    def _death_loss(self, old, new):
        """The EXP a death cost, if going from `old` to `new` (two reads agreed on it) is one: the same
        level, the bar lower by at most DEATH_MAX of the level's EXP, or down to 0. Else None."""
        e0, p0, l0 = old
        e1, p1, l1 = new
        if (l0 is not None and l1 is not None and l0 != l1) or e1 >= e0:
            return None
        need = self.need or need_of(e1, p1) or need_of(e0, p0)
        if not need:
            return None
        lost = e0 - e1
        return lost if DEATH_MIN * need <= lost <= DEATH_MAX * need + 1 else None

    def _died(self, lost, read, now):
        """Count a death: its EXP comes off the session, the map's log, the chart and the rates."""
        self.last = read
        self.deaths.append({"ts": now, "lost": lost, "map": self.pq or self.map})
        self.s_gained -= lost
        self.s_paced -= lost
        if self.seg is not None:
            self.seg["exp"] -= lost
            self.seg["deaths"] = self.seg.get("deaths", 0) + 1
            self.seg["exp_lost"] = self.seg.get("exp_lost", 0) + lost
        m = int(now // 60)
        self.minutes[m] = self.minutes.get(m, 0) - lost
        self.events.append((now, -lost, self.s_active, False))

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

    def add_kill(self, name, now, party=False):
        """A kill told by an EXP gain; name None when no monster here gives it. party: a party member's
        kill, whose share of the EXP came to you (not yours: kept apart, not in your kill counts)."""
        if party:
            self.party_kills[name] = self.party_kills.get(name, 0) + 1
            return
        self.kills[name] = self.kills.get(name, 0) + 1
        if self.seg is not None:
            self.seg["kills"] = (self.seg.get("kills") or 0) + 1

    def add_loot(self, name, count, now):
        """An item picked up ("Tree Branch x1 earned")."""
        self.loot[name] = self.loot.get(name, 0) + int(count)

    def add_mesos(self, n, now):
        """Mesos picked up ("You have gained mesos (+15)")."""
        self.picked += int(n)
        if self.seg is not None:
            self.seg["picked"] = (self.seg.get("picked") or 0) + int(n)

    def _kills_total(self):
        line = sum(self.kills.values())
        if line:
            return line
        k = self.per_kill()
        killed = self.s_paced + sum(d["lost"] for d in self.deaths)      # what was killed, deaths aside
        return max(0, round(killed / k)) if k else 0

    def _mesos_picked(self):
        if self.picked:
            return self.picked
        if self.s_mesos0 is not None and self.s_mesos is not None:
            return max(0, self.s_mesos - self.s_mesos0)
        return 0

    def _gain_pct(self):
        """How far the EXP bar moved this session, in % of a level (a level-up adds 100)."""
        if not self.s_first or not self.last:
            return None
        levels = 0
        if self.last[2] is not None and self.s_first["level"] is not None:
            levels = self.last[2] - self.s_first["level"]
        return round(levels * 100 + self.last[1] - self.s_first["pct"], 2)

    def _session_brief(self, now):
        """The session as Now's town view shows it once it's over."""
        end = self.last_gain or now or self.s_start
        active = self.s_active
        hr = round(self.s_paced / active * 3600) if active >= 1 else None
        return {"map": self.s_map, "start": self.s_start, "end": end, "active_s": round(active, 1),
                "exp_hr": hr if hr and hr > 0 else None,
                "gain_pct": self._gain_pct(), "level": self.last[2] if self.last else None,
                "kills_total": self._kills_total(), "items": sum(self.loot.values()),
                "mesos_picked": self._mesos_picked(), "deaths": len(self.deaths)}

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
        if hr is not None and hr <= 0:
            hr = None                     # a death cost more than was gained: no rate to speak of yet
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
        if self.last and clock_hr and clock_hr > 0:
            e, p, _ = self.last
            if p:
                ttl = (e / (p / 100) - e) / (clock_hr / 3600)
        mhr = None
        if self.s_mesos0 is not None and self.s_mesos is not None and active >= 60:
            mhr = (self.s_mesos - self.s_mesos0) / active * 3600
        now_m = int(now // 60)
        spark = [self.minutes.get(m, 0) for m in range(now_m - SPARK_MINUTES + 1, now_m + 1)]
        level = self.last[2] if self.last else None
        # "no EXP for a minute": you were grinding here a while and the HUD still reads, but nothing comes
        stalled = (not self.paused and self.last_gain is not None and self.seg is not None
                   and self.seg.get("active", 0) >= STALL_AFTER and now - self.last_gain >= BREAK)
        need = self.need if self.need is not None else (need_of(self.last[0], self.last[1]) if self.last else None)
        return {"running": running, "paused": self.paused, "no_reset": self.no_reset, "gained": self.s_gained,
                "level": level, "need": round(need) if need else None,
                "left": round(need - self.last[0]) if need and self.last else None,
                "since": self.s_start, "spark": spark,
                "active_s": round(active, 1), "exp_hr": hr, "exp_hr_5m": hr5, "exp_hr_clock": clock_hr,
                "ttl_s": ttl, "mesos_hr": mhr, "stalled": stalled,
                "deaths": [{"ts": d["ts"], "lost": d["lost"]} for d in self.deaths],
                "kills": [{"name": n, "count": c} for n, c in sorted(self.kills.items(), key=lambda kv: -kv[1])],
                "kills_total": self._kills_total(),
                "party_kills": [{"name": n, "count": c} for n, c in sorted(self.party_kills.items(), key=lambda kv: -kv[1])],
                "loot": [{"name": n, "count": c} for n, c in self.loot.items()],
                "mesos_picked": self._mesos_picked(), "start": self.s_first, "gain_pct": self._gain_pct(),
                "chart": self._chart(now),
                "exp_lost": sum(d["lost"] for d in self.deaths),
                "stalled_s": round(now - self.last_gain) if stalled else None,
                "per_kill": self.per_kill(), "kills_left": self.kills_left(need),
                "map": self.pq or self.map, "map_id": self.map_id,
                "pq": self.pq_summary(now, need - self.last[0] if need and self.last else None) if self.pq else None,
                "exp": self.last[0] if self.last else None, "pct": self.last[1] if self.last else None}

    def per_kill(self):
        """The EXP a kill usually gives: the median of the recent killing gains (a read that caught two
        kills at once is rarer than one), None until KILL_MIN of them."""
        gains = [e[1] for e in self.events if not e[3] and e[1] > 0][-KILL_SAMPLE:]     # deaths aren't kills
        if len(gains) < KILL_MIN:
            return None
        return sorted(gains)[len(gains) // 2]

    def kills_left(self, need):
        """About how many kills to the next level, at the usual EXP a kill."""
        k = self.per_kill()
        if not k or not need or not self.last:
            return None
        return max(0, math.ceil((need - self.last[0]) / k))

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

    def _chart(self, now):
        """EXP per minute over the whole session (net of deaths), from its first minute to now."""
        if not self.minutes:
            return {"t0": None, "vals": []}
        t0, t1 = min(self.minutes), max(max(self.minutes), int(now // 60))
        return {"t0": t0, "vals": [self.minutes.get(m, 0) for m in range(t0, t1 + 1)]}

    def all_maps(self, level, levels_back=5, min_active=600):
        """Every map ground on in your last few levels, best EXP an hour first, with kills and mesos
        an hour: mesos picked up where the corner was read, else your mesos' change. No party quests."""
        rows = self.db.execute(
            "SELECT map_id, map, MIN(level_start), MAX(level_end), SUM(exp_gained), SUM(active_s),"
            " SUM(kills), SUM(CASE WHEN kills IS NOT NULL THEN active_s END),"
            " SUM(COALESCE(mesos_picked, mesos_gained)), SUM(CASE WHEN COALESCE(mesos_picked, mesos_gained)"
            " IS NOT NULL THEN active_s END) FROM sessions"
            " WHERE pq IS NULL AND map_id IS NOT NULL AND level_end >= ? GROUP BY map_id",
            (int(level) - levels_back + 1,)).fetchall()
        out = []
        for m, name, lo, hi, e, a, k, ka, ms, ma in rows:
            if not a or a < min_active:
                continue
            out.append({"map_id": m, "map": name, "level_lo": lo, "level_hi": hi, "active_s": a,
                        "exp_hr": round(e / a * 3600), "kills_hr": round(k / ka * 3600) if k and ka else None,
                        "mesos_hr": round(ms / ma * 3600) if ms is not None and ma else None})
        return sorted(out, key=lambda r: -r["exp_hr"])

    def best_maps(self, level, levels_back=5, min_active=600, limit=5):
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
