# Reader Accuracy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the reader's wrong values (and stop wrong values reaching `profile.json`) by testing against real game pictures, fixing the misreads found on 2026-11-06, anchoring windows by their title picture, and checking every value against the game's rules before it is saved.

**Architecture:** A local test set of masked game frames with known true values drives every change. Window titles are found by picture (numpy normalized cross-correlation) with the current OCR finder as fallback, so field offsets start from an exact point. A new `trust.py` gate sits between `Reader.read()` and the profile in `sniper.apply_seen`.

**Tech Stack:** Python 3.12, Pillow, winocr, rapidfuzz, numpy (already shipped via windows-capture), pytest (dev only). No OpenCV (user's choice, 2026-11-06).

**Spec:** the "Findings" section below (live tests, 2026-11-06, game windowed, character Tura1, Hunter level 32).

## Findings (the spec)

60 frames of the live game in 6 scenes (frames `s1`–`s5` in the session scratchpad, `t1` in `samples/raw/`), plus 17 saved shop pictures (`debug/samples/`).

| scene | what was on screen | result |
|---|---|---|
| t1 | 1920x1200, Free Market: mini map, Quest window (In Progress), inventory, CHARACTER STAT + Detail, own shop | see field table |
| s1 | same, Quest Helper (4 quests), Lemon tooltip over the stat window, inventory moved | Helper 15/15 correct; full read misses the tooltip, quick look finds it; level read 132 on 1 frame |
| s2 | hunting map (A Hill West of Henesys), stat + mini map moved, killing | Helper numbers never wrong (Maple Leaf 1→2→3, Omok Piece: Pig 0→1); a count line dropped on 6/15 frames (Omok Piece: Pig / Octopus, Arwen's Glass Shoe); EXP and MP lines missing on 6/15 frames, under the game's own "Maple Leaf 2 / 30" popup |
| s3a/s3b | Skill window, 1st-job tab then Hunter tab; mini map collapsed | skills 8/8 frames perfect (incl. "Amazon's Judgem..."); collapsed bar read None on 8/8 |
| s4 | another player's shop with the Earring INT Scroll tooltip over its rows; see-through Quest Helper over ropes | seller, 3 prices and the tooltip correct; **"Hat Accuracy Scroll: Inter..." matched to "…: Greater"**; Helper lost most count lines (no wrong numbers) |
| s5 | 1920x1080 | stat values fine; **Helper lists "Make a Slime & …", a quest not tracked, on every frame**; collapsed bar None |

Field misreads:

| field | truth | read | cause |
|---|---|---|---|
| `stat.name` | `Tura1` | `Tural`, every frame | OCR word guess. The game's 1 has a flag in its top rows; an l is a straight stem |
| `stat.dex_base` | 142 | 152, every frame | OCR text `1 52 (1 42+1 0)`; the `\(\s*(\d+)\s*\+` pattern fails on the spaces |
| `stat.ap` | 0 | 1 or None | the values box catches "…OINT" and the box edge. `read_small_number` on (x+122, y+388, x+170, y+410) reads 0 |
| `stat.level` | 32 | 132 on 1/15 | title read as `I CHARACTER STAT` at x=771, not 778 (a tooltip's edge glued on); every offset shifted 7 px |
| `map` (open) | Hidden Street / Free Market <7> | None | the 1x full-frame pass reads only `ree Market`; a 3x read of (x+62, y+26, x+224, y+80) from the MINI MAP title reads both lines. After moving it, it reads (street as "Wikitoria Road") |
| `map` (collapsed) | Victoria Road : A Hill West of Henesys | None | the 1x pass gives `Victoria Road Hill West of Henesys` (colon and "A" lost); a 3x read of the bar gives `Victoria Road :A Hill West of Henesys` |
| `quest` (In Progress) | 5 entries | 3 unmatched | the list shows quest-line names (`parent` in quests.json, kept in its `chains` list) |
| `shop` | — | 0 items on 17/17 saved pictures | 11 are NPC shops ("50 Mesos" rows) taken for player shops; the rest have only gray sold-out rows |
| `shop` item | Hat Accuracy Scroll: Intermediate | …: Greater | a name cut with "..." is fuzzy-matched whole, not by its start |
| `helper` at 1080 | 4 tracked quests | 5, one never tracked | a misread line matched a similar quest; it repeats every read, so the 3-read `Agree` would add it |
| `profile.json` | Tura1, 385,973 mesos | `Tural`, mesos 61 | single reads are saved with no check |

Rules verified on Tura1:
- **AP:** base STR+DEX+INT+LUK + unspent AP = 30+142+4+4+0 = 180 = 5 × 32 + 20.
- **SP:** 1st-job tab skill levels sum to 61 = 1 + 3 × 20. The Hunter tab sums to 7 = 1 + 3 × 2. With 0 SP left, the total 68 = 3 × 32 − 28.

Title picture match (`cv2.TM_CCOEFF_NORMED`):
- Same size: 1.000 at the window, at most 0.62 anywhere else, 40–62 ms per title.
- Templates cut at 1200 px and shrunk to 0.9, on the 1080 frame: 0.86 at the window against 0.48 elsewhere.
- A fixed 0.90 threshold is wrong. Use the gap to the second-best match, and learn a template per game height.
- Matching the WORLD button by its orange color is NOT usable (the map emblem has the same orange).

Tried and dropped:
- Sharper enlarging (`NEAREST`) for OCR: worse than today's `LANCZOS`.
- Reading stat rows one by one: fails on the same frames, because the cause is the game's popup.
- Keeping only the text color on the see-through Helper: white keeps nothing, and dark keeps tree bark.
- Exact glyph keys: the same `1` differs by 1–2 pixels between rows. Match by nearest shape.

## Global Constraints

- The reader never sends input to the game and never opens the game process (capture.py's rules stay).
- Test pictures stay on this PC: `samples/cases/` is git-ignored (the repo Tura2/classic-companion is PUBLIC). Committing any picture needs the user's yes.
- Masked case frames keep only the window boxes listed in the case; everything else is filled with (128, 128, 128). No other player's name or chat may remain in a case picture.
- Open text files with `encoding="utf-8"` (this PC's locale is cp1255).
- Tests run with `python -I -m pytest tests -q` from `classic/companion/`.
- No new runtime dependency: `numpy` is listed in `requirements.txt` explicitly (it already ships with windows-capture). No OpenCV. The exe build (`build.bat`, `Companion.spec`) must still produce a working `Companion.exe`.
- No change may lower the pass count of `tests/test_cases.py` below the previous task's count.
- A field the reader can't read is None, never a guess. Every rule here prefers a missing value to a wrong one.

## Review Focus

1. A window dragged over another window's title. Task 3 test: a gray block over half the stat title → stat comes from the OCR finder or is absent, never at a wrong place.
2. Switching characters (Offir vs Tura1): the gate must not save one character's stats into the other's profile. Task 8 test: a name agreed 3 times that differs from `profile.name` → no stat, level, mesos or skill write.
3. A level-up during play: the gate must accept level+1 at once (Task 8 test), or the guide lags behind the player.
4. The game's UI Size setting (not tested): the learned per-height templates of Task 3 also cover it, because the title is found at the size it is drawn. Task 3 test: the 1080 frame with templates cut at 1200 still finds stat.
5. A magician (job advance at 8, not 10): the SP rule's constant differs. Task 8 falls back to "5 equal reads" for any character the rule doesn't fit; test it with a total that is off by 3.

---

### Task 1: Test cases from real frames, and the harness

**Files:**
- Create: `tools/make_case.py`, `tests/conftest.py`, `tests/test_cases.py`, `requirements-dev.txt` (`pytest`)
- Create (local only): `samples/cases/*.png`, `samples/cases/*.json`
- Modify: `.gitignore` (add `samples/cases/`)

**Interfaces:**
- Produces:
  - Case JSON `{"frame": str, "keep": [[l,t,r,b], ...], "tip_region": [l,t,r,b] | null, "job": str, "expect": {dotted_field: value}}`.
  - Fixture `seen(case_name) -> dict`: the `Reader.read` output, read once per session with `set_job(case["job"])`.
  - Helper `field(seen, "stat.name")`: walks dotted keys and returns None when a key is missing.
  - Two computed fields: `quicklook.tooltips` (`[t["name"] for t in reader.look_for_tooltips(frame, tip_region, item_names)]`) and `helper.list` (`[[q["quest"], [[n["what"], n["have"], n["need"]] for n in q["needs"]]] for q in seen["helper"]["quests"]]`).

- [ ] **Step 1: Write `tools/make_case.py --frame PATH --name NAME --job JOB --keep l,t,r,b [--keep ...] [--tip l,t,r,b]`**. It writes `samples/cases/NAME.png` (masked as in Global Constraints) and `NAME.json`, with `expect` pre-filled from the current reader output for correcting by hand against the picture.
- [ ] **Step 2: Make the cases** from the 13 frames kept in `samples/raw/cases-src/` (git-ignored; the frame names below are those files). True values come from the Findings and from the frames themselves; job "Hunter" throughout. Once every case is made and passes Step 4's check, delete `samples/raw/cases-src/`.
  - `fm_quest_window` (t1): `stat.name` "Tura1", `stat.level` 32, `stat.exp` 1206, `stat.str_base` 30, `stat.dex_base` 142, `stat.ap` 0, `stat.acc` 72, `hud.level` 32, `inventory.mesos` 385973, `map.street` "Hidden Street", `map.name` "Free Market <7>", `quest.tab` "in_progress", `quest.lines` ["Caretaker's Ledger", "Legend of the Snail", "Maple World's Unique Fun: Omok"] (the 5th confirmed by the user's screenshot: its current step is "Make a Pig & Octopus Omok Set").
  - `fm_tooltip` (s1_07): the stat values above; `helper.list` = the 4 quests with 0/30, 0/1, 0/25, 0/1 ×3; `quicklook.tooltips` ["Lemon"].
  - `fm_title_glued` (s1_04): `stat.level` 32.
  - `hunt_moved` (s2_00 and s2_13): `map.name` "A Hill West of Henesys", `stat.exp` 1334 / 1344, and `helper.list` as on the frame. The Omok lines must be 0/1, 0/1, 0/1 on s2_00 and 0/1, 1/1, 0/1 on s2_13.
  - `hunt_popup` (s2_02): `stat.exp` None (covered by the game's popup), `stat.level` 32.
  - `skills_1st` (s3a_00): `skills.levels` {Critical Shot 15, The Eye of Amazon 15, Focus 10, Power Knockback 0, Arrow Blow 20, Double Shot 1}, `skills.sp` 0, `map.street` "Victoria Road", `map.name` "A Hill West of Henesys", `map.collapsed` true.
  - `skills_hunter` (s3b_00): {Bow Mastery 5, Amazon's Judgement 0, Final Attack: Bow 0, Bow Booster 1, Soul Arrow: Bow 0, Arrow Bomb 1}, `skills.sp` 0.
  - `player_shop` (s4_00): `shop.seller` (the seller's name, kept only in the local case), `shop.items` names/prices: Hat Accuracy Scroll: Intermediate 58000, Earring INT Scroll: Intermediate 131000, Horny Mushroom Cap 25; `quicklook.tooltips` ["Earring INT Scroll: Intermediate"].
  - `res_1080` (s5_00): `stat.level` 32, `stat.exp` 1646, `helper.list` with exactly the 4 tracked quests (no "Make a Slime & …").
  - `npc_shop` (shop_20261105_104043), `npc_shop_2` (shop_20261102_114059): `shop` None. `player_shop_soldout` (shop_20261105_094702): `shop.kind` "player".
- [ ] **Step 3: Write `tests/test_cases.py`**: one test per (case, field), parametrized from the JSON files, `assert field(seen, f) == expected`. Skip the whole module when `samples/cases/` is empty.
- [ ] **Step 4: Run** `python -I -m pytest tests/test_cases.py -q`. Expected: the failures are exactly the misreads in the Findings table. If a masked case fails where its raw frame passed, widen its `keep` boxes until both agree.
- [ ] **Step 5: Commit** the tool, the tests, `requirements-dev.txt` and `.gitignore` (no pictures): `"Add reader test cases from real game frames"`.

### Task 2: Stat numbers with OCR spaces, and AP as a small number

**Files:**
- Modify: `reader.py` (`read_stat`, line 284ff)
- Create: `tests/test_parse.py`

**Interfaces:**
- Produces: `reader.stat_number(text: str) -> tuple[int | None, int | None]`, giving (total, base).

- [ ] **Step 1: Write failing tests**:
  - `stat_number("152 (142+10)") == (152, 142)`
  - `stat_number("1 52 (1 42+1 0)") == (152, 142)`
  - `stat_number("32 (30+2)") == (32, 30)`
  - `stat_number("4") == (4, 4)`
  - `stat_number("") == (None, None)`
- [ ] **Step 2: Run** `python -I -m pytest tests/test_parse.py -q`. Expected: FAIL (no `stat_number`).
- [ ] **Step 3: Implement**:
  - `stat_number` removes spaces between two digits, then parses. Use it for str/dex/int/luk.
  - Read `ap` with `read_small_number(frame, (x+122*s, y+388*s, x+170*s, y+410*s), s)`.
  - Apply the same space removal to the EXP text before its pattern.
- [ ] **Step 4: Run** all tests. Expected: `test_parse.py` passes; `stat.dex_base` and `stat.ap` pass in every case; nothing else changes.
- [ ] **Step 5: Commit** `"Read stat values through OCR's spaces; read AP as a small number"`.

### Task 3: Find windows by their title picture

**Files:**
- Create: `anchors.py`, `assets/titles/{stat,inventory,quest,helper,skills,minimap,minibar}.png`, `assets/titles/boxes.json`
- Modify: `reader.py` (`Reader.read`, line 882ff), `requirements.txt` (add `numpy`), `Companion.spec` (add `assets/titles` to datas)
- Create: `tests/test_anchors.py`

**Interfaces:**
- Produces: `anchors.Titles(app_dir)` with `.find(frame: PIL.Image, s: float) -> dict[str, tuple[str, float, float, float, float]]` and `.learn(frame, name, line)`.
  - The values have the same `(text, x, y, w, h)` shape as an OCR line, so the `read_*` functions are unchanged. The text is the window's title (`"QUEST HELPER ("` for the helper, so its `(` check holds).
  - `minibar` is the collapsed mini map's right-end buttons ("– + WORLD"). Its line is the bar's buttons; Task 4 reads the text left of them.
- `boxes.json` maps each title to the OCR line box it was cut at, so a picture match lands at the same (x, y) a clean OCR read gives.

- [ ] **Step 1: Cut the templates** at the 1200 px size:
  - stat, inventory, quest and minimap from t1 (stat at (778, 662), w=126); helper from s2_00, "Quest Helper" text only, without the count; skills from s3a_00; minibar from s3a_00 (the buttons at about (455, 108)–(560, 130)).
- [ ] **Step 2: Write failing tests**:
  - On every case, `find` returns stat exactly where a clean OCR read puts it ((778, 662) in t1).
  - On `res_1080`, stat is found within 2 px of the OCR position, using templates cut at 1200.
  - With a gray block over the left half of the stat title, stat is not returned.
  - Nothing is returned on an all-(128, 128, 128) frame.
  - After `learn` on `res_1080`, a template for height 1080 exists, and `find` on that frame scores ≥ 0.98.
- [ ] **Step 3: Run** `python -I -m pytest tests/test_anchors.py -q`. Expected: FAIL (no module).
- [ ] **Step 4: Implement**:
  - `anchors.ncc(img, tpl) -> np.ndarray`: normalized cross-correlation with numpy (FFT product for the numerator, summed-area tables for the window sums), equal to OpenCV's TM_CCOEFF_NORMED. Use the learned template for this frame height when there is one, else the 1200 one resized by `s` (PIL BOX).
  - Search order: first a box 40 px around the window's last place (`Titles` keeps it); then, when not found there, the whole frame at quarter size, and the best spot found is confirmed at full size in a box 8 px around it.
  - Accept a match when best ≥ 0.75 and best − (best score more than 10 px away) ≥ 0.25.
  - When the OCR finder finds a title that `find` missed and the read passes, `learn` cuts a template for this height into `cache/titles/<height>/<name>.png`.
  - In `Reader.read`, picture matches replace OCR-found titles. OCR still supplies `hud`, `shop`, unmatched windows and the kept-window logic.
  - Add `numpy` to `requirements.txt`.
- [ ] **Step 5: Run** all tests. Expected: `fm_title_glued stat.level` passes and nothing that passed fails. Measure the time added per read: under 60 ms when no window moved, under 600 ms when one did, at 1920x1200.
- [ ] **Step 6: Build the exe** with `build.bat` and start it once with screen reading off. Expected: it opens with no import error.
- [ ] **Step 7: Commit** `"Find windows by their title picture, OCR as fallback"`.

### Task 4: Read the mini map, open or collapsed, from its picture

**Files:**
- Modify: `reader.py` (`read_minimap` line 486, `read_minimap_bar` line 522, the map part of `Reader.read`)

**Interfaces:**
- Consumes: `Titles.find(...)["minimap"]` and `["minibar"]` from Task 3.
- Produces:
  - `reader.read_minimap_at(frame, title_line, s, map_names) -> (street, name, title_box, collapsed)`, the same tuple `read_minimap` returns.
  - `reader.read_minibar_at(frame, buttons_line, s, map_names) -> (street, name, title_box, True)`.

- [ ] **Step 1: Confirm** that the `map.*` fields fail in `fm_quest_window` and `skills_1st` (baseline).
- [ ] **Step 2: Implement**:
  - Open: `read_box` over (x+60s, y+24s, x+340s, y+82s) from the MINI MAP title. The last line goes through `match_place(..., 86)`; the line before it is the street.
  - Collapsed: `read_box` over (bx−470s, by−4s, bx, by+h+4s) left of the buttons, then split with `BAR_SPLIT` as today.
  - `title_box` is the read box, so `minimap_window` keeps working.
  - Fall back to today's readers when neither picture is found.
- [ ] **Step 3: Run** all tests. Expected: `map.*` passes in `fm_quest_window`, `hunt_moved` and `skills_1st`; nothing else changes.
- [ ] **Step 4: Commit** `"Read the mini map close up from its picture, open or collapsed"`.

### Task 5: Quest Helper: no extra quests, no dropped lines

**Files:**
- Modify: `reader.py` (`read_helper`, line 432ff; `find_windows` keeps the helper title text)
- Modify: `tests/test_parse.py`

**Interfaces:**
- Produces:
  - `reader.helper_count(title_text: str) -> int | None`: the N in "Quest Helper (N/5)".
  - `read_helper(..., active_ids: set[str] = frozenset())` returns at most N quests.

- [ ] **Step 1: Write failing tests**:
  - `helper_count("Quest Helper (4/5)") == 4`
  - `helper_count("Quest Helper (4 / 5)") == 4`
  - `helper_count("Quest Helper") is None`
- [ ] **Step 2: Run.** Expected: FAIL. In the cases, `res_1080 helper.list` and `hunt_moved helper.list` (s2_13) fail.
- [ ] **Step 3: Implement**:
  - When more than N titles match, keep the N with the best match scores; a quest in `active_ids` gets +10. Today's "Make a Slime & …" goes, because it neither scores best nor is active. The app passes the profile's `quests_active` ids.
  - When a count line's best requirement is already taken, give it to the best untaken requirement scoring ≥ 60, instead of dropping it. This keeps Omok Piece: Pig and Omok Piece: Octopus.
- [ ] **Step 4: Run** all tests. Expected: both `helper.list` fields pass and every other `helper.list` is unchanged.
- [ ] **Step 5: Commit** `"Quest Helper: no more quests than its title says, keep look-alike count lines"`.

### Task 6: Quest-line names in the Quest window

**Files:**
- Modify: `gamedata.py` (`GameData.__init__`, line 295: keep `chains`), `reader.py` (`Reader.__init__`, `read_quest_window`), `sniper.py` (`apply_seen`, In Progress branch, line 912ff)
- Modify: `tests/test_parse.py`

**Interfaces:**
- Produces:
  - `GameData.chains: dict[str, list[str]]` (parent → quest_ids in order, from quests.json `chains`).
  - `Reader.line_names: list[str]`.
  - Each `read_quest_window` entry gains `"line": str | None`.
  - `sniper.current_step(chain_ids: list[str], done: set[str]) -> str | None` returns the first id not done.

- [ ] **Step 1: Write failing tests**:
  - `current_step(["10213", "10214"], set()) == "10213"`
  - `current_step(["10213", "10214"], {"10213"}) == "10214"`
  - `current_step(["1"], {"1"}) is None`
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement**:
  - An entry that matches no quest is matched against `line_names` with `match_quest(text, line_names)`, which also handles cut-off "…" titles.
  - In `apply_seen`, a line seen in the In Progress tab adds `current_step(...)` to `quests_active` through the 3-read `Agree`, with scope `"tab:in_progress"` and key `"line:" + parent`.
- [ ] **Step 4: Run** all tests. Expected: `quest.lines` passes and the unit tests pass.
- [ ] **Step 5: Commit** `"Recognize quest-line names in the Quest window"`.

### Task 7: Shops: NPC vs player, and cut-off item names

**Files:**
- Modify: `reader.py` (`read_shop`, `_shop_items`), `sniper.py` (`_watch` line 790, shop handling)
- Modify: `tests/test_parse.py`

**Interfaces:**
- Produces:
  - `read_shop(...)["kind"]`, either `"player"` or `"npc"`. `Reader.read` drops `seen["shop"]` for `"npc"`.
  - `reader.match_item(text: str, names: list[str]) -> str | None`.

- [ ] **Step 1: Write failing tests**:
  - `match_item("Hat Accuracy Scroll: Inter...", names) == "Hat Accuracy Scroll: Intermediate"`
  - `match_item("Earring INT Scroll: Interm...", names) == "Earring INT Scroll: Intermediate"`
  - `match_item("Horny Mushroom Cap", names) == "Horny Mushroom Cap"`
  - `match_item("Hat Accuracy Scroll: ...", names) is None` (more than one item has that start)
- [ ] **Step 2: Run.** Expected: FAIL. In the cases, `npc_shop*`, `player_shop_soldout` and the `player_shop` item names fail.
- [ ] **Step 3: Implement**:
  - `match_item`: a name ending in "..", "..." or "…" matches by its start, using the cut text without its last character. It returns None when more than one item starts that way. Other names keep today's `fuzz.ratio` ≥ 80. Use it in `_shop_items`; an item that returns None is left out, never guessed.
  - A shop is `"npc"` when at least 2 rows in its list box match `^\s*\d[\d,]*\s*Mesos\s*$` (case-insensitive) and no `LISTING` row matched; otherwise `"player"`.
  - Nothing is saved for NPC shops and no debug sample is taken.
- [ ] **Step 4: Run** all tests. Expected: all shop fields pass.
- [ ] **Step 5: Commit** `"Shops: tell NPC from player shops; match cut-off item names by their start"`.

### Task 8: The save gate

**Files:**
- Create: `trust.py`, `tests/test_gate.py`
- Modify: `sniper.py` (`apply_seen` lines 876–897: route level, name, stats, acc, mesos, skills and sp through the gate; line 925ff: Helper quests)
- Modify: `reader.py` (`Reader.read` line 923: stop learning digits there; `LevelDigits.read`/`learn`)

**Interfaces:**
- Produces:
  - `trust.Gate(skill_max: dict[str, int])` with `.check(prof: dict, seen: dict) -> dict`. It returns only the accepted values, from the keys `name`, `level`, `stats` (`{"str","dex","int","luk"}` bases), `ap`, `acc`, `mesos`, `skills_now`, `sp`, plus `"other_name": str | None`.
  - `Reader.learn_level(level: int)`, which learns from the last read's HUD glyphs.
- Rules (exact):
  - `name`: the first name needs 3 equal reads in a row. Once `prof["name"]` is set, a different name is never written. If it is read 3 times in a row it becomes `other_name`, and while it is set, nothing else is accepted.
  - `level`: accepted at once if it is `prof.level + 1`. Any other value (including the first) needs 3 equal reads in a row. A stat level is used before a HUD level; a HUD level counts only when `level_exact`.
  - `stats` and `ap`: accepted when `sum(bases) + ap == 5 * level + 20` (level = accepted this read, else `prof.level`). Otherwise they need 5 equal reads in a row.
  - `skills_now` and `sp`: merge the read tab into `prof.skills_now`.
    - No level may go down or exceed `skill_max[name]` (`max_level` in `data.skills`).
    - The merged total plus `sp` must be `3 * level - 28` from level 30 up, or `3 * level - 29` below 30. That holds for the 1st-job tabs once the read covers all of the character's tabs; until then only the per-skill limits apply.
    - Otherwise the read needs 5 equal reads in a row.
  - `mesos`: a change of more than 50% from a previous value above 1,000 needs 2 equal reads in a row.
  - `acc`: today's cap (40 + 6 × level) stays.
  - Helper quests: only quests the Helper read lists (after Task 5) go through the existing 3-read `Agree`. No change in rule.
- `LevelDigits`:
  - `read` matches each glyph to the nearest known shape of the same size, needing ≥ 92% equal pixels, before the Arial guess.
  - `learn` never overwrites a known shape with a different digit; on a conflict it deletes that shape.

- [ ] **Step 1: Write failing tests in `tests/test_gate.py`** with the measured numbers:
  - prof level 32, stat level 132 once → no level; 3 times in a row → 132.
  - prof 32, stat 33 once → 33.
  - bases 30/142/4/4 + ap 0 at level 32 → accepted. Bases 30/152/4/4 + ap 1 → rejected.
  - prof mesos 385973, read 61 once → rejected; twice in a row → 61.
  - prof name "Tura1", read "Tural" 3 times → no name write, `other_name == "Tural"`, and the stats in those reads are not accepted.
  - Skills: prof has the 1st-job tab from `skills_1st` and the read is the `skills_hunter` tab with sp 0 at level 32 → accepted (61 + 7 + 0 = 68). The same read with Bow Mastery 8 → rejected. "Arrow Blow" 20 → read 2 → rejected. Arrow Blow 21 with max 20 → rejected.
  - A total off by 3 (Review Focus 5), read 5 times in a row → accepted.
  - `LevelDigits`: learning shape A as "9" then as "8" → A is deleted, not remapped.
- [ ] **Step 2: Run** `python -I -m pytest tests/test_gate.py -q`. Expected: FAIL (no module).
- [ ] **Step 3: Implement `trust.py`** and route `apply_seen` through it. Call `reader.learn_level(level)` only when the gate accepted a stat-window level.
- [ ] **Step 4: Run** all tests. Expected: everything passes, and the case pass count is unchanged.
- [ ] **Step 5: Fix `profile.json` by hand** after asking the user: name "Tura1", mesos 385973, level 32.
- [ ] **Step 6: Commit** `"Check every value against the game's rules before saving it"`.

### Task 9: Tell 1 from l in names

**Files:**
- Modify: `reader.py` (`read_stat` name; new `fix_one_vs_l`)
- Modify: `tests/test_parse.py`

**Interfaces:**
- Produces: `reader.fix_one_vs_l(text: str, crop: PIL.Image) -> str`.

- [ ] **Step 1: Write failing tests**:
  - On the name crop from `fm_quest_window`, `fix_one_vs_l("Tural", crop) == "Tura1"`.
  - A synthetic straight 2-px stem 14 px tall reads as `l`. A stem with a 2-px flag to its left in its top 3 rows reads as `1`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement**:
  - Split the dark ink (< 150) into glyphs by empty columns. Act only when the glyph count equals `len(text)`, since names have no spaces.
  - Each `l`, `I`, `|` or `1` glyph becomes `1` when its top third reaches ≥ 2 px left of its stem, and `l` otherwise. Keep `I` as read when there is no flag.
- [ ] **Step 4: Run** all tests. Expected: `stat.name` passes in every case.
- [ ] **Step 5: Commit** `"Tell 1 from l in character names by the 1's flag"`.

## Still needed from the user

1. The full name of the 5th quest line in the Quest window ("Maple World's Unique Fun: …" is cut off).
2. **Decided 2026-11-06: numpy only** (no OpenCV). Measured on the same frame and title: OpenCV `matchTemplate` 50 ms; numpy FFT cross-correlation 460 ms, same score and spot. numpy already ships inside Companion (capture.py uses it); OpenCV would add tens of MB to the 78 MB exe. With numpy, Task 3 searches near each window's last place first and runs a full-frame search on a quarter-size frame only when a window isn't there.
3. Done 2026-11-06: `profile.json` fixed (backup in `profile.json.bak`). Task 8 Step 5 is no longer needed.
4. Done 2026-11-06: all game pictures deleted except the 13 in `samples/raw/cases-src/`.
