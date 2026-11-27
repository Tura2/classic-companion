# Discord through the report server: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the report server, move Discord posting behind it (signed cards, server-built
messages, one channel), and add grind-session and valuable-pickup posts.

**Architecture:**
- **Server.** The Vercel project `reports-server/` gets a shared guard module, a hardened
  `api/report.js`, and a new `api/discord.js`.
- **App.** `app/discord_link.py`'s Outbox posts structured `{card, kind, data}` to the server
  instead of a webhook. `companion.py` and `app/sniper.py` feed it sales, notices, finished grind
  cards (a hook on `Grind`) and pickups.

**Tech Stack:** Node 18+ (CommonJS, `node --test`), Python 3 (pytest), vanilla JS dashboard
(`web/index.html`).

**Spec:** `docs/superpowers/specs/2026-11-27-discord-via-server-design.md`

## Global Constraints

- **Caps** (env, with defaults):
  - `DAY_STORED` 100;
  - `DAY_NEW_KEYS` 50;
  - `DAY_PER_INSTALL` 25;
  - per IP: 30 requests / 10 min;
  - per Discord ID: 20 posts / 10 min.
- **App constants:** `GRIND_SHARE_MIN = 600` (seconds of `active_s`), `DROP_SHARE_MIN = 80_000`
  (market median per item, strictly greater), `DROPS_A_DAY = 10`.
- **`allowed_mentions`** is always `{"parse": [], "users": [<card id>]}`. The client never sends a
  URL, a mention or free text.
- **Username:** the character name kept to `[A-Za-z0-9 ]`, up to 12 characters, else "Companion".
  **Game names:** `[A-Za-z0-9 '().:-]`, up to 40 characters.
- **The card:** `card = "v1.<id>.<issued>.<base64url HMAC-SHA256(CARD_SECRET, "v1.<id>.<issued>")>"`.
- **Item picture:**
  `https://raw.githubusercontent.com/ohmi69/osms_datamine_dashboard/main/data/current/images/items/<id:08d>.png`
- **The day counters** live in `index.json` under the key `"#day"`.
- **`REPORTS_MODE`** is `on|count|off`. **`DISCORD_MODE`** is `on|off`. `off` means 503.
- **New env vars:** `UPLOAD_KEY` (may be comma-separated), `DISCORD_WEBHOOK`, `DISCORD_CLIENT_ID`,
  `CARD_SECRET`, `BLOCKED_IDS`.
- Everything Discord stays off until the player connects. Sales is on after Connect (as today);
  grind and pickups are off.
- **Secrets:** never print `UPLOAD_KEY`, `CARD_SECRET` or the webhook. Never commit
  `reports.json` or `discord.json`.

## Review Focus

1. **An old config (`discord_id`, no `discord_card`) and an old outbox** (`"text"` entries,
   webhook-era payloads) must load without crashing. The old entries are dropped, and the player
   sees "Connect again". Test in Task 3.
2. **A grind card saved final more than once** (`_new_session` then `close`) must post once. Test
   in Task 4 (the key `grind:<card id>`).
3. **The same pickup line seen on two corner reads** must post once (the Outbox key dedupes; the
   corner already counts once). Test in Task 3 (the same key twice).
4. **The server's day rollover at UTC midnight** must reset the counters, not keep refusing. Test
   in Task 1.
5. **Server unreachable at Connect** must give a clear error and keep nothing half-linked. Test
   in Task 4.

---

### Task 1: Harden the report endpoint

**Files:**
- Create: `reports-server/lib/guard.js`
- Modify: `reports-server/api/report.js`
- Test: `reports-server/report.test.js` (the fixture's `"png!"` becomes real PNG bytes), new
  `reports-server/guard.test.js`

**Interfaces:**
- Produces (`lib/guard.js`):
  - `keyOk(given: string, env.UPLOAD_KEY: string) -> bool`: comma-separated, each compared with
    `crypto.timingSafeEqual`.
  - `throttle(store: Map, who: string, limit: number, windowMs: number, now: number) -> {ok: bool, retry_after: number}`:
    a sliding window.
  - `mode(value, allowed: string[], dflt) -> string`.
  - `today(now = Date.now()) -> "YYYY-MM-DD"` (UTC).

**Steps:**
- [ ] Write `guard.test.js`:
  - `keyOk("b", "a,b") === true`, `keyOk("", "a") === false`, `keyOk("a ", "a") === false`;
  - `throttle`: 30 ok, the 31st not ok within 10 min, ok again after the window;
  - `today(Date.UTC(2026,10,27,23,59))` gives "2026-11-27".
- [ ] Add these tests to `report.test.js`, with fake `now`, `env` and `ip` passed through `deps`:
  - "pictures stop after DAY_STORED a day, reports still count": `DAY_STORED: "2"`, 3 new keys →
    the third `stored === false`, `index()["#day"].stored === 2`;
  - "a new key over DAY_NEW_KEYS is refused, a known key still counts" (429);
  - "DAY_PER_INSTALL" (429 on the 26th from one `install`);
  - "a new UTC day resets the counters";
  - "a .png that isn't a PNG is refused" (400), and the same for `.jpg` without `FF D8 FF`;
  - "REPORTS_MODE count stores no pictures; off answers 503 without asking GitHub";
  - "either of two upload keys is accepted";
  - "31 requests from one IP in 10 minutes: the 31st is 429".
- [ ] Run `cd reports-server && node --test`. The new tests should fail.
- [ ] Implement in `report.js`:
  - `file()` reads `index["#day"]`, resets it on a new `today()`, and applies the caps inside the
    same commit loop;
  - `check()` verifies the magic bytes;
  - `handler` gets `deps.now`, `deps.ip` (default: the first `x-forwarded-for`), and a
    module-level `Map` for the throttle;
  - `wantFiles` is unchanged.

  A cap refusal returns `{error}` with 429 before any blob upload. `index.json` is written only
  when the report is taken.
- [ ] Run `node --test`. All should pass.
- [ ] Commit: `feat(server): day caps, real-picture check, mode switch, key rotation, IP throttle`.

### Task 2: The Discord endpoint

**Files:**
- Create: `reports-server/api/discord.js`, `reports-server/discord.test.js`

**Interfaces:**
- Consumes: `keyOk`, `throttle`, `mode` from Task 1.
- Produces:
  - **HTTP:**
    - `GET /api/discord` → `{client_id, on}`.
    - `POST {link:{token}}` → `{id, name, card}`.
    - `POST {card, kind, data}` → `{ok:true}`.
  - **Exports:** `makeCard(id, issued, secret)`, `readCard(card, secret) -> id|null`,
    `render(kind, data, id) -> webhook payload|null` (null means 400).

**Steps:**
- [ ] Write `discord.test.js`, with fetch stubbed for Discord `/users/@me` and the webhook:
  - "link asks Discord who the token is and returns a card that reads back to that ID". The token
    is never in the response.
  - "a changed card, or one signed with another secret, is refused" (401).
  - "a blocked ID is refused" (403, `BLOCKED_IDS: "1,123"`).
  - "every post mentions only the sender" (`allowed_mentions` for each kind).
  - "sale renders like today", ported from `tests/test_discord.py`:
    - content `<@123> sold Bazlud ×1 for 24,999 mesos`;
    - "25% above the market median";
    - thumbnail from `item_id` 4000000 → `.../items/04000000.png`.
  - "notice sends only its fixed sentences": `soldout` → "your shop sold out: time to restock.";
    an unknown notice → 400.
  - "grind renders map, time, EXP/hr, levels, kills, party and top pickups".
  - "drop renders 'picked up **Work Gloves** (about 120,000 mesos each)'".
  - "names with @, <, or links are cleaned"; a username over 12 characters is cut, and an empty
    one becomes "Companion".
  - "21 posts in 10 minutes from one ID: the 21st is 429 with retry_after".
  - "Discord's 429 is passed back with its retry_after".
  - "DISCORD_MODE off is 503", and "a wrong upload key is 401".
- [ ] Run `node --test`. The new tests should fail.
- [ ] Implement `discord.js`:
  - Discord's API is `https://discord.com/api`.
  - Post to `DISCORD_WEBHOOK + "?wait=true"`.
  - The fixed notices are:
    - `connected`: "connected Companion: what you share will show up here.";
    - `test`: "this is a test from Companion.";
    - `soldout`: "your shop sold out: time to restock.";
    - `closed`: "your shop closed: the game left the Free Market (disconnected, or back at the login screen).";
    - `correction`: "correction: {items} didn't sell after all, that post was wrong (your shop's Total Sales doesn't show it)."
  - A grind embed's fields: Time `Xh Ym`, EXP/hr, EXP gained, Level `a → b` (or `a`), Kills,
    `Party`/`Solo`, and Top pickups (up to 3).
  - Numbers are formatted `toLocaleString("en-US")`.
- [ ] Run `node --test`. All should pass.
- [ ] Commit: `feat(server): Discord posts through the server, signed cards, built messages`.

### Task 3: The app's Discord client

**Files:**
- Modify: `app/discord_link.py`
- Test: `tests/test_discord.py` (rewritten for the new shape)

**Interfaces:**
- Produces:
  - `server_url(reports_cfg) -> str|None`: the reports `url` with `/api/report` → `/api/discord`.
  - `fetch_setup(reports_cfg, get) -> {"client_id", "on"}|None`: cached on success.
  - `link(reports_cfg, token, post) -> {"id", "name", "card"}`: raises `ValueError` with a
    player-facing message.
  - `Outbox(path, target, post, build)`:
    - `target()` returns `{"url", "key", "card"}` or None;
    - `build(sales)` returns the sale `data`;
    - posts `{card, kind, data}` with the header `X-Companion-Key`;
    - kinds are `sale|notice|grind|drop`;
    - on load, it drops entries of any other kind;
    - 400 drops the entry; 401 sets the error "Connect Discord again"; 403 sets "Posting is
      blocked for this Discord account"; 429/503 wait.
  - `sale_data(sales, median, item_id, total_today) -> dict`.
  - `grind_data(card: dict) -> dict|None`: None under `GRIND_SHARE_MIN`.
  - `drop_data(name, count, median, item_id, map_name) -> dict|None`: None unless `median > DROP_SHARE_MIN`.
  - `linked(cfg) -> bool` (`discord_enabled` and `discord_card`).
  - `share(box, cfg, kind, data, key) -> bool`: checks `linked`, the kind's switch
    (`discord_post_sales|discord_post_grind|discord_post_drops`; notices need only `linked`) and,
    for `drop`, `DROPS_A_DAY` (counted in the outbox file under `"drops": {"date", "n"}`).
  - **Removed:** `load_discord_config`, `who_is`, `sale_message`, `text_message`. `authorize_url`
    is kept.

**Steps:**
- [ ] Rewrite `tests/test_discord.py`. Keep the batching, 429, offline-restart and same-sale-once
  tests on the new shape (with the posts recorded with their headers). Add:
  - `test_posts_go_to_the_server_with_the_card_and_key`;
  - `test_old_text_entries_are_dropped_on_load`;
  - `test_401_keeps_the_queue_and_asks_to_connect_again`, and 400 dropping the entry;
  - `test_grind_data_needs_ten_minutes` (599 → None, 600 → dict with `loot_top` of at most 3, by
    count);
  - `test_drop_data_over_80k_only` (80_000 → None, 80_001 → dict, None median → None);
  - `test_share_respects_each_switch_and_the_link`;
  - `test_ten_drops_a_day` (the 11th refused, a new day ok);
  - `test_server_url_from_reports_url`;
  - `test_link_error_says_what_happened` (a 502 from the server → `ValueError`).
- [ ] Run `pytest tests/test_discord.py -q`. These should fail.
- [ ] Implement them in `app/discord_link.py`.
- [ ] Run `pytest tests/test_discord.py -q`. All should pass.
- [ ] Commit: `feat(discord): post through the report server, grind and pickup data`.

### Task 4: Wire it into the app and Settings

**Files:**
- Modify: `companion.py` (`make_outbox`, `discord_status`, `discord_send` → notices,
  `/api/discord/link|test|unlink`, the SETTINGS keys)
- Modify: `app/sniper.py` (`DEFAULTS`: `discord_post_grind: False`, `discord_post_drops: False`;
  `handle_myshop` notices; `handle_corner` pickups; the Grind hook)
- Modify: `app/grind.py`
- Modify: `web/index.html` (`discordCard`, the switch handlers)
- Test: `tests/test_grind_session.py` (the hook), `tests/test_grind_app.py` (pickups through
  `handle_corner`), and a new `tests/test_discord_app.py` (link and status through companion's
  functions)

**Interfaces:**
- Consumes: Task 3's functions.
- Produces:
  - `Grind.on_final: Callable[[dict], None] | None`. It's called from `save_card` when `final` is
    true and a row was kept, with the row's columns plus the parsed `data`, and `id`.
  - `state["discord_share"](kind, data, key)`.

**Steps:**
- [ ] Write the tests:
  - `test_on_final_gets_the_card_once_per_session` (`_new_session` then `close` → posted once,
    via the key `grind:<id>`);
  - `test_a_valuable_pickup_is_shared_and_a_cheap_one_isnt` (`handle_corner` with a fake
    `app.state["discord_share"]` and a market `{"Work Gloves": {"p": 120000}, "Snail Shell": {"p": 50}}`);
  - `test_status_wants_connect_again_for_an_old_link` (`discord_id` without a card →
    `linked False`, `relink True`);
  - `test_link_unreachable_keeps_nothing` (the link raises → the cfg has no card or `discord_id`
    written).
- [ ] Run them. They should fail.
- [ ] Implement:
  - `make_outbox` takes setup from `autoreport.load_reports_config()`.
  - `discord_status` adds `relink`, `post_grind` and `post_drops`, and `authorize` (from
    `fetch_setup`, in a background thread; None until it's known).
  - The link route calls `discord_link.link` and stores `discord_card`, `discord_id` and
    `discord_name`.
  - The notices are queued as `notice` with `{"what": ...}` (plus `{"items": [...]}` for a
    correction).
  - `sniper.App` sets `self.grind.on_final`.
  - The dashboard card has three switches, with the copy from the spec, and "our server's
    Companion channel" replaces `#shop-sales`. A relink shows "Connect again (once) to keep
    posting" with the Connect button.
- [ ] Run the full suite: `python -m pytest -q -p no:cacheprovider`. It should be green except
  the known worktree-only `test_a_real_tab[inventory_etc]`.
- [ ] Commit: `feat(discord): grind sessions and valuable pickups, three switches in Settings`.

### Task 5: Builds, docs, deploy

**Files:**
- Modify: `build.bat` (drop `--with-discord`; `--with-reports` is now the release path, and its
  wording changes), `docs/discord.md`, `README.md` (the Discord lines), `reports-server` header
  comments (the new env vars)

**Steps:**
- [ ] Edit the build script and the docs. The admin steps come from the spec's "Admin steps".
- [ ] Run `node --test` and pytest again: all green.
- [ ] Commit: `docs: Discord through the server; builds carry reports.json, not discord.json`.
- [ ] Deploy:
  - Copy `reports-server/` to a scratch deploy folder.
  - Add `DISCORD_CLIENT_ID` and `DISCORD_WEBHOOK` to Vercel from the player's local
    `discord.json`, read by a script, never printed. Add `CARD_SECRET` (32 random bytes, never
    printed).
  - `vercel deploy --prod`.
- [ ] Smoke test against the live server:
  - `GET /api/discord` gives `on: true` and a `client_id`.
  - A POST with a bad card is 401.
  - A report with a fake PNG is 400.
  - The player does Connect, then the test message, in their own app copy (the player's step).
- [ ] Push the branch and open the PR (base `feat/problem-reports`). Don't merge.
