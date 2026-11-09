# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the dashboard's Now, Go to, Gear, Skills, Shops and Settings tabs to the approved mockups: one screen each, no page scroll, MapleStory Classic look.

**Architecture:** New data comes from small pure functions in `gamedata.py`, `grind.py`, `advisor.py` and `sniper.py` (pytest-tested), served by new or extended GET routes in `companion.py`. The UI stays one file, `web/index.html`: shared pieces first (game window, tooltip, pager, full-height layout, icons), then one task per tab, each checked in a browser against its mockup.

**Tech Stack:** Python 3.11 (stdlib http.server, requests, Pillow, sqlite3), vanilla HTML/CSS/JS, pytest.

**Spec:** `docs/superpowers/specs/2026-11-09-dashboard-redesign-design.md`. Mockups (git-ignored, on this PC): `.superpowers/brainstorm/929-1794223004/content/` — `now-v7.html`, `goto-v2.html`, `goto-town-v2.html`, `gear-v5.html`, `skills-v8.html`, `shops-v4.html`, `settings-v1.html`; their CSS is the reference for each tab's look.

## Global Constraints

- Work on a new branch `feat/dashboard-redesign` made from `feat/grind-dashboard` (index.html changed there). Don't push without asking.
- Tests: `python -I -m pytest tests -q` must stay green (today 110+ passed, 2 xfailed). Open files with `encoding="utf-8"` (the PC's locale is cp1255).
- Game pictures (items, NPCs, Map Marks, monsters, portal frames) are fetched at runtime and cached under `cache/`, never committed: the repo `Tura2/classic-companion` is public. The one bundled game picture is `web/equip_classic.png` (spec, call 2).
- Prices: MSC (`data.market.items[name]`: `p` median, `p25` snipe) and Cozy only.
- Never send input to the game; test against the real game only if the user asks.
- UI copy is English and plain: words on buttons, no cryptic chips (spec anti-goals).
- No page scroll at 1693×784 and 1150×680 CSS px; under 760 px wide or 600 px tall, columns stack and the page scrolls.
- Drops credit line, verbatim: `Drops: MapleClassic Wiki (CC BY-NC-SA 4.0) via Club FM. Prices: MSC.`

## Review Focus

1. Club FM's file missing, unreachable or renamed → Companion still starts; This map shows monsters and "Drop data isn't available right now." (Task 1 test `test_no_drop_file_still_starts`.)
2. A map with no monsters (towns) or monsters with no listed drops → This map shows its NPCs or "No monsters here", never an empty box or an error. (Task 1 test `test_town_has_npcs_no_drops`.)
3. Grind log with no session ≥ 10 min in the last 5 levels → "Your best maps" shows a one-line hint, not an empty table. (Task 2 test `test_best_maps_empty_log`.)
4. A weekly rotation quest that is in your quest log → still keeps its item (the new rule must not drop the active case). (Task 4 test `test_weekly_quest_in_log_keeps`.)
5. Portal frames can't be downloaded → portals fall back to the old ring-only marker, the route still works. (Task 6 test `test_portal_sprite_none_when_offline`.)

---

### Task 1: This map data (drops, monsters, NPCs, portals)

**Files:**
- Modify: `gamedata.py` (constant beside `WIKI`; `GameData.__init__`; new methods after `layout`)
- Modify: `companion.py` (GET `/api/here`)
- Test: `tests/test_here.py`

**Interfaces:**
- Produces: `CLUBFM = "https://raw.githubusercontent.com/maplefm/maplefm.github.io/live/data/itemguide.json"`
- Produces: `load_drops(guide: dict) -> dict[int, list[dict]]` (module function): monster id → `[{"item": str, "rate": float|None}]`, from `guide["items"][name]["d"]` rows `[mob, mob_lv, rate, kills, map, _, mob_id]`.
- Produces: `GameData.drops_by_mob: dict[int, list[dict]]` (empty when the file can't be had), `GameData.scroll_rates: dict[str, int]` (from `items.json` `scrolls[].success_rate`).
- Produces: `GameData.here(mid: int) -> dict` → `{"id", "name", "street", "town": bool, "mark": url|None, "mobs": [{"id","name","level","count","exp","img"}], "drops": [{"item","img","from","rate","price","success"}], "drops_ok": bool, "npcs": [{"id","name","img","x","y","role"}], "portals": [{"x","y","to","to_id"}]}`. Drops sorted by `price` (MSC `p`) descending, unpriced last, one row per item (the first monster that drops it). `role` ∈ `"Quests"`, `"Taxi"`, `None` (Quests when any quest has `npc_id` = this NPC; Taxi when the name contains "Cab").
- Produces: `GET /api/here?id=<map id>` (defaults to `prof["current_map"]`) → `data.here(id)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_here.py`, building a bare `GameData` with `object.__new__(gamedata.GameData)` and setting only the attributes `here` reads (`maps`, `monsters`, `drops_by_mob`, `market`, `scroll_rates`, `item_ids`, `portals`, `quest_list`, `npc_names`). Helpers `ant_tunnel(**override)` and `henesys()` in the test file build it with the values below (Ant Tunnel I 10005060: Zombie Mushroom id 21 lv 24 ×11 exp 45, Horny Mushroom id 19 lv 22 ×15 exp 41; MSC `p` 449999 for the claw scroll; `scroll_rates` {"Claw Attack Scroll: Intermediate": 60}; Henesys 10001000 `is_town` with Chief Stan 202 and a quest whose `npc_id` is 202).

```python
def test_load_drops_keys_by_monster_id():
    guide = {"items": {"Claw Attack Scroll: Intermediate": {"d": [["Zombie Mushroom", 24, None, 0, "Ant Tunnel I", 0, 21]]},
                       "Orange Potion": {"d": [["Zombie Mushroom", 24, 3.5, 200, "Ant Tunnel I", 0, 21]]}}}
    d = gamedata.load_drops(guide)
    assert {x["item"] for x in d[21]} == {"Claw Attack Scroll: Intermediate", "Orange Potion"}
    assert [x["rate"] for x in d[21] if x["item"] == "Orange Potion"] == [3.5]

def test_drops_most_valuable_first_with_scroll_rate():   # Ant Tunnel I
    h = ant_tunnel().here(10005060)
    assert h["drops"][0] == {"item": "Claw Attack Scroll: Intermediate", "from": "Zombie Mushroom", "rate": None,
                             "price": 449999, "success": 60, "img": ANY}
    assert [m["name"] for m in h["mobs"]] == ["Zombie Mushroom", "Horny Mushroom"] and h["drops_ok"]

def test_no_drop_file_still_starts():          # Review Focus 1
    g = ant_tunnel(drops_by_mob={})
    assert g.here(10005060)["drops"] == [] and g.here(10005060)["drops_ok"] is False

def test_town_has_npcs_no_drops():             # Review Focus 2: Henesys, Chief Stan 202 at (4166, 719) gives quests
    h = henesys().here(10001000)
    assert h["town"] and h["mobs"] == [] and h["drops"] == []
    assert {"id": 202, "name": "Chief Stan", "x": 4166, "y": 719, "role": "Quests", "img": ANY} in h["npcs"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -I -m pytest tests/test_here.py -q` — Expected: FAIL (`load_drops` / `here` not defined).

- [ ] **Step 3: Implement** `load_drops`, the `__init__` additions and `GameData.here` in `gamedata.py`. Load the guide with `fetch_json(CLUBFM, "clubfm_itemguide.json", age)` inside `try/except (Exception, SystemExit)` → `{}` and print one line on failure (the file is optional; `fetch_json` raises `SystemExit` when there's no cache). Map Mark URL: `f"{OSMS}current/images/map_marks/{m['map_mark']}.png"` when `map_mark` is set. Monster count and EXP come from `self.monsters[*]["maps"]` (count on this map) and `["exp"]`; `img` from `mob_img`. Portals: as `layout` does, with `to_id`.

- [ ] **Step 4: Add the route** `/api/here` in `companion.py` `do_GET`, beside `/api/layout`.

- [ ] **Step 5: Run the tests**

Run: `python -I -m pytest tests -q` — Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add gamedata.py companion.py tests/test_here.py
git commit -m "feat(here): the map you're on: monsters, drops by price, NPCs, portals"
```

### Task 2: Your best maps

**Files:**
- Modify: `grind.py` (new method after `by_map`)
- Modify: `companion.py` (`/api/grind` adds `"best"`)
- Test: `tests/test_grind.py`

**Interfaces:**
- Produces: `Grind.best_maps(level: int, levels_back: int = 5, min_active: float = 600, limit: int = 3) -> list[dict]`, each `{"map_id", "map", "level_lo", "level_hi", "active_s", "exp_hr"}`, sorted by `exp_hr` descending. Counts only non-PQ sessions with `level_end >= level - levels_back + 1`; groups by `map_id`; keeps maps whose summed `active_s >= min_active`.
- Produces: `/api/grind` JSON gains `"best": g.best_maps(int(prof["level"]))`.

- [ ] **Step 1: Write the failing tests** in `tests/test_grind.py`, inserting rows straight into `sessions`:

```python
def test_best_maps_last_five_levels(tmp_path):
    g = grind.Grind(tmp_path / "g.sqlite")
    add(g, map_id=1, map="Ant Tunnel I", lv=(32, 33), exp=612_000, secs=3600)
    add(g, map_id=2, map="Ant Tunnel II", lv=(31, 32), exp=287_000, secs=1800)
    add(g, map_id=3, map="Pig Beach", lv=(20, 21), exp=900_000, secs=3600)      # too long ago
    add(g, map_id=4, map="Short Stop", lv=(33, 33), exp=99_000, secs=300)       # under 10 minutes
    best = g.best_maps(33)
    assert [b["map"] for b in best] == ["Ant Tunnel I", "Ant Tunnel II"]
    assert best[0]["exp_hr"] == 612_000 and (best[0]["level_lo"], best[0]["level_hi"]) == (32, 33)

def test_best_maps_empty_log(tmp_path):    # Review Focus 3
    assert grind.Grind(tmp_path / "g.sqlite").best_maps(33) == []
```

- [ ] **Step 2: Run them to see them fail** — `python -I -m pytest tests/test_grind.py -q` → FAIL (`best_maps` missing).
- [ ] **Step 3: Implement** `best_maps` (one `SELECT map_id, map, MIN(level_start), MAX(level_end), SUM(exp_gained), SUM(active_s) ... WHERE pq IS NULL AND level_end >= ? GROUP BY map_id`), then add `"best"` to `/api/grind`.
- [ ] **Step 4: Run all tests** — `python -I -m pytest tests -q` → pass.
- [ ] **Step 5: Commit** — `git commit -m "feat(grind): your best maps by EXP/hr in your last 5 levels"` (files: `grind.py companion.py tests/test_grind.py`).

### Task 3: The next 3 skill points

**Files:**
- Modify: `gamedata.py` (`next_points`, plus a module function)
- Test: `tests/test_points.py`

**Interfaces:**
- Produces: `single_points(steps: list[tuple[int, str, int]], now: dict[str, int], n: int = 3) -> list[dict]`: the first `n` single points in the guide's order that `now` hasn't reached, each `{"skill", "from", "to", "level"}` with `to == from + 1`.
- Produces: `next_points(...)` result gains `"sp3": single_points(steps, now)`; existing `"sp"` unchanged.

- [ ] **Step 1: Write the failing test** (Tura1's real case):

```python
def test_next_three_points_are_single_steps():
    steps = [(34, "Bow Booster", 5), (34, "Soul Arrow: Bow", 1)] + [(34, "Bow Mastery", t) for t in range(6, 21)]
    now = {"Bow Booster": 4, "Soul Arrow: Bow": 0, "Bow Mastery": 5}
    assert gamedata.single_points(steps, now) == [
        {"skill": "Bow Booster", "from": 4, "to": 5, "level": 34},
        {"skill": "Soul Arrow: Bow", "from": 0, "to": 1, "level": 34},
        {"skill": "Bow Mastery", "from": 5, "to": 6, "level": 34}]
```

- [ ] **Step 2: Run it to see it fail** — `python -I -m pytest tests/test_points.py -q` → FAIL.
- [ ] **Step 3: Implement** `single_points` (walk `steps`; a step whose target is above `now` yields the single points from the current level up to it, tracking levels already handed out so a later step continues from there) and add `"sp3"` in `next_points`.
- [ ] **Step 4: Run all tests** → pass.
- [ ] **Step 5: Commit** — `git commit -m "feat(skills): the next three single skill points"`.

### Task 4: Keep for a quest only when it applies

**Files:**
- Modify: `advisor.py` (`verdict`, the `soon` filter)
- Test: `tests/test_advisor.py`

**Interfaces:**
- Consumes: quest dicts with `rotation` (`{"cadence": "weekly", "one_time": False}` on rotating ones) and `requirements_list` entries `{"type": "quest", "id": "80023", "state": 2}`.
- Produces: unchanged `verdict(...)` signature; the `soon` list now skips (a) quests with `rotation` and `rotation.get("one_time") is False`, (b) quests whose required quests (`type == "quest"`, `state == 2`) aren't all in `quests_done`.

- [ ] **Step 1: Write the failing tests** (fixtures in the file's style):

```python
WEEKLY = {"id": "506032", "name": "Donating to Henesys", "level_min": 12,
          "rotation": {"cadence": "weekly", "one_time": False},
          "requirements_list": [{"type": "item", "name": "Lorang Claw", "count": 30}]}
NEEDS_EARLIER = {"id": "80025", "name": "Chrishrama in Need of Help", "level_min": 15,
                 "requirements_list": [{"type": "quest", "id": "80023", "state": 2},
                                       {"type": "item", "name": "Fragment of Magic", "count": 10}]}

def test_weekly_quest_not_in_log_doesnt_keep():
    v = advisor.verdict("Lorang Claw", 3, prof(), data(quests=[WEEKLY]), market())
    assert v["verdict"] != "keep"

def test_weekly_quest_in_log_keeps():                 # Review Focus 4
    v = advisor.verdict("Lorang Claw", 3, prof(quests_active=[{"id": "506032", "name": "Donating to Henesys"}]),
                        data(quests=[WEEKLY]), market())
    assert v == {"verdict": "keep", "why": "Donating to Henesys: need 30, have 3", "price": None}

def test_quest_waiting_on_an_earlier_one_doesnt_keep():
    assert advisor.verdict("Fragment of Magic", 2, prof(), data(quests=[NEEDS_EARLIER]), market())["verdict"] != "keep"
    assert advisor.verdict("Fragment of Magic", 2, prof(quests_done=["80023"]), data(quests=[NEEDS_EARLIER]),
                           market())["verdict"] == "keep"
```

(Add an optional `quests` parameter to the file's `data()` helper, defaulting to today's `[JANE, LATER, FAR]`.)

- [ ] **Step 2: Run them to see them fail** — `python -I -m pytest tests/test_advisor.py -q` → the first and third FAIL.
- [ ] **Step 3: Implement** the two skips in the `soon` filter (small helpers `_rotating(q)` and `_earlier_done(q, done)` in `advisor.py`).
- [ ] **Step 4: Run all tests** → pass.
- [ ] **Step 5: Commit** — `git commit -m "fix(sell-or-keep): keep for a weekly or locked quest only when it's in your log"`.

### Task 5: Sell or keep remembers only the last 48

**Files:**
- Modify: `sniper.py` (`note_hovered`)
- Test: `tests/test_advisor.py` (or a new `tests/test_hovered.py`)

**Interfaces:**
- Produces: `HOVER_KEEP = 48` in `sniper.py`; after `note_hovered` the dict holds at most 48 names, the newest by `ts`.

- [ ] **Step 1: Write the failing test**

```python
def test_hovered_keeps_the_newest_48():
    state = {}
    for i in range(60):
        sniper.note_hovered(state, [{"name": f"Item {i}"}])
    assert len(state["hovered"]) == 48 and "Item 59" in state["hovered"] and "Item 0" not in state["hovered"]
```

- [ ] **Step 2: Run it to see it fail** → FAIL (60 kept).
- [ ] **Step 3: Implement** the trim at the end of `note_hovered` (drop the oldest by `ts`; hovering an item again refreshes its `ts`, as now).
- [ ] **Step 4: Run all tests** → pass.
- [ ] **Step 5: Commit** — `git commit -m "feat(sell-or-keep): remember the last 48 items hovered"`.

### Task 6: The game's portal sprite, and bundled pictures

**Files:**
- Modify: `gamedata.py` (portal sprite build + cache)
- Modify: `companion.py` (GET `/api/portal.webp`; serve `web/*.png` by name from an allowlist)
- Create: `web/equip_classic.png` (copy from `.superpowers/brainstorm/929-1794223004/content/equip_classic.png`, 244×404)
- Test: `tests/test_portal.py`

**Interfaces:**
- Produces: `PORTAL_URL = "https://maplestory.io/api/wz/GMS/83/Map/MapHelper.img/portal/game/pv/{n}"` (frame n is base64 PNG in `value`; its origin at `.../pv/{n}/origin` → `value.x`, `value.y`).
- Produces: `compose_frames(frames: list[tuple[PIL.Image.Image, tuple[int, int]]]) -> tuple[list[PIL.Image.Image], tuple[int, int]]`: pads every frame onto one canvas so all origins line up; returns the frames and the shared anchor (x, y). With the real 8 frames: canvas 89×257, anchor (44, 248).
- Produces: `GameData.portal_sprite() -> pathlib.Path | None`: `cache/portal.webp` (animated, 110 ms a frame, loop), built once from the 8 frames; `None` when they can't be downloaded and there's no cache.
- Produces: `GET /api/portal.webp` → the file, `max-age=86400`, or 404; `GET /api/portal` → `{"anchor": [x, y], "size": [w, h]}`; `GET /equip_classic.png` → the bundled file.

- [ ] **Step 1: Write the failing tests**

```python
def test_frames_line_up_on_their_origins():
    a, b = Image.new("RGBA", (87, 182)), Image.new("RGBA", (85, 256))
    frames, anchor = gamedata.compose_frames([(a, (43, 173)), (b, (41, 248))])
    assert anchor == (43, 248) and {f.size for f in frames} == {(87, 256)}

def test_portal_sprite_none_when_offline(tmp_path, monkeypatch):   # Review Focus 5
    monkeypatch.setattr(gamedata, "CACHE", tmp_path)
    monkeypatch.setattr(gamedata.requests, "get", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    assert object.__new__(gamedata.GameData).portal_sprite() is None
```

- [ ] **Step 2: Run them to see them fail** → FAIL.
- [ ] **Step 3: Implement** `compose_frames` and `portal_sprite` (requests with the module's `UA`; save the anchor beside it in `cache/portal.json`), the two routes, the `equip_classic.png` route, and copy the picture into `web/` (it ships through `--add-data "web;web"` already).
- [ ] **Step 4: Run all tests** → pass. Then `curl -s localhost:8765/api/portal` with the app running → `{"anchor": [44, 248], "size": [89, 257]}`.
- [ ] **Step 5: Commit** — `git commit -m "feat(map): the game's portal sprite, and the Classic Equip window picture"` (files incl. `web/equip_classic.png`).

### Task 7: Shared UI pieces in index.html

**Files:**
- Modify: `web/index.html` (CSS block, the tab bar markup, shared JS helpers near `win()`)

**Interfaces:**
- Produces (JS): `GI` (tab → item id: now 4000094, nav 2030000, train 1452002, quests 4031001, gear 1002032, skills 4031032, flips 2028001, settings 4000089), `itemIcon(id, size) -> html`, `markIcon(mark, size) -> html`; tab buttons get their icon.
- Produces (JS): `gameWin(title, tabsHtml, bodyHtml) -> html` (title strip, blue close box, tabs on a red rule; CSS from `skills-v8.html` `.gwin/.gtitle/.gx/.gtabs`).
- Produces (JS): `showTip(html, anchorEl)` / `hideTip()` on one `#tip` element (navy tooltip CSS from `gear-v5.html` `.tip`), kept inside the window.
- Produces (JS): `pageFit(listEl, rows, renderRow, pagerEl)`: renders as many rows as fit `listEl`'s height (measure one row), with ◀ n / m ▶ buttons (`.pg`, CSS from `now-v7.html`), re-fits on resize.
- Produces (CSS): `.full` page layout (`height:100vh` column flex; `#view` takes the rest), and the fallback: `@media (max-width:760px), (max-height:600px)` → normal flow and page scroll.
- Removes: nothing yet (each tab task removes its old code).

- [ ] **Step 1: Add the pieces** (no tab uses them yet; the page must look as before apart from tab icons).
- [ ] **Step 2: Check in the browser:** start `python companion.py`, open `http://localhost:8765`, every tab still renders, tab icons show, no console errors.
- [ ] **Step 3: Run all tests** → pass.
- [ ] **Step 4: Commit** — `git commit -m "feat(ui): game icons, game window, tooltip, pager, full-height layout"`.

### Task 8: Now

**Files:**
- Modify: `web/index.html` (`renderLive`, `grindCard`, `nextUpCard`; new `bestMaps(best)`, `hereCard(h)`; remove `myShopCard`/shop/deals/helper from Now)

**Interfaces:**
- Consumes: `/api/grind` `best` (Task 2), `/api/here` (Task 1), Task 7 helpers.

- [ ] **Step 1: Rebuild Now** to `now-v7.html`: left column Grind (Pause / Start over buttons with words; chart fills spare height; Your best maps rows: medal, map, "Lv a–b · time", EXP/hr, Go or "here"; empty → "Grind 10 minutes on a map and it shows here.") and Next up (one-line Train / SP / AP rows); right column This map (Map Mark, "street · town", monster tiles, Worth picking up with `pageFit`, top row highlighted, success chip on scrolls, "rate unknown" or the rate, MSC price, the credit line; `drops_ok` false → "Drop data isn't available right now."). While a route runs, one strip above Next up: "Step i of n · portal <side> → <map>" linking to Go to. Remove the status line, player-shop cards, deals and Quest Helper from Now; move "What Companion sees" into Settings → Advanced (Task 13 renders it).
- [ ] **Step 2: Check in the browser** at 1693×784 and 1150×680: `document.scrollingElement.scrollHeight <= innerHeight` is `true`; both columns end on the same line; compare with `now-v7.html`. With screen reading off: Your best maps + Next up on the left, This map from the HUD's map.
- [ ] **Step 3: Run all tests** → pass.
- [ ] **Step 4: Commit** — `git commit -m "feat(now): grind, your best maps, next up, this map with drops worth picking up"`.

### Task 9: Go to

**Files:**
- Modify: `web/index.html` (`renderNav`, `buildMap`; new `hereLeft(h)`, `whereTo()`)
- Modify: `companion.py` (POST `/api/nav` remembers `prof["recent_nav"]`, last 5 destination ids, newest first; `/api/state` returns it)
- Test: `tests/test_nav_recent.py`

**Interfaces:**
- Consumes: `/api/here` (Task 1), `/api/portal` + `/api/portal.webp` (Task 6), `/api/train`, `/api/maps`.
- Produces: `remember_recent(prof: dict, map_id: int, keep: int = 5) -> None` in `companion.py`.

- [ ] **Step 1: Write the failing test**

```python
def test_recent_destinations_newest_first_no_repeats():
    prof = {}
    for m in (1, 2, 3, 2, 4, 5, 6):
        companion.remember_recent(prof, m)
    assert prof["recent_nav"] == [6, 5, 4, 2, 3]
```

- [ ] **Step 2: Run it to see it fail; implement; run all tests** → pass.
- [ ] **Step 3: Rebuild Go to** to `goto-v2.html` / `goto-town-v2.html`: left You're here (hunting map: monster tiles; town: NPC list with picture and role tag, click → select) and Where to (search; Towns: map ids looked up by name in `data.maps` (Henesys is 10001000 in OSMS), with Map Marks Henesys / Ellinia / Perion / KerningCity / Dungeon (Sleepywood) / Rith (Lith Harbor); Train for your level from `/api/train` top 3 with your EXP/hr from `/api/grind` `by_map`; Recent from `recent_nav`). Right: the map with every portal drawn as `<image href="/api/portal.webp">` placed at `(x - anchor.x, y - anchor.y)`, size from `/api/portal`, each with a label (blue; the target one dark with a red ring + white halo, r ≈ 150 map px, centred 110 px above the foot); NPCs drawn standing (`<image>` 140×150, `xMidYMax meet`, foot at the NPC's x, y) with the selected one ringed and named; no portal sprite available → today's ring only.
- [ ] **Step 4: Check in the browser** at both sizes: no page scroll; a route to Sleepywood from Ant Tunnel I shows the ringed portal upper left; in Henesys, clicking Chief Stan rings him by the Henesys Park door.
- [ ] **Step 5: Commit** — `git commit -m "feat(goto): quick picks, NPCs in towns, the game's portals with a red ring"`.

### Task 10: Gear

**Files:**
- Modify: `gamedata.py` (`gear`: each entry gains `"id"`, `"job"` (`req_job_label`), `"speed_n"` (`attackSpeed`), and the result gains `"overall_instead": bool` per the spec's call 9)
- Modify: `web/index.html` (`renderGear`)
- Test: `tests/test_gear.py`

**Interfaces:**
- Produces: slot coordinates in `equip_classic.png` pixels, `EQ_SLOTS = {Hat:[100,95], "Ear Acc":[146,142], Cape:[7,188], Top:[54,188], Weapon:[146,188], Shield:[193,188], Gloves:[7,234], Bottom:[54,234], Shoes:[54,281]}`; data slot names map Hat←Hat, Ear Acc←Earring, Cape←Cape, Top←Top or Overall, Bottom←Bottom, Gloves←Glove, Shoes←Shoes, Weapon←Weapon, Shield←Shield.

- [ ] **Step 1: Write the failing test**: with two fake equips (an Overall scoring 40, a Top 15 + Bottom 20) `gear(...)["overall_instead"] is True`; with Top 25 + Bottom 20 it's `False`; every entry has `id`, `job`, `speed_n` keys.
- [ ] **Step 2: Run it to see it fail; implement; run all tests** → pass.
- [ ] **Step 3: Rebuild Gear** to `gear-v5.html`: the window picture (absolute box, scaled by `min(1.6, freeHeight / 404)`, never cut), items at `EQ_SLOTS` (42 px pictures in 47 px boxes), the caption "Best <job> gear for Lv <level>" in DotGothic16 at the bottom; hover a slot or a list row → `showTip` with name, picture, REQ LEV/STR/DEX/INT/LUK (met white, unmet red `#FF6B5E`, zero greyed) from `prof.stats`/Character Stat, the job row with lit jobs, ✦ Type / Attack Speed "Normal (6)" / stats / Remaining Enhancements, prices Snipe at / MSC usual / Cozy or "Not traded on the market yet". Right list: picture, bold name, "Weapon · Lv 30" grey, snipe price; the set total beside your mesos; the Overall note.
- [ ] **Step 4: Check in the browser** at both sizes: window whole (bottom border visible), tooltip stays on screen, no page scroll.
- [ ] **Step 5: Commit** — `git commit -m "feat(gear): the Classic Equip window with the best item per slot and game tooltips"`.

### Task 11: Skills

**Files:**
- Modify: `gamedata.py` (`skill_list(job, with_beginner=False)`: when true, the `beginner` family's skills come first with `"job": "Beginner"`)
- Modify: `companion.py` (`/api/skills` passes `with_beginner=True`)
- Modify: `web/index.html` (`renderSkills`)
- Test: `tests/test_points.py`

- [ ] **Step 1: Write the failing test**: `skill_list("Hunter", with_beginner=True)` has jobs `["Beginner", "Archer", "Hunter"]` in that order (use the session's cached data the way `conftest.game_reader` patches `fetch_json`).
- [ ] **Step 2: Run it to see it fail; implement; run all tests** → pass.
- [ ] **Step 3: Rebuild Skills** to `skills-v8.html`: `gameWin("SKILL INVENTORY", …)` with a tab per job present, each tab's icon being that job's first skill icon from `skill_list` (Beginner: 0001000), the current job open; header "<job> · <n>th job · N SP spent here"; rows filling the height (icon, name, kind, bar, "4 / 20"), no next-point markers; right: "Your next 3 skill points" from `next.sp3` with icons, the "Then …" line from `next.sp`, "N SP to spend now", AP; the picked skill card (plan − / +, At level 1 / At max, a button opening the build table).
- [ ] **Step 4: Check in the browser** at both sizes: no page scroll, tabs switch, no future-job tab.
- [ ] **Step 5: Commit** — `git commit -m "feat(skills): a skill window with job tabs and the next three points"`.

### Task 12: Shops

**Files:**
- Modify: `web/index.html` (`renderFlips`, `sellKeepCard`, `myShopCard` placement)

**Interfaces:**
- Consumes: `/api/sellkeep` (48 max, Task 5; verdicts per Task 4), `/api/seen`, `/api/state` `myshop` and `game.shop`, POST `/api/quest_done`.

- [ ] **Step 1: Rebuild Shops** to `shops-v4.html`: pills Your shop / Sell or keep / Shops you visited (remember the pick). Sell or keep: `gameWin("SELL OR KEEP", tabs Free Market / NPC / Keep / Not sure / Drop (only when non-empty) with counts)` holding a 6-across slot grid paged with `pageFit`, hint line, "Keeps the last 48 items you hovered" + Clear; hover → `showTip` with a verdict label, the price and `why`. Right: What your bag is worth (FM sum, after 3% fee, count; NPC sum; keep count) and the 4 worth the most; Why keep these (scrolls inside its card; a row whose `why` names a quest gets "Done with this quest" → POST `/api/quest_done` `{id, done: true}` then re-render; `/api/sellkeep` must therefore return the quest `id` with a quest reason: add `"quest_id"` to `advisor.verdict`'s keep-for-quest results and a test in `tests/test_advisor.py`). Shops you visited: today's grid and detail, plus the open player shop's live rows (moved from Now).
- [ ] **Step 2: Run all tests** → pass (incl. the `quest_id` test).
- [ ] **Step 3: Check in the browser** at both sizes: no page scroll; the keep list scrolls inside its card; Clear empties the grid.
- [ ] **Step 4: Commit** — `git commit -m "feat(shops): sell or keep as a paged inventory, your shop and visited shops under pills"`.

### Task 13: Settings

**Files:**
- Modify: `web/index.html` (`renderSettings`, `discordCard`)

- [ ] **Step 1: Rebuild Settings** to `settings-v1.html`: Screen reading card with status pill and three switches (Read the game / Draw on the game / Beep on a deal or a sale, each one bold line + one short line), the collapsed "⚠ Unofficial tool: use at your own risk" holding the full risk text and the consent checkbox (reading stays disabled until consent, as now); Discord card with the simple-icons Discord path in `#5865F2`, status pill, linked user, "#shop-sales", the Post my shop's sales switch, blurple Send a test message, Unlink (not linked → Connect Discord; not set up → "Not set up in this build."); Help card; Advanced collapsed with label side, window title, the fallback shop area fields and "What Companion sees" (the frame picture and Scan / Auto-scan / Select buttons from old Now).
- [ ] **Step 2: Check in the browser:** every switch still saves (reload keeps it), consent gating works, no page scroll.
- [ ] **Step 3: Run all tests** → pass.
- [ ] **Step 4: Commit** — `git commit -m "feat(settings): switches, a Discord card, the rest under Advanced"`.

### Task 14: Whole-branch check

- [ ] **Step 1:** `python -I -m pytest tests -q` → all pass.
- [ ] **Step 2:** In the browser, every tab at 1693×784, 1150×680 and 700×700 (stacked fallback scrolls, nothing overlaps); light and dark colour schemes; screen reading off.
- [ ] **Step 3:** Update `README.md`'s tab descriptions and the drops credit; commit `docs: the redesigned tabs`.
- [ ] **Step 4:** Tell the user it's ready for a check with the game running; build the exe only when they ask.
