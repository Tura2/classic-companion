# Companion: next features (spec for implementation)

Three features to build, in this order, plus short notes on ideas for later.

1. **Shop sale alerts on Discord**: your own player shop sells something, and you get a ping on your phone.
2. **Grind tracker**: EXP/hr, mesos/hr, time to level, and net profit after potions, per session and per map.
3. **Sell or keep**: for each item in your inventory, says whether to keep it, sell it to an NPC or sell it on the Free Market.

Read `README.md` first. Its "Rules the app follows" section applies to everything here.

---

## 0. Ground rules (apply to every feature)

- **Safe by default.** Every feature that reads the screen works only when Settings → Screen reading is on, and says so when it's off. Features that only use data (prices, quests) work without it.
- **Nothing touches the game.** Only Windows Graphics Capture of the game window and OCR. No game memory, files, input, injection, or keyboard hooks or global hotkeys. Everything is controlled from the dashboard.
- **One misread never acts.** Follow the existing pattern (`Agree` / `SteadyCounts` in `sniper.py`). A change counts only when two reads in a row agree, and an impossible value (a total going down, a jump too big to be real) is dropped as a misread.
- **Reading stays light.** Keep the current budget: a full read every 1.5 s, quick partial reads only while a specific window is open. New readers hook into `Reader.read()` / `App._watch()` and don't add a new capture loop.
- **Your data stays local.** It goes in `profile.json`, `config.json`, `scans.sqlite` or a new local SQLite file next to the app (`paths.APP_DIR`). Feature 1 is the first thing that sends data out, so it's **off by default**, says exactly what it sends and where, and the README's "Nothing is uploaded anywhere" line must be updated to match.
- **Samples before code.** The repo keeps reader samples in `samples/` (`tools/grab_samples.py`). Each new reader needs real screenshots at 1920×1080 or larger, both before and after the change it detects. Ask the owner for them, and don't guess pixel offsets.
- **Keep the existing UI language and style.** The dashboard is `web/index.html`. The first-run setup is in Hebrew. Every tab fits without scrolling the page, in a narrow window beside the game.

---

## 1. Shop sale alerts on Discord

### Goal
You leave your player shop open in the Free Market. When something sells, Companion sees it on screen and posts to a shared channel on our Discord server, tagging only you, so your phone pings. Everyone else sees the sales in the channel, which makes it social.

Everyone in the group is on the same Discord server. Each person runs their own Companion on their own PC. **Each person must get pings only for their own shop.** Setup must be one click for players who aren't technical.

### Architecture

```
Game (your shop open)
  → Companion on your PC (screen read every 5–10 s, sale = total mesos went up)
     → POST to one shared Discord webhook (#shop-sales)
        → message "<@your_id> sold X"  → only you get pinged; everyone sees it in the channel
```

- **No bot and no server.** One channel webhook is shared by everyone. A webhook can only post: it can't read the channel, and it isn't a member of the server.
- **"Connect Discord"** uses Discord OAuth2 with scope `identify` only, so Companion learns the user's Discord ID and name. That ID is the only thing that makes the ping personal.
- **Isolation comes from the design.** Each Companion stores its own Discord ID in its local `config.json` and only ever mentions that ID. `allowed_mentions` is always `{"parse": [], "users": ["<own id>"]}`, so a message can't ping anyone else, `@everyone` or a role.

### What the player does (once, about 10 seconds)
1. Settings → **Connect Discord** (one big button).
2. Discord's own page opens: "Companion wants to know who you are" → **Authorize**.
3. Back in Companion: **"Connected as <name> ✓"**, and a test message appears in `#shop-sales` tagging them.

### What the admin does (once): see the setup guide at the end of this section

### Detecting a sale (needs samples)
The reader for **your own** shop window doesn't exist yet. Today `reader.py` finds only **other people's** shops, by their LEAVE STORE button (`SHOP_BUTTONS`, `find_windows`, `read_shop`). The owner's shop window looks different, and it has a tab showing what sold and the total mesos made.

- **Primary signal: the total mesos** on the owner's shop window. It's one number, easy to read, and it only ever goes up. If it goes up, something sold.
- **Detail: the sold list or the remaining quantities.** Diff it against the previous read to find what sold and how many. The message falls back to "sold something for +X mesos" if the detail can't be read.
- **Confirm before acting.** A sale counts after 2 agreeing reads. A total that goes down, or rises by more than a sanity cap (for example 10× the shop's total listed value), is dropped as a misread.
- **Cadence.** While the owner's shop is open, read only that window every 5–10 s. This is like `read_shop_only`, but slower, because nobody is interacting with it.
- **Status in the dashboard.** The Now tab shows "Watching your shop" or "Can't see your shop", with the reason: game minimized, shop window closed, or screen reading off. Windows Graphics Capture can't see a **minimized** window. A window covered by other windows is fine.

**Open questions for the owner (needed before writing the reader):**
- Screenshots of the owner shop window, before and after a sale, with the sold/total tab visible.
- Is it a personal store (your character sits in it) or a Hired Merchant (it runs while you're offline)? If it's a Hired Merchant and you log off, there's no screen to read, so that case is out of scope.
- Does the sold/total tab stay open on its own, or do you have to open it?
- Does the game print a chat or system message when an item sells? If it does, that's a second, cheaper signal.

### Discord connection (OAuth2 implicit grant, no secret)
- Authorize URL: `https://discord.com/oauth2/authorize?client_id=<CLIENT_ID>&response_type=token&scope=identify&redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fdiscord`
- Add a `GET /discord` page in `companion.py` (served by the app itself). Its JS reads `access_token` from `location.hash` and POSTs it to a new local endpoint, `POST /api/discord/link`. It goes through the existing `trusted()` check, the same as other dashboard API calls.
- The server calls `GET https://discord.com/api/users/@me` with `Authorization: Bearer <token>`, stores `discord_id`, `discord_name` (`global_name` or `username`) in `config.json`, then **discards the token**. It is never written to disk.
- Add an **Unlink** button that clears those fields.
- **Verify first:** that Discord still allows `response_type=token` (the implicit grant) for this app. If it doesn't, fall back to the authorization-code flow with PKCE. Never ship a client secret inside the exe.

### Posting
- Endpoint: `POST <webhook>?wait=true`, JSON body:
  ```json
  {
    "content": "<@123> sold Steely Throwing Knives ×1 for 450,000 mesos",
    "username": "<character name or Companion>",
    "avatar_url": "<optional>",
    "embeds": [{
      "title": "Steely Throwing Knives ×1",
      "description": "450,000 mesos · 15% above the market median",
      "thumbnail": {"url": "<GameData.item_img(name)>"},
      "footer": {"text": "Shop total today: 1,200,000"}
    }],
    "allowed_mentions": {"parse": [], "users": ["123"]}
  }
  ```
- Item picture: `GameData.item_img(name)` (OSMS image URL). Market comparison: the existing `source_prices` / `judge` logic in `sniper.py`.
- **Batching:** sales within ~60 s go into one message, so the channel doesn't flood.
- **Reliability:** queue sends on disk, so a failed send (no internet, HTTP 429) is retried and no sale is lost. Respect `retry_after` on a 429. Never post the same sale twice: use an idempotency key per sale.
- Keep `requests` (it's already a dependency), with a short timeout. Send off the reader thread.

### Config and build
- The webhook URL and OAuth client ID come from a `discord.json` next to `build.bat`, bundled into the exe:
  ```json
  { "webhook": "https://discord.com/api/webhooks/...", "client_id": "123456789012345678" }
  ```
- Add `discord.json` to `.gitignore`. In `build.bat`, add `--add-data "discord.json;."` only when the file exists. Load it from `paths.RES_DIR`. When run from source, read it from the repo folder if present.
- If there's no `discord.json`, the Discord section in Settings says "Not set up in this build" and everything else works.
- New `config.json` keys (add them to `clean_setting` / settings whitelist in `companion.py`): `discord_enabled` (default false), `discord_id`, `discord_name`, `discord_post_sales` (default true once linked).

### Dashboard
- **Settings, Discord section:** what's sent (item, quantity, price, character name, shop total) and where (only our server's `#shop-sales`). Includes the Connect/Unlink button, a "Send test message" button and an on/off switch.
- **Shops tab, new "My shop" block:** what sold, when, for how much, and a total for the session. Includes a "while you were away" summary that shows until it's dismissed.
- **Local PC beep:** on a sale, reuse `cfg["sound"]` and `winsound.MessageBeep()` as the deal alert does.

### Requirements
| # | Requirement | Priority |
|---|---|---|
| FR-1 | Detect the owner's own shop window, separately from other people's shops | Must |
| FR-2 | Read the total mesos. A rise is a sale | Must |
| FR-3 | Diff the sold list or quantities to know what sold | Must |
| FR-4 | A sale counts after 2 agreeing reads. Impossible totals are dropped | Must |
| FR-5 | While the owner's shop is open, read every 5–10 s only | Must |
| FR-6 | Connect Discord via OAuth `identify`. Store the ID locally and discard the token | Must |
| FR-7 | Webhook and client ID come from the build. The player pastes nothing | Must |
| FR-8 | Mention only the owner (`allowed_mentions.users = [own id]`, `parse: []`) | Must |
| FR-9 | The message has item, quantity, price, shop total and the item picture, and is posted under the character name | Must |
| FR-10 | Sales within ~60 s go into one message | Must |
| FR-11 | A test message on connect, plus a test button | Must |
| FR-12 | Failed sends are queued on disk and retried. Never lost, never duplicated | Must |
| FR-13 | Now tab status: "Watching your shop" or "Can't see your shop" plus the reason | Must |
| FR-14 | "My shop" block plus a while-you-were-away summary | Should |
| FR-15 | Market comparison in the message ("15% above median") | Should |
| FR-16 | Local beep on a sale | Should |

**Acceptance:** a linked player opens their shop, a friend buys an item, and within 30 s only the owner's phone pings, with the right item and price. During an hour with the shop open and no sales, no false message is sent.

### Security notes
- The webhook URL is inside a publicly downloadable exe, so someone determined can extract it and **post** to the channel. They can't read anything. The fix is to delete the webhook, create a new one, rebuild and re-release (steps below). Players' Discord links survive this.
- The OAuth scope is `identify` only: it gives no access to messages, servers or friends.

### Admin setup guide (one time, about 5 minutes)
1. **Channel:** create a text channel `#shop-sales`. Optional: in Edit Channel → Permissions, turn off **Send Messages** for `@everyone`, so the channel holds only sales. Webhooks can still post there.
2. **Webhook:** in Edit Channel → Integrations → Webhooks → New Webhook, name it `Companion` and use `web/logo.png` as its picture → **Copy Webhook URL**. Don't paste it in chat.
3. **Application:** at <https://discord.com/developers/applications>, click New Application and name it `Companion`, with the logo (players see this on the authorize page). Go to OAuth2, copy the **Client ID**, then under Redirects → Add `http://localhost:8765/discord` → Save. You don't need a bot or a client secret.
4. **Build:** put `discord.json` (format above) next to `build.bat`, run `build.bat` and upload the exe to Releases.
5. **Test:** Settings → Connect Discord → Authorize, and check that the test message arrives with your tag.
6. **Tell the group:** download the new exe and click Connect Discord. If you want pings only for your own sales, set `#shop-sales` → Notification Settings → Only @mentions.
7. **If the URL leaks:** delete the webhook, create a new one, update `discord.json`, rebuild and re-release.

### Optional extras on the same webhook and reader (small, build together if cheap)
- **"Your shop closed"**: the game disconnected or went back to the login screen, so the shop is gone. Ping the owner.
- **"Shop sold out"**: everything sold, so restock. Ping the owner.
- **Lie Detector alert**: if a Lie Detector window appears, ping the owner to come back. Companion never interacts with it, per the README rule.

---

## 2. Grind tracker

### Goal
While training, show EXP/hr, mesos/hr, time to the next level, and net profit after potions. Do it per session and per map. Over time this builds a personal log of which map actually pays best for you, next to the computed ranking in the Train tab.

Other Classic tools all have this, and it's the biggest gap here. Examples: Maple Classic Exp Overlay (github.com/beanguri/Maple-Classic-Exp-Overlay), Maple Helper (github.com/Itamar-Avitan/maple-helper) and Minerva/MapleCompass (github.com/itechify/minerva).

### Signals: what to read and where (needs samples)
| Signal | Source on screen | Status in this codebase |
|---|---|---|
| Map | Mini map title | Already read: `read_minimap` gives `seen["map"]` |
| Level, job | HUD | Already read: `read_hud` + `LevelDigits` |
| EXP and % | **HUD EXP bar** (number + percent on the bottom bar) | **New.** Read it every full read (1.5 s). Also already in CHARACTER STAT: `read_stat` gives `exp` and `exp_pct` |
| Mesos | ITEM INVENTORY mesos line | Already read: `read_inventory`. Only while the inventory is open |
| Gains | Pickup and EXP messages in the bottom-right corner ("You have gained experience", "You have gained mesos", "x1 earned") | **New.** Optional, phase 2 |
| Potions | Quick-slot counts | **New.** Optional, phase 2. Reuse `read_small_number` |

### Logic
- **Session:** starts on the first EXP gain. It pauses automatically after ~15 s with no EXP gain or on a map change, and resumes on the next gain. Map changes split the session into per-map segments. A "No reset" toggle keeps one session across maps.
- **EXP/hr:** for the whole session and for the last 5 minutes. On a level-up, keep counting: the % wraps from ~100 to ~0, so add the remainder. EXP needed per level comes from the game data's EXP table if present (look in OSMS data); otherwise work in % and EXP numbers per level.
- **Time to level:** (EXP to the next level) ÷ (rate over the last 5 minutes). Show "—" until there's at least 1 minute of data.
- **Mesos/hr:** the difference between inventory reads, divided by time. Mesos are only seen while the inventory is open, so the dashboard says "open your inventory now and then".
- **Net profit:** mesos gained, plus loot value, minus potions used × the cheapest NPC price. Loot value is phase 2: the higher of the NPC price and the FM price for each pickup.
- **Misreads:** the same two-reads rule. An EXP value that goes down without a level-up is dropped.

### Storage
New local SQLite file `grind.sqlite` in `paths.APP_DIR` with tables `sessions` (start, end, map, level_start, level_end, exp_gained, mesos_gained, potions_cost, party flag) and `pickups` (phase 2). Add it to the README's "Your data".

### Dashboard
- **Now tab:** a compact strip showing EXP/hr · time to level · mesos/hr, with Start/Pause and Reset buttons.
- **Train tab:** next to each ranked map, show "your real EXP/hr here" from the log, when you have data for it.
- **Session history:** a small table with map, time, EXP/hr, mesos/hr and net.
- **Optional, Draw on game:** add the numbers to the existing route strip under the mini map. Don't add a new overlay window.

### Phases
1. HUD EXP bar reader, session logic, the Now strip and the per-map log.
2. Mesos/hr from the inventory, potions from the quick slots with net profit, and pickups from the message log.

**Acceptance:** after 10 minutes on one map, EXP/hr is within ±5% of a manual calculation, time to level updates once a minute, and the map log has a row for that map.

**Needs from the owner:** screenshots of the HUD EXP bar at 1920×1080 and 1920×1200, before and after a kill, plus one at a level-up. For phase 2, the bottom-right message area while picking up loot, and the quick slots with potions.

---

## 3. Sell or keep

### Goal
For each item in your inventory, a clear verdict: **KEEP** (and why), **SELL TO NPC** (for how much) or **SELL ON FM** (at what price). This makes cleaning the inventory a 1-minute job.

### Decision rules (pure function, data only, easy to unit test)
Put this in a new `advisor.py`: `verdict(item_name, count, profile, data, market) -> {"verdict", "why", "price"}`. Rules, first match wins:

1. **Starred by the user**: KEEP ("you starred it"). Add a star list to `profile.json`.
2. **Needed by a quest in progress**: KEEP ("<Quest>: need N, have M"). Use `requirements_list` entries of `type: "item"` from `data.quest_list` and the in-progress quests in the profile.
3. **Needed by a quest you can take within the next ~10 levels**: KEEP ("for <Quest> at level L").
4. **Equip you'll wear**: KEEP if it's in `GameData.gear(job, level)` for your job, now or soon.
5. **Untradable** (the tooltip says so: `tip["untradable"]`): SELL TO NPC, or "drop it" if no NPC buys it.
6. **Tradable, priced on both sites:** let `fm` be the conservative FM price, the lower of the MSC median (`market.items[n]["p"]`) and Cozy. Let `liquid` mean that `vol` and sell-through `st` are above thresholds (reuse the spirit of `Market.flips`).
   - If `npc >= 0.8 * fm`, or the item isn't liquid: **SELL TO NPC** for the NPC price.
   - Otherwise: **SELL ON FM**, at the median as the suggested price, with "sells fast" or "sells slowly".
7. **Equips on the FM**: always add "check its stats". A scrolled or high-stat equip is worth more than the median, and a clean one may be worth less.
8. **No price data**: "No market data. Check it yourself."

Thresholds go in one constants block at the top of `advisor.py`.

**Data gaps to check:**
- `NPC_PRICES` in `gamedata.py` is a short hand-made list. Find a full NPC sell price per item: check the OSMS `items.json` (or the Classic Maple Wiki `items.json` already downloaded in `load_wiki`) for a price field. If neither has it, keep the rule but say "NPC price unknown".
- Does the Free Market take a fee or tax on sales in Classic? If it does, subtract it from `fm`. Ask the owner.

### Getting the inventory contents: two phases
The hard part is knowing what's in the inventory. Inventory slots show only icons and counts, not names. `read_inventory` reads only the mesos today.

**Phase 1: on hover (cheap, builds on what exists).** The tooltip reader (`read_tooltips` / `look_for_tooltips`, and the price strip in `App.set_tips`) already knows the item name when you hover an item. Add the verdict as one more line on that price strip, for example `KEEP · Quest X 3/20`, `NPC 1,200` or `FM ~45K · sells fast`. Also collect every item hovered in this session into a **Sell or keep** list on the dashboard. The player hovers over each slot once (a few seconds per tab) and gets the full list. This needs no new OCR or samples.

**Phase 2: full-tab scan (automatic, needs samples).** When ITEM INVENTORY is open:
- **Find the grid** from the window anchor (`wins["inventory"]`), the same way `read_inventory` does, with cell offsets measured from samples at game scale `s`.
- **Find the open tab** (Equip / Use / Setup / Etc / Cash) from the tab highlight.
- **Identify each cell's icon** by template matching against item icons (`GameData.item_img`, cached locally like map images in `cache/`). Narrow the candidates to items of that tab's type. Use a perceptual hash plus a pixel check, and leave a cell **unknown** rather than guess.
- **Read the count** in each cell with `read_small_number`.
- **Run** `verdict()` on every identified item.

Then the dashboard shows the whole tab sorted: SELL TO NPC (with a total "NPC pays you X for all of this"), SELL ON FM, then KEEP.

**Dashboard:** a new block in the Gear tab or Shops tab, "Sell or keep". It has three groups with item pictures, the reason line and the price, a star toggle on each item, and a total value per group.

**Acceptance:**
- Hovering a quest item you need shows KEEP with the quest name.
- Hovering a common ore shows the right NPC-or-FM choice with prices.
- Phase 2: on an Etc tab sample, at least 90% of cells are identified, and the unknown ones are marked unknown, never mislabeled.

**Needs from the owner (phase 2):** screenshots of each inventory tab (Equip, Use, Etc) at 1920×1080 and 1920×1200, with a mix of items and stack counts.

---

## 4. Ideas for later (short notes, not now)

- **Discord Rich Presence:** shows "Lv 32 Hunter · training at <map>" on the Discord profile. Talks only to the local Discord app, with no server needed. Seen in itzSnoopy/maplestory-classic-companion.
- **Level-up / job-advance announcements** to the channel, opt-in. The level and job are already read.
- **Party finder button:** posts "looking for a party for <X>" to `#party-finder` with job, level and channel, pinging a role. Uses a webhook with `allowed_mentions.roles`.
- **Share a deal:** a button on a found snipe or NPC flip posts it to `#deals`.
- **Weekly personal summary** posted to the channel: mesos sold, levels gained, quests done.
- **Boss timers per channel**, shared via Discord (as on meowdb's boss timers page). Needs shared state, so it needs a small bot.
- **Shared map log:** everyone's real EXP/hr per map, for a group "where to train" table. Needs a small bot or a shared store.
- **Low-potion warning** with the nearest potion shop. Fits the grind tracker's phase 2.
- **Shop pricing helper:** while you set up your own shop, suggest prices from the market.
- **Undercut alert:** someone in the FM sells the same item cheaper than your shop. The data is already in `scans.sqlite`.
- **Scroll cost calculator:** the expected cost to reach a target with 60% and 10% scrolls at current prices, against buying the finished item.
- **Wishlist "find it for me":** friends' Companions ping you when they see your item under your price. Needs a small bot.
- **Not doing:** a KPQ helper (rejected), and anything that needs hotkeys, input or game memory.
