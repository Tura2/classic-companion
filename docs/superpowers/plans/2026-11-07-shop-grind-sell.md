# Shop alerts, grind tracker, sell or keep: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Discord pings for your own shop's sales, an EXP/hr grind tracker, and a sell-or-keep verdict per item.

**Architecture:** Pure logic in new small modules (`shopwatch.py`, `discord_link.py`, `grind.py`, `advisor.py`), each unit-tested. Readers added to `reader.py` and hooked into `Reader.read()` / `App._watch()`; dashboard pieces in `web/index.html`; endpoints in `companion.py`.

**Tech Stack:** Python 3.10+, numpy, PIL, winocr, requests, sqlite3, pytest; vanilla JS dashboard.

**Spec:** `docs/superpowers/specs/2026-11-07-shop-grind-sell-design.md`

## Global Constraints
- Screen-reading features run only when Settings → Screen reading is on, and say so when off.
- No new capture loop; owner-shop re-read every 6 s (`MYSHOP_EVERY = 6.0`), a full read every 10th time.
- One misread never acts: 2 agreeing reads before a sale or EXP change counts; impossible values dropped.
- `allowed_mentions` is always `{"parse": [], "users": [<own id>]}`.
- The OAuth token is never written to disk; no client secret in the exe.
- Data stays in `APP_DIR`: `discord_outbox.json`, `grind.sqlite`, `config.json`, `profile.json`.
- FM fee 3% (`FM_FEE = 0.03`).
- Files opened with `encoding="utf-8"` (cp1255 locale).
- Tests: `python -I -m pytest tests -q` stays green (110 passed, 2 xfailed before this branch).

## Review Focus
- Shop window closed, then reopened in a new store session (total back to 0): no phantom sale. → test in Task 2.
- No internet / Discord 429 for minutes: sales queue on disk and arrive once, in order. → test in Task 3.
- App restarted with sales still in the outbox: sent once after restart, not twice. → test in Task 3.
- Level-up mid-session: EXP/hr keeps counting, no negative gain. → test in Task 6.
- Item with no market data or no NPC price: verdict says so, never a made-up price. → test in Task 7.

---

### Task 1: Owner shop reader
**Files:** Modify `reader.py`; Test `tests/test_myshop.py` (cases in git-ignored `samples/cases/myshop_*.png|json`, made with `tools/make_case.py`).
**Interfaces — Produces:**
- `find_windows` returns `"myshop"` → an OCR-line tuple of the CLOSE STORE button.
- `read_my_shop(frame, anchor, item_names) -> {"title", "mesos", "items": [{name,count,price,unit,sold}], "panel": {"total_sales", "total_received", "rows": [{name,count,price}]} | None, "u": float, "box": [l,t,w,h]}`
- `Reader.read()` sets `seen["myshop"]` (plus `["anchor"]`); `Reader.read_my_shop_only(frame, anchor) -> seen | None`.
- [ ] Measure offsets (relative to CLOSE STORE, divided by `u` = button text height / its 1200-UI height) on both samples.
- [ ] Tests: both samples give title "Scrolls and more", mesos 428351, 5 items (first "Cape STR Scroll: Intermediate", 1, 388887), panel totals 0/0; other people's shop cases still give no `myshop`.
- [ ] Implement, run all tests, commit.

### Task 2: ShopWatch (sale detection)
**Files:** Create `shopwatch.py`; Test `tests/test_shopwatch.py`.
**Interfaces — Produces:** `ShopWatch().update(read: dict | None, now: float) -> list[Sale]`, `Sale = {"key", "item", "count", "price", "total_sales", "ts"}`; `ShopWatch.status -> {"watching": bool, "since": float, "total": int, "sales": [Sale]}`.
- [ ] Tests: a total rising once is not a sale; twice in a row is one sale with key `f"{session}:{total}"`; a drop is ignored; a rise > max(10× listed value, 10,000,000) is ignored; total back to 0 starts a new session, no sale; panel row diff names the item; with no panel, a listed count drop + mesos rise gives the sale; unreadable detail gives `item=None`; sold out (no unsold row) reported once.
- [ ] Implement, test, commit.

### Task 3: Discord link and outbox
**Files:** Create `discord_link.py`; Modify `build.bat`, `.gitignore`, `paths.py` (nothing if `RES_DIR` suffices); Test `tests/test_discord.py`.
**Interfaces — Produces:**
- `load_discord_config() -> {"webhook", "client_id"} | None` (RES_DIR, then repo folder).
- `authorize_url(client_id, port=8765) -> str`.
- `who_is(token, session=requests) -> {"id", "name"}` (`GET https://discord.com/api/users/@me`).
- `sale_message(sales, discord_id, character, market) -> dict` (payload incl. `allowed_mentions`).
- `Outbox(path, webhook, post=requests.post)` with `.add(kind, payload, key)`, `.pump(now) -> int sent`, `.start()` (thread), batching sales within 60 s into one message (≤ 10 embeds).
- [ ] Tests: allowed_mentions exact; content starts with `<@id>`; batching of 3 sales in 60 s → 1 post; 429 with `retry_after` 2 → not resent before 2 s; failure keeps entry on disk; new `Outbox` from same file sends it once; same key added twice → posted once.
- [ ] Implement; `build.bat` adds `--add-data "discord.json;."` only `if exist discord.json`; `.gitignore` gets `discord.json`, `discord_outbox.json`, `grind.sqlite`. Test, commit.

### Task 4: Wire shop alerts into the app
**Files:** Modify `sniper.py` (watch loop cadence, `apply_seen`, beep), `companion.py` (settings keys, `GET /discord`, `POST /api/discord/link|unlink|test`, state), `web/index.html` (Settings → Discord, Now status, Shops → My shop + while-you-were-away), `README.md`.
**Interfaces — Consumes:** Tasks 1–3. **Produces:** `state["myshop"] = ShopWatch.status + {"reason"}`.
- [ ] Settings keys `discord_enabled` (False), `discord_post_sales` (True); `discord_id`/`discord_name` only via the link endpoint.
- [ ] Test (`tests/test_apply_seen.py` style): a seen with `myshop` totals 0→450000 twice → one outbox entry and `state["myshop"]["sales"]` has it; with `discord_enabled` False → no outbox entry, sale still listed.
- [ ] "Your shop closed": watched shop gone with no HUD for 3 reads while the game window is there → one ping; "Shop sold out" from ShopWatch → one ping.
- [ ] UI, README "Your data" + admin guide, run app from source against the live game, commit.

### Task 5: HUD EXP reader
**Files:** Modify `reader.py`; Test `tests/test_myshop.py` cases (same frames show the HUD) → `tests/test_hud_exp.py`.
**Interfaces — Produces:** `read_hud_exp(frame, hud_line) -> {"exp": int, "pct": float} | None`; `seen["hud"]["exp"]`, `seen["hud"]["exp_pct"]`.
- [ ] Tests: both samples → 73665, 60.01; existing cases' HUD still read.
- [ ] Implement, test, commit.

### Task 6: Grind tracker
**Files:** Create `grind.py`; Modify `sniper.py`, `companion.py` (`GET /api/grind`, `POST /api/grind` pause/reset/no_reset), `web/index.html` (Now strip, Train "your EXP/hr", history); Test `tests/test_grind.py`.
**Interfaces — Produces:** `Grind(db_path).update(exp, pct, level, map_id, map_name, now)`, `.mesos(mesos, now)`, `.summary(now) -> {"running", "exp_hr", "exp_hr_5m", "ttl_s", "mesos_hr", "map"}`, `.history(limit) -> [rows]`, `.by_map() -> {map_id: exp_hr}`.
- [ ] Tests: 10 min at +100 EXP / 6 s → 60,000/hr ±1%; ttl `None` before 60 s; 15 s idle pauses; map change → new segment row; level-up (exp 122,000 @99.4% → 500 @0.2%, need 122,755) adds 1,255; a lone lower read ignored.
- [ ] Implement, wire, test, commit.

### Task 7: Sell or keep (phase 1)
**Files:** Create `advisor.py`; Modify `gamedata.py` (`npc_price(name)` from OSMS `price` + `NPC_PRICES`), `sniper.py` (`set_tips` line, hovered list), `companion.py` (`GET /api/sellkeep`, `POST /api/star`), `web/index.html` (Shops → Sell or keep); Test `tests/test_advisor.py`.
**Interfaces — Produces:** `verdict(name, count, profile, data, market) -> {"verdict": "keep"|"npc"|"fm"|"drop"|"unknown", "why": str, "price": int|None}`.
- [ ] Tests: starred → keep; in-progress quest item → keep "Jane and the Mushroom: need 15, have N"; quest within 10 levels → keep; equip in `gear()` → keep; NPC ≥ 0.8 × FM after fee → npc; liquid → fm "sells fast"; equip fm adds "check its stats"; no data → unknown "No market data. Check it yourself."
- [ ] Implement, wire, test, commit.
