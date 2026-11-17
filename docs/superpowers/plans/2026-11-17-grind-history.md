# Grind History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save every grind session in full and show past sessions in a Grind history pop-up: a short list, each row opening to the full card.

**Architecture:** `grind.Grind` gains a `history` table (one row per session, details as JSON), saved alongside the per-map segments and at session end. `companion.py` serves `/api/history` (paged list) and `/api/history/<id>` (one card, with item and monster pictures resolved). `web/index.html` adds a **History ›** button beside **All maps ›** and a pop-up built on the existing `openModal`.

**Tech Stack:** Python 3.11, sqlite3, pytest; vanilla JS/CSS in `web/index.html`.

**Spec:** `docs/superpowers/specs/2026-11-17-grind-history-design.md`

## Global Constraints

- Work in the worktree `classic/companion-history`, branch `feat/grind-history`. Run tests from its root: `python -m pytest -q`.
- The worktree has no `cache/`: copy `classic/companion/cache` into it once before the first test run (git-ignored; `game_reader` tests read it).
- A session is saved only once it has **2 minutes of grinding (`active_s` ≥ 120)** and **EXP gained > 0**; for a PQ run the 2 minutes are wall time.
- **30 minutes (1800 s) with no EXP gain ends a session.** The next gain starts a new one.
- Entering or leaving a PQ always starts a new session, even with "keep counting across maps" on.
- The session in progress is not in the list. A row left open by a crash is closed at its last save on the next start.
- List: newest first, **8 a page**, orange ◀ ▶ `.pg` arrows. Row: map, day + start time, level tile ("Lv. 36→37"), time grinding, EXP gained, EXP / hour, Lucide `chevron-down` (inline SVG, `<path d="m6 9 6 6 6-6"/>`).
- One row open at a time; the open row fills the pop-up and the others hide; no scrolling anywhere.
- Net mesos = mesos picked up, else the inventory change, else "—". **No potion cost, no prices on the page** (item worth stays in tooltips, as Now does).
- Old `sessions` rows that start before the history table was created are listed as older, totals only; walk-throughs (< 120 s or no EXP) are hidden.
- Character name is stored per row; rows show it only when the history holds more than one character.
- Plain words in the UI; game names exactly as in the data.

## Review Focus

1. A session that ends by the 30-minute idle rule must be saved with the end time of its last gain, not the time the next gain came (else "grinding 1h 23m, 8:20 PM – 9:30 AM next day").
2. Companion closing mid-session (window closed, update installing) must leave the card saved and closed on the next start, with nothing lost but the last minute.
3. Old and new rows sharing one paged list: a page boundary must not drop or repeat a row when the two kinds interleave by start time.
4. A card whose items or monsters aren't in today's data (renamed, removed, or `None` = unnamed kills) must still open, with no picture and the name as saved ("Unnamed" for `None`).
5. A session spanning a level-up of two or more levels (PQ, quest turn-in) must show every level in the bar and one dotted chart line per level-up.

---

### Task 1: Save a session's full card

**Files:**
- Modify: `grind.py` (`Grind.__init__`, `_new_session`, `update`, `_died`, `reset`; new methods)
- Modify: `sniper.py` (`handle_grind`: pass the character; the `"quit"` message in `pump`: save on close)
- Test: `tests/test_grind_history.py` (new)

**Interfaces:**
- Produces, in `grind.py`:
  - constants `IDLE_END = 1800.0`, `CARD_MIN_ACTIVE = 120.0`
  - table `history(id INTEGER PRIMARY KEY, start REAL, end REAL, map_id INTEGER, map TEXT, pq TEXT, character TEXT, job TEXT, level_start INTEGER, pct_start REAL, level_end INTEGER, pct_end REAL, exp_gained INTEGER, active_s REAL, exp_hr REAL, open INTEGER, data TEXT)` and table `meta(key TEXT PRIMARY KEY, value TEXT)` holding `history_since` (epoch seconds, written once when `history` is first created).
  - `Grind.who: dict` — `{"name": str|None, "job": str|None}`, set by `handle_grind` before each `update`.
  - `Grind.save_card(now: float, final: bool = False) -> int | None` — upserts this session's row (`open = 0 if final else 1`), returns its id, or None when below the 2-minute / EXP > 0 rule.
  - `Grind.close(now: float) -> None` — `_save_segment(now)` then `save_card(now, final=True)`; for app exit.
  - `data` JSON keys: `minutes` (`{"t0": int, "vals": [int]}`, as `_chart` gives), `levelups` (`[{"ts": float, "level": int}]`), `kills`, `party_kills` (`[{"name": str|None, "count": int}]`), `kills_total`, `loot`, `used` (`[{"name", "count"}]`), `mesos_picked` (int|None), `mesos_change` (int|None), `deaths` (`[{"ts", "lost"}]`), `maps` (`[str]`, in order first seen).

- [ ] **Step 1: Write the failing tests** in `tests/test_grind_history.py`, using `feed`, `pct`, `tracker`, `NEED` from `test_grind`:

```python
def rows(g):
    return g.db.execute("SELECT map, open, exp_gained, active_s, level_start, level_end, character FROM history").fetchall()

def test_a_short_walk_through_is_not_saved(tmp_path):           # 1 minute of gains, then a new map
    g = tracker(tmp_path); g.who = {"name": "Tura1", "job": "Hunter"}
    t = feed(g, [50000 + 100 * i for i in range(11)])
    feed(g, [51100], t0=t, map_id=2, name="Ant Tunnel II")
    assert rows(g) == []

def test_a_session_is_saved_while_it_runs_and_closed_on_a_new_map(tmp_path):
    g = tracker(tmp_path); g.who = {"name": "Tura1", "job": "Hunter"}
    t = feed(g, [50000 + 100 * i for i in range(41)])           # 4 minutes
    assert rows(g)[0][1] == 1                                    # saved, still open
    feed(g, [54100, 54200], t0=t, map_id=2, name="Ant Tunnel II")
    (mp, op, exp, act, l0, l1, who), = rows(g)
    assert (mp, op, exp, l0, l1, who) == ("Ant Tunnel I", 0, 4000, 32, 32, "Tura1") and act >= 120

def test_the_card_keeps_kills_loot_used_deaths_and_minutes(tmp_path):
    # feed 4 minutes, add_kill("Jr. Wraith") x3, add_kill(None), add_loot("Tablecloth", 2), add_used("Orange Potion", 1),
    # add_mesos(15), then g.close(t); data = json.loads(row data)
    # assert data["kills"] == [{"name": "Jr. Wraith", "count": 3}, {"name": None, "count": 1}]
    # assert data["loot"] == [{"name": "Tablecloth", "count": 2}] and data["used"] == [{"name": "Orange Potion", "count": 1}]
    # assert data["mesos_picked"] == 15 and sum(data["minutes"]["vals"]) == 4000 and data["maps"] == ["Ant Tunnel I"]

def test_level_ups_are_kept_with_their_time(tmp_path):
    # feed up to NEED - 500 at level 32 (4+ minutes), then feed([1000], level=33),
    # then feed([1500], level=34) (two levels in one session, Review Focus 5); close
    # assert [u["level"] for u in data["levelups"]] == [33, 34] and row level_start 32, level_end 34

def test_thirty_minutes_without_exp_ends_the_session(tmp_path):
    # feed 4 minutes, then one gain 1801 s after the last one on the same map
    # assert 2 rows... first row open == 0 and its end == the time of its last gain (not the late one)
    # assert g.summary(now)["gained"] == the late gain only (Now restarted too)

def test_a_pq_starts_its_own_session_even_when_keeping_across_maps(tmp_path):
    # g.no_reset = True; feed on Ant Tunnel I 4 minutes; then kpq_run(...) from test_grind
    # assert the KPQ card is its own row (pq == "KPQ"), active_s == its wall time

def test_close_saves_and_a_crash_is_closed_on_next_start(tmp_path):
    # feed 4 minutes; do NOT close; open grind.Grind(same path) again
    # assert the old row has open == 0 and end == its last save
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest tests/test_grind_history.py -q`
Expected: FAIL (`no such table: history` / `AttributeError: ... 'who'`).

- [ ] **Step 3: Implement in `grind.py`**
  - `__init__`: create both tables; if `meta.history_since` is missing, write `time.time()`; `UPDATE history SET open = 0 WHERE open = 1`; `self.who = {"name": None, "job": None}`, `self.card_id = None`.
  - `_new_session(now)`: before resetting, `self.save_card(<end>, final=True)` where `<end>` is `self.last_any or now`; then `self.card_id = None`, `self.levelups = []`, `self.s_pq = self.pq`, `self.s_maps = []`.
  - `update`: on a map change, `old_pq = self.pq` before reassigning; start a new session when `not self.no_reset or pq or old_pq`. Before counting a gain, if `self.last_any is not None and now - self.last_any > IDLE_END`: `_save_segment(self.last_any)`, `_new_segment(now, level)`, `_new_session(now)`. When a read's level is above `self.last[2]`, append `{"ts": now, "level": level}` to `self.levelups`. Add the map to `self.s_maps` on each gain if new. Call `save_card(now)` where `_save_segment` is called on the 60-second rhythm.
  - `save_card`: active = wall time `end - self.s_start` when `self.s_pq` else `self.s_active`; skip when active < `CARD_MIN_ACTIVE` or `self.s_gained <= 0`; `exp_hr` = `exp_gained / active * 3600` for PQs, else the `summary`'s `exp_hr`; `mesos_change` = `s_mesos - s_mesos0` when both read. INSERT the first time, UPDATE by `self.card_id` after.
- [ ] **Step 4: Wire `sniper.py`:** in `handle_grind`, `g.who = {"name": prof.get("name"), "job": prof.get("job")}` before `g.update(...)`; in `pump`, on `"quit"`, call `self.grind.close(time.time())` (guarded `if self.grind is not None`) before `self.root.destroy()`.
- [ ] **Step 5: Run the new tests and the whole suite**

Run: `python -m pytest -q`
Expected: all pass (the existing grind tests too: the idle rule must not touch them; none waits 30 minutes).

- [ ] **Step 6: Commit** — `git commit -m "feat(grind): save every session in full for the history"`

---

### Task 2: The history list and card, served

**Files:**
- Modify: `grind.py` (new read methods)
- Modify: `companion.py` (`session_view`'s loot block moved into a helper; two GET routes; `card_view`)
- Test: `tests/test_grind_history.py` (list/card), `tests/test_history_api.py` (new, views with `game_reader`)

**Interfaces:**
- Consumes: Task 1's tables and `data` keys.
- Produces:
  - `Grind.history_page(page: int, per: int = 8) -> dict` → `{"total": int, "page": int, "pages": int, "multi_char": bool, "rows": [row]}`; `row` = `{"id": "h<id>" | "s<id>", "old": bool, "start", "end", "map", "map_id", "pq", "character", "level_start", "level_end", "active_s", "exp_gained", "exp_hr"}`. New rows exclude `open = 1`; old rows are `sessions` with `start < history_since AND active_s >= 120 AND exp_gained > 0`. Both kinds merged newest first by `start` in one SQL `UNION ALL ... ORDER BY start DESC LIMIT ? OFFSET ?`.
  - `Grind.history_card(key: str) -> dict | None` → the row fields plus, for `h` rows, the parsed `data`; for `s` rows, `kills` / `mesos_picked` / `deaths` / `exp_lost` totals from the segment.
  - `companion.loot_tiles(data, picked: dict, used: dict) -> list` — the exact list `session_view` builds today (picked − drunk, ordering, tooltip fields); `session_view` calls it.
  - `companion.card_view(card: dict, data) -> dict` → the card plus `loot` (via `loot_tiles`), `kills` with `img` (from `data.here(map_id)["mobs"]` by name, else None), `best_minute` (max of `minutes.vals`, or None), `kills_per_min`, `mesos_per_min`.
  - `GET /api/history?page=N` → `history_page(N)`; `GET /api/history/<key>` → `card_view(...)` or 404 `{"error": "not found"}`.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_list_pages_eight_newest_first_without_the_open_one(tmp_path):
    # make 10 saved sessions (feed 3 minutes on map k, then change map), leave the 11th running
    # p = g.history_page(0); assert p["total"] == 10 and p["pages"] == 2 and len(p["rows"]) == 8
    # assert [r["start"] for r in p["rows"]] is descending and no row is the running session

def test_old_rows_mix_in_by_time_and_walk_throughs_are_hidden(tmp_path):
    # insert sessions rows directly (start before meta.history_since): one 600 s, one 60 s, one with exp 0
    # plus 2 new cards; assert total == 3 and the old one is placed by its start, "old": True, id "s<id>"
    # page through with per=2 and assert every id appears exactly once (Review Focus 3)

def test_multi_char_only_with_two_characters(tmp_path):
    # two cards by "Tura1" -> multi_char False; a third by "Tura4" -> True

def test_card_view_resolves_pictures_and_keeps_unknown_names(tmp_path, game_reader):   # in test_history_api.py
    # a card on Line 2 <Area 1> with kills Jr. Wraith 3, "Gone Monster" 1, None 2 and loot Tablecloth 2, "Gone Item" 1
    # v = companion.card_view(card, game_reader.data)
    # assert the Jr. Wraith kill has an img, "Gone Monster" and None have img None and keep their names
    # assert v["best_minute"] == max(card["data"]["minutes"]["vals"])

def test_session_view_unchanged_by_the_loot_helper(tmp_path, game_reader):
    # the existing tests in test_now_api.py stay green; add none beyond running them
```

- [ ] **Step 2: Run to see them fail** — `python -m pytest tests/test_grind_history.py tests/test_history_api.py -q` → FAIL (`no attribute 'history_page'`).
- [ ] **Step 3: Implement** `history_page`, `history_card` in `grind.py`; `loot_tiles`, `card_view` and the two routes in `companion.py` (beside `/api/allmaps`; `<key>` from `url.path[len("/api/history/"):]`).
- [ ] **Step 4: Run** `python -m pytest -q` → all pass.
- [ ] **Step 5: Commit** — `git commit -m "feat(grind): history list and card endpoints"`

---

### Task 3: The Grind history pop-up

**Files:**
- Modify: `web/index.html` (`bestMaps` button row, `wireNow`, `chartBox`, new `historyModal` + CSS)

**Interfaces:**
- Consumes: Task 2's endpoints and fields.
- Produces: `historyModal()` (opens on page 0); `chartBox(ch, deaths, gained, dim, levelups)` — a fifth optional argument drawing a dotted vertical line at each level-up minute (existing callers unchanged).

- [ ] **Step 1: Button.** In `bestMaps`, beside `#allmaps-btn`, add `<button class="btn mini allmaps" id="history-btn">History ›</button>`; wire it in `wireNow` like `#allmaps-btn`. It shows in every Grind state that shows best maps.
- [ ] **Step 2: The list.** `historyModal(page = 0)` fetches `/api/history?page=`, opens `openModal` titled `${itemIcon(4001009, 22)} Grind history` with `<small>N sessions</small>`, rows as in the mockup (`classic/companion/.superpowers/brainstorm/781-1794912311/scripts/mock_history2.py`: `.hr`, `.hrow` grid `minmax(0,1fr) 92px 84px 104px 88px 24px`, `.hlv` orange tile, `.hc` cells, `.chev`), and a `.pager` with `.pg` arrows that re-render the list for the next/previous page. Day label: "Today" / "Yesterday" / `Sat, Nov 15`, then the start time via `clock`. Level tile: `Lv. 36→37` or `Lv. 37`. Character name after the day when `multi_char`. Older rows: no change to the row.
- [ ] **Step 3: The open view.** Clicking a row (or Enter/Space on its `<button>`) fetches `/api/history/<id>`, adds `.open` to that row and `.has-open` to the list (other rows and the pager hide), turns the chevron up; clicking again closes. Content:
  - map picture `<img src="/api/mapimg?id=…" onerror="this.remove()">`, four boxes (best minute; killed + "N a minute"; net mesos as "+N" or "—"; deaths + "−N EXP", "0" when none);
  - `chartBox(card.minutes, card.deaths, card.exp_gained, false, card.levelups)`;
  - the level bar: start level/percent → end level/percent, a LEVEL UP chip per level gained (Review Focus 5), `+N%` gained;
  - loot tiles via the existing `lootTile` + `wireTips` (tooltips as Now), killed rows (`.krow`: picture, name — "Unnamed" for `null` —, bar against the top count, count), a death line ("Died once, at 8:52 PM · lost 19,481 EXP" / "Died N times · lost …").
  - an older row opens to its four totals and the note: "Saved before Companion kept the full story: no chart, loot or kills per monster for this one. Sessions from now on keep everything."
- [ ] **Step 4: Check it in a browser.** Run a dev copy from the worktree with a seeded `data/grind.sqlite` (copy the user's `%LOCALAPPDATA%\Programs\Companion\data\grind.sqlite` for real old rows, then add a few full cards with a short script using `Grind` + `close`): `python companion.py --no-browser` (it takes the next free port after 8765). Screenshot with headless Edge (`msedge --headless=new --screenshot=... --window-size=1280,900`) the list, an open card, an older card, and page 2; check: no scrollbars, no gaps, chevron turns, Escape and Close shut it.
- [ ] **Step 5: Run** `python -m pytest -q` → all pass.
- [ ] **Step 6: Commit** — `git commit -m "feat(now): Grind history pop-up"`

---

### Task 4: Docs and finish

**Files:**
- Modify: `README.md` / `site/` feature lists only if they list Now's features one by one (keep EN and HE in sync, per the site rule).

- [ ] **Step 1:** Add one line for "Grind history" where Now's features are listed, in English and Hebrew.
- [ ] **Step 2:** `python -m pytest -q` → all pass.
- [ ] **Step 3: Commit** — `git commit -m "docs: grind history"`; then hand off to superpowers:finishing-a-development-branch (push and PR only with the user's OK).
