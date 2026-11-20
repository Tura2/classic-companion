# A lighter Companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Companion takes less of the PC while you play, and almost nothing while you're away, with every read as good as before.

**Architecture:** Four independent changes:
- a cheaper picture per captured frame (`app/capture.py`);
- below-normal priority for the whole app (`companion.py`);
- a slow pace while you're away from the game (`app/sniper.py` timers, plus the capture's frame rate);
- Cozy prices refreshed at a pace a pass can actually keep (`app/cozy.py`).

**Tech Stack:** Python 3, Pillow, numpy, windows_capture (WGC), pytest.

**Spec:** the measurements below, from 2026-11-20 (Companion 1.4.5 installed, game windowed 1920×1200, Tura1 grinding).

## Measurements (what this plan fixes)

**Live:**
- Companion used ~19% of one core, steadily: 8,085 CPU-s since 00:40, about as much as MapleStory since yesterday 17:07 (8,852 CPU-s).
- It runs at Normal priority, the same as the game. 264 MB of memory, 30 threads.

**Each step on one real frame**, CPU time on one core (`time.process_time`):

| step | cost | how often | core share |
|---|---|---|---|
| WGC frame → RGB picture (`on_frame_arrived`) | 20–25 ms | 7 a second, always | **~14%** |
| full read (`reader.read`) | 191 ms | every ~1.7 s | ~11% |
| tooltip check (`navy_mask`) | 7 ms | 7 a second, game in front | ~5% |
| corner + quick slots | 9 ms | 2.5 a second | ~2% |
| mini map only | 5.5 ms | ~1.3 a second | ~1% |

**Findings:**
- **The frame conversion** does a numpy fancy-index copy, then `tobytes()`, then `convert("RGB")`. Pillow's raw `BGRX` decoder makes the same pixels in **7 ms** instead of 25 ms (checked byte for byte).
- **Nothing slows down while you're away.** The game was open all night, and the full read ran every 1.5 s and the capture at 7 fps the whole time.
- **Cozy never stops fetching.**
  - `EVERY_HOURS = 2`, but a pass at one page a second takes ~4.7 h (1,459 pages in 281 min). Each pass ends with every price already over 2 h old, so the next starts 10 minutes later: 00:41→05:21, 05:31→10:17, 10:27→…
  - The 149 pages that fail are retried on every pass (`wanted` always wants a failure), 3 tries each.

## Global Constraints

- Reads must stay exactly as good: the same pixels, the same read cadence while grinding with the game in front or behind the dashboard, and tooltips 7 times a second when the game is in front.
- Run tests with the repo's `tests/conftest.py`: `python -m pytest <files> -q -p no:cacheprovider` from `classic/companion`. Every benchmark runs one-threaded at idle priority.
- Work on a branch `perf/lighter-companion` off `main`. No release in this plan.

## Review Focus

- **Grinding with the dashboard in front** (game not in front, EXP coming in) must stay at full pace. "Away" needs no EXP for 5 minutes as well. → Task 3, `test_grinding_behind_the_dashboard_is_not_idle`.
- **Coming back after being away:**
  - a click into the game puts the full pace back on the next tick;
  - the first kill's EXP still counts, read within ~5 s at worst.
  → Task 3, `test_back_in_front_is_not_idle`.
- **A shop open** (yours or another's) keeps its own fast pace, idle or not. → Task 3, `test_an_open_shop_is_never_idle`.
- **A frame whose rows are padded** (WGC's buffer wider than the window): the picture must still be the window's size. → Task 1, `test_padded_rows_keep_the_frame_size`.
- **Failed Cozy pages with no fetch time** (rows written by older versions): fetched on the next pass, not never. → Task 4, `test_an_old_failure_without_a_time_is_fetched`.

---

### Task 1: One cheap copy per captured frame

**Files:**
- Modify: `app/capture.py` (`on_frame_arrived` inside `GameCapture._start`)
- Test: `tests/test_capture_frame.py` (new)

**Interfaces:**
- Produces: `capture.frame_to_rgb(buf: numpy.ndarray, width: int, height: int) -> PIL.Image.Image`. `buf` is WGC's `(h, w', 4)` BGRA array; the result is RGB `width × height`.

- [ ] **Step 1: Write the failing tests:**
  - `test_same_pixels_as_before`: a random `(120, 200, 4)` uint8 BGRA array; `frame_to_rgb(buf, 200, 120).tobytes()` equals today's `Image.frombuffer("RGBA", (200, 120), buf[:, :, [2, 1, 0, 3]].tobytes()).convert("RGB").tobytes()`.
  - `test_padded_rows_keep_the_frame_size`: a `(120, 208, 4)` buffer with `width=200` gives a `(200, 120)` picture whose pixels are the first 200 columns.
  - `test_the_picture_owns_its_pixels`: change `buf` after the call; the picture doesn't change.

- [ ] **Step 2: Run them and make sure they fail**

Run: `python -m pytest tests/test_capture_frame.py -q -p no:cacheprovider`
Expected: FAIL with `AttributeError: module 'capture' has no attribute 'frame_to_rgb'`.

- [ ] **Step 3: Implement.**
  - `frame_to_rgb`: `Image.frombuffer("RGB", (w', h), np.ascontiguousarray(buf), "raw", "BGRX", 0, 1)`, cropped to `width` when `w' > width`, then `.copy()` so the picture owns its pixels.
  - `on_frame_arrived` stores `frame_to_rgb(frame.frame_buffer, frame.width, frame.height)`.

- [ ] **Step 4: Run the tests, then a timing**

Run: `python -m pytest tests/test_capture_frame.py tests/test_capture_area.py -q -p no:cacheprovider`
Expected: all pass. A 1936×1240 frame then converts in ≤ 10 ms CPU, measured with `time.process_time` one-threaded.

- [ ] **Step 5: Commit**

```bash
git add app/capture.py tests/test_capture_frame.py
git commit -m "perf(capture): one copy per frame with Pillow's BGRX decoder (25 ms -> 7 ms, same pixels)"
```

### Task 2: The game comes first

**Files:**
- Modify: `companion.py` (`main`, near the thread settings at the top)
- Test: `tests/test_priority.py` (new)

**Interfaces:**
- Produces: `companion.lower_priority(setter=None) -> bool`. It sets the process to `BELOW_NORMAL_PRIORITY_CLASS` (`0x4000`) on Windows and returns True. It returns False off Windows, or when `setter` raises. `setter(cls: int)` is injected in tests.

- [ ] **Step 1: Write the failing tests:**
  - `test_below_normal_is_asked_for`: with a recording `setter`, the result is True and the recorded value is `[0x4000]`.
  - `test_a_failure_is_not_fatal`: a raising `setter` gives False and no exception.

- [ ] **Step 2: Run them and make sure they fail**

Run: `python -m pytest tests/test_priority.py -q -p no:cacheprovider`
Expected: FAIL with `AttributeError: module 'companion' has no attribute 'lower_priority'`.

- [ ] **Step 3: Implement.** `lower_priority` goes in `companion.py`, and `main()` calls it first. A False result is logged once with `applog.log`.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_priority.py tests/test_single_instance.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add companion.py tests/test_priority.py
git commit -m "perf: Companion runs below normal priority, so the game always comes first"
```

### Task 3: A slow pace while you're away

**Files:**
- Modify: `app/sniper.py` (`watch_loop`, `map_loop`, `corner_loop`; new constants)
- Modify: `app/capture.py` (`GameCapture.min_interval`, read by `on_frame_arrived`)
- Test: `tests/test_idle_pace.py` (new)

**Interfaces:**
- Produces:
  - `sniper.IDLE_AFTER = 300.0`, `sniper.IDLE_EVERY = 5.0`, `capture.IDLE_FRAME_S = 0.5`;
  - the pure function `sniper.is_idle(last_gain: float | None, started: float, now: float, in_front: bool, shop_open: bool) -> bool`. It is True only when the game isn't in front, no shop is open, and the last EXP gain (or the app's start, if there was none) is more than `IDLE_AFTER` ago;
  - `GameCapture.min_interval: float`, which defaults to `FRAME_INTERVAL_MS / 1000`.

- [ ] **Step 1: Write the failing tests** for `is_idle`:
  - `test_away_five_minutes_is_idle`: last gain 301 s ago, not in front, no shop → True.
  - `test_grinding_behind_the_dashboard_is_not_idle`: last gain 20 s ago, not in front → False.
  - `test_back_in_front_is_not_idle`: last gain an hour ago, in front → False.
  - `test_an_open_shop_is_never_idle`: last gain an hour ago, not in front, shop open → False.
  - `test_no_gain_yet_counts_from_start`: `last_gain=None`, started 200 s ago → False; 400 s ago → True.

- [ ] **Step 2: Run them and make sure they fail**

Run: `python -m pytest tests/test_idle_pace.py -q -p no:cacheprovider`
Expected: FAIL with `AttributeError: module 'sniper' has no attribute 'is_idle'`.

- [ ] **Step 3: Implement.**
  - `Sniper.idle()` calls `is_idle` with `self.grind.last_any`, the app's start time, `self.game_in_front()`, and `bool(self.shop_anchor or self.myshop_anchor)`.
  - While idle:
    - `watch_loop` uses `IDLE_EVERY`;
    - `map_loop` and `corner_loop` skip their look;
    - `self.capture.min_interval = IDLE_FRAME_S`.
  - Otherwise it's back to `FRAME_INTERVAL_MS / 1000`.
  - `on_frame_arrived` compares with `self.min_interval`.
  - The first tick that isn't idle puts every pace back.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_idle_pace.py tests/test_grind_app.py tests/test_now_api.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/sniper.py app/capture.py tests/test_idle_pace.py
git commit -m "perf: while you're away from the game (no EXP for 5 min, game not in front), Companion looks every 5 s"
```

### Task 4: Cozy prices at a pace a pass can keep

**Files:**
- Modify: `app/cozy.py` (`EVERY_HOURS`, `wanted`, the failure row in `refresh.fetch`)
- Test: `tests/test_cozy.py` (new)

**Interfaces:**
- Produces:
  - `cozy.EVERY_HOURS = 12`;
  - a failure row is `{"error": str, "fetched": now()}`;
  - `wanted(row, older_than)` wants:
    - an empty row;
    - a failure with no `fetched`;
    - a failure older than `older_than` hours;
    - every failure when `older_than` is None (`tools/scrape_cozy.py`'s full runs keep retrying);
    - a priced row older than `older_than`, as today.

- [ ] **Step 1: Write the failing tests:**
  - `test_a_fresh_failure_waits_for_the_next_pass`: `wanted({"error": "HTTP 404", "fetched": now()}, 12)` is False.
  - `test_an_old_failure_without_a_time_is_fetched`: `wanted({"error": "HTTP 404"}, 12)` is True.
  - `test_a_failure_older_than_the_pace_is_fetched`: a failure fetched 13 h ago → True.
  - `test_full_runs_still_retry_failures`: `wanted({"error": "x", "fetched": now()}, None)` is True.
  - `test_a_pass_fits_the_pace`: `EVERY_HOURS * 3600 >= 2200 * 1.0 * 1.5`. At ~2,200 items, one a second, and half again for retries and the site's slowdowns, a pass ends before the next is due.

- [ ] **Step 2: Run them and make sure they fail**

Run: `python -m pytest tests/test_cozy.py -q -p no:cacheprovider`
Expected: FAIL on the fresh failure and on the pace.

- [ ] **Step 3: Implement.**
  - The failure branch of `fetch` writes `"fetched": now()` with the error. A price already there is still kept, as today.
  - `wanted` follows the Interfaces block.
  - `EVERY_HOURS = 12`. `gamedata.COZY_MAX_AGE` (14 days) is already far above that.
  - The docstrings of `keep_fresh` and `EVERY_HOURS` say 12 hours.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_cozy.py tests/test_advisor.py -q -p no:cacheprovider`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/cozy.py tests/test_cozy.py
git commit -m "perf(cozy): prices refresh every 12 h (a pass takes ~5 h), and a failed page waits for the next pass"
```

---

## After the tasks

- **Live check, with the user's OK:**
  - run the branch from source beside nothing else (close the installed copy first) for 10 minutes of grinding;
  - measure CPU the same way: `TotalProcessorTime` over 30 s, game in front and behind;
  - then 6 minutes away. Expected: about a third less while playing, and a few percent of a core while away.
- **Release:** the user decides, together with the Grind party plan if both are done.
