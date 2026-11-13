# Now: this session — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Now shows the grind session's EXP change, kills, loot, mesos and deaths (layout C), a town layout, and two pop-ups; deaths count wherever EXP does.

**Architecture:**
- `grind.Grind` gains deaths and per-session tallies (kills, loot, mesos picked up), stored per segment in `grind.sqlite`.
- A new `notices.py` turns the game's bottom-right corner lines into events, counted once.
- `reader.read_notices` reads that corner (tuned on samples, Task 9). `sniper.handle_grind` feeds the events to `Grind`.
- `/api/grind` and a new `/api/allmaps` carry it all to `web/index.html`, whose Now tab is rebuilt.

**Tech Stack:** Python 3.11, numpy, Pillow, winocr, rapidfuzz, sqlite3; vanilla JS/HTML/CSS dashboard; pytest.

**Spec:** `docs/superpowers/specs/2026-11-13-now-session-design.md` (approved). The approved look: `.superpowers/brainstorm/1848-1794574135/content/now-session-v16.html` (generator `scripts/mock_session3.py`); match it.

## Global Constraints

- Never send input to the game; reads are passive pictures. Test against the real game only when the user asks.
- No page scroll, no blank gaps, nothing spilling out of a card; long lists page with the orange ◀ ▶ arrows (`pageFit`).
- No prices on the page; worth only in the hover tooltip (`#tip.small`, ~250 px wide).
- A death counts only when EXP drops: more than 0 and at most 10% of the level's EXP (or to 0 when less was left), two reads in a row, no level change. A bigger drop is a misread.
- Deaths count in EXP / hour, time to level, session EXP gained, the EXP change bar, the chart, best maps, All maps, Last session.
- Session = Grind's session (resets on map change unless `no_reset`, and on Start over).
- NET = mesos picked up (corner lines); fallback to the inventory mesos Grind already reads.
- Party quests keep Grind's PQ strip; All maps leaves PQs out.
- Files open with `encoding="utf-8"` (cp1255 locale). Branch `feat/now-session` from `origin/main`. Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A corner line still on screen next read, after scrolling up a row, must not count twice; two identical new lines must count as two (Task 3, `test_identical_lines_count_by_their_shift`).
2. A HUD misread of a lower EXP that happens to be under 10% must not become a death unless two reads agree (Task 1, `test_one_low_read_is_not_a_death`).
3. A level-up in the session: the EXP change row reads `Lv. 37 → 38` and the gain counts across the level (Task 2, `test_exp_change_across_a_level_up`).
4. Walking into town with `no_reset` on: the session goes on; Now shows "This session" in the compact row (Task 6, `test_town_with_keep_counting_shows_this_session`).
5. An EXP line matching no monster on the map (party share, event bonus) still counts as a kill, unnamed (Task 4, `test_unknown_exp_is_an_unnamed_kill`).

---

### Task 1: Deaths in Grind

**Files:**
- Modify: `grind.py` (`Grind._gain`, `Grind.update`, `_new_session`, `summary`, `_save_segment`, schema)
- Test: `tests/test_grind_deaths.py` (helpers `tracker`, `feed`, `pct`, `NEED` from `tests/test_grind.py`)

**Interfaces:**
- Produces:
  - `Grind.deaths: list[dict]` — `{"ts": float, "lost": int, "map": str|None}`, this session.
  - `summary()` adds `"deaths": [{"ts", "lost"}]` and `"exp_lost": int`.
  - `sessions` table gains columns `deaths INTEGER`, `exp_lost INTEGER` (ALTER in try/except, like `pq`).
- Constants: `DEATH_MAX = 0.10` (share of the level's EXP).

- [ ] **Step 1: Write the failing tests**

```python
def test_a_ten_percent_drop_is_a_death(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(20)])            # grinding
    t = feed(g, [51900 - round(NEED * 0.10)], t0=t)              # two reads agree on the drop
    s = g.summary(t)
    assert [d["lost"] for d in s["deaths"]] == [round(NEED * 0.10)] and s["exp_lost"] == round(NEED * 0.10)
    assert s["gained"] == 1900 - round(NEED * 0.10)              # net

def test_a_smaller_drop_is_a_death_too(tmp_path):                 # LUK lowers the loss
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(20)])
    t = feed(g, [51900 - round(NEED * 0.04)], t0=t)
    assert len(g.summary(t)["deaths"]) == 1

def test_a_bigger_drop_is_a_misread(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(20)])
    t = feed(g, [51900 - round(NEED * 0.30)], t0=t)
    assert g.summary(t)["deaths"] == []

def test_one_low_read_is_not_a_death(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(20)])
    g.update(50000, pct(50000), 32, 1, "Ant Tunnel I", t)          # one read only
    t = feed(g, [52000], t0=t + 2)
    assert g.summary(t)["deaths"] == []

def test_deaths_lower_exp_per_hour_and_are_saved(tmp_path):
    g = tracker(tmp_path)
    t = feed(g, [50000 + 100 * i for i in range(101)])
    hr = g.summary(t)["exp_hr"]
    t = feed(g, [60000 - round(NEED * 0.10)], t0=t)
    assert g.summary(t)["exp_hr"] < hr
    g.flush(t)
    row = g.db.execute("SELECT deaths, exp_lost FROM sessions").fetchone()
    assert row == (1, round(NEED * 0.10))
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -I -m pytest -q tests/test_grind_deaths.py`
Expected: FAIL (`KeyError: 'deaths'`).

- [ ] **Step 3: Implement**

- In `update`, where `_gain` returns None and the read is confirmed (`agreed and fits`), add a check: same level as `self.last`, `0 < last_exp - exp <= DEATH_MAX * need + 1`, or `exp == 0`. If it passes:
  - append the death;
  - subtract the loss from `s_gained`, `s_paced`, `seg["exp"]` and `minutes[m]`;
  - append a negative event to `events`, so the recent rate and the clock pace behind the time to level count it;
  - set `self.last = read`.
- `_gain` keeps returning None for drops.
- Reset `deaths` in `_new_session`; count deaths and the EXP lost per segment (`seg["deaths"]`, `seg["exp_lost"]`); write both in `_save_segment`.

- [ ] **Step 4: Run them to see them pass, plus the grind suites**

Run: `python -I -m pytest -q tests/test_grind_deaths.py tests/test_grind.py tests/test_grind_now.py tests/test_grind_app.py`
Expected: all pass.

- [ ] **Step 5: Commit** — `feat(grind): a confirmed EXP drop of up to 10% of the level is a death, counted net`

---

### Task 2: Session tallies, EXP change, the whole-session chart, last session, all maps

**Files:**
- Modify: `grind.py`
- Test: `tests/test_grind_session.py`

**Interfaces:**
- Produces:
  - `Grind.add_kill(name: str|None, now: float)`.
  - `Grind.add_loot(name: str, count: int, now: float)`.
  - `Grind.add_mesos(n: int, now: float)`: mesos picked up.
  - `summary()` adds:
    - `"kills": [{"name": str|None, "count": int}]`, sorted by count, descending;
    - `"kills_total": int`: line kills; when there are none, the HUD estimate `round(paced EXP / per_kill)`;
    - `"loot": [{"name": str, "count": int}]`, in first-picked-up order;
    - `"mesos_picked": int`: picked-up mesos; when there are none, the inventory delta;
    - `"start": {"level": int, "pct": float}`;
    - `"chart": {"t0": epoch_minute, "vals": [int]}`: every minute of the session, net of deaths;
    - `"since": float`.
  - `Grind.last_session: dict|None`: the summary of the session that just ended (set in `_new_session` before resetting). Shape: `{"map", "start", "end", "active_s", "exp_hr", "gain_pct", "level", "kills_total", "items", "mesos_picked", "deaths"}`.
  - `Grind.all_maps(level, levels_back=5, min_active=600) -> list[dict]`: `{"map_id", "map", "level_lo", "level_hi", "active_s", "exp_hr", "kills_hr", "mesos_hr"}`, best EXP/hr first, no PQs.
  - `best_maps` stays; its `limit` default becomes 5.
  - `sessions` gains `kills INTEGER`, `mesos_picked INTEGER`.

- [ ] **Step 1: Write the failing tests**

```python
def test_kills_loot_and_mesos_add_up(tmp_path):
    g = tracker(tmp_path); t = feed(g, [50000 + 100 * i for i in range(10)])
    for _ in range(3): g.add_kill("Jr. Wraith", t)
    g.add_kill(None, t); g.add_loot("Tablecloth", 1, t); g.add_loot("Tablecloth", 2, t); g.add_mesos(15, t)
    s = g.summary(t)
    assert s["kills"] == [{"name": "Jr. Wraith", "count": 3}, {"name": None, "count": 1}] and s["kills_total"] == 4
    assert s["loot"] == [{"name": "Tablecloth", "count": 3}] and s["mesos_picked"] == 15

def test_kills_fall_back_to_the_hud(tmp_path):
    g = tracker(tmp_path); t = feed(g, [50000 + 100 * i for i in range(20)])
    assert g.summary(t)["kills_total"] == 19

def test_exp_change_across_a_level_up(tmp_path):
    g = tracker(tmp_path); t = feed(g, [NEED - 2000 + 500 * i for i in range(4)])
    t = feed(g, [1000], t0=t, level=33)                           # the bar starts over at level 33
    s = g.summary(t)
    assert s["start"] == {"level": 32, "pct": pct(NEED - 2000)} and s["level"] == 33

def test_a_new_map_keeps_the_last_session(tmp_path):
    g = tracker(tmp_path); t = feed(g, [50000 + 100 * i for i in range(20)]); g.add_kill("Jr. Wraith", t)
    t = feed(g, [52000, 52000], t0=t, map_id=2, name="Kerning City")
    assert g.last_session["map"] == "Ant Tunnel I" and g.last_session["kills_total"] == 1

def test_all_maps_has_kills_and_mesos_an_hour(tmp_path):
    g = tracker(tmp_path); t = feed(g, [50000 + 100 * i for i in range(101)])
    for _ in range(100): g.add_kill("Horny Mushroom", t)
    g.add_mesos(3000, t); g.flush(t)
    m = g.all_maps(32)[0]
    assert m["map"] == "Ant Tunnel I" and m["kills_hr"] == 600 and m["mesos_hr"] == 18000
```

- [ ] **Step 2: Run to see them fail**

Run: `python -I -m pytest -q tests/test_grind_session.py`. Expected: FAIL (`AttributeError: add_kill`).

- [ ] **Step 3: Implement**

- Tallies live in the session (`_new_session` resets them) and in the segment (saved to the new columns).
- `minutes` is no longer trimmed to `SPARK_MINUTES`. `spark` stays for any older use; `chart` covers the session.
- `all_maps`:
  - mesos/hour sums `COALESCE(mesos_picked, mesos_gained)` per row;
  - kills/hour counts only rows with `kills` set: `SUM(kills)` over `SUM(active_s)` of those rows;
  - EXP/hour is computed from the net `exp_gained`, which counts deaths.

- [ ] **Step 4: Run to see them pass, plus the grind suites** (same command as Task 1, plus this file). Expected: pass.

- [ ] **Step 5: Commit** — `feat(grind): kills, loot, mesos picked up, EXP change and last session per session; all maps`

---

### Task 3: Corner lines into events, counted once (`notices.py`)

**Files:**
- Create: `notices.py`
- Test: `tests/test_notices.py`

**Interfaces:**
- Produces:
  - `parse(text: str, item_names: list[str]) -> tuple|None`, returning one of:
    - `("exp", int)` for `You received EXP (+66)`; a trailing bonus such as `(+66) (+13)` sums;
    - `("mesos", int)` for `You have gained mesos (+15)`;
    - `("item", name, count)` for `Tree Branch x1 earned. (Etc)`; the name is fuzzy-matched to `item_names` with rapidfuzz `ratio >= 85`, and None when nothing matches;
    - None for anything else.
  - `class Tracker: update(lines: list[tuple[str, float]], row_h: float) -> list[tuple]`. `lines` is `(text, y)`, top to bottom. It returns the parsed events of the lines new since the last call.

- [ ] **Step 1: Write the failing tests**

```python
NAMES = ["Tree Branch", "Squishy Liquid", "Tablecloth"]

def test_parse_the_three_kinds():
    assert notices.parse("You received EXP (+66)", NAMES) == ("exp", 66)
    assert notices.parse("You received EXP (+66) (+13)", NAMES) == ("exp", 79)
    assert notices.parse("You have gained mesos (+15)", NAMES) == ("mesos", 15)
    assert notices.parse("Tree Branch x1 earned. (Etc)", NAMES) == ("item", "Tree Branch", 1)
    assert notices.parse("Squishy Liquid x12 earned (Etc)", NAMES) == ("item", "Squishy Liquid", 12)
    assert notices.parse("Buddy: hi", NAMES) is None

def test_a_line_still_shown_counts_once():
    tr = notices.Tracker()
    assert tr.update([("You have gained mesos (+15)", 500)], 13) == [("mesos", 15)]
    assert tr.update([("You have gained mesos (+15)", 500)], 13) == []                    # same, not moved
    got = tr.update([("You have gained mesos (+15)", 487), ("You received EXP (+66)", 500)], 13)
    assert got == [("exp", 66)]                                                            # it scrolled up one row

def test_identical_lines_count_by_their_shift():
    tr = notices.Tracker()
    tr.update([("You received EXP (+66)", 500)], 13)
    got = tr.update([("You received EXP (+66)", 487), ("You received EXP (+66)", 500)], 13)
    assert got == [("exp", 66)]

def test_lines_fading_off_the_top_are_not_new():
    tr = notices.Tracker()
    tr.update([("You received EXP (+66)", 487), ("You have gained mesos (+15)", 500)], 13)
    assert tr.update([("You have gained mesos (+15)", 500)], 13) == []
```

- [ ] **Step 2: Run to see them fail.** `python -I -m pytest -q tests/test_notices.py`. Expected: FAIL (no module).

- [ ] **Step 3: Implement.** `Tracker` keeps the last read's lines. On each read it finds how many rows the lines moved up, `shift`: try each `k` from `len(new)` down to 0. A `k` fits when the last `len(new) - k` old lines fuzzy-match (`ratio >= 85`) the first `len(new) - k` new lines, and those matched lines sit `k * row_h` (± `row_h / 3`) higher than before. The first `k` that fits wins, and the last `k` lines of the new read are the new ones. A first read counts all its lines.

- [ ] **Step 4: Run to see them pass.** Expected: PASS.

- [ ] **Step 5: Commit** — `feat(notices): the corner's EXP, mesos and item lines as events, each counted once`

---

### Task 4: Naming a kill, monsters' HP

**Files:**
- Modify: `gamedata.py` (`GameData.here` mobs get `"hp"`; new `GameData.kill_name`)
- Test: `tests/test_here.py` (append)

**Interfaces:**
- Produces:
  - `GameData.kill_name(map_id: int, exp: int) -> str|None`: the monster on that map whose EXP equals `exp`. When several match, the one with the most spawns. None when there's no match.
  - `here()` mobs gain `"hp"`.

- [ ] **Step 1: Failing tests** (real data via `game_reader.data`)

```python
def test_a_kill_is_named_by_its_exp(game_reader):
    d = game_reader.data; line2 = d.match_map_name("Line 2 <Area 1>")
    assert d.kill_name(line2, 66) == "Jr. Wraith" and d.kill_name(line2, 39) == "Jr. Necki"

def test_unknown_exp_is_an_unnamed_kill(game_reader):
    d = game_reader.data
    assert d.kill_name(d.match_map_name("Line 2 <Area 1>"), 71) is None

def test_here_has_each_monsters_hp(game_reader):
    d = game_reader.data
    assert {m["name"]: m["hp"] for m in d.here(d.match_map_name("Line 2 <Area 1>"))["mobs"]}["Jr. Wraith"] == 982
```

- [ ] **Step 2–4:** run (FAIL: no `kill_name`), implement, run (PASS): `python -I -m pytest -q tests/test_here.py`.
- [ ] **Step 5: Commit** — `feat(gamedata): name a kill by its EXP on the map; monsters' HP`

---

### Task 5: The game's tombstone

**Files:**
- Modify: `gamedata.py` (`TOMB_URL = "https://maplestory.io/api/wz/GMS/83/Effect/Tomb.img/land/0"`, `GameData.tomb_sprite() -> Path|None`, a PNG kept at `cache/tomb.png`, the same retry wait as `portal_sprite`)
- Modify: `companion.py` (`GET /api/tomb.png` serves it; 404 when it's missing)
- Test: `tests/test_portal.py` (append; the same offline pattern its portal tests use)

- [ ] **Step 1: Failing tests:** `test_tomb_is_kept_once` (the downloader is mocked to return the base64 PNG and is called only once); `test_tomb_offline_waits_before_trying_again`.
- [ ] **Step 2–4:** run (FAIL), implement, run (PASS).
- [ ] **Step 5: Commit** — `feat(now): the game's tombstone, kept in cache`

---

### Task 6: Wiring and the API

**Files:**
- Modify: `reader.py`: `read_notices(frame, s) -> list[tuple[str, float]]` for now returns `[]` (Task 9 fills it in). `Reader.read` sets `seen["notices"]` and `seen["notice_row"]`.
- Modify: `sniper.py` (`handle_grind`, the `App` gets `self.notices = notices.Tracker()`)
- Modify: `companion.py` (`/api/grind`, new `/api/allmaps`)
- Test: `tests/test_grind_app.py` (append), `tests/test_now_api.py` (new)

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces:
  - `/api/grind` adds `"session"`, built by `session_view(grind, data, map_id, now) -> dict`, a new pure function in `companion.py`. It holds:
    - `kills`: `[{name, count, img, level, hp, exp}]`, the map's monsters plus an unnamed row;
    - `kills_total`;
    - `loot`: `[{name, count, img, kind, desc, msc, npc}]`;
    - `mesos_picked`, `mesos_per_min`;
    - `start`, `level`, `pct`;
    - `deaths`, `exp_lost`;
    - `chart`;
    - `since`.
  - It also adds `"last"` (`Grind.last_session`), `"town": bool` (the current map's `is_town`) and `"keep": bool` (`no_reset`).
  - `GET /api/allmaps` → `Grind.all_maps(level)`.

- [ ] **Step 1: Failing tests**

```python
def test_exp_lines_become_named_kills(tmp_path, game_reader): ...
    # handle_grind with seen["notices"] = [("You received EXP (+66)", 500)] on Line 2 <Area 1>
    # -> grind.summary(...)["kills"] == [{"name": "Jr. Wraith", "count": 1}]

def test_items_and_mesos_from_lines(tmp_path, game_reader): ...
    # "Tablecloth x1 earned. (Etc)" and "You have gained mesos (+15)" -> loot and mesos_picked

def test_session_view_has_tooltip_fields(game_reader): ...
    # loot row for "Tablecloth": kind "Etc", desc from items.json, msc from market, npc from npc_price

def test_town_with_keep_counting_shows_this_session(tmp_path, game_reader): ...
    # no_reset on, map change to Kerning City -> /api/grind "town" True, "keep" True, session still counting
```

- [ ] **Step 2–4:** run (FAIL), implement, run: `python -I -m pytest -q tests/test_grind_app.py tests/test_now_api.py`. Expected: PASS.
- [ ] **Step 5: Commit** — `feat(now): corner lines feed the session; /api/grind session, last, town; /api/allmaps`

---

### Task 7: Now while grinding (layout C) in the dashboard

**Files:**
- Modify: `web/index.html`:
  - `grindCard` rewritten;
  - new `sessionCard`, `chartSvg`, `lootTile`, `lootTip`, `monsterBoxes`, `modal`, `allMapsModal`, `dropsModal`;
  - `renderLive` lays out `.now2` as Grind | (This session over This map);
  - `nextUpCard` and its call are deleted;
  - `#tip.small` CSS.

**Interfaces:**
- Consumes: `/api/grind` (Task 6), `/api/here` (mobs with `hp`), `/api/allmaps`, `/api/tomb.png`.
- Matches `now-session-v16.html` "Grinding" and "No loot yet" views exactly:
  - Grind: 4 boxes, the clock line, the chart, 5 best maps, "All maps ›", Pause / Start over with icons.
  - This session: the EXP change row with the tomb pill, the dark loot tiles paged with `pageFit`, the small tooltip, the "Nothing picked up yet" empty state, NET.
  - This map: monster boxes with Lv / HP / EXP icons and "N killed", and "Worth picking up ›".
- The PQ strip shows in place of the four boxes during a PQ.

- [ ] **Step 1:** Implement against the mockup. Run the dev copy: `python -I <scratchpad>/dev_server.py <companion dir>`, after backing up `profile.json`.
- [ ] **Step 2: Check.** Fill the dev copy's Grind with recorded events: write `tests/fixtures/now_session.json` and add a dev-only `?demo=1` to `/api/grind` that serves it. Then take Playwright screenshots at 1400×860 and 1180×760, in four states: grinding, no loot, one death, level-up. Each must show no page scroll and no blank gap, and the tooltip must work on hover.
- [ ] **Step 3: Commit** — `feat(now): this session, the chart, monster boxes and the two pop-ups; Next up removed`

---

### Task 8: Now in a town

**Files:** Modify `web/index.html` (`renderLive` picks the town layout when `gr.town`; `townCard` gets NPC pictures and paging; `lastSessionCard`; `grindSmall`).

- Matches the mockup's "In town" view:
  - This map is about 63% of the width, with people paged.
  - Last session row: time, +%, killed, items, mesos, the tomb pill. It reads "This session" when `gr.keep` is on.
  - Grind small: "not grinding" chip, last session's EXP/hour, time to level at that pace, best maps as many as fit, "All maps ›". No kills box.
- [ ] **Step 1:** Implement. **Step 2:** Playwright check in Henesys and Kerning City (no page scroll, people paged, nothing spilling). **Step 3:** Commit — `feat(now): the town layout`

---

### Task 9: Reading the corner (needs the user's samples)

**Stop here and ask the user to grind for about a minute.** Collect one passive frame a second with `SetProcessDpiAwareness(2)`, keeping only the bottom-right quarter. Save 4–6 of them as `samples/cases/notices_*.png`, with `.json` files listing their lines (git-ignored, like the other cases).

**Files:** Modify `reader.py` (`read_notices`); Test `tests/test_notices.py` (append the case tests).

- [ ] **Step 1: Failing tests:** each sample's lines come back as its JSON lists, and `Tracker` run over the frames in order counts each event once (counted by hand from the frames).
- [ ] **Step 2: Implement:**
  - pick the area;
  - prep the picture (white text; try `reader.ink(…, "white")` if PR #31 is merged, else min-channel ≥ 200);
  - OCR at 2–3×;
  - work out the row height from the lines.
- [ ] **Step 3:** Run the tests; time a read (budget: 60 ms median).
- [ ] **Step 4: Live check, only if the user asks.** Grind 3 minutes. The kills must match the HUD EXP gain divided by the monster's EXP within 5%, and the loot must match what the game listed.
- [ ] **Step 5: Commit** — `feat(reader): read the corner's EXP, mesos and item lines`. If the lines can't be read reliably, say so in the PR and ship the fallbacks.

---

### Task 10: Docs and the PR

- [ ] Update `README.md` (Now: This session, town layout, pop-ups, deaths) and the dashboard help text that mentions Next up.
- [ ] Run the whole suite: `python -I -m pytest -q -W error::DeprecationWarning`. Expected: all pass.
- [ ] Commit the spec and plan with the code, push `feat/now-session`, open the PR with screenshots described in words, and run the audit (combined suite, dev copy, exe build smoke test) before asking the user to merge.
