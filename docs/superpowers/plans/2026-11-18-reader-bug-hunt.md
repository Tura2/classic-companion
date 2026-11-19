# Reader, resolution and measurements bug hunt — plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development for the fix tasks) to work through this plan task by task. Use superpowers:systematic-debugging on every finding before fixing it, and superpowers:test-driven-development for every fix. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Find and fix the places where Companion reads the game wrong because of the game's size, shape, scaling or full screen, or because a measured offset or threshold is off. Each fix ships only with a test that pins it.

**Architecture:** This is a search before it's a build. Three passes find candidates:
1. A static audit of every place that turns frame pixels into positions or sizes.
2. A **same picture, other size** test: the 1920×1200 cases are re-drawn at other heights through `native.py`'s model of the game's stretch, and must read the same.
3. A short live round, only when the player says go.

Candidates go into the **Findings** table at the end of this file. Each confirmed one gets a failing test, a fix and its own PR.

**Tech Stack:** Python 3, Pillow, numpy (no OpenCV, the player's choice), Windows OCR, pytest. Windows Graphics Capture for frames.

**Spec:** none. The facts this plan argues from are in:
- `samples/README.md` (the measured sizes table);
- the module docstrings of `reader.py`, `native.py`, `anchors.py`, `capture.py`, `invgrid.py`, `quickslots.py`, `hudexp.py`;
- `docs/superpowers/plans/2026-11-06-reader-accuracy.md` (the last accuracy round and its Findings).

## Global Constraints

- **Never send input to the game.** Take pictures only when the player says they're ready.
- Work from `origin/main` (v1.4.2 or later). The local checkout may sit on an old branch without the full-screen code (`native.find_bars`, `capture.game_area`).
- Run tests with `python -I -m pytest -q -W error::DeprecationWarning` from `classic/companion`. The baseline is all passing.
- Capture scripts call `ctypes.windll.shcore.SetProcessDpiAwareness(2)` first, or frames come back at 1536×960.
- This PC's locale is cp1255. Open files with `encoding="utf-8"`. Under `python -I`, call `sys.stdout.reconfigure(encoding="utf-8")` before printing non-ASCII.
- The GitHub repo is **public**:
  - game pictures stay in git-ignored `samples/cases/` and `samples/raw/`;
  - no other player's name goes in a commit, test name or message;
  - mask cases with `casekit.masked`.
- Ask before deleting game pictures.
- One PR per fix, or per tightly related group of fixes. Ask the player before merging. Releases are patch versions, and public builds never include `discord.json`.

## Review Focus

These are the inputs most likely to break the reader without any current test noticing. Each one is checked in Task 3 or Task 4.

1. **A game area 1000–1199 px tall** (1920×1080, 1680×1050), where every offset is scaled below 1.0 and rounding drifts. Fields should read the same as at 1200.
2. **Full screen on a monitor of another shape** (a 16:10 game on a 16:9 monitor, and the reverse), where the black bars are trimmed. Expected: `s` comes from the trimmed picture, never from the monitor.
3. **The game on a second monitor with other Windows scaling** (100% beside 125%). Expected: capture, `client_box` and the overlays agree on physical pixels.
4. **Windows dragged near the frame's edge**, so a crop box runs past the edge. Expected: the window is skipped or read cleanly. No zero-width crop, no exception, no field read from the wrong spot.
5. **A wrong title learned once** into `cache/titles/<height>/`. Expected: a bad learned title can't poison every later read at that height.

---

### Task 1: Baseline and inventory

**Files:**
- Modify: this plan's Findings section

- [ ] **Step 1:** `git fetch origin`. Create the branch: `git switch -c fix/reader-bug-hunt origin/main`. Expected: `git log -1` shows the v1.4.2 commit or later.
- [ ] **Step 2:** Run the suite. Expected: all pass. Write the count and run time under Findings → Baseline.
- [ ] **Step 3:** List the cases and raw pictures by size: `ls samples/cases samples/raw`, plus each PNG's size from PIL. Write how many there are at each height (1080, 1200, 1440, full screen) under Findings → Samples. The heights with no sample are the gaps Task 5 asks the player to fill.

### Task 2: Static audit of every pixel measurement

Find each place a position, size or threshold is computed from the frame, and check it against the scale model below.

**The scale model** (from `native.py` and `samples/README.md`):
- The game draws at 768 px tall and Windows stretches that picture to the window.
- So the UI scale is `h / 1200` for game areas taller than 768, and a fixed `768 / 1200 = 0.64` at 768 and below. The README measured about 0.67 there.
- `h` is the game's picture after the black bars are trimmed.

- [ ] **Step 1: Find every scale site.** Run these from `classic/companion`:
  ```
  rg -n "REF_HEIGHT|/ ?1200|\* ?1200|frame\.height|frame\.width|\.size\b" --glob "*.py" --glob "!tests/**"
  rg -n "\b(u|s)\s*=\s*" reader.py anchors.py invgrid.py quickslots.py hudexp.py notices.py party.py sniper.py
  ```
  List each site under Findings → Scale sites, as file:line, what it measures, and which `s` it uses.
- [ ] **Step 2: Find bare pixel numbers.** These are constants in crop, box or distance expressions that aren't multiplied by `s`, `u` or `K`:
  ```
  rg -n "[-+] ?\d{2,}\b(?! ?\* ?(s|u|K))" reader.py invgrid.py quickslots.py hudexp.py notices.py anchors.py
  ```
  Example: `reader.py` around line 1167, `l - 20, t - 20`. For each one, write down whether it's meant in frame pixels (a margin) or in game pixels (it must scale). Every one that must scale and doesn't is a finding.
- [ ] **Step 3: Check each hypothesis below against the code**, and write a one-line verdict with its evidence (file:line) under Findings → Hypotheses:
  - **H1. One scale for all.** Do the reader (`frame.height / REF_HEIGHT`), `anchors.learn` (`/ 1200`), `invgrid`, `quickslots`, `hudexp` (`bh / 9`) and `notices` agree on `s` for the same frame, including after `native.trim_bars`?
  - **H2. Bars trimmed before `s`.** Does `frame.info[native.AREA]` survive `crop`, `convert` and `resize` everywhere the reader passes the frame on? Is `s` ever taken from an untrimmed frame?
  - **H3. Rounding.** Look for `int()` used where `round()` is meant (and the reverse) on scaled offsets. At `s = 0.9` and `1.2`, does an offset drift by ≥ 1 px from where the README's table puts it?
  - **H4. Width assumptions.** Do `frame.width * 0.5`-style rules (`reader.py:984`, `:1428`) hold at 4:3, 16:9 and 16:10, and with bars?
  - **H5. DPI.** `sniper.py` and `window.py` set Per-Monitor v2 awareness, falling back to system-aware. Does `client_box`/`window_bounds` stay in physical pixels when the game sits on a monitor with other scaling? Do the overlays move with `overlay.scale` (`sniper.py:1472`)?
  - **H6. Learned titles.** `anchors.learn` keys on height only. Can a misread line, or a different width at the same height (bars), save a bad template? Is there a way out (a score check, an expiry)?
  - **H7. Constants measured at one size.** `invgrid.GRID_X/GRID_Y/K`, the quick-slot frame and the corner rows were measured at 1920×1200 only. Do they hold at 1080 and 1440?
  - **H8. `MIN_HEIGHT = 1000`.** Is the gate still needed now that `native.py` reads the game's own pixels? This one isn't a bug; it's a question for the player once the evidence is in.
  - **H9. Game rules as checks.** Base stats + AP = 5×level+20. Skill points + SP = 3×level−28 from level 30. Do they hold on every case? A miss is a systematic misread.
- [ ] **Step 4: Commit** the Findings so far: `git commit -m "docs(plan): reader bug hunt, static audit findings"`.

### Task 3: Same picture, other size

**Files:**
- Modify: `tools/casekit.py` (add `resample`)
- Create: `tests/test_scale_invariance.py`

**Interfaces:**
- Produces: `casekit.resample(frame: Image.Image, height: int) -> Image.Image`. It un-stretches a frame to the game's own 768-tall picture (`native.rgb` over the whole frame), then stretches it bilinearly to `height`, keeping the aspect ratio. This is the same thing Windows does to the game's picture.

- [ ] **Step 1: Write the failing tests.**
  - `test_resample_roundtrip`: `resample(f, f.height)` differs from `f` by a mean of at most 2 levels per channel.
  - `test_resample_size`: `resample(f1920x1200, 1050).size == (1680, 1050)`.
- [ ] **Step 2:** Run the tests. Expected: FAIL (`resample` isn't defined).
- [ ] **Step 3:** Implement `resample`. Run the tests. Expected: PASS.
- [ ] **Step 4: Write `test_case_at_height`.** Parametrize it over every 1920×1200 case in `load_cases()` and every height in `(1050, 1080, 1440, 1600)`, using 16:10 widths. Read `resample(frame, h)` with the same three-read routine as `tests/test_cases.py::seen_case`, and assert each `expect` field equals the 1200 case's. Skip the module when there are no cases, as `test_cases.py` does.
- [ ] **Step 5:** Run it. Each failure is a finding:
  - record field, height, got and want under Findings → Invariance;
  - mark the failure `xfail(strict=True, reason="F<n>")` so the suite stays green and the fix flips it.

  Expected: the run ends with no unexpected failures.
- [ ] **Step 6: Commit:** `git commit -m "test(reader): every case reads the same at 1050-1600 px tall"`.

### Task 4: Full screen, bars and monitors

**Files:**
- Test: `tests/test_capture_area.py` and `tests/test_native.py` (extend these)

- [ ] **Step 1: Write tests for Review Focus 2 and 4** on synthetic frames:
  - a 1920×1200 case framed in black to 2560×1440 (pillarbox) and to 1920×1440 (letterbox);
  - `capture.game_area(img, window, client, full=True)` gives back the case's own size within 1 px;
  - `reader.Reader.read` on that result reads the same fields as the case;
  - a window title found 5 px from the frame's right edge doesn't raise and reads no field from outside the frame.
- [ ] **Step 2:** Run them. Each failure is a finding: write it down and mark it `xfail(strict=True)` as in Task 3.
- [ ] **Step 3: Review Focus 3 (DPI) can't be tested off-screen.** Write the exact live check for Task 5 instead: the game on the 100% monitor, Companion on the 125% one, then compare the mini map's route strip position with the game.
- [ ] **Step 4: Commit:** `git commit -m "test(capture): full screen bars and edge windows"`.

### Task 5: Live round (only when the player says go)

- [ ] **Step 1:** Ask the player for the pictures still missing after Task 1 Step 3, using `tools/grab_samples.py --label <label>`. Ask in one message for:
  - `res-1920x1080`, `res-2560x1440`, `fullscreen-16x9`;
  - `minimap-moved` and `tooltip`;
  - `ui-size-<setting>` for each of the game's UI Size settings (never checked so far);
  - the DPI check from Task 4 Step 3, if the player has two monitors.
- [ ] **Step 2:** Turn the new pictures into masked cases with `tools/make_case.py`, labelling the true values by eye with the player. Re-run Tasks 3 and 4 on them.
- [ ] **Step 3:** Ask the player whether any pictures can be deleted now.

### Task 6: Triage, then fix one finding at a time

- [ ] **Step 1:** Rank the Findings table by how often the player meets the problem × how wrong the result is. A wrong number shown as true ranks above a field left blank. Show the ranked table to the player and ask which to fix.
- [ ] **Step 2: For each finding chosen:**
  1. Find the root cause with superpowers:systematic-debugging.
  2. Its xfail flips to a plain test, which fails.
  3. Make the smallest fix, and the test passes.
  4. The full suite passes.
  5. Commit `fix(reader): <what the player sees now>`.
- [ ] **Step 3:** Open a PR per fix group, build and smoke-test the exe (`build.bat --no-pause`, then run it from `dist` with `--no-update --no-browser`), and ask the player before merging.
- [ ] **Step 4:** Update the memory entry `companion-reader-accuracy.md` with what was proven and what's left.

---

## Findings

### Baseline
`origin/main` at 150f2ff (v1.4.2). Suite: **520 passed in 104 s**. After Tasks 3-4: 651 passed, 64 xfailed in 217 s (the new size test reads every 1920 x 1200 case at four more heights, about +110 s).

### Samples
| size | cases (`samples/cases/`) | raw (`samples/raw/`) |
|---|---|---|
| 1920 x 1200 windowed | 16 (10 with expected values) | 1 |
| 1920 x 1080 windowed | 9: `res_1080`, 5 `myshop_*`, 3 `hudexp_*` (`myshop_ui73` is the game drawn **unstretched**, see F10) | 9 |
| 2560 x 1440 full screen | 1 (`hudexp_fullscreen_29192`, HUD only) | 4 |
| 960 x 600 | 6 `notices_*` (corner crops) | 0 |

**Gaps:** no window (stat, inventory, skills, helper, quest, shop, mini map) at 1440 or in full screen with bars; nothing at 1680 x 1050; no window with the game drawn unstretched; no DPI pair.

### Scale sites
| file:line | measures | uses | ok? |
|---|---|---|---|
| `reader.py:1410,1350,1526,1553,1566` | every window's offsets | `s = frame.height / 1200` | ok while the game stretches its 768 px picture; wrong when it draws unstretched (F10) |
| `anchors.py:198` (`learn`) | the cut of a learned title | `frame.height / 1200` | as above; keyed on height only |
| `anchors.py:107` | title pictures shrunk to the frame | `s` | ok (stat found at 1080 with 1200 cuts) |
| `reader.py:193` | shop button offsets | `ln[4] / 12` (OCR text height) | ok-ish: rides on OCR's box |
| `reader.py:243,262,348,369,380,1547` | your own store | `u` from the notice's width | ok at any UI scale (proven on `myshop_ui73`/`ui100`) |
| `hudexp.py:100` | HUD EXP digits (fallback) | `u = bh / 9` (bracket height) | ok, scale-free |
| `invgrid.py:56-72` | inventory slots | `s`, then the grid resized to the 1200 size | ok in the size test |
| `hudnative.py`, `quickslots.py`, `notices.py` | HUD level/EXP, quick slots, corner lines | the game's own 768 px pixels (`native.View`) | ok: size-free by design; `hudnative` also tries the unstretched frame |
| `reader.py:199` | someone else's shop above your store notice | bare 400 / -700 px | not scaled (F11) |
| `reader.py:1168` | margin round a tooltip's navy | bare 20 px | ok: a frame-pixel margin for OCR |
| `sniper.py:1057` | tooltip search pad | `160 * h / 1200` | ok |
| `sniper.py:983-991, 1071-1074` | route strip, tooltip price cards on screen | client corner + frame position | **wrong in full screen with bars (F1)** |

### Hypotheses
| id | verdict | evidence |
|---|---|---|
| H1 one scale for all | Holds while the game stretches its 768 px picture: reader, anchors and invgrid agree on `h/1200`; the native readers are size-free; hudexp and the store measure their own. Fails when the game draws unstretched (F10). | `reader.py:1410`, `anchors.py:198`, `hudnative.py:60-68`, probe on `myshop_ui73` |
| H2 bars trimmed before `s` | Holds for reading: `grab_game` trims and every `s` comes from the cut frame (2-4 px of kept edge, < 0.3 %). PIL's `crop`/`resize` copy `info`, but no reader hands a crop to `native`. **The cut's offset is lost for drawing (F1).** | `capture.py:145,293`, `native.py:219-221`, `sniper.py:1071-1074` |
| H3 rounding | `int()` truncation on scaled offsets is everywhere. Reads change with the sub-pixel place (pillarbox vs a plain 1440 window differ: F6, F9). No single bad rounding found; the misreads are OCR at small or blurred sizes. | both new test files |
| H4 width rules | `frame.width * 0.5` (`reader.py:985`) and `height * 0.92/0.12` scale with the trimmed picture; fine at 16:9 and 16:10. | code read |
| H5 DPI | The app sets `SetProcessDpiAwareness(2)` = Per-Monitor **v1** (not v2 as this plan said). `client_box`/`window_bounds` are physical pixels then, and the overlays follow `dpi_scale(game)`. Can't be proven off-screen: live check below. | `sniper.py:45`, `window.py:23`, `overlay_art.py:53-67` |
| H6 learned titles | At 1200 the game's own cursor over a title doesn't break the match (0.94-0.97), so nothing bad is learned there. Learning is keyed on height only: a title learned with the game unstretched at 1080 is used with it stretched at 1080 too (part of F10). No expiry, no score check. | probe of `place_by_picture` with a cursor over the stat title at 4 spots |
| H7 constants at one size | invgrid, quick slots and HUD hold at 1050-1600 in the size test (the last two are native, size-free). | `tests/test_scale_invariance.py` |
| H8 `MIN_HEIGHT` | Still earns its keep: 1050-1080 is where most size-test misses are (F5). Not a bug. The gate measures the frame, not the UI: the game drawn unstretched at 1080 passes it with UI as small as at 768 (F10). | size test |
| H9 game rules | Hold on every case with a stat window (lv 32: 30+142+4+4+0 = 180 = 5x32+20). The edge test breaks it (32+152+4+4 = 192): **the rule would have caught F2.** | cases, F2 test |

### Invariance
Every 1920 x 1200 case redrawn at 1050, 1080, 1440 and 1600 through `casekit.resample` (the stretch model; its round trip is within 0.07-0.15 levels on real cases): **56 of 180 field checks differ** from the 1200 read. Each is a strict xfail in `tests/test_scale_invariance.py::KNOWN`, named by finding.

| F# | case · field | height | got | want |
|---|---|---|---|---|
| F3 | player_shop · shop.list | 1080, 1440 | Earring INT Scroll **1,311,000** | 131,000 |
| F4 | player_shop · shop.seller | 1050 / 1440, 1600 | "O U U r bWeeC" / None | the seller's name |
| F4 | player_shop · shop.list | 1050 / 1600 | a row lost / the shop not found | 3 rows |
| F4 | player_shop_soldout · shop.kind | all four | None (not found) | player |
| F5 | fm_quest_window, fm_tooltip, fm_title_glued · stat.* | 1050, 1080 | None (window not found) | your name, 32, 30, 142, 0, 72, ... |
| F6 | fm_quest_window · map.street/name | 1080, 1440 | None | Hidden Street / Free Market <7> |
| F6 | minimap_light_bg · map.street | 1050, 1440 | "Victor ia Road" | Victoria Road |
| F6 | skills_1st · map.street | 1080 / 1440 | "Road" / "[ Victoria Road" | Victoria Road |
| F7 | fm_tooltip, hunt_moved_a · helper.list | 1080, 1600 | a need line dropped | all lines |
| F8 | fm_tooltip · stat.name | 1440 | **"ura"** | None (a tooltip covers it) |
| F9 | fm_quest_window · inventory.mesos | 1080 | None | 385973 |
| F9 | fm_quest_window, fm_tooltip · stat.ap | 1440 | None | 0 |
| F9 | skills_1st, skills_hunter · skills.levels | 1050, 1600 | a row lost (Focus / Power Knockback) | all rows |
| F9 | fm_tooltip · quicklook.tooltips | 1600 | [] | Lemon |

Full screen (`tests/test_fullscreen_reads.py`, a case boxed in black at 2560 x 1440 and 1920 x 1440): the capture gives back the picture's size within a pixel; the reads differ in 6 of 8 (F4, F6, F7, F9 again). A window mostly past the right edge reads **STR base 32, DEX base 152** (true 30, 142): F2. A window mostly past the bottom reads no wrong mesos.

**Live check for DPI (Task 5):** the game on the 100 % monitor and Companion on the 125 % one (then the reverse); hover an item and start a route. Expected: the price card's left edge on the tooltip's left edge, the route strip right under the mini map.

### Ranked findings
Ranked by how often a player meets it x how wrong it is (a wrong value shown as true above a blank).

| F# | what the player sees | cause | severity | fix size | status |
|---|---|---|---|---|---|
| F1 | Full screen on a monitor of another shape (a 1920 x 1200 game on 2560 x 1440): tooltip prices and the route strip sit ~127 px left of where they belong | `trim_bars` cuts the bar off and keeps no offset; `sniper` adds only the client corner | high: wrong place, every time | small | xfail |
| F3 | Someone's shop price read 10x (131,000 as 1,311,000) at 1080 and 1440 | OCR on the shop's pixel font at other sizes; the price parse accepts a malformed digit group | high: wrong number | medium | xfail |
| F2 | STR/DEX base taken as the total (32 for 30) when "(30+2)" is covered or off screen | `read_stat` falls back to the total when the bracket doesn't read; nothing checks base + AP = 5 x level + 20 | high: wrong numbers | small | xfail |
| F5 | At 1920 x 1080 / 1680 x 1050, CHARACTER STAT is often not seen at all (stats blank) | windows are found only once OCR's 1x pass reads their title; the whole-frame picture search is for the mini map only | high for 1080 players: blank | medium | xfail |
| F6 | The mini map lost at 1080 and 1440 (and letterbox), or its street read "Road" / "Victor ia Road" | mini map title not found at those sizes; the street text is taken raw from OCR | high: the map drives routes | medium | xfail |
| F7 | Quest Helper drops a need line at 1080 / 1600 / letterbox | OCR at those sizes splits or loses a line | medium: a quest count missing | medium | xfail |
| F10 | With the game drawing unstretched (a graphics setting; `myshop_ui73`), windows are read at s = 0.9 where the UI is ~0.64: HUD job blank, windows likely misplaced | `s = h/1200` assumes the stretched mode | unknown until live pictures: possibly every window field | medium (take the scale from the HUD) | needs the live round |
| F4 | A player shop's seller read as garbage or lost; a sold-out shop not found at any other size | as F3/F7, plus the LEAVE STORE anchor rides on OCR's text height | medium | medium | xfail |
| F8 | A tooltip over the stat window's name: "ura" read as your name at 1440 | the name takes a partial read | medium: a wrong name (check what a name change does to profiles) | small | xfail |
| F9 | Other blanks: mesos at 1080, AP at 1440, a skill row at 1050/1600, a tooltip at 1600 | OCR at those sizes | low: blank | varies | xfail |
| F11 | Your store can be taken for someone else's (or the reverse) at 1440+ | `reader.py:199` distances 400 / 700 px aren't scaled | low | tiny | no test yet |

### False-positive check (2026-11-18)
The size and full-screen tests redraw a 1200 px case; the redraw itself was then put on trial:

- **Redrawn at its own 1200 px**, every case should read as the original. Most do (mean pixel error 0.1-0.2 levels), but the mini map title of `fm_quest_window` is lost and a Quest Helper line of `fm_tooltip` dropped: the un-stretch is off by up to ~70 levels on a few sharp text edges there. `myshop_ui73` breaks entirely: at UI Size 73 % the frame is no plain stretch of a 768 px picture (error p99 45 levels), so the redraw can't model it. The size test now skips any field the redraw already reads otherwise at 1200.
- **Real pictures at other sizes** (`samples/raw/grind/`, 4 at 1920 x 1080 windowed and 1 at 2560 x 1440 windowed; 4 full-screen 2560 x 1440 in `samples/raw/`): CHARACTER STAT found and read at 1080 and 1440, mesos read at 1080, AP read at 1440.
- **`myshop_ui73` is the game's UI Size setting at 73 %** (`reader.py`, own store: "measured on two UI sizes, u = 1.0 and 0.73"), not a different draw mode.

| F# | verdict | evidence |
|---|---|---|
| F1 | **real** | 4 real full-screen pictures: bars cut at x 126, the game from 127.46; the overlays never add it (code) |
| F2 | **real, worse than thought** | real 1080 (`grind/163859`): DEX "157 (147+10)" read as base 157 with nothing covering it; base + AP = 195 ≠ 5 x 33 + 20 = 185 |
| F3 | unconfirmed | the redraw only; no real player shop at 1080/1440 |
| F4 | unconfirmed | as F3 |
| F5 | **false positive (R)** | real 1080 pictures find and read CHARACTER STAT; the redraw's extra blur stops OCR reading its title |
| F6 street | **real** | real 1080 x4: "Victoyia Road"; real 2560 x 1440: "Victor ia Road", "War ning Stl eet"; the same street at 1200 reads right |
| F6 map lost | **false positive** | the redraw loses it at 1200 too |
| F7 | unconfirmed | `fm_tooltip`: false positive (redraw at 1200); `hunt_moved_a` 1080/1600: the redraw only, while real `res_1080` reads the helper |
| F8 | unconfirmed | the redraw only |
| F9 mesos 1080, AP 1440 | **false positive (R)** | real pictures read both |
| F9 skill rows | unconfirmed | the redraw only |
| F10 | plausible, reframed | UI Size below 100 %: the own-store reader takes its scale from the fee notice; the stat window, inventory, mini map and quick look use h/1200 |
| F11 | real (code), low | unchanged |

### Beyond the reader (2026-11-18)
The dashboard was run alone on copies of the data (no screen reading), browsed at 1366 x 640, 1280 x 800 and 960 x 1000; the server, updater, problem report and build were read.

| # | what | evidence | severity |
|---|---|---|---|
| U1 | Opening Companion twice runs two full copies: two overlays on the game, two grind trackers writing one `grind.sqlite`, the second dashboard on port 8766 (Discord connect then refused there) | `hold_single_instance` makes the mutex and never checks `ERROR_ALREADY_EXISTS`; `start_server` moves to the next port | medium: double labels, a split grind log |
| U2 | Go to's town buttons cut their names at half-screen width ("Kerning Cit", "Sleepywoo") | seen at 960 px | low |
| P1 | `build.bat` bundles `discord.json` whenever it's in the folder (it is now); the release rule says public builds never do | `if exist discord.json set DISCORD=...`; `Companion.spec` (git-ignored, unused) also lists it | release risk |

Checked and fine: the API answers this PC only (Host and Origin checked, JSON-only POSTs); every name shown on the dashboard is escaped; the update is checked against the release's size and SHA-256; the problem report leaves out the profile, pictures and Discord identity; no script errors and no page scroll on any tab at the three sizes.

### Live round (2026-11-19, capture desk)
22 shots in `samples/raw/desk/` (sessions 1-6 and 8; session 7, small window, not taken). Read with the reader on `fix/reader-bug-hunt`, three reads like the app. Labels were drawn by the installed v1.4.2, so without PR #56.

| F# | verdict | evidence |
|---|---|---|
| F5 | **real** (reverses the false-positive verdict) | 1920 x 1080 window, stat window with Detail open and inventory beside it: OCR reads its title as "OHRRROTER STAT" (ratio < 78), so `find_windows` drops it and `place_by_picture` only searches around OCR's hints. The same layout at 2560 x 1440 reads in full. All stat fields blank. |
| F3 | **false positive** | real player shop at 1080 and 1440: all four prices read right (5 digits) |
| F4 seller | **real** | the seller's name loses a letter at 1080 and is `None` at 1440 |
| F4b (new) | real, low | the two grayed rows (sold) aren't listed at all at 1080 or 1440; the banded retry only runs when no row read |
| F1 | **real, live** (fix in PR #56, not installed) | full screen 1920 x 1200 on 2560 x 1440: price cards ~125 px left of their tooltip, route strip in the black bar |
| F10 | **real: blank, not wrong** | UI Size "ideal" (UI drawn unscaled at 1200): only the mini map reads; stat, inventory mesos and skills blank |
| F13 (new) | **real: wrong numbers** | full screen 1280 x 720 on a 1440 monitor: the frame is 2560 x 1440, so s = 1.2, but the game's picture is 720 tall (< 768), so the UI is 1440/720 x 0.64 = 1.28. Rows shift by one: LV **138**, DEX **37** (base 32), INT **181** (base 170). At 800 x 600 full screen nothing in the stat window reads. 1024 x 768 and up read right. Needs s from the game's own picture height (`native`), not the frame's. |
| F14 (new) | **real: wrong numbers** | a tooltip over the stat window's lower rows (full screen 1920 x 1080): AP read **60** (the tooltip's "REQ DEX: 60"), LUK **3**. Like F8. The H9 rule (base + AP = 5 x level + 20) would catch it. |
| F15 (new) | real: wrong number, rare | full screen 1920 x 1200, nothing covering: ACCURACY 83 read as **33**. No rule checks ACC. |
| F16 (new) | real, medium | windowed at 100 / 125 / 150 %: the price card's x is right, but over the compare tooltip (and both at 100 %) it's drawn inside the tooltip, over its REQ or stat lines, not under it |
| H5 DPI | **holds** | windowed on the 125 % monitor, the 150 % laptop and the main at 100 %: cards on the tooltips' left edges, route strip under the mini map |
| F6 street | fixed holds | Victoria Road, Hidden Street, Ant Tunnel I (Dungeon) read right; one 1024 x 768 full-screen read lost the street (None, not wrong) |
| F7, F8, F9 skill rows, F11 | still open | no skill window or covered name in a shot that tests them |

### Fixed (2026-11-18)
Reader PR (`fix/reader-bug-hunt`): F1, F2 (and two more found fixing it: a crash when the AP box is wholly off the frame, and a title cut by the frame's edge placing the window a row off), F6 street, F12 (new: ACCURACY never read at real 1080, Windows OCR blank at one box edge; real case `stat_1080_real`). App PR (`fix/app-routes-and-copies`): U1, U2 (+ monster names on hover), P1, and Go to's town-to-town routes always taking the cab (now walking, the cab a button away; Beginners ride first). Still open, waiting for pictures: F3, F4, F7, F8, F9 skill rows, F10, F11.

### Fixed (2026-11-19, live round; plan `2026-11-19-reader-live-round-fixes.md`)
Branch `fix/reader-live-round` (on `fix/reader-bug-hunt`), plus `fix/go-to-arrival` (on `fix/app-routes-and-copies`). Merged together on main: 777 passed, 31 xfailed, 0 failed (6 min on one core, below normal).

| F# | what the player sees now |
|---|---|
| F13 | Full screen below 768 (1280 x 720 on a 1440 monitor, pixels doubled; 800 x 600): stats read on the right rows (LV 38, not 138); the HUD level reads too. `native.measure` tells the game's own picture height from the HUD band; every reader's `s` follows it |
| F10 | UI Size ideal: stat window and inventory read (found by title picture; OCR can't read titles at 0.64). Skill points still blank there (SKILL INVENTORY's title too like ITEM INVENTORY's) |
| F5 | 1920 x 1080 with the stat title misread ("OHRRROTER STAT"): found by its title picture every third read; every stat reads. 15 size-test xfails flipped |
| F15 | ACCURACY 83 no longer read 33: the Detail panel isn't always at the same place beside the stat window (9 game px nearer in one picture); its box follows the panel's label edge |
| F16 | Price cards go under the tooltip: its bottom follows its own text lines (sky behind passes the navy test, a light row broke the old walk) |
| F14, F8 | A stat value 70 %+ under a tooltip is left out (AP read "60" from "REQ DEX: 60"); a name 20 %+ covered too ("ura") |
| F4 | A player shop's seller read at 1440 (button offsets at the UI's scale, not OCR's text height). 6 shop size-test xfails flipped |
| trust | The HUD's exact level wins over a stat window that disagrees |
| Go to | Arriving ends the route: walking on no longer re-plans back to the destination |

Still open: F4 seller loses a letter at 1080 (OCR); F4b sold rows not listed; F7, F9 skill rows, F11; session 7 (small window); UI Size 73 % unconfirmed.
