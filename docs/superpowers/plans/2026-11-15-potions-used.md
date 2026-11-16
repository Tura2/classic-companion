# Potions Used Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Count the potions drunk from the 12 quick slots and show them on Now's This session card. Each item gets one loot tile with its net count, red below zero.

**Architecture:** A new `quickslots.py` reads the quick slots on the game's own pixels (`native.py`). It reads each slot's count against the game's ItemNo digit sprites and names the slot's item by its icon. A small tracker in the same file turns confirmed count drops into `("used", name, n)` events. The events ride the corner loop's existing queue message into `Grind.add_used`. `session_view` then merges loot and used into net tiles.

**Tech Stack:** Python 3, numpy, Pillow, pytest. Dashboard is the single file `web/index.html` (vanilla JS).

**Spec:** `docs/superpowers/specs/2026-11-14-potions-used-design.md`

## Global Constraints

- **Branch and PR:** branch `feat/potions-used`, stacked on `feat/corner-lines` (PR #43, which is on hold). The PR's base is `feat/corner-lines`. Don't merge anything without the player's OK.
- **No input:** never send input to the game. Reading only takes pictures.
- **Tests:** run the full suite from `classic/companion` with `python -I -m pytest -q -W error::DeprecationWarning`. Every task ends green.
- **Encoding:** open files with `encoding="utf-8"`. Scripts run under `python -I` call `sys.stdout.reconfigure(encoding="utf-8")`. The locale is cp1255.
- **Speed:** a corner look plus the slot read adds about 60 ms or less. The corner look is about 10 ms today.
- **No wrong counts:** a missed count is better than a potion counted that wasn't drunk.
- **UI:**
  - no page scroll and nothing spilling out of cards;
  - no prices on the page, worth only in tooltips;
  - the game's own sprites, plain words, no sounds;
  - NET stays mesos only.
- **Tooltip copy for a used item, exact:** `Picked up N · used M`
- **Samples:** game pictures stay out of git (`samples/` is ignored). Tests use synthetic frames.

## Review Focus

1. **The mouse cursor or a window resting over a count.** Two looks then agree on a wrong, smaller number, such as 145 → 45 with the "1" covered. Expected: not counted. A drop bigger than `MAX_DROP` re-baselines instead. Test in Task 3.
2. **The speed skill's top-right number (2 → 1)** must never count. Only the bottom-left count spot is read, and only slots named as a Use item count. Test in Task 3.
3. **The icons not downloaded yet** (first run, or offline). Expected: no counts at all, and loot lines still read on time. Icons load on their own thread, never inside a corner look. Tests in Tasks 3 and 5.
4. **A potion moved from one slot to another, or a slot swapped to a different potion.** Expected: the slot re-baselines and nothing is counted. Test in Task 3.
5. **A session reset or a new session.** Expected: the used counts start at zero, like loot. Test in Task 4.

---

## Geometry (measured 2026-11-15 on `samples/cases/notices_012…065.png`, native 1228×768)

- The count's top-left in slot (row r, col c), r = 0..2 and c = 0..3: x = NW − 357 + 35·c, y = NH − 153 + 34·r. NW and NH are the native width and height.
  - Measured: (871, 649), (906, 649) and (976, 649) in row 1; (906, 683) in row 2.
- Counts are left-aligned at that spot. Each digit is an ItemNo sprite (8×11; "1" is 5 wide). The next digit starts at x + 8, or x + 5 after a "1".
- Slot (r, c) spans about x = NW − 358 + 35·c to +33, and y = NH − 172 + 34·r to +33. Its icon sits inside, under the key label (top left) and the count (bottom left).
- The speed skill's "2" sits at the slot's top right, (999, 664). It is outside every count spot.
- Assumed anchored to the bottom right like the corner lines. Not yet seen at 16:9 (1366×768).

---

### Task 1: Count reader on native pixels

**Files:**
- Create: `assets/itemno/0.png` … `9.png`. Copy them from `%TMP%/itemno/`, the maplestory.io `GMS/83/UI/Basic.img/ItemNo` sprites.
- Create: `quickslots.py`
- Modify: `native.py`. Add `rgb(frame, box)`.
- Test: `tests/test_quickslots.py`, `tests/test_native.py`

**Interfaces:**
- Produces:
  - `native.rgb(frame, box) -> (np.ndarray[h, w, 3] float32, (fx, fy))`: the same un-stretch as `lum`, per channel.
  - `quickslots.ROWS, COLS = 3, 4`; `CX, CY = 357, 153`, the offsets from NW and NH to slot (0,0)'s count; `PX, PY = 35, 34`.
  - `quickslots.Digits()` loads the sprites from `RES_DIR/"assets"/"itemno"`.
  - `Digits.read(L, x, y) -> int | None` reads the count whose first digit's top-left is at native (x, y), with L in native coordinates.
    - Each digit is tried at its place ±1 px.
    - It is accepted when the share of the sprite's opaque pixels within 6 levels is ≥ 0.85, and the best digit wins.
    - It returns None when no first digit matches.
  - `quickslots.count_spots(nsize) -> list[(slot, x, y)]`, slots 0..11 numbered row by row.

- [ ] **Step 1: Write the failing tests.** Synthetic frames: draw sprites with alpha over a textured native background (as `tests/test_notices.py::background`), then resize to 1920×1200 BILINEAR.
  - `test_reads_counts_at_each_spot`: counts {0: 93, 1: 145, 3: 52, 5: 65, 7: 0, 11: 1203} drawn at their spots read back exactly. Other slots read None.
  - `test_one_is_narrow`: 111 and 1203 read right, since "1" advances 5.
  - `test_a_covered_first_digit_reads_none`: 145 with the "1" painted over by a flat grey box reads None or 45. That decides Task 3's guard. Assert the result is in `(None, 45)` and record which.
  - `test_rgb_matches_lum`: `native.rgb(...) @ LUM` is within 0.01 of `native.lum(...)` on a random frame.
- [ ] **Step 2:** Run `python -I -m pytest -q tests/test_quickslots.py tests/test_native.py`. Expect failures: no module or no attribute.
- [ ] **Step 3: Implement** `native.rgb`, `Digits` and `count_spots`. Load the sprites as luminance plus an alpha≥250 mask. Use one `lum` call over the box covering all 12 count bands, not one per slot.
- [ ] **Step 4:** Run the same tests. Expect PASS. Then time `Digits.read` over the 12 spots on a 1920×1200 frame, from the lum call to 12 reads, and expect ≤ 10 ms.
- [ ] **Step 5:** Add `tools/check_slots.py`. It reads the six `samples/cases/notices_*.png`, which are bottom-right quarters pasted at (960, 600) as in `check_corner`. It prints the counts per slot and compares them with this truth:
  - 012 and 020: {4: 93, 5: 145, 7: 52, 9: 65};
  - 027 through 065: {4: 94, 5: 145, 7: 52, 9: 66}.

  Expect 6/6 frames right.
- [ ] **Step 6: Commit** `quickslots: read quick-slot counts by the game's digit sprites`.

### Task 2: Naming a slot's item by its icon

**Files:**
- Modify: `quickslots.py`
- Test: `tests/test_quickslots.py`

**Interfaces:**
- Consumes: `native.rgb`; the slot boxes from the Geometry section.
- Produces:
  - `quickslots.Icons(items, icon_path)`. `items` is a list of `(id, name)` (`data.bag_items["Consumable"]`). `icon_path(id) -> Path | None` is `invgrid.Bag._get`, which shares `cache/icons/`.
  - `Icons.load()`: blocking; builds a stack of RGBA icons at native size (no scaling). `Icons.ready -> bool`.
  - `Icons.name(slot_rgb) -> str | None`: the best Use item.
    - The icon is slid ±3 px in the slot box.
    - Score: the share of the icon's opaque pixels (alpha ≥ 250) whose RGB is within 30 (summed) of the slot.
    - Accept when the score is ≥ 0.6 and beats the best *different-named* item by ≥ 0.1. Otherwise return None.
    - Results are memoized by a blake2b hash of the slot's pixels with the count band (bottom 14 rows) blanked, up to 500 entries.

- [ ] **Step 1: Write the failing tests.** They use a fake `items` set of 4 icons built in the test as solid shapes in distinct colours, two of them the same shape in different colours like Red and Orange Potion.
  - `test_names_the_icon_in_a_slot`: each icon drawn in slot 5 is named.
  - `test_same_shape_other_colour_is_told_apart`
  - `test_a_skill_or_empty_slot_is_none`: an icon not in `items`, and a bare slot background.
  - `test_label_and_count_over_the_icon_still_name_it`: "Shift"-like white blocks at the top left, and a count drawn with the digit sprites.
- [ ] **Step 2:** Run the tests. Expect FAIL.
- [ ] **Step 3: Implement** `Icons`. Load the icon files with PIL RGBA; skip files that fail to open. Stack them padded to the largest size, using a per-icon mask.
- [ ] **Step 4:** Run the tests. Expect PASS. Check that naming 12 new slots takes ≤ 40 ms, which happens once per change thanks to the memo.
- [ ] **Step 5:** On the real samples, `tools/check_slots.py --names` names slot 4 Blue Potion, slot 5 a lemon item, slot 7 a milk item and slot 9 Orange Potion. Use the item names the data has. The icons come from `cache/icons/` (OSMS). Record any slot that reads None in the commit message.
- [ ] **Step 6: Commit** `quickslots: name a slot's Use item by its icon`.

### Task 3: The tracker: confirmed drops become "used" events

**Files:**
- Modify: `quickslots.py`
- Test: `tests/test_quickslots.py`

**Interfaces:**
- Consumes: `Digits.read`, `count_spots`, `Icons`.
- Produces: `quickslots.QuickSlots(icons)` and `QuickSlots.step(frame, now) -> list[("used", name, n)]`. `MAX_DROP = 20`.

The rules, per slot:
- **Baseline:**
  - A look sets the baseline `(name, count)` when the slot has none.
  - It also resets the baseline when the name changes, or when the name or count reads None. Nothing is counted on those looks.
  - The baseline is also reset when the icons aren't ready. Until `icons.ready`, `step` returns [] and reads nothing.
- **Confirming a new count:** a count different from the baseline becomes *pending*. The next look reading the same count confirms it.
  - If the confirmed count is lower, the drop d = baseline − count. When 1 ≤ d ≤ MAX_DROP, emit `("used", name, d)`. When d > MAX_DROP, emit nothing.
  - If the confirmed count is higher, emit nothing (pickups).
  - Either way, the baseline becomes the confirmed count.
  - A pending count not confirmed by the next look is dropped.

- [ ] **Step 1: Write the failing tests.** Each feeds a sequence of synthetic frames; a fake `Icons` maps the slot hash to a name.
  - `test_first_look_is_a_baseline`: 93 → []
  - `test_a_drop_counts_once_two_looks_agree`: 93, 90, 90, 90 → one `("used", "Blue Potion", 3)` on the 3rd look
  - `test_a_one_look_blip_is_not_counted`: 93, 80, 93, 93 → []
  - `test_the_last_potion_counts`: 1, 0, 0 → `("used", name, 1)`
  - `test_pickups_are_not_counted`: 93, 94, 94, 92, 92 → `("used", name, 2)` only
  - `test_a_slot_changing_item_rebaselines`: Blue 93, Orange 65, Orange 65, Orange 60, 60 → only `("used","Orange Potion",5)`
  - `test_a_covered_count_is_not_counted`: 145, 45, 45, 45 → [] (Review Focus 1)
  - `test_a_skill_slot_is_ignored`: a skill icon (Icons → None) with the top-right "2" then "1" → [] (Review Focus 2)
  - `test_unreadable_look_rebaselines`: 93, None, 90, 90 → [] (90 is the new baseline after the None)
  - `test_nothing_until_icons_ready` (Review Focus 3)
- [ ] **Step 2:** Run the tests. Expect FAIL.
- [ ] **Step 3: Implement** `QuickSlots.step`. One `native.lum` for the counts and one `native.rgb` for the 12 slot boxes per look.
- [ ] **Step 4:** Run the tests. Expect PASS.
- [ ] **Step 5:** Extend `tools/check_slots.py` to run `QuickSlots.step` over the six frames in order. Expect no events: the counts only go up, and the skill's 2 → 1 is ignored.
- [ ] **Step 6: Commit** `quickslots: count confirmed drops as potions used`.

### Task 4: Storing used and the net view

**Files:**
- Modify: `grind.py` (`_new_session`, new `add_used`, `summary`), `companion.py` (`session_view`)
- Test: `tests/test_grind_session.py`, `tests/test_now_api.py`

**Interfaces:**
- Produces:
  - `Grind.add_used(name, n, now)`, with `self.used = {}` reset in `_new_session`.
  - `summary()["used"] = [{"name", "count"}]`.
  - `session_view(...)["loot"]` items gain `picked` and `used` (ints), and `count = picked − used`.
  - The loot order is: items with count > 0 in pickup order, then items with count ≤ 0 by count ascending (most drunk first).
  - Items only drunk get the same tooltip fields (img, kind, desc, msc, npc).

- [ ] **Step 1: Write the failing tests.**
  - `test_used_adds_up_and_resets` in `test_grind_session.py`: `add_used("Orange Potion", 3)` twice gives `summary["used"] == [{"name": "Orange Potion", "count": 6}]`. After `g.reset(t)` it is `[]`. (Review Focus 5)
  - `test_session_view_nets_loot_and_used` in `test_now_api.py`, with `add_loot("Orange Potion", 1)`, `add_used("Orange Potion", 12)`, `add_loot("Tablecloth", 3)`, `add_used("Blue Potion", 9)` and `add_used("White Potion", 2)` plus `add_loot("White Potion", 2)`:
    - the loot names in order are `["Tablecloth", "Orange Potion", "Blue Potion", "White Potion"]`;
    - the counts are `[3, -11, -9, 0]`;
    - Orange's `picked, used` is `(1, 12)`;
    - Blue's `img` and `kind == "Use"`.
- [ ] **Step 2:** Run the tests. Expect FAIL.
- [ ] **Step 3: Implement** it. `_session_brief["items"]` stays the sum of picked only.
- [ ] **Step 4:** Run the full suite. Expect PASS.
- [ ] **Step 5: Commit** `Now: potions used next to the loot, net per item`.

### Task 5: Wiring into the corner loop

**Files:**
- Modify: `sniper.py` (`handle_corner`, App init, `_corner_look`, a new `_load_slot_icons`)
- Test: `tests/test_now_api.py`

**Interfaces:**
- Consumes: `QuickSlots.step`, `Icons.load`, `Grind.add_used`.
- Produces: `handle_corner` also takes `("used", name, n)` and calls `g.add_used(name, n, now)` when a name is given.

- [ ] **Step 1: Write the failing test.** `test_used_events_reach_the_session`: `reads(a, prof, 50000, [("used", "Orange Potion", 2), ("used", None, 1)])` gives `summary["used"] == [{"name": "Orange Potion", "count": 2}]`.
- [ ] **Step 2:** Run it. Expect FAIL.
- [ ] **Step 3: Implement** the wiring.
  - In App init: `self.slots = quickslots.QuickSlots(quickslots.Icons(data.bag_items.get("Consumable", []), <icon_path>))`.
  - `<icon_path>` is a `invgrid.Bag(...)._get` built the way `sniper.py:1338` builds its Bag. Reuse one Bag if `self.bag` is set lazily; otherwise make a module-level helper that both use.
  - Start a daemon thread running `icons.load()` at startup, after the data loads. It must never run inside `_corner_look`. (Review Focus 3)
  - In `_corner_look`, after `corner.step`: `events += self.slots.step(frame, now)` with the same `now`. Wrap the slot read in its own try, so a failure there never loses the corner's events.
- [ ] **Step 4:** Run the full suite. Expect PASS. Time one `_corner_look` body on a 1920×1200 frame (corner plus slots): expect ≤ 60 ms more than today.
- [ ] **Step 5: Commit** `Now: read potions used every corner look`.

### Task 6: The tiles and tooltip on Now

**Files:**
- Modify: `web/index.html` (`lootTile`, `lootTip`, `lastSessionCard`'s items sum, CSS next to `.lt.meso`)

**Interfaces:**
- Consumes: the loot items' `count`, `picked` and `used` from Task 4.

- [ ] **Step 1: Implement** it.
  - Tiles:
    - `lootTile` adds class `used` when `count < 0`, and `zero` when `count === 0 && used`;
    - the number is `−N` (a real minus sign) for below zero.
  - CSS, from mockup A:
    - `.lt.used{border-color:#6b3340;background:linear-gradient(#2a1b26,#1d1420)}`, with its number in `#ff8f8f`;
    - `.lt.zero` gets a muted grey number, `#8A97B2`.
  - `lootTip` replaces "You picked up N" with `Picked up N · used M` when `used` is set.
  - `lastSessionCard` sums `x.picked ?? x.count`.
- [ ] **Step 2: Check on a dev copy.**
  - Back up `profile.json`, then run the scratchpad `dev_now.py` on port 8766, with fake `add_used` calls added: Orange −11, Blue −9, White 0, and 14 loot items so the grid pages.
  - Screenshot it with headless Edge.
  - Check: red tiles last, the grey 0 tile, the ◀ ▶ paging still fitting, no scroll, and the tooltip text.
  - Restore `profile.json`.
- [ ] **Step 3:** Run the full suite. Expect PASS.
- [ ] **Step 4: Commit** `Now: red tiles for potions drunk`.

### Task 7: Ship-ready checks

- [ ] **Step 1:** `tools/check_corner.py` still gives 80/80, and `tools/check_slots.py` gives 6/6 counts and no events.
- [ ] **Step 2: Build** a test exe to the scratchpad, without discord.json and with absolute `--add-data` paths for `assets`, which now include `itemno/`. Smoke-run it: the dashboard answers, `corner: true`, and no errors from the slot reader in the console.
- [ ] **Step 3: Update** memory note `companion-minimap-read.md` with the slot geometry, the rules, and what's still unverified live: 4-digit counts, 16:9 position, how the empty slot's 0 is drawn.
- [ ] **Step 4:** Push, and open a PR with base `feat/corner-lines`. **Ask the player** before merging, and offer a live recording to confirm. Release only after both PRs are approved.
