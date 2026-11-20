# Grind: honest grinding time, and parties Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grind's EXP/hour, kill counts and best maps stay true when your EXP comes in a party's shares.

**Architecture:** Two changes in `app/grind.py`:
- Reads that show your EXP rising, but don't count yet, count toward grinding time.
- The corner's "Bonus EXP for PARTY" lines (already parsed by `notices.Corner`) mark the session as a party one.

Then `app/sniper.py` stops making up kills in a party. The best-maps SQL keeps party rows apart, and the dashboard (`web/index.html`) says "party" where it matters.

**Tech Stack:** Python 3 (sqlite3), pytest, vanilla JS in `web/index.html`.

**Spec:** the findings below. They come from a live party grind on 2026-11-20 (Tura1, Hunter lv 38→39, The Burnt Land II, Companion 1.4.5), with no separate spec doc.

## Findings (what this plan fixes)

1. **EXP/hour too high (112K shown, ~85K real).**
   - A new EXP counts only after two reads in a row agree, so one misread can't count. In a party the EXP changes on almost every read, so in the live samples an EXP change was counted only every 3–30 s.
   - `_open_gap` counts the wait since the last counted gain only up to `BREAK` (60 s); a longer wait counts 0 s. The EXP that came in during that wait still counts in `s_paced`, so the rate is inflated.
   - Live: 30 min wall, 23 min "grinding", while the chart had EXP in 27 of 30 minutes.
   - Over a later 5-minute sample with no time lost, the real pace was 75K/hr (5-min rate 72K, clock 68K), while the headline still showed 104K from the time lost earlier.
   - Simulated on today's code, reads that rise every 2 s but match only every 90 s give 644 s of grinding as 0 s and 1.1M EXP/hr.
   - The EXP total is right: gains are differences between reads and add up correctly.
2. **Made-up kills in a party.**
   - One counted change (~229 EXP) holds many party shares. `handle_grind` counts it as one unnamed kill (145 "kills", "948 kills to level 40"), or as whole Fire Boars when it happens to divide by 60 ("Fire Boar 12").
   - The loot (167 Fire Boar's Tooth) shows the real kills were several times higher.
   - `party.Fitter` can't explain gains of more than `MOST` = 4 kills.
3. **Party sessions logged as solo.**
   - The `sessions.party` column is written as the party-quest flag and read nowhere.
   - `best_maps`/`all_maps`/`by_map` rank party EXP against solo maps: The Burnt Land II 113K in a party sat above Ant Tunnel Park 99K solo.

4. **A death right at the limit.**
   - 12:46 live: a death cost 26,668 EXP (9.99% of 266,857). The limit is `DEATH_MAX * need + 1` = 26,686, a margin of 18 EXP.
   - It was counted, and the card (+28,433 net, 53K/hr) is right.
   - Simulated a hair over the limit, the first read misses it. The next read catches it as a smaller loss, ~200 EXP off.
   - Headroom makes such a death exact.

**Not changed:** the headline stays EXP per *grinding* hour (the 2026-11-11 decision). "By the clock" stays the 15-minute pace with breaks included. Once finding 1 is fixed they differ only by real breaks.

## Global Constraints

- Run every test with the repo's `tests/conftest.py` (it sets one thread and below-normal priority). Run from `classic/companion`: `python -m pytest <files> -q -p no:cacheprovider`. Never start a multi-core numpy or OCR run: the user is playing.
- The misread rules stay as they are: two reads must agree before a gain counts, plus `_fits_level`, the rethink and `MAX_GAIN_SHARE`. This plan changes only how *time* is counted and how gains are *told as kills*.
- Solo behaviour stays the same: every existing test in `tests/test_grind*.py`, `tests/test_party.py` and `tests/test_now_api.py` keeps passing unchanged.
- No schema change. `sessions.party` already exists. The party flag for a history card goes into its `data` JSON.
- Dashboard copy is plain words, like the rest of the card. Party copy: "In a party your EXP comes in shares, so kills aren't counted."
- Work on a branch `fix/grind-party-time` off `main`. No version bump, build or release in this plan: the user decides that afterwards.

## Review Focus

- **A quest turned in after a break** (one +7,020 jump with nothing before it) must still be a lump. It must not count as grinding time or toward the EXP/hour. → Task 1, `test_a_quest_after_a_break_is_still_a_lump`.
- **Rising reads while paused** must not count. → Task 1, `test_rising_reads_while_paused_dont_count`.
- **A duo that the Fitter does explain** (the 2026-11-13 West Rocky Mountain IV gains) must still be told as your kills and your party's, once the corner reports party lines. → Task 2, `test_a_duo_the_fitter_explains_is_still_told`.
- **Leaving a party:** after 5 minutes without a party line, solo kill naming comes back. The session that saw party EXP stays a party session. → Task 2, `test_party_is_forgotten_after_five_minutes`.
- **Old rows** (party column 0, or PQ rows written with 1) must not show as party maps. PQ rows are already left out by `pq IS NULL`. → Task 3, `test_old_pq_rows_are_not_party_maps`.

---

### Task 1: Rising reads count as grinding time

**Files:**
- Modify: `app/grind.py` (`_new_session`, `update`, `_open_gap`, `pause`, `summary`)
- Test: `tests/test_grind_party.py` (new)

**Interfaces:**
- Produces:
  - `Grind.moves: list[tuple[float, int]]`, the `(ts, exp)` of reads since the last counted gain that fit the level and showed EXP rising but weren't counted yet;
  - `Grind._open_gap(now: float, below: int | None = None) -> float`;
  - `Grind._last_active() -> float | None`.

- [ ] **Step 1: Write the failing tests** in `tests/test_grind_party.py`. Reuse the helpers from `tests/test_grind.py` (`tracker`, `pct`, `NEED`, `feed`). Add one more helper: `rising(g, t0, exp0, holds, step=2.0, per_read=20, per_hold=45) -> (t, exp)`.
  - Each hold block is `per_hold - 1` reads, `step` s apart, each +`per_read` EXP, then one more +`per_read` read shown twice so two reads agree.
  - So the feed always ends on an agreed read. A block is +900 EXP, under 1% of `NEED`, so it's never a lump.

```python
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
    t = feed(g, [50000 + 100 * i for i in range(30)])   # 3 min of grinding
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
```

- [ ] **Step 2: Run them and make sure they fail**

Run: `python -m pytest tests/test_grind_party.py -q -p no:cacheprovider`
Expected: `test_rising_reads_count_as_grinding_time` FAILS (`active_s` far below 540). The other two may pass already: they guard the change.

- [ ] **Step 3: Implement in `app/grind.py`**
  - `_new_session`: `self.moves = []`.
  - `update`: after `fits` is computed, if `fits and not agreed and not self.paused` and `self.last` is on the same level with `self.last[0] < exp <= self.last[0] + MAX_GAIN_SHARE * (self.need or need_of(exp, pct))`, append `(now, exp)` to `self.moves`.
  - `_open_gap(now, below=None)`: walk the points `[last_gain] + [t for (t, e) in moves if t > last_gain and (below is None or e < below)] + [now]`. Sum each step `b - a` with `0 <= b - a <= BREAK`. Return 0 when paused or when `last_gain` is None. With no moves this equals today's rule.
  - The counting branch:
    - `dt = self._open_gap(now, below=exp)`;
    - `resumed`: measure from the latest of `last_any` and the move times with `e < exp`. A quest's own first sighting carries its full EXP, so it never hides the break before it;
    - clear `self.moves` wherever `last_gain` is set.
  - `pause(True)` and `_died`: clear `self.moves`. After a death the old rises are above the new bar.
  - `_last_active()`: the latest of `last_gain` and the last move's time.
  - `summary`: `running` and `stalled` use `_last_active()` in place of `last_gain`.

- [ ] **Step 4: Run the new tests and every Grind test**

Run: `python -m pytest tests/test_grind_party.py tests/test_grind.py tests/test_grind_session.py tests/test_grind_deaths.py tests/test_grind_history.py tests/test_grind_now.py tests/test_grind_app.py -q -p no:cacheprovider`
Expected: all pass (88 old + 3 new).

- [ ] **Step 5: Commit**

```bash
git add app/grind.py tests/test_grind_party.py
git commit -m "fix(grind): reads that show EXP rising count as grinding time, so a party's EXP/hour isn't inflated"
```

### Task 2: The corner's party lines make a party session; no made-up kills

**Files:**
- Modify: `app/grind.py` (`__init__`, `_new_session`, `_new_segment`, `_save_segment`, `save_card`, `_session_brief`, `summary`, `_kills_total`, `kills_left`)
- Modify: `app/sniper.py` (`handle_corner`, `handle_grind`)
- Test: `tests/test_grind_party.py`

**Interfaces:**
- Consumes: Task 1's `Grind.moves` (untouched here).
- Produces:
  - `PARTY_FORGET = 300.0` in `grind.py`;
  - `Grind.add_party_bonus(n: int, now: float) -> None`;
  - `Grind.in_party(now: float) -> bool`;
  - `Grind.s_party: bool`;
  - `summary(now)["party"]: bool` (this session saw party EXP);
  - the history card's `data["party"]: bool`;
  - the `sessions.party` column is 1 for a party segment (or a PQ run, as before).

- [ ] **Step 1: Write the failing tests.** Grind-level tests, plus app-level ones using `sniper.handle_grind` and `sniper.handle_corner` with a fake data object (no `game_reader`):

```python
BL2 = 10004112
MOBS = [("Fire Boar", 60, 19), ("Dark Axe Stump", 43, 12)]
def fake_data():
    def split(mid, gain):          # whole kills only, like gamedata.split_kills
        for k in range(1, 7):
            if gain == 60 * k: return ["Fire Boar"] * k
        return None
    return SimpleNamespace(maps={BL2: {"name": "The Burnt Land II"}}, split_kills=split, map_mobs=lambda mid: MOBS)

def test_party_lines_mark_the_session(tmp_path):
    # handle_corner(a, [("party", 3)]) -> grind.summary(t)["party"] is True; after gains + flush,
    # SELECT party FROM sessions -> 1; the saved card's data JSON has "party": true

def test_in_a_party_chunks_are_not_made_up_kills(tmp_path):
    # a party line, then live chunk gains [734, 195, 214, 106, 206, 240, 58, 120] (two reads each)
    s = a.grind.summary(t)
    assert s["kills"] == [] and s["kills_total"] == 0 and s["kills_left"] is None and s["party"]

def test_solo_gains_are_still_named(tmp_path):
    # no party line, gains of 60 and 120 -> kills == [{"name": "Fire Boar", "count": 3}]

def test_party_is_forgotten_after_five_minutes(tmp_path):
    g.add_party_bonus(3, 1000.0)
    assert g.in_party(1000.0 + 300) and not g.in_party(1000.0 + 301)

def test_a_duo_the_fitter_explains_is_still_told(tmp_path, game_reader):
    # tests/test_now_api.py's two-player West Rocky Mountain IV gains, with handle_corner(a, [("party", 3)])
    # before them: yours["Wild Boar"] >= 10 and party["Wild Boar"] >= 2, as that test asserts
```

- [ ] **Step 2: Run them and make sure they fail**

Run: `python -m pytest tests/test_grind_party.py -q -p no:cacheprovider`
Expected: FAIL with `AttributeError: 'Grind' object has no attribute 'add_party_bonus'` (and `KeyError: 'party'`).

- [ ] **Step 3: Implement**
  - In `grind.py`:
    - `party_at = None` in `__init__`; it stays across sessions, since you're still in the party on the next map;
    - `s_party = False` in `_new_session`, and `"party": False` in `_new_segment`;
    - `add_party_bonus` sets all three;
    - `in_party` is `party_at is not None and now - party_at <= PARTY_FORGET`;
    - `_save_segment` writes `party` as `1 if g["pq"] or g.get("party") else 0`, and skips `kills_est` for a party segment;
    - `_kills_total` returns only the told kills when `s_party`;
    - `kills_left` returns None when `s_party`;
    - `summary`, `_session_brief` and the card's `data` carry `"party": self.s_party`.
  - In `sniper.py`:
    - `handle_corner`: `("party", n)` → `g.add_party_bonus(n, now)`;
    - `handle_grind`: when `g.in_party(now)`, skip the solo `split_kills` naming and use the Fitter's model only. When the model is None, add no kills. Out of a party, nothing changes.

- [ ] **Step 4: Run the new tests and the regression set**

Run: `python -m pytest tests/test_grind_party.py tests/test_grind*.py tests/test_party.py tests/test_now_api.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/grind.py app/sniper.py tests/test_grind_party.py
git commit -m "fix(grind): the corner's party lines mark a party session, and its EXP shares aren't counted as kills"
```

### Task 3: Best maps keep party grinding apart

**Files:**
- Modify: `app/grind.py` (`best_maps`, `all_maps`, `by_map`)
- Test: `tests/test_grind_party.py`

**Interfaces:**
- Consumes: Task 2's `sessions.party` = 1 for party segments.
- Produces:
  - each row of `best_maps()` / `all_maps()` gains `"party": bool`, grouped by `(map_id, party)`;
  - `by_map()` counts only rows with `COALESCE(party, 0) = 0`. It feeds the advisor's "your real EXP/hr", which is a solo figure.

- [ ] **Step 1: Write the failing tests.** Insert `sessions` rows straight into `g.db`:
  - map 1 solo: 600 s, 10,000 EXP, level 38;
  - map 1 party: 600 s, 20,000 EXP, level 38;
  - a PQ row with `party` 1 and `pq` "Kerning PQ".

```python
def test_party_and_solo_rows_rank_apart(tmp_path):
    rows = g.best_maps(38)
    assert sorted((r["exp_hr"], r["party"]) for r in rows if r["map_id"] == 1) == [(60000, False), (120000, True)]
    assert g.by_map()[1] == 60000
    assert [r["party"] for r in g.all_maps(38) if r["map_id"] == 1].count(True) == 1

def test_old_pq_rows_are_not_party_maps(tmp_path):
    assert all(r["map_id"] is not None for r in g.best_maps(38))
```

- [ ] **Step 2: Run them and make sure they fail**

Run: `python -m pytest tests/test_grind_party.py -k "rank_apart or pq_rows" -q -p no:cacheprovider`
Expected: FAIL with `KeyError: 'party'`.

- [ ] **Step 3: Implement.** Add `COALESCE(party, 0)` to the SELECT and GROUP BY of `best_maps` and `all_maps`, and put it into each row as `bool`. In `by_map`, add `WHERE COALESCE(party, 0) = 0`.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_grind_party.py tests/test_grind*.py tests/test_now_api.py tests/test_advisor.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/grind.py tests/test_grind_party.py
git commit -m "fix(grind): best maps and your real EXP/hr per map keep party grinding apart from solo"
```

### Task 4: The dashboard says "party"

**Files:**
- Modify: `companion.py` (`session_view`: add `"party": s["party"]`)
- Modify: `web/index.html` (`grindCard`, `mapCard`, `bestMaps`, `allMapsModal`)
- Modify: `docs/features.md` (one line under Grind)
- Test: `tests/test_now_api.py`

**Interfaces:**
- Consumes: `summary(now)["party"]` (Task 2) and the best-map rows' `party` (Task 3).

- [ ] **Step 1: Write the failing test** `test_session_view_says_party`. After `handle_corner(a, [("party", 3)])` and a few reads, assert `companion.session_view(a.grind, d, mid, 1e10)["party"] is True`. Solo, assert it is False.

- [ ] **Step 2: Run it and make sure it fails**

Run: `python -m pytest tests/test_now_api.py -k party -q -p no:cacheprovider`
Expected: FAIL with `KeyError: 'party'`.

- [ ] **Step 3: Implement**
  - `session_view`: add `"party"`.
  - `grindCard`, when `n.party`:
    - a `<span class="chip">Party</span>` after the map in the title;
    - the third tile shows `fmt(n.left)` over "EXP to level ${up}" instead of kills.
  - `mapCard`, when `sv.party`:
    - the kill boxes show "—";
    - the "more killed…" / "About N killed…" lines become "In a party your EXP comes in shares, so kills aren't counted."
    - Leave the "+N by party" line from the Fitter in place when it has told kills.
  - `bestMaps` and `allMapsModal`: `<span class="chip">party</span>` after a party row's map name.
  - `docs/features.md`: one line saying party grinding is marked and its kills aren't counted.

- [ ] **Step 4: Run the tests, then a look**

Run: `python -m pytest tests/test_now_api.py tests/test_grind_party.py -q -p no:cacheprovider`
Expected: all pass.

Then, with the user's OK only (it reads the game beside their installed copy), run `python companion.py --second-copy --no-update --no-browser` and open its port (8766 when 8765 is taken). Put a screenshot of Now in the brainstorming preview with a short Hebrew caption.

- [ ] **Step 5: Commit**

```bash
git add companion.py web/index.html docs/features.md tests/test_now_api.py
git commit -m "feat(grind): the card, the map's kills and best maps say when you're grinding in a party"
```

### Task 5: A death right at 10% counts at once

**Files:**
- Modify: `app/grind.py` (`DEATH_MAX`)
- Test: `tests/test_grind_deaths.py`

**Interfaces:** none new. `DEATH_MAX` goes from `0.10` to `0.105`, and its comment says why.

- [ ] **Step 1: Write the failing test** `test_a_death_a_hair_over_ten_percent_counts_whole`:
  - grind on level 39 with `NEED = 266857`, the percent from `round(e / NEED * 100, 2)` and two reads each, until the level's EXP is learned;
  - then drop the EXP by `round(0.1003 * NEED)` and read twice;
  - `assert len(s["deaths"]) == 1 and s["deaths"][0]["lost"] == round(0.1003 * NEED)` right after those two reads.

- [ ] **Step 2: Run it and make sure it fails**

Run: `python -m pytest tests/test_grind_deaths.py -k hair -q -p no:cacheprovider`
Expected: FAIL (no death yet on those reads).

- [ ] **Step 3: Implement.** Set `DEATH_MAX = 0.105` (the level's EXP is worked out from a percent shown to 0.01, so it can be a little low).

- [ ] **Step 4: Run the death tests and the Grind tests**

Run: `python -m pytest tests/test_grind*.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/grind.py tests/test_grind_deaths.py
git commit -m "fix(grind): a death a hair over 10% of the level's estimated EXP counts at once, whole"
```

---

## After the tasks (the user decides each)

- Push the branch and open a PR. Merge only after the user says "approved".
- Release: bump `version.py`, then build `CompanionSetup.exe` in a clean clone without `discord.json` (see the release rules).
- Today's party rows in the installed `data/grind.sqlite` were saved as solo with too little grinding time (The Burnt Land II, sessions 225 onward, history card 8). Ask whether to mark them `party = 1` or delete them. They can't be corrected, and as solo rows they top "Your best maps" with an inflated 113K.
