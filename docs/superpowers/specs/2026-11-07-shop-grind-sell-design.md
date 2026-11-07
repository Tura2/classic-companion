# Shop sale alerts, grind tracker, sell or keep: design

Date: 2026-11-07. Branch `feat/shop-grind-sell`, stacked on `fix/reader-accuracy` (PR #23, still open).
Source: the owner's feature brief "Companion: next features" (pasted 2026-11-07), plus what the
code and two live frames of the owner's own shop showed. README's "Rules the app follows" apply to
everything here and are not repeated.

## What the live frames settled (2026-11-07, Tura1 in Free Market <7>)

Frames are in `samples/raw/` (git-ignored: they show names and chat).

- **The owner's shop is a personal store**: the character sits in it, and the window shows the
  title the owner typed ("Scrolls and more"), the character, buttons **SOLD ITEMS**, **OPEN STORE**
  (grayed while open) and **CLOSE STORE**, a mesos box under the character (the character's own
  mesos, 428,351, same as ITEM INVENTORY), the item list ("Cape STR Scroll: Interme... / 1 for
  388,887 mesos", the same row format other people's shops use), a visitor chat log ("X has
  entered." / "X has left the room.") and a red notice: **"Please be aware that a 3% fee will be
  deducted from sales."** Hired Merchants are out of scope.
- **SOLD ITEMS opens a side panel** to the right: "Total Sales / Total Received", two numbers
  ("0 mesos" / "0 mesos"), then empty rows for sold items. It stays open on its own once opened.
- **The Free Market fee is 3%** (stated by the game). Sell or keep subtracts it from FM prices.
- **The UI scale isn't height/1200.** Both frames are 1920×1080, but the game drew its UI at two
  different sizes (the mini map frame about 150 px wide in one, about 210 in the other; the reader
  assumes about 305 at 1080). The owner switched the game's graphics setting between them. New
  readers here take their scale from what they find (a button's text height, as `read_shop`
  already does with `ln[4] / 12`), not from `frame.height / 1200`.
- **The HUD EXP reads "EXP 73,665 [60.01%]"**: the number and the percent, at the right of the HUD.
  So EXP needed for the level is `exp / pct` (122,755 here): no EXP table needed.

Still to see: a frame **after a sale** (what the sold row looks like, whether the mesos box and
Total Received both go up, and whether the chat log prints a line). A watcher is saving frames
whenever the shop's panels change.

## 1. Shop sale alerts on Discord

### Reader (`reader.py`)
- `find_windows` learns the owner's shop by its **CLOSE STORE** button (OCR, fuzzy like the
  others), with SOLD ITEMS above it as a second anchor. Key `myshop`, kept apart from `shop`
  (other people's, by LEAVE STORE). Scale `u` = the button's text height / its height at the
  1200 px UI size (measured from the samples).
- `read_my_shop(frame, anchor, u)` returns `{"title", "mesos", "items": [...listed rows...],
  "sold_panel": {"total_sales", "total_received", "rows": [...]} | None}`. Offsets from the
  anchor are measured on both samples (two UI sizes) and tested on both. The listed rows reuse
  `_shop_items`.
- `Reader.read_my_shop_only(frame, anchor)`: the slow re-read while the owner's shop is open.

### Sale logic (`shopwatch.py`, new, pure, unit-tested)
`ShopWatch.update(read, now)` → list of confirmed sales.
- Primary signal: **Total Sales** (gross). It only goes up during a store session. Fallback when
  the panel is closed: the listed rows (a row's count drops or the row goes gray/vanishes) and the
  mesos box going up.
- A change counts after **2 agreeing reads** in a row. A total that goes down, or rises by more
  than 10× the shop's listed value (minimum 10M), is a misread and dropped. A new store session
  (CLOSE/OPEN, or the total back to 0 with the store re-opened) resets the baseline, it is not a
  sale.
- Which item sold: diff of the sold panel's rows, else of the listed rows' counts. If neither can
  be read: "sold something for +X mesos".
- Each sale gets an idempotency key: `store session id + total_sales after the sale`.

### Cadence (`sniper.py`)
While the owner's shop is open, `watch_loop` reads only that window every **6 s** (`MYSHOP_EVERY`,
inside the brief's 5–10 s), with a full read every 10th time. No new capture loop.

### Discord (`discord_link.py`, new)
- Config from `discord.json` (`{"webhook", "client_id"}`), bundled by `build.bat` only when the
  file exists, loaded from `paths.RES_DIR` (exe) or the repo folder (source). Git-ignored. Without
  it, Settings says "Not set up in this build" and nothing else changes.
- **Connect**: opens `https://discord.com/oauth2/authorize?client_id=…&response_type=token&scope=identify&redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fdiscord`
  (checked 2026-11-07: Discord still documents the implicit grant, "not recommended outside of
  quick prototypes"; it's fine here because the token is used once and dropped). `GET /discord`
  (served by the app) reads `access_token` from `location.hash` and POSTs it to
  `/api/discord/link` (through `trusted()`). The server calls `GET /api/users/@me`, stores
  `discord_id` and `discord_name` (global_name or username) in config.json, and drops the token
  (never written). Then it sends the test message. **Unlink** clears both. Fallback if Discord ever
  drops the implicit grant: authorization code + PKCE with the app marked Public Client. Never a
  client secret in the exe.
- **Posting**: `POST <webhook>?wait=true` with `content` "<@id> sold …", `username` = character
  name, an embed (item, quantity, price, "N% above/below the market median" from
  `source_prices`, thumbnail `item_img`, footer the shop total today), and always
  `allowed_mentions = {"parse": [], "users": [own id]}`.
- **Batching**: sales within 60 s go into one message (embeds up to 10).
- **Outbox** (`discord_outbox.json` in `APP_DIR`): every sale is written to disk before sending;
  a sender thread posts, retries with back-off on network errors and 5xx, waits `retry_after` on
  429, and drops an entry only after a 2xx. Idempotency keys of sent sales are kept (last 500), so
  a sale is never posted twice. Sends never run on the reader thread. `requests`, 10 s timeout.
- **Extras on the same pieces** (cheap, included): "Your shop closed" when the owner's shop
  was being watched and the game goes to the login screen or disconnects (the shop window and
  the HUD both gone for 3 reads in a row while the game window is still there); "Shop sold out"
  when no listed row is left. Lie Detector ping: needs a sample of the Lie Detector window; left
  for later.

### Config keys
`discord_enabled` (false), `discord_id`, `discord_name`, `discord_post_sales` (true once linked),
added to `SETTINGS`/`DEFAULT_SETTINGS`/`clean_setting` (id and name are set only by the link
endpoint, not by the settings POST).

### Dashboard
- Settings → Discord: what's sent (item, quantity, price, character name, shop total) and where
  (our server's #shop-sales only); Connect / Unlink, Send test message, on/off switch; or "Not set
  up in this build".
- Now tab: "Watching your shop" / "Can't see your shop" + reason (screen reading off, game
  minimized, shop window not found).
- Shops tab: "My shop" block: sales this session (item, qty, price, time) and the total; a "While
  you were away" summary of sales since the dashboard was last looked at, until dismissed.
- Local beep on a sale (`cfg["sound"]`, `winsound.MessageBeep()`).

### README
"Nothing is uploaded anywhere" becomes: nothing is uploaded unless you connect Discord; then each
sale (item, quantity, price, character name, shop total) is posted to the group's #shop-sales
channel, and nothing else. Add the admin setup guide from the brief to README.

## 2. Grind tracker (phase 1 now; phase 2 later)

- Reader: `read_hud_exp(frame, hud_line, u)` reads "EXP 73,665 [60.01%]" right of the HUD's LV
  anchor, every full read. Returns `{"exp", "pct"}`.
- `grind.py` (new, pure, unit-tested) `Grind.update(exp, pct, level, map_id, now)`:
  session starts on the first EXP gain; pauses after 15 s without a gain or on a map change
  (each map a segment), resumes on the next gain; "No reset" keeps one session across maps.
  Level-up: pct wraps, gained = (need_old − exp_old) + exp_new, with need = exp / pct. Two-reads
  rule; EXP going down without a level-up is dropped. EXP/hr for the session and the last 5 min;
  time to level = (need − exp) / 5-min rate, "—" until 1 minute of data. Mesos/hr from inventory
  reads when the inventory is open.
- `grind.sqlite` in `APP_DIR`: `sessions(start, end, map_id, map, level_start, level_end,
  exp_gained, mesos_gained, potions_cost, party)`; a row per map segment.
- Dashboard: Now strip "EXP/hr · time to level · mesos/hr" with Pause/Resume and Reset; Train tab
  "your real EXP/hr here" per map from the log; a small history table.
- Phase 2 (not now): potions from quick slots, pickups from the message log, net profit, route
  strip numbers.

## 3. Sell or keep (phase 1 now; phase 2 later)

- `advisor.py`: `verdict(name, count, profile, data, market) -> {"verdict", "why", "price"}`, rules
  in the brief's order (starred, quest in progress, quest within 10 levels, gear you'll wear,
  untradable, NPC vs FM, equips "check its stats", no data). Thresholds in one block at the top.
  `fm` = the lower of MSC median and Cozy, **minus the 3% fee**. Liquid = at least 10 sales on the
  last full day (`vol`) and sell-through `st` ≥ 0.5 (MSC fields; the market file keeps no total).
- **NPC prices**: OSMS `items.json` has `price` for 1,181 equips (what an NPC pays), used with
  `NPC_PRICES` (hand list for etc). Use/etc items mostly have none → "NPC price unknown". (The KB's
  NPC sell-back numbers come from NiaDB/MeowDB, which needs permission first, so they're not used.)
- Phase 1: the verdict as one more line on the tooltip price strip, and every item hovered this
  session in a "Sell or keep" block (Shops tab) in three groups with totals and a star toggle
  (stars in `profile.json` → `starred`).
- Phase 2 (not now, needs inventory-tab samples): full-tab icon matching.

## Order of work
1. Discord plumbing + outbox + Settings (no samples needed). 2. Owner shop reader + ShopWatch
(on the samples, finished when the after-sale frame arrives). 3. Sell or keep phase 1.
4. Grind tracker phase 1. Tests for every pure piece; reader tests on masked cases in
`samples/cases/` (git-ignored), as PR #23 does.

## Decisions made here (Claude's calls, for the owner to check)
- Owner shop found by CLOSE STORE; scale from the button's text height.
- 6 s owner-shop cadence; sanity cap 10× listed value, at least 10M.
- Liquid = ≥ 10 sales a day and sell-through ≥ 0.5; NPC wins when it pays ≥ 80% of the FM price after fee.
- A shop row's "1 for 12,999" is the bundle, not the stock (the stock is the unread number on its
  icon), so a sale is named by the one row whose price the Total Sales rise is a whole multiple of.
- Your store is told from someone else's (which shows the same fee notice) by its one orange button.
- The HUD EXP is read by digit shape (OCR can't read its font); shapes for 0,1,3,5,6,7 ship from the
  samples, the rest are learned from CHARACTER STAT.
- Outbox and grind log are local files in `APP_DIR`; nothing new leaves the PC except Discord posts.
- Lie Detector ping postponed until there's a sample.
