# Reader live-round fixes — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix what the 2026-11-19 live round showed: wrong numbers and blank windows at full screen below 768, at UI Size "ideal", at 1920 x 1080, under tooltips, and the price card drawn inside a tooltip. Each fix comes with a test on a real picture.

**Architecture:**
- The UI scale `s` is measured, not assumed. The game draws its UI 1:1 on its own picture, and that picture is one of three things:
  - 768 tall, stretched smoothly (the usual);
  - 720 or 600 tall, stretched by the monitor in full screen;
  - not stretched at all (UI Size "ideal").
- `native.measure` tells these apart from the HUD's bottom strip, and every reader takes `s = (h / nh) × 768 / 1200` from it.
- The other fixes are small and local:
  - a whole-frame search for window titles OCR misread;
  - a wider Detail box;
  - a sturdier tooltip bottom;
  - stat cells under a tooltip left blank;
  - the HUD's exact level beating the stat window's;
  - the shop's button offset taken from `s`.

**Tech Stack:** Python 3, Pillow, numpy (no OpenCV), Windows OCR, pytest.

**Spec:** `docs/superpowers/plans/2026-11-18-reader-bug-hunt.md`, section **Live round (2026-11-19)** (F5, F10, F13, F14, F15, F16, F4). The measurements behind each task are under "Evidence" in that task.

## Global Constraints

- **One core, low priority.** Every Python run that loads numpy or OCR (tests, probes, the desk) has `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1` set before numpy loads, and runs at idle or below-normal priority. Multi-core runs froze the player's PC.
- **Branch.** Create `fix/reader-live-round` from `fix/reader-bug-hunt` (PR #56, open; this builds on its F1/F2/F12 code). If #56 is merged first, branch from `origin/main` instead.
- **Running tests.** Run them from `classic/companion` with `python -I -m pytest -q -W error::DeprecationWarning`. The baseline must pass before Task 1.
- **Locale and output.** This PC's locale is cp1255. Open files with `encoding="utf-8"`, and call `sys.stdout.reconfigure(encoding="utf-8")` before printing non-ASCII.
- **Pictures stay local.** The repo is public:
  - test pictures live only in git-ignored `samples/cases/` (made with `tools/make_case.py`, which masks everything outside `--keep`);
  - sources are in git-ignored `samples/raw/desk/`;
  - no other player's name or chat goes in a case picture, test file, commit or PR text.
- **No game input.** Never send input to the game.
- **Pictures, deletes, merges.** Take new pictures only when the player says go. Ask before deleting pictures. Ask before merging.
- **One fix group per commit**, and one PR for the plan. Releases are patch versions; public builds never include `discord.json`.
- **Scale constants.** `REF_HEIGHT = 1200` and `NATIVE_H = 768` stay as they are. Today's behaviour (`s = h / 1200`) is exactly the 768-smooth case of the new rule, so every existing case must still read the same.

## Review Focus

1. **Same frame size, other mode.** UI Size switched between normal and "ideal" at 1920 x 1200, with no size change. Expected: `s` follows by the next read, with no stale result cached by frame size. *(Task 2 test.)*
2. **A HUD strip with nothing to measure** (a black loading screen, a map change). Expected: `measure` returns the usual `Stretch(768, False)` (or `h` when `h ≤ 768`), never a wild height. *(Task 2 test.)*
3. **A small window** (≤ 768 tall, session 7 not yet taken). Expected: `measure` says unstretched, so `s = 0.64`, and `MIN_HEIGHT` still gates reading as today. *(Task 2 test, on a synthetic 1280 x 720 frame.)*
4. **Learned titles from before the update** in `cache/titles/<height>/`. Expected: ignored, and learned again per scale; never used at a different scale. *(Task 3 test.)*
5. **A false window from the whole-frame search** (title-like text elsewhere). Expected: no case without a stat window gains one. *(Task 4 test.)*

---

### Task 1: One core and low priority for the desk and the tests

**Files:**
- Modify: `tools/capture_desk.py` (top, before any import that loads numpy)
- Modify: `tools/desk_check.py` (top)
- Modify: `tests/conftest.py` (after the thread lines)

- [ ] **Step 1:** In `capture_desk.py` and `desk_check.py`, set the three thread variables with `os.environ.setdefault` (as `tests/conftest.py` does) before any other import. `capture_desk.py` also lowers its own priority to `BELOW_NORMAL_PRIORITY_CLASS` (`0x4000`) via `ctypes.windll.kernel32.SetPriorityClass`.
- [ ] **Step 2:** In `tests/conftest.py`, lower the test process to `BELOW_NORMAL_PRIORITY_CLASS` on Windows.
- [ ] **Step 3:** Run the full suite, and write its time in the commit message. Expected: all pass. Compare with the last time in the bug-hunt plan's Baseline (~4 min).
- [ ] **Step 4: Commit:** `chore(tools): the desk and the tests run on one core at low priority`

### Task 2: The game's own picture height (`native.measure`)

**Evidence:** probe of 2026-11-19, rows of the HUD band, the smooth fit's mean error per candidate height:

| frame | 600 | 720 | 768 | true |
|---|---|---|---|---|
| 1920 x 1080 window, 1920 x 1200 window, 2560 x 1440 full screen at 1920 x 1080 / 1366 x 768 / 2560 x 1440 | ~10 | ~6.5 | **0.06–0.09** | 768 |
| 1024 x 768 full screen (1922 x 1440 after bars) | 10.8 | 6.2 | **1.00** | 768 |
| 800 x 600 full screen (1920 x 1440 after bars) | **2.03** | 4.60 | 3.80 | 600 |
| UI Size "ideal", 1920 x 1200 window | 21 | 18 | 16.6 (no minimum) | 1200, unstretched |

- 1280 x 720 full screen on 2560 x 1440 isn't smooth: every pixel is doubled. In the HUD band, rows differing from the row above make up 0.497 of rows (columns 0.500); every other picture gives 1.000.

**Files:**
- Modify: `native.py` (new `Stretch`, `measure`, `ui_scale`; `game_view` and `_native` use them)
- Test: `tests/test_native.py`
- Cases (local): `fs720_stat`, `fs600_hud`, `ui_ideal`

**Interfaces:**
- Produces:
  - `native.Stretch`, a `NamedTuple(nh: int, nearest: bool)`;
  - `native.measure(frame) -> Stretch`;
  - `native.ui_scale(frame) -> float`;
  - `native.View`, which gains the attribute `nearest: bool` and passes it to `_native`.
- `measure` reads the game area from `frame.info[AREA]` when it's there, else the whole frame, as `game_view` does.

- [ ] **Step 1: Make the cases.** Use `tools/make_case.py` with `--job Hunter`. Every case keeps the HUD's bottom band, `(0, h - round(0.04 * h), w, h)`, which `measure` reads (the status bar only, not the chat line above it).
  - `fs720_stat` from `samples/raw/desk/20261119_172332_2560x1440_fullscreen-1280x720.png`. Keep the stat window with Detail, plus the band. Expect: `stat.level` 38, `stat.str_base` 32, `stat.dex_base` 170, `stat.ap` 0, `stat.acc` 83, `hud.level` 38.
  - `fs600_hud` from `…_172101_1920x1440_fullscreen-800x600.png`. Keep the band only. No field expectations (`"expect": {}`).
  - `ui_ideal` from `…_171644_1920x1200_ui-size-ideal.png`. Keep the stat window with Detail, the inventory, the skill window, the mini map and the band. Expect: `stat.level` 38, `stat.str_base` 32, `stat.dex_base` 170, `stat.ap` 0, `stat.acc` 83, `inventory.mesos` 1192122, `skills.sp` 0.
  - `map_ant1200` from `…_172952_1920x1200_map-anttunnel1.png`. Keep the mini map and the band. Expect: `map.name` Ant Tunnel I, `map.street` Dungeon, `stat.level` null.
  - Check each expected value by eye against the picture.
  - Add `case_frame(name) -> Image.Image` to `tests/conftest.py`. It returns the case's picture as RGB, or calls `pytest.skip` when the case isn't there.
- [ ] **Step 2: Write the failing tests** in `tests/test_native.py`. They skip when a case is missing, as `test_cases.py` does.

```python
@pytest.mark.parametrize("case,want", [
    ("fs720_stat", native.Stretch(720, True)),
    ("fs600_hud", native.Stretch(600, False)),
    ("ui_ideal", native.Stretch(1200, False)),
    ("stat_1080_real", native.Stretch(768, False)),
    ("stat_1440_real", native.Stretch(768, False)),
])
def test_measure_real(case, want): assert native.measure(case_frame(case)) == want

def test_ui_scale_values():
    assert native.ui_scale(case_frame("fs720_stat")) == pytest.approx(1.28, abs=0.005)
    assert native.ui_scale(case_frame("ui_ideal")) == pytest.approx(0.64, abs=0.005)
    assert native.ui_scale(case_frame("stat_1080_real")) == pytest.approx(0.9, abs=0.001)

def test_measure_follows_mode_at_one_size():          # Review Focus 1
    assert native.measure(case_frame("ui_ideal")).nh == 1200
    assert native.measure(case_frame("map_ant1200")).nh == 768

def test_measure_blank_band():                        # Review Focus 2
    assert native.measure(Image.new("RGB", (1920, 1200), (20, 20, 20))) == native.Stretch(768, False)
    assert native.measure(Image.new("RGB", (800, 600), (20, 20, 20))) == native.Stretch(600, False)

def test_measure_small_window():                      # Review Focus 3
    f = case_frame("fs720_stat").resize((1280, 720), Image.NEAREST)   # the game's own 720 picture
    assert native.measure(f) == native.Stretch(720, False)
    assert native.ui_scale(f) == pytest.approx(0.64, abs=0.005)

def test_native_nearest_hud_level():
    assert hudnative.read_level(case_frame("fs720_stat")) == 38
```

- [ ] **Step 3:** Run `python -I -m pytest -q tests/test_native.py`. Expected: FAIL (`measure` isn't defined).
- [ ] **Step 4: Implement `measure(frame) -> Stretch`** on the HUD band, the bottom `HUD_BAND` of the game area:
  1. **Doubled pixels.** `f` is the share of the band's rows that differ from the row above (full width, any pixel). If `f < 0.9`, return `Stretch(nh, True)`, where `nh` is the candidate in `(600, 720, 768)` within 3 % of `round(h * f)`. If none is that close, fall through to step 2.
  2. **Smooth fit.** For each candidate `n` in `(600, 720, 768)` with `n < h`, take the mean error of rebuilding the band through `_stretch` at `n`. Use `_width`'s method on one strip: 240 columns starting at 63 % of the width, with the pseudo-inverses cached per `(frame size, n)` by `lru_cache`. Take the smallest error `e`. If `e < 3.0` and `e < 0.7 ×` the next smallest, return `Stretch(n, False)`.
  3. **Otherwise** return `Stretch(h, False)` (unstretched), or `Stretch(768, False)` when the band has no contrast (standard deviation < 4).
  4. **No size cache.** Nothing is cached by frame size alone: the smooth fit is a few small products per call. Check by timing: a call takes under 20 ms on one core at 2560 x 1440.
  5. **Re-measure before pinning.** The 3.0 / 0.7 / 0.9 thresholds come from the probe above, which used a taller band. Re-run the probe on the 4 % band, for both the raw desk pictures and the masked cases, and set each threshold midway in the gap it finds. Write the numbers you measured in the commit message.
- [ ] **Step 5: Implement `ui_scale(frame) -> float`** as `h / nh * NATIVE_H / 1200`, where `h` is the game area's height. Make `game_view` build its `View` from `measure` (`nh`, plus `nw` from `_width` as now; `nearest` from `measure`). When `nearest`, `_native` takes each game pixel as the frame pixel at its centre (`floor((i + 0.5) * h / nh)`), with no least squares.
- [ ] **Step 6:** Run `tests/test_native.py`, then the full suite. Expected: all pass.
- [ ] **Step 7: Commit:** `feat(native): measure the game's own picture height (768 stretched, 720/600 full screen, unstretched)`

### Task 3: Every reader takes `s` from `native.ui_scale` (F13, F10)

**Evidence:**
- At 1280 x 720 full screen, `s = 1440 / 1200 = 1.2` where the true value is 1.28. Every stat row shifts by one: LV **138**, DEX **37**, INT **181**. `trust._level` would save 138 after `LEVEL_READS` identical reads.
- At UI Size "ideal", `s = 1.0` where the true value is 0.64, so only the mini map reads.

**Files:**
- Modify: `reader.py`. The scale is taken at lines 1197, 1377, 1442, 1558, 1585 and 1598 (`frame.height / REF_HEIGHT`). Also `find_windows` (new `s` parameter).
- Modify: `anchors.py` (`template`, `learn`, the `_sized` key, and the learned folder)
- Modify: `sniper.py:1066` (tooltip pad)
- Test: `tests/test_cases.py` (the new cases run through it as-is), `tests/test_anchors.py`

**Interfaces:**
- Consumes: `native.ui_scale(frame) -> float` (Task 2).
- Produces:
  - `reader.find_windows(lines, height, s)`;
  - `anchors.Titles.template(name, s)`;
  - `anchors.Titles.learn(frame, name, line, s)`;
  - learned titles in `cache/titles/s<round(s*1000)>/<name>.png`.

- [ ] **Step 1: Write the failing tests.**
  - `fs720_stat` and `ui_ideal` already run in `test_cases.py::test_case_field` through their `expect`. Run them now. Expected: FAIL (LV 138; the `ui_ideal` stat is blank).
  - Add to `tests/test_anchors.py`:

```python
def test_learned_title_keyed_by_scale(tmp_path):      # Review Focus 4
    t = anchors.Titles(tmp_path, res_dir=APP)
    old = tmp_path / "cache" / "titles" / "1200" / "stat.png"
    old.parent.mkdir(parents=True); Image.new("L", (10, 3)).save(old)
    assert t.template("stat", 1.0).shape != (3, 10)                # an old height-keyed title is never used
    f = case_frame("stat_1080_glued")                                # made in Task 4; skips until then
    line = t.find(f, 0.9, full={"stat"}, names={"stat"})["stat"]
    t.learn(f, "stat", line, 0.9)
    assert (tmp_path / "cache" / "titles" / "s900" / "stat.png").exists()
    assert t.template("stat", 1.0).shape != t.template("stat", 0.9).shape
```

- [ ] **Step 2: Implement.**
  - `Reader.read` takes `s = native.ui_scale(frame)` once and passes it on everywhere `frame.height / REF_HEIGHT` is used today.
  - `find_windows` gets `s` for its shop-button offset (used in Task 9; until then the signature only).
  - `anchors` keys `_sized` and the learned folder on `round(s * 1000)`, never on the frame height.
  - `sniper.py:1066` uses `native.ui_scale(frame)`.
  - If a `ui_ideal` field still doesn't read at `s = 0.64`, because the 1x OCR pass can't read text that small, don't chase it here. Mark that field `xfail(strict=True, reason="F10-ocr")` and list it in the PR.
- [ ] **Step 3:** Run the full suite. Expected: all pass. `fs720_stat` reads LV 38, STR base 32, DEX base 170. Every older case reads as before.
- [ ] **Step 4: Commit:** `fix(reader): windows read right in full screen below 768 and at UI Size ideal`

### Task 4: Find a window by its title picture when OCR misreads the title (F5)

**Evidence:**
- 1920 x 1080 window, stat window with Detail open and the inventory beside it. OCR reads the title as `'OHRRROTER STAT'`, so `find_windows` drops it.
- `Titles.find(..., full={"stat", "inventory", "skills"})` on that frame finds stat at (759, 130), score 0.867, in 0.20 s on one core.

**Files:**
- Modify: `reader.py`, `Reader.place_by_picture` (the `full` set)
- Test: `tests/test_cases.py` (new case), `tests/test_anchors.py`
- Case (local): `stat_1080_glued`

- [ ] **Step 1: Make the case** `stat_1080_glued` from `samples/raw/desk/20261119_171021_1920x1080_res-1080-all.png`. Keep the inventory, the stat window with Detail, and the HUD band. Expect: `stat.name` Tura1, `stat.level` 38, `stat.exp` 136260, `stat.str_base` 32, `stat.dex_base` 170, `stat.ap` 0, `stat.acc` 83, `inventory.mesos` 1192122.
- [ ] **Step 2: Write the guard test** in `tests/test_anchors.py`:

```python
@pytest.mark.parametrize("name", ["map_ant1200", "fs600_hud"] +
                         [n for n, c in CASE_LIST.items() if "stat.level" in c["expect"] and c["expect"]["stat.level"] is None])
def test_whole_frame_search_adds_no_window(seen_case, name):   # Review Focus 5
    assert not seen_case(name).get("stat")
```

  Put it in `tests/test_cases.py`, beside the `seen_case` fixture it uses.

  Run it with the case's test. Expected: the case FAILS (stat blank); the guard passes.
- [ ] **Step 3: Implement.** On the reads where `place_by_picture` already searches the whole frame for the mini map (`self.reads % 3 == 1`), `full` also holds every `KEPT` window that has a title picture in `self.titles.boxes` and is in neither `wins` nor `self.titles.last`.
- [ ] **Step 4:** Run the full suite. Expected: all pass.
- [ ] **Step 5: Commit:** `fix(reader): the stat window is found by its title picture when OCR misreads the title`

### Task 5: The Detail box starts before the first digit (F15)

**Evidence:**
- Full screen 1920 x 1200, after bars 2308 x 1440. ACCURACY 83 was read as **33** with nothing covering it.
- The Detail box's left edge is at `x + 388 * s`. Along the ACCURACY row, in game units from the placed title: the blue label cell ends at ~375, the value's first digit starts at ~382.5, so the box cuts into the digit.
- `trust` saves any ACC ≤ 40 + 6 × level, so 33 would be saved.

**Files:**
- Modify: `reader.py`, `read_stat`'s Detail box
- Test: `tests/test_cases.py` (new case)
- Case (local): `acc_fs1200`

- [ ] **Step 1: Make the case** `acc_fs1200` from `samples/raw/desk/20261119_172548_2308x1440_fullscreen-1920x1200.png`. Keep the stat window with Detail and the HUD band. Expect: `stat.level` 38, `stat.acc` 83.
- [ ] **Step 2:** Run it. Expected: FAIL (33 or None).
- [ ] **Step 3: Measure, then fix.** On every case with an expected `stat.acc`, measure from the placed title x: the label cell's right edge, and the first digit's left edge. Use the gap's midpoint (about 379) as the box's left offset. Fix it at the smallest digit gap found, and write the measured numbers as a comment beside the offset.
- [ ] **Step 4:** Run the full suite. Expected: all pass, and every `stat.acc` expectation still holds.
- [ ] **Step 5: Commit:** `fix(reader): ACCURACY's first digit isn't cut off`

### Task 6: A tooltip's bottom where it really ends (F16)

**Evidence:**
- Full screen 1920 x 1080 frame `…_172442_2560x1440_fullscreen-1920x1080.png`. `read_tooltips` gives Blue Jean Shorts a bottom of 658 (true ≈ 822) and Green Legolier Pants a bottom of 666 (true ≈ 880).
- `depth()` walks down only 4 columns: 3 at the right edge and 1 at the left border. It stops at a gap of 10 × s. The job-name row (~20 game px at s 1.2) and a chat bubble under the right edge both break it. The price card is drawn at `box[3]`, inside the tooltip.

**Files:**
- Modify: `reader.py`, `read_tooltips` (`depth` and the columns it's taken on)
- Test: `tests/test_hovered.py` (or whichever file already tests `read_tooltips`; add there)
- Case (local): `tips_fs1080`

- [ ] **Step 1: Make the case** `tips_fs1080` from the frame above. Keep both tooltips whole, plus the stat window and the HUD band. Then paint the chat bubble's text with the bubble's own fill colour, so its white block stays (it's what breaks the measure) but no chat does.
  - Measure the true boxes by eye and write them in the case JSON as `"tips": [{"name": ..., "left": ..., "bottom": ...}]`. They're about Blue Jean Shorts left 1168, bottom 822, and Green Legolier Pants left 1615, bottom 880.
  - Expect for the stat: `stat.str_base` 32, `stat.dex_base` 170, `stat.ap` null, `stat.int` null, `stat.luk` null. Those three rows are under a tooltip; Task 7 fixes them.
- [ ] **Step 2: Write the failing test:**

```python
def test_tooltip_boxes_real_fs1080(game_reader):
    case = load_cases()["tips_fs1080"]; f = case_frame("tips_fs1080")
    got = {t["name"]: t["box"] for t in game_reader.look_for_tooltips(f, [0, 0, f.width, f.height])}
    for want in case["tips"]:
        assert abs(got[want["name"]][0] - want["left"]) <= 4
        assert abs(got[want["name"]][3] - want["bottom"]) <= 6
```

  Run it. Expected: FAIL (bottoms 658 / 666).
- [ ] **Step 3: Implement.**
  - `depth` allows a gap of `26 * s` (the job row plus a margin; a tooltip's own gaps are never taller).
  - It's taken on 7 columns evenly across the title's own span (`x .. x + w`, always inside the tooltip, away from what lies beside it), plus the existing `left + 4 * s`.
  - The bottom is the **second** deepest of these, so one column running on into navy below can't carry the box down.
- [ ] **Step 4:** Run the full suite. Expected: all pass, and every existing tooltip test is unchanged.
- [ ] **Step 5: Commit:** `fix(reader): a tooltip's price card goes under the tooltip, not over its text`

### Task 7: A stat cell under a tooltip is left blank (F14)

**Evidence:** in `tips_fs1080`, a tooltip covers the INT, LUK and AP rows. AP was read as **60** (the tooltip's "REQ DEX: 60") and LUK as **3**. `trust` didn't save them only because LUK's base was missing.

**Files:**
- Modify: `reader.py` (new `covered`; `read_stat` uses it)
- Test: `tests/test_cases.py` (case `tips_fs1080` from Task 6)

**Interfaces:**
- Produces: `reader.covered(frame, box) -> bool`. True when ≥ 20 % of the box's pixels pass `_tip_navy`.

- [ ] **Step 1:** Run `tips_fs1080`'s stat fields. Expected: FAIL (`stat.ap` 60, `stat.luk` 3).
- [ ] **Step 2: Implement `covered`.** In `read_stat`:
  - each of str/dex/int/luk whose value cell (`x + 76*s .. x + 230*s`, its row's `STAT_ROWS` y ± 9·s) is covered gets total and base `None`;
  - the AP box, when covered, gives `ap = None`;
  - each Detail row (`DETAIL_ROWS`, the Detail box's x range), when covered, gives `None`.
- [ ] **Step 3:** Run the full suite. Expected: all pass. The stat cases with no tooltip keep every field.
- [ ] **Step 4: Commit:** `fix(reader): no stat read through a tooltip covering it`

### Task 8: The HUD's exact level beats the stat window's

**Evidence:** a systematic misread repeats on every read, so `trust._level`'s repeat rule lets it through (F13's LV 138 would have been saved). `hudnative` reads the HUD level from the game's own sprites, exactly (`hud.level_exact`).

**Files:**
- Modify: `trust.py`, `_level`
- Test: `tests/test_gate.py`

- [ ] **Step 1: Write the failing test:**

```python
def test_exact_hud_level_beats_stat_window():
    g = <a Gate built the way test_gate.py's other tests build theirs>
    # one change only: _level is given hud.level when hud.level_exact and it differs from stat.level
    seen = {"stat": {"name": "Tura1", "level": 138}, "hud": {"level": 38, "level_exact": True}}
    outs = [g.check({"name": "Tura1", "level": 37}, seen) for _ in range(10)]
    assert all(o.get("level") in (None, 38) for o in outs) and any(o.get("level") == 38 for o in outs)
```

- [ ] **Step 2:** Run it. Expected: FAIL (138 gets through).
- [ ] **Step 3: Implement.** In `_level`, when `hud.level_exact` and `hud.level` differ from `stat.level`, the HUD's level is the one read.
- [ ] **Step 4:** Run the full suite. Expected: all pass.
- [ ] **Step 5: Commit:** `fix(trust): the HUD's exact level wins over a stat window that disagrees`

### Task 9: A player shop's buttons placed by `s` (F4 at 1440)

**Evidence:**
- Real shop at 2560 x 1440: only SELLER INFO read, with OCR text height 17. `find_windows` puts LEAVE STORE `80 * (17 / 12) = 113` px under it, where the true distance is `80 * 1.2 = 96`. The seller box lands 17 px low, so the seller is `None`.
- Prices read right at 1080 and 1440 (F3 was a false positive).

**Files:**
- Modify: `reader.py`, `find_windows` (the `SHOP_BUTTONS` offset)
- Test: `tests/test_cases.py` (new case)
- Case (local): `shop_1440_real`

- [ ] **Step 1: Make the case** `shop_1440_real` from `samples/raw/desk/20261119_171131_2560x1440_res-1440-shop.png`. Keep the shop window, without the chat pane on its right. Expect:
  - `shop.seller`: the seller's name as shown (in the local case JSON only, never in a test file or commit);
  - `shop.list`: the four rows the reader gives today (the prices are right).
- [ ] **Step 2:** Run it. Expected: FAIL (`shop.seller` is None).
- [ ] **Step 3: Implement.** The button offset uses the `s` passed in (Task 3), not `ln[4] / 12`. `read_shop`'s seller box is unchanged.
- [ ] **Step 4:** Run the full suite. Expected: all pass, including the older shop cases.
- [ ] **Step 5: Commit:** `fix(reader): a player shop's seller read at 1440`

### Task 10: Build, check on the real game, PR

- [ ] **Step 1:** Run the full suite once more. Write its count and time in the bug-hunt plan's Findings → Fixed, with a line per F#.
- [ ] **Step 2: Build and smoke-run the exe.** Build with `build.bat --no-pause` (by full path, from a scratch clone without `discord.json`). Run it from `dist` with `--no-update --no-browser --second-copy`, beside the installed copy. Expected: it starts and reads a frame without errors in `logs/`.
- [ ] **Step 3: Live check, only when the player says go.** Re-run the desk's session 6 at 1280 x 720 and session 4 (UI Size), plus one hover over the stat window. Expected:
  - LV 38, STR/DEX bases 32/170, and ACC 83;
  - no AP under a tooltip;
  - price cards under the tooltips.
- [ ] **Step 4:** Open the PR `fix/reader-live-round` into `fix/reader-bug-hunt`, or into `main` if #56 is merged. List each F# with what the player sees now and any `F10-ocr` xfail. Ask the player before merging.
- [ ] **Step 5:** Update the memory entry `companion-reader-accuracy.md`.

## Not in this plan

- **F4, 1080:** the seller name loses a letter (OCR).
- **F4b:** grayed (sold) shop rows aren't listed.
- **Pictures still needed:** F7 Quest Helper lines, F9 skill rows, F11, and session 7 (small window, ≤ 768). Session 7 only makes sense after Task 3, and opening `MIN_HEIGHT` for it is a separate decision for the player.
- **Other UI Size values (e.g. 73 %).** The model (UI 1:1 on an unstretched picture) predicts 0.64 × 1200 / h, but only "ideal" has a real picture.
