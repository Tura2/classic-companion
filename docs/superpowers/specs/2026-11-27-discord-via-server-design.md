# Discord through the report server, and a harder server

Date: 2026-11-27. Builds on `feat/problem-reports` (PR #72): the Vercel project `companion-reports`
(`reports-server/`) and `app/autoreport.py`.

## Why

- Public builds are going to ship with `reports.json`, so every player can send problem reports.
  Anything inside the exe can be pulled out, so the upload key is effectively public. Today the
  server takes anything that passes a format check: someone with the key can invent problem keys
  without end, fill the private repository with "pictures" that aren't pictures, and use up the
  GitHub token's 5,000 calls an hour so real reports stop landing.
- Discord today goes straight from the exe to a webhook in `discord.json`. That's why public builds
  have no Discord at all. Moving it behind the server takes the webhook out of the exe, so every
  player can get Discord.
- The player wants more in Discord: their grind sessions and their valuable pickups, beside the
  shop's sales. **Everything goes to one channel.** No new channels.

## Goals

1. **Harden the report endpoint** so a public key can't flood the repository or the token.
2. **Discord through the server.** The exe holds no webhook. Each player proves who they are once
   (Connect Discord), and from then on can only post messages that tag themselves.
3. **Three kinds of post, one channel, each switched separately in Settings, all off by default:**
   - shop sales (today's feature, unchanged in content);
   - **grind sessions** of more than 10 minutes, sent on their own when the session ends;
   - **valuable pickups:** an item picked up whose market median per item is above 80,000 mesos.

## Non-goals

- No problem-report pings to Discord (offered, not chosen).
- No more channels, no bot, no slash commands, no leaderboard or weekly digest (for now).
- No storage service (Upstash or similar): approach 1 was picked.
- No change to what a problem report contains or when Companion sends one.

## Anti-goals (a failure even if it works)

- A post that tags anyone but its sender, or `@everyone`, a role, or a link the sender typed.
- Anything posted while its switch is off, or before the player connected Discord.
- A secret in the exe beyond the upload key (the GitHub token and the webhook stay on Vercel).
- A sale, session or pickup posted twice, or lost because the internet was down.

## Approaches (picked: 1)

1. **Stateless server (picked).** Same Vercel project, a second endpoint beside `/api/report`.
   - Connect returns a signed card that proves the player's Discord ID; the server stores nothing.
   - The blocklist lives in an environment variable (a redeploy, about a minute).
   - Flooding is limited by the app's own caps, Discord's webhook limit, and a best-effort count in
     the server's memory.
   - Free, and no new service.
2. **With a small store (Upstash Redis, free via Vercel).** Exact per-player and daily caps, and
   instant blocking. But it adds a service to sign up for, look after, and that can go down.
   Can be added later without changing the app.
3. **A real Discord bot.** Ruled out: it needs an always-on host, which Vercel's free plan isn't.

## Design

### 1. Report endpoint hardening (`reports-server/api/report.js`)

- **Day counters in `index.json`,** under a key the client can't send. `KEY` allows only
  `[A-Za-z0-9_.:x-]`, so the counters go under `"#day"`:
  `{"date": "YYYY-MM-DD", "stored": n, "new_keys": n, "installs": {id: n}}`. They're read and
  written in the same commit as the report, so there's no extra call. A new UTC day resets them.
- **Caps** (environment variables, with defaults):
  - `DAY_STORED` 100: reports with pictures in a day. After that, reports only count.
  - `DAY_NEW_KEYS` 50: new problem keys in a day. After that, a report with a new key is refused
    (429), so `index.json` can't be grown without end.
  - `DAY_PER_INSTALL` 25: reports from one install id in a day (the same as the app's cap). Over
    it: 429. The id is the client's word, so this guard is weak; the two caps above are the real ones.
- **Files must be real pictures.** Decode the base64 and check the first bytes: PNG `89 50 4E 47`
  for `.png`, JPEG `FF D8 FF` for `.jpg`. Otherwise 400.
- **Mode switch** `REPORTS_MODE`: `on` (default), `count` (take reports, store no pictures), or
  `off` (answer 503 so the app keeps reports and tries later).
- **Key rotation.** `UPLOAD_KEY` may hold several keys, comma-separated, and any of them is
  accepted. A new key ships in a release while the old one keeps working, and comes out later.
- **Best-effort throttle in memory,** per caller IP (`x-forwarded-for`): at most 30 requests in 10
  minutes, else 429. It only lives while the function instance is warm. That's fine: it's a speed
  bump, not the guard.
- The app already treats 429 and 503 as "try later": `autoreport` drops a report only on 400, 413
  or 422.

### 2. Discord endpoint (`reports-server/api/discord.js`)

The environment gets: `DISCORD_WEBHOOK`, `DISCORD_CLIENT_ID`, `CARD_SECRET` (random, at least 32
bytes), optional `BLOCKED_IDS` (comma-separated Discord IDs), and `DISCORD_MODE` (`on` or `off`).
The same `x-companion-key` header as the reports is required on every call.

- **`GET /api/discord`** returns `{"client_id": ..., "on": bool}`. The client ID is public and
  needed for the Connect page, so `discord.json` isn't needed in the build any more.
- **`POST /api/discord {"link": {"token"}}`:** the server asks Discord `/users/@me` with the token,
  then drops the token. It returns `{"id", "name", "card"}`, where:
  - `card = "v1.<id>.<issued unix>.<sig>"`;
  - `sig = base64url(HMAC-SHA256(CARD_SECRET, "v1.<id>.<issued>"))`.
  - The name isn't in the card: the server takes the shown name from each post, sanitized.
  - The app keeps the card in its config instead of `discord_id`. The token never touches a file,
    as today.
- **`POST /api/discord {"card", "kind", "data"}`:** checks the card's signature (constant-time)
  and refuses blocked IDs (403). Then **the server builds the message** from structured data, so a
  post can't carry free text, links or mentions of the sender's choosing:
  - `allowed_mentions = {"parse": [], "users": [id]}` always;
  - `username` = the character's name, kept to `[A-Za-z0-9 ]`, up to 12 characters (the game's
    limit), else "Companion";
  - thumbnails built by the server from an item's numeric id (`item_id`, up to 8 digits), as
    `https://raw.githubusercontent.com/ohmi69/osms_datamine_dashboard/main/data/current/images/items/<id:08d>.png`.
    This is the host `gamedata.item_img` already uses. The client never sends a URL.
- **The kinds and what each carries** (numbers are checked as numbers, names as game names,
  `[A-Za-z0-9 '().:-]`, up to 40 characters):
  - `sale`: today's sale batch: up to 10 of `{item, count, price, median?}`, plus `total_today?`.
    It renders like `discord_link.sale_message` today, which moves to JS.
  - `notice`: one of a fixed set: `connected`, `test`, `soldout`, `closed`, `correction` (with the
    item list). Sent as fixed sentences, so nothing free-form.
  - `grind`: `{map, minutes, exp_gained, exp_hr, level_start, level_end, pct_start?, pct_end?,
    kills_total?, party, loot_top: up to 3 of {name, count}, mesos?, job?}`.
    - Rendered as one embed: the map in the title, then time, EXP/hr, EXP gained, levels, kills,
      solo or party, the top three pickups, and the mesos.
  - `drop`: `{item, item_id?, count, median, map?}`. A sale's items may carry `item_id` too, for
    their pictures.
    - Rendered as "<@id> picked up **item** (about 120,000 mesos each) on map", with the item's picture.
- **Limits:**
  - In memory, per Discord ID: 20 posts in 10 minutes, else 429 with `retry_after`.
  - Discord's own 429 is passed back with its `retry_after`; the app's Outbox already waits on it.
  - `DISCORD_MODE=off` answers 503.
- **Card revocation:** add the ID to `BLOCKED_IDS`. If `CARD_SECRET` leaks, rotating it makes
  everyone press Connect again.

### 3. The app

- **`app/discord_link.py`:**
  - The `Outbox` posts `{card, kind, data}` to the server URL. That URL is the reports URL with
    `/api/report` swapped for `/api/discord`, using the same key header. `webhook()` becomes
    "server set up, Discord on, and a card".
  - Batching, dedupe, the disk queue and backoff stay as they are.
  - `sale_message` and `text_message` give way to small builders of the structured `data`. The
    message text now lives on the server.
- **`load_discord_config` goes.**
  - Setup comes from `reports.json` (already loaded by autoreport) plus `GET /api/discord` for the
    client ID, fetched in the background when Settings or Connect needs it, and cached for the run.
  - A build without `reports.json` shows "Not set up in this build", as today.
- **Connect (`companion.py` `/api/discord/link`):**
  - The page's token goes to the server's link call instead of to `who_is` locally.
  - The config gets `discord_card` and `discord_name` (and `discord_id`, for showing only).
  - An old config with a `discord_id` but no card counts as not linked: the card says
    "Connect again (once) to keep posting". Old queued payloads are dropped, since they're in the old
    format.
- **Settings → Discord card:** three switches, all off until the player turns them on (after
  Connect, sales stays on as today):
  - "Post my shop's sales". The sub-text is the same as today.
  - "Share my grind sessions": "Sessions over 10 minutes, when they end: map, time, EXP/hr, levels,
    kills, top pickups".
  - "Share valuable pickups": "Items worth over 80,000 mesos each (market median)".
  - The channel's name in the copy: "our server's Companion channel". The channel's real name is the
    player's to set in Discord.
  - Config keys: `discord_post_sales` (exists), `discord_post_grind`, `discord_post_drops`, plus the
    existing `discord_enabled` master switch.
- **Grind sessions:**
  - When a card is saved with `final=True` and `active_s` ≥ 600 (for a party-quest run, its whole
    time), and the switch is on, queue a `grind` post keyed `grind:<card id>`.
  - That covers the session ending on a map change, a break or the app closing. A post queued at
    close goes out on the next start, since the Outbox is on disk.
  - `exp_hr` is the card's own: the paced figure, or the PQ's.
  - Sessions in a town or with no EXP aren't cards, so they're never posted.
- **Valuable pickups:**
  - In `handle_corner`, for each item picked up, look up `data.market.items[name]["p"]`. If it's
    more than 80,000, and the switch is on, queue a `drop` post.
  - Its key: `drop:<session start>:<name>:<pickup time>`, with time to the second.
  - At most 10 drop posts a day, on the app's side.
  - An item with no market price isn't posted.
  - Constants: `GRIND_SHARE_MIN = 600` and `DROP_SHARE_MIN = 80_000`, both in one place.
- **Builds:**
  - `discord.json` and `--with-discord` go away.
  - `reports.json` goes into release builds. The `build.bat` wording "a private build, never a
    release" changes for reports.
  - Update `docs/discord.md` and the README.

### 4. Tests

- **Server (`reports-server/*.test.js`, node's test runner, fetch stubbed):**
  - the day caps and their reset;
  - a new key refused over the cap;
  - a fake PNG refused;
  - each `REPORTS_MODE`;
  - several upload keys;
  - the card made and checked, with tampering refused;
  - a blocked ID;
  - each kind rendered, with mentions only for the sender, names sanitized, and links refused;
  - the per-ID limit;
  - Discord's 429 passed through.
- **App (pytest):**
  - the Outbox posting to the server shape;
  - an old config being not linked;
  - a grind post only at ≥ 600 s and only once per card;
  - a pickup at 80,001 posted and at 80,000 not, a price-less pickup not posted, and the daily cap;
  - the switches off meaning nothing queued.

## Admin steps (once, after the build)

1. In Vercel (`companion-reports`), add `DISCORD_WEBHOOK` (the existing #shop-sales webhook, or a
   new one for the renamed channel), `DISCORD_CLIENT_ID` and `CARD_SECRET`. Then redeploy.
2. Optionally rename the Discord channel (for example `#companion`) and change its description.
3. Discord's developer portal needs no change: the redirect stays `http://localhost:8765/discord`.

## Decided by the player, and the calls made for them

**The player decided:**
- approach 1;
- one channel;
- grind sessions over 10 minutes, sent on their own;
- a pickup counts by market price, over 80,000 mesos;
- no problem-report pings in Discord;
- reports go to everyone.

**Calls made for the player, to be checked:**
- The cap numbers: 100 with pictures, 50 new keys, 25 per install, 30 requests per IP, 20 posts per
  Discord ID, 10 pickups a day.
- Party sessions and party-quest runs are shared too.
- The price is per item, not per stack.
- Players linked before this must press Connect again once.
- `reports.json` keeps its name.

## Left to the builder

- Exact embed colours and wording, within the fields above.
- Whether the server's two endpoints share a small module (key check, throttle).
- How the client ID fetch is cached and retried.
