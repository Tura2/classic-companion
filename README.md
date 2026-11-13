# Companion

An unofficial helper for MapleStory Classic World: where to train, which quests to do, what gear
to wear, which skills to level, what to flip, and step-by-step routes between maps, in a
browser dashboard on your PC (a second monitor works well).

Not affiliated with or endorsed by Nexon.

## Quick start
**Windows app:** download `Companion.exe` from
[the latest release](https://github.com/Tura2/classic-companion/releases/latest), put it in its own folder and run it. The dashboard opens in
your browser at http://localhost:8765. It only listens on this PC. Companion's own small window,
with its logo, says what's running, has an Open the dashboard button and shows its messages; keep
it open while you play: closing it closes Companion. The exe isn't signed, so Windows may say "Windows protected
your PC": click **More info**, then **Run anyway**. Play the game in windowed or borderless mode; a
game in exclusive full screen can't be captured.

**From source:** install Python 3.10+ from python.org, then double-click `run.bat`
(or `pip install -r requirements.txt` and `python companion.py`).

**Build the exe yourself:** double-click `build.bat`. Output: `dist\Companion.exe`.

The first time the dashboard opens, a short setup in Hebrew asks for your job and level, checks
that prices loaded, offers screen reading (off unless you tick it, with the risk spelled out), checks
the game window and its resolution, and ends with how to use it. The **?** button at the top, or
Settings → How to use, opens that how-to again.

The dashboard is built to sit beside the game and look like the game's own windows: item pictures
as icons, the game's Map Marks and portals, Classic's Equipment Inventory. Now, Go to, Gear and
Skills fit the window without scrolling the page; long lists turn pages with the game's orange
arrows. In a small or zoomed-in window the columns stack and the page scrolls instead.

## Safe by default
Out of the box the app only uses public game data and market prices. It does not touch the game,
read your screen, install keyboard hooks, or even look for the game window. Everything below works
in this mode:

- **Now**: your grind (EXP an hour, time to level, EXP a minute, your 3 best maps by EXP an hour in
  your last 5 levels), what's next (map, SP, AP, the route you're on), and the map you're on: its
  monsters and everything they drop, most valuable on the market first.
- **Train**: maps for your level, ranked by EXP per HP and spawns, with ACC needed.
- **Quests**: what you can take now, where the NPC stands, what to kill and where, items you
  can buy instead of farming, and rewards with their market value. Tap Done to unlock chains.
- **Go to**: where you are (its monsters, or in a town the people there: tap one to see them on the
  map), quick picks (towns, maps to train, recent places), and routes between maps on the real map
  picture with the game's own portals drawn and labelled, the one to take in a red ring.
  A route is the quickest way, not the fewest portals: it counts the walk across each map (from
  the portal you came out of to the next one, climbing counted double) and takes a Regular Cab
  between Henesys, Ellinia, Perion, Kerning City and Lith Harbor when that's shorter.
  Tap "I went through" after each portal. The picture opens zoomed on the circled portal or NPC;
  drag it, zoom with the wheel or +/-, or see the whole map. Each map's picture is downloaded once,
  shrunk to 4096 px on its longest side and kept in `cache/maps/`, and a route's maps are fetched
  ahead one at a time, so each step's map is there when you reach it.
- **Gear**: Classic's Equipment Inventory with the best item for your job and level in each slot;
  hover one for the game's tooltip (requirements in red when you're short, jobs, stats, upgrade
  slots, snipe and usual prices). The whole set's cost beside your mesos.
- **Skills**: a skill window with a tab per job you have; your next 3 skill points; what each skill
  does at level 1 and at max, your plan, and where your next SP and AP
  go. The SP order comes from the class guide for each job (`builds.json`, made by
  `tools/make_builds.py`); AP goes into your secondary stat while a weapon you'll want soon needs
  it, otherwise into your main stat.
- **Quest guide**: pick a quest and tap Guide me in game. Each quest shows the game's own "what to
  do" text, and the guide lays it out step by step: take the quest, each monster to hunt (its level,
  HP and ACC needed, at the nearest map with plenty of it) and item to collect (what drops it, how
  often, about how many kills, or what it costs to buy), anyone to see on the way, and who to bring
  it back to: the wiki's turn-in NPC; else, for a quest that gives you something to deliver or has
  nothing to collect, the last NPC its text sends you to; else whoever gave it. A step is done when the game's Quest Helper shows its count reached, or when you tick
  it, so it works without screen reading too. The route strip by the mini map says what to do now
  and takes you where the step happens.

Set your job, level and mesos at the top of the dashboard.

## Optional: screen reading (at your own risk)
Settings has two separate switches, both off by default:

1. **Screen reading**: captures the game window up to 7 times a second, reads what's open every 1.5
   seconds, wherever you dragged it, with Windows' built-in OCR, and looks for item tooltips in
   between. Nothing to select. The **Now** tab shows what it read; its "What Companion sees" opens
   the picture.
   - HUD: level and job. Mini map: the map you're on, so routes move along by themselves. Between
     full reads it takes a quick look at just the mini map every half second (about 40 ms each), so
     a new map counts within a second or so of the title showing.
   - Quest Helper: the quests you track and their kill / collect counts. Over a busy map a count
     is often half read; when only its goal comes through ("25" of "3 / 25 Axe Stump"), the count
     is left unread rather than taken as reached.
   - CHARACTER STAT (S): level, EXP, stats, and ACC with Detail open. ITEM INVENTORY (I): mesos.
   - SKILL INVENTORY (K): your skill levels and SP left. QUEST (Q): the quests in the open tab;
     open Completed once and those quests are marked Done.
   - How a shop price is judged, against what the item really sold for lately on both price sites
     (see Data sources): **snipe** is at or under the cheapest quarter of recent sales, **fair** at
     or under the middle price, **pricey** above it, **overpriced** above three quarters of sales,
     **NPC flip** under what an NPC pays. A verdict shows only when both sites agree; when they
     don't, it says **sources differ** and you compare the two prices yourself. An item only Cozy
     Market prices shows **Cozy only**, with no verdict. A price far under every recent sale is
     shown as **check price** (probably misread), and a deal is announced only once two reads in a
     row agree on it.
   - Your own shop: your personal store, found by the "3% fee" notice under it (and its one orange
     button, CLOSE STORE). While it's open only it is read, every 6 seconds. When SOLD ITEMS' Total
     Sales goes up in two reads in a row, something sold: it lands in **Your shop** (Now and Shops,
     with a "while you were away" summary), the PC beeps, and with Discord connected it's posted to
     the group's channel (see Discord below). A total that goes down or jumps past what the shop
     holds is a misread and is dropped. Open SOLD ITEMS once; without it, a sale is seen only when
     a row sells out and the mesos box goes up. A Hired Merchant (shop while you're offline) can't
     be seen: there's no game on screen to read.
   - The HUD's EXP and percent ("73,665 [60.01%]"), read by digit shape: the HUD's tiny font
     doesn't OCR. Digits not seen yet are learned from CHARACTER STAT (S): keep it open while you
     kill monsters for about a minute, so every digit shows up once. Works windowed and full screen.
     From it, the **Grind** card on Now: EXP per hour (the last 5 minutes), time to the next level
     and the clock time you'll reach it at this pace, a bar to the next level, EXP per minute over
     the last 30 minutes, and EXP per hour on each map you grinded. The clock stops after 15 s
     without EXP and on a map change (unless "Keep counting across maps" is on). A read whose EXP
     and percent don't agree on the level's EXP is dropped. Each map's numbers go into
     `grind.sqlite`, and Train shows your real EXP/hr on maps you've grinded.
   - Player shops: found by their LEAVE STORE button (a shop's title is whatever its owner typed).
     While a shop is open only its list is re-read, about three times a second.
     Each listed item is read with its price ("1 for 4,500 mesos", bundles too), judged against the
     market, and logged with the seller's name; sold-out rows are skipped. Scroll the shop's list
     and the rest come in. Everything lands in **Shops → Shops you visited**, a grid like your
     inventory with each item's picture, the cheapest price you saw, where, and what it's worth.
   - Items in your inventory: **Shops → Sell or keep**, an inventory window with tabs (Free
     Market, NPC, Keep, Not sure), the game's tooltip with the reason, and what your bag is worth.
     Open a tab of your Item Inventory (Equip, Use, Set-up, Etc) and every item on it is told apart
     by its picture, against the icons of that tab's items (downloaded once into `cache/icons/`;
     the first look at a tab takes a few seconds, on the side). Where two items look the same (Wild
     Boar Tooth and Fire Boar's Tooth) the tooltip names both; hovering an item settles it. Counts
     aren't read off the slots yet. It keeps the last 120 items. An item is kept for a quest only when the quest is in your log, or is a
     one-time quest near your level whose earlier quests you've done (never for a weekly board quest
     not in your log); "Done with this quest" fixes a quest Companion missed. If a shop window
     can't be read, the app saves a picture of it to `debug/samples/` so the reader can be fixed
     (the newest 30 are kept).

   The game area has to be at least 1000 px tall (a 1920×1080 game or larger; the reader was
   measured at 1920×1200). Smaller, its text reads wrong, so reading pauses and the dashboard says
   so until the game is made bigger. A quest joins In progress or Done only once three reads in a
   row agree on it, and a Quest Helper count changes once two reads agree, so one misread doesn't
   end up in your quests; a quest put in In progress by mistake has a Not in progress button.
   Windows are looked for again on every read, wherever you dragged them; a window whose title
   didn't read this time still counts if its title is pixel for pixel where it was.
   The game scales its UI with the size of its window, and the reader scales with it. The HUD's
   orange level digits are learned the first time CHARACTER STAT shows your level.
2. **Draw on game**: a label pointing at each shop row (SNIPE / NPC FLIP / FAIR / PRICEY /
   OVERPRICED / SOURCES DIFFER, then each site's price in its own color: MSC blue, Cozy purple),
   and during a route a small strip: an arrow toward the portal to take (its side and height, so
   "far right, down low" is ↘), where it leads, and one bar per portal with the hops left. It hangs
   under the game's mini map, at least as wide as its window (found by the window's frame), or
   under the collapsed mini map's bar, or beside its title if the frame can't be made out. It stays
   there while the game window doesn't move, and sits in a corner of the game window only until
   the mini map has been seen. It lets 20% of the game through. A quest guide adds a line on top
   of it with what to do now ("Hunt Stirge · Stranger's Request"); the counts stay in the game's
   own Quest Helper.
   Hovering an item (inventory, equipment, any shop) adds its prices under the game's tooltip: each
   site's in its color, and what an NPC pays when that's known; nothing for an untradable item. An
   equip's tooltip comes with the one you wear beside it, and each gets its own. The prices show
   about half a second after the tooltip, and go when it does: a quick look seven times a second (a
   few milliseconds, no reading) sees a tooltip come up, move or go, and only the new tooltip's
   title is read. The item names the Quest Helper and the Quest window list ("0/20 Broken Mirror
   Glass") aren't tooltips and get no prices; the Quest Helper counts only as far down as its last
   quest, so a tooltip right under it still does.
   It follows Windows' display scaling. Unlike Discord's in-game overlay, nothing is injected into
   the game: these are separate click-through windows that sit above it.

## Rules the app follows
Learned from similar community tools (MapleCompass, Maple Classic Exp Overlay) and their issues:

- Capture goes through Windows Graphics Capture on the game window only, the same API as OBS's
  Window Capture and Discord's window sharing: at most 7 frames a second, nothing else on your screen,
  and it keeps working when the dashboard covers the game. There is no screenshot fallback: if
  window capture can't run, nothing is captured and the reason shows in Settings and the log.
- Capture runs only while screen reading is on, and stops right away when it's turned off.
- The game window is found by its title. Browser tabs, Discord, terminals and the app's own
  windows are skipped even with "MapleStory" in their title. Only window titles and class names
  are read: the game process is never opened.
- Only screen capture and its own windows. No game memory, files, injection, hooks,
  input, or attaching to the game window.
- The dashboard's API answers only the dashboard: other web pages you visit can't use it to change
  settings or switch screen reading on.
- No keyboard hooks or global hotkeys. Everything is controlled from the dashboard.
- On-game windows never take focus and are click-through, so the game keeps the keyboard.
- On-game drawing hides whenever the game isn't the window in front.
- Reading stays light: one full read every 1.5 s (about half a second of OCR); while a shop is
  open only its list, about three times a second (a twentieth of a second each); and a few
  milliseconds' look for item tooltips seven times a second, with OCR only on a new tooltip's title.
- One failed read or save is logged and skipped; the reading and drawing keep going.
- The risk is stated up front and never downplayed. The app doesn't claim to be safe or approved.

If a Lie Detector appears in game, answer it. The app never touches it.

**Risk:** Nexon's terms ban unauthorized third-party software, including software that changes
the user experience, and Nexon has named screen recognition in its enforcement policy for another
of its games. Tools like this are widely used, but none are authorized. A ban applies to both
Classic World and Global MapleStory. The app asks you to confirm this before turning it on.
If you want certainty, ask Nexon Support in writing.

If labels never show, set "Game window title contains" in Settings to match your game window.

**Tuning the shop reader:** if shop rows read wrong, compare `debug/last_capture.png` and
`debug/last_ocr.txt` (next to the app) with the game and adjust "Fine-tuning" in Settings.

## Discord (optional, off by default)
Settings → Discord → **Connect Discord** opens Discord's own page ("Companion wants to know who you
are", scope `identify`: your user ID and name only, no messages, servers or friends). Companion
reads your ID once and drops the access token; it's never saved. After that, each sale in your shop
is posted to our server's **#shop-sales** channel, tagging only you (every message allows a mention
of your ID and nothing else: no @everyone, no roles, no one else), so your phone pings. Sent: the
item, how many, the price, your character's name and the shop's total today. Also, once each: "your
shop sold out" and "your shop closed" (the game left the Free Market). Sales wait in
`discord_outbox.json` until Discord takes them: no internet or Discord saying "slow down" delays
them, never loses or repeats them. Sales within a minute of the last message go together. Unlink
or the switch in Settings stops it. Tip: set #shop-sales → Notification Settings → Only @mentions.

The webhook and the Discord app's client ID come with the build (`discord.json` next to
`build.bat`, never committed); without it Settings says "Not set up in this build".

**Admin setup (once, about 5 minutes):**
1. Create a text channel `#shop-sales`. Optional: Edit Channel → Permissions → turn off Send
   Messages for @everyone, so it holds only sales (webhooks still post).
2. Edit Channel → Integrations → Webhooks → New Webhook, name it Companion, picture
   `web/logo.png` → Copy Webhook URL (don't paste it in chat).
3. https://discord.com/developers/applications → New Application "Companion", with the logo
   (players see it on the authorize page) → OAuth2: copy the Client ID; Redirects → Add
   `http://localhost:8765/discord` → Save. No bot, no client secret.
4. Next to `build.bat`: `discord.json` = `{"webhook": "https://discord.com/api/webhooks/...",
   "client_id": "123456789012345678"}`. Run `build.bat`, upload `dist\Companion.exe` to Releases.
5. Test: Settings → Connect Discord → Authorize; a message tagging you arrives in #shop-sales.
6. If the webhook URL leaks (it's inside a public exe, so someone determined can post to the
   channel, though never read it): delete the webhook, make a new one, update `discord.json`,
   rebuild and re-release. Players' links keep working.

Connect needs the dashboard on port 8765 (the only redirect registered): with another copy of
Companion holding that port, close it first.

## Your data
Everything stays on your PC: `profile.json` (job, level, quests done, skill plan, what the game
showed), `config.json` (settings), `scans.sqlite` (shop prices you've seen, behind Shops;
`--report` lists them), `cache/` (downloaded game data, learned level digits), `debug/samples/`
(pictures of shop windows). The Now tab's picture of the game is only served to this PC.
`grind.sqlite` (your EXP per map and session, behind the Grind card and "your real EXP/hr" on
Train), `discord_outbox.json` (sales waiting to be posted, and the keys of ones already posted, so none
goes twice). Nothing is uploaded anywhere unless you connect Discord; then only your shop's sales
(item, quantity, price, character name, shop total) go to the group's #shop-sales channel.

## Data sources
- Game data: OSMS Data Explorer (MIT), github.com/ohmi69/osms_datamine_dashboard. Refreshed every 12h.
- Prices: maplestory-classic.com/market.json. Refreshed every 30 min. The file is rebuilt once a day
  (~07:00 UTC), so intraday moves aren't in it.
- Second prices: Cozy Market (cozy.markets) item pages, read into `cache/cozy_items.json` by the
  app itself (`cozy.py`): when it starts and every 10 minutes after, it fetches again any price
  older than two hours, in the background and one page a second (the pages aren't cached, so a full
  pass is spread over about half an hour rather than a burst). Cozy publishes one number per item -- its usual sale price, the listing
  and sale counts, and the day it was last seen -- in each page's meta description, and lists every
  page in its public sitemap; robots allows all and the site has no terms page. Its `/api` (behind a
  browser check) is not used. Labels and the dashboard show both prices, MSC in blue and Cozy in
  purple. Cozy has no spread, so the verdict against Cozy uses maplestory-classic.com's spread moved
  to Cozy's price, and a verdict is claimed only when both agree. Prices Cozy only has for items no
  one bought yet (asking prices) are left out. Cozy names an item's male and female versions the
  same; for those the busier one's price is used. The dashboard footer shows when Cozy's prices were
  fetched; older than two weeks, they are left out. By hand, and faster:
  `python tools/scrape_cozy.py --refresh` fetches every price again (about 5 minutes). Without the
  file the app works on maplestory-classic.com alone.
- ACC to never miss: NiaDB's Classic accuracy values (meowdb.com/msclassic), interpolated.
- Every monster's drop list (This map on Now): MapleClassic Wiki (mapleclassic.wiki), CC BY-NC-SA 4.0,
  via Club FM's public data (github.com/maplefm/maplefm.github.io, `data/itemguide.json`), credited
  under the list. Rates only where players counted them; optional, the app runs without it.
- The game's portal picture: maplestory.io (Map.wz/MapHelper.img/portal/game/pv), fetched once and
  kept in `cache/portal.webp`. Classic's Equipment Inventory picture is bundled (`web/equip_classic.png`).
- Quest steps, who takes each quest back, and monster drops: Classic Maple Wiki contributors
  (classicmaple.wiki/data), much of it from MapleClassic Wiki (mapleclassic.wiki), CC BY-NC-SA 4.0.
  Downloaded and refreshed like the game data, reformatted for the dashboard, credited with links
  on each quest. Non-commercial: Companion is free.
- SP order per job: NiaDB's class guides (meowdb.com/msclassic/guides), credited on the Skills
  tab with a link to each guide, as NiaDB's reuse page asks for single facts. Using NiaDB's
  prices or crawling the site would need their permission first (contact@meowdb.com).
- Game images belong to Nexon. Fine for personal use; don't sell them. The logo is the game's own Maple Leaf
  and Steely Throwing Knives item pictures, on a badge.

Not used, on purpose: MesoWatch (meso.watch) says its price data isn't free to copy, disallows its
data files in robots.txt and names crawlers and AI agents on a full disallow, so nothing of its is
read here. maplestory.watch sits entirely behind a Cloudflare challenge. NiaDB (meowdb.com) asks
tools to get permission before using its API or data files. Any of them can be added once its owner
says yes.
