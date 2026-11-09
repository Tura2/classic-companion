# Dashboard redesign: Now, Go to, Gear, Skills, Shops, Settings

Date: 2026-11-09. Status: approved by the user, tab by tab, on mockups.

## Why

The dashboard (`web/index.html`) works but reads like a long web page: Now mixes grinding with player-shop rows, Shops grows without end, Skills is one long list, Settings is walls of text. The user plays with the dashboard beside the game and glances at it mid-grind. They want each tab to answer its question on one screen, and to look and feel like MapleStory Classic's own windows.

What the user checks in Now while grinding, in their words: EXP per hour, the chart, time to level, what's best for their level, and the map they're on with its monsters and drops.

## Goals

- Every tab fits the window: no page scroll at the user's setup (2560×1440 at 150% zoom, about 1690×780 CSS px) or at about 1150×680. Columns end at the same line, no empty gaps; leftover height goes to the part that can use it (the EXP chart, the drop list, the skill rows).
- A game look: item pictures from the game as icons, the game's Map Marks, the real portal sprite, the Classic EQUIPMENT INVENTORY window, the game's navy item tooltip.
- Long lists page with the game's orange arrow buttons (◀ 1 / 4 ▶), sized to what fits; they never grow the page.

## Non-goals

- **Quests tab and quest reading.** The user said quests aren't read well from the game yet; that is a separate project about the reader, not this redesign.
- **Train tab.** Stays as it is.
- A Pickup Log reader (Minerva-style crowd drops). Not now.
- New price sources.

## Anti-goals (failure even if it works)

- Text a player has to read to understand a control (the "SP 2" box, icon-only Pause/Reset were both rejected as unclear).
- Anything that scrolls the whole page or leaves big blank areas.
- Future content shown greyed out (a "Ranger" tab before 3rd job exists was rejected).
- Telling the player to keep an item for a quest they can't or won't do.

## Shared pieces

- **Icons:** item pictures from OSMS (`{OSMS}current/images/items/{id:08d}.png`), shown pixel-sharp. Tabs: Now = Table Clock 4000094, Go to = Return Scroll 2030000, Train = a bow 1452002 (may follow the job's weapon), Quests = Maria's Letter 4031001, Gear = Metal Gear 1002032, Skills = Secret Book 4031032, Shops = 10,000 Meso Pouch 2028001, Settings = Cog 4000089. Window titles: Grind = Snail Shell 4000001, Next up = Maple Leaf 4031134, Worth picking up = Mysterious Meso Pouch 2028000, Your best maps = Event Trophy 4001009. A map's window uses its real Map Mark (`maps.json` `map_mark_icons`).
- **Game window style** (Skills, Sell or keep): light-blue rim, a white title strip in black pixel caps (DotGothic16) with a blue close box and a white ×, grey tabs with the active one in red-pink on a red rule. Final look: `skills-v8.html`.
- **Game tooltip:** navy (`rgba(27,32,72,.985)`), item name with a blue dot, the picture in a grey box, then rows. Opens beside the hovered slot, kept on screen.
- **Pager:** orange arrow buttons, "1 / 4"; per-page count = how many rows fit the box (measure one row, divide).
- **Too short a window** (heavy zoom): below a minimum height the full-height layout gives way to stacked columns with normal page scroll, rather than squeezing (the user saw things "get messy" when zooming in).

## Now

Mockup: `now-v7.html`. Two columns, full height.

**Left: Grind** (window icon Snail Shell). Stays as today (EXP/hour killing, time to level, grinding time, the EXP bar, "by the clock" line, EXP per minute chart) with these changes:
- Pause and Start over are buttons with an icon and a word (Reset renamed Start over).
- The per-minute chart stretches to take the column's spare height.
- **Your best maps**: the top 3 maps by killing EXP/hour from the grind log (`grind.sqlite` `sessions`, map, levels, `exp_gained`, `active_s`). Only sessions in your last 5 levels (EXP/hour falls as you level) and maps with at least 10 minutes. One thin line each: gold/silver/bronze medal, map, "Lv 32–33 · 2h 40m", EXP/hour, then **Go** (starts the route) or "here" (green row) for the map you're on.

**Left: Next up**, under Grind: one line each for Train (map, its monsters, Go), SP (next point), AP.

**Right: This map · <name>** with the region's Map Mark and "street · town":
- Monsters on it: sprite, name, "Lv 24 · ×11 · 45 EXP".
- **Worth picking up**: every item those monsters drop, sorted by MSC price, most valuable first, the top one highlighted. Each row: item picture, name, a chip with the scroll's success rate when it's a scroll, "from <monster> · rate unknown" or the rate when known, the MSC price. Paged to fit. Footer credit: "Drops: MapleClassic Wiki (CC BY-NC-SA 4.0) via Club FM. Prices: MSC."

**Moved out of Now:** everything player-shop (your shop's sales, an open shop's rows, deals this session) goes to Shops. The "Watching the game" status line goes (the HUD shows map and level). "What Companion sees" goes to Settings → Advanced.

## Drop data (new source)

Every Classic site's drops come from mapleclassic.wiki. Companion's current source, classicmaple.wiki `monsters.json`, copies only drops with a counted rate, so it has nothing at or above level ~27 (Zombie Mushroom: nothing). Club FM publishes the full lists in its public repo: `https://raw.githubusercontent.com/maplefm/maplefm.github.io/live/data/itemguide.json`, `items[<item name>].d = [[monster, monster_level, rate|null, kills, map, ?, monster_id], ...]`, with `src` crediting mapleclassic.wiki. The user decided: use it, no permission request, give credit. Fetch it like the other data files (cached, refreshed with the rest), match monsters by id, items by name.

## Go to

Mockups: `goto-v2.html` (a hunting map, route on), `goto-town-v2.html` (a town).

**Left, "You're here"** with the Map Mark and a "Wrong map?" link (sets the map by hand):
- On a hunting map: its monsters (no drops).
- In a town: the people there in a two-column list, each with its NPC picture (`{OSMS}current/images/npcs/{id:07d}.png`) and a tag (Quests, Taxi, Shop, Housing, Board, Events, from what Companion knows: quest givers, shops; no tag when unknown). Clicking one shows it on the map.

**Left, "Where to":** a big search box (map, town or NPC); **Towns**: Henesys, Ellinia, Perion, Kerning City, Sleepywood, Lith Harbor as buttons with their Map Marks; **Train for your level**: the Train tab's top maps with your EXP/hour; **Recent**: the last places you navigated to. One click starts the route. In a town the list is shorter (search and towns).

**Right, the map:**
- **Portals are drawn with the game's portal sprite** (the blue swirl, 8 frames, animated), at each portal's spot, each with a label naming where it leads. Frames: `https://maplestory.io/api/wz/GMS/83/Map/MapHelper.img/portal/game/pv/{0..7}` (base64 PNG in `value`), each with an `origin` (`.../pv/{n}/origin`: 43,173 · 43,173 · 44,193 · 43,193 · 42,209 · 42,209 · 41,248 · 42,246). Aligned on the origin they make an 89×257 canvas whose foot is at (44,248); place that foot on the portal's (x, y).
- **The portal to take has a red ring** (white halo under it) and a dark label; the view zooms on it. Others have blue labels.
- With a route: direction ("↖ Portal on the upper left"), "in X, leads to Y", I went through / Stop route, the steps as chips.
- No route: the map you're on with all its portals labelled.
- In a town: NPCs drawn standing at their spots (`npc_positions`); the picked one gets the red ring and its name, the header says what they do and where ("stands on the middle-right, by the Henesys Park door").

## Gear

Mockup: `gear-v5.html`.

**Left: the Classic EQUIPMENT INVENTORY window.** The image is cropped from the user's screenshot of the game (`equip_classic.png`, 244×404, corners made transparent; tabs Equip / Deco / Beauty). Its 9 slots, top-left corners in the image's pixels, each about 45 px: Hat (100,95), Ear Acc (146,142), Cape (7,188), Top (54,188), Weapon (146,188), Shield (193,188), Gloves (7,234), Bottom (54,234), Shoes (54,281). The best item per slot (`gamedata.gear`, first of `now`, else first of `soon`) sits in its slot; Overall goes in Top when it's the pick. Slots with no pick stay empty. Under the slots, in the game's font: "Best <job> gear for Lv <level>". The window scales to the free height (never cut at the bottom; the user saw that at first).

**Hover a slot (or a list row): the game tooltip** like the one the user sent (a market site's item card):
- the name, the picture
- REQ LEV / STR / DEX / INT / LUK: ones you meet in white, ones you don't in red, zeros greyed. Your stats come from Character Stat.
- the job row BEGINNER WARRIOR MAGICIAN BOWMAN THIEF with the item's jobs lit in orange
- ✦ Type, Attack Speed (label and number), each stat, Remaining Enhancements (`tuc`)
- prices: Snipe at (MSC p25), MSC usual, Cozy; or "Not traded on the market yet".

**Right: "Best gear for your level"**: a row per slot with the picture, the name in bold, "Weapon · Lv 30" small and grey under it (no coloured slot badges; the user found them ugly), the snipe price. Then the whole set's cost at snipe prices beside your mesos, and a note when an Overall is a choice instead of top + bottom.

## Skills

Mockup: `skills-v8.html`.

**Left: a SKILL INVENTORY window** in the game style:
- Tabs: only the jobs this character has (Beginner, Archer, Hunter), each with a skill icon (Beginner 0001000, Archer 3000001, Hunter 3101004). The current job's tab is open. No tabs for jobs not reached or not in the game.
- Under the tabs: "Hunter" in pixel font, "2nd job · 10 SP spent here".
- One row per skill, filling the window's height (rows grow up to a cap): icon, name, its kind (Mobbing attack, Speed buff, Passive...), a level bar, "4 / 20". The picked row is highlighted. No markers for the next points in the window (the user found numbered circles confusing).

**Right: "Your next 3 skill points"**, always three single points in order from the class guide, with icons: e.g. 1. Bow Booster 4 → 5, 2. Soul Arrow: Bow 0 → 1, 3. Bow Mastery 5 → 6. `next_points` merges a run into one line ("Bow Mastery 5 → 20"); split runs into single points for this list. Under them: what follows ("Then Bow Mastery up to 20, then Final Attack: Bow up to 30"), SP to spend now, and where AP goes.

**Right, under it: the picked skill**: big icon, level in the game, your plan with − / +, description, At level 1 vs At max, and a button to the class guide's level-by-level build table (today a separate filter button).

## Shops

Mockup: `shops-v4.html`.

**Inner tabs** (pills): **Your shop** (sales and Discord status, today's card), **Sell or keep**, **Shops you visited** (today's seen-items grid and detail, plus the open player shop live, moved from Now).

**Sell or keep:**
- **Left: a SELL OR KEEP window** in the game style with tabs Free Market / NPC / Keep / Not sure (and Drop when it has items), each with its count. Items are inventory slots (6 across) of that tab only, paged. Hover: the game tooltip with the verdict (a coloured label), the price and the reason.
- **It never grows without end:** it keeps the last 48 items hovered; older ones drop off. A Clear button. A hint line: "Hover items in your inventory in the game and they land here".
- **Right: What your bag is worth**: on the Free Market (sum, count, after the 3% fee), to an NPC, how many to keep; then the 4 worth the most. **Why keep these**: each kept item and why, scrolling inside its card. A row kept for a quest has a **Done with this quest** button, which marks the quest done (the existing quest-done API) so the item moves to its sell verdict.

**Keep-for-a-quest rule (change to `advisor.verdict`).** Found during review: it said to keep Horny Mushroom Cap and Charm of the Undead "for Donating to Henesys at level 12", but that is a weekly Citizenship quest picked from a pool of 17 (`rotation.cadence = weekly`, `one_time = False`) that also needs a citizenship grade, and "Chrishrama in Need of Help" is a weekly crafting quest needing Arcforge Lv 2. New rule:
1. In your quest log now: keep (as today).
2. One-time quests: keep only if not done, within `LEVELS_AHEAD` of your level, and the quests it requires are done.
3. Weekly / rotating quests: keep only if that quest is in your log now.
The "Done with this quest" button only shows on a keep-for-quest row, so only for a quest that isn't done and applies to you.

## Settings

Mockup: `settings-v1.html`. Two columns of cards:
- **Screen reading** (status pill "Game found · reading"): switches with a bold label and one short line each: Read the game; Draw on the game; Beep on a deal or a sale. The risk notice is one collapsed yellow line, "⚠ Unofficial tool: use at your own risk", opening to the full text and the "I understand the risk" box (consent stays required before reading turns on).
- **Discord** with the Discord logo (simple-icons, CC0) in Discord's blurple: status pill, the linked user, where it posts (#shop-sales, tagging only you), a switch "Post my shop's sales", a blurple "Send a test message" and Unlink. Not linked: Connect Discord.
- **Help**: How to use (Hebrew), Run the setup again.
- **Advanced** (collapsed): label side, game window title, the fallback shop-area settings, "What Companion sees".

## Constraints

- One file of HTML/CSS/JS (`web/index.html`), served by `companion.py`; no build step, no framework.
- Game data stays fetched at runtime from OSMS (MIT) and cached, as today. Prices: MSC and Cozy only.
- Game pictures (items, NPCs, Map Marks, monsters, portal frames) are fetched and cached, not committed: the repo is public.
- Never touch the game: everything still comes from screen capture.
- The page must also work with screen reading off (no Grind, no This map from the reader; the HUD's map set by hand still drives This map and Go to).

## Left to the builder

- Endpoint shapes (e.g. a `/api/here` payload with the map's monsters, drops and portals; a "best maps" query on `grind.sqlite`).
- Exact paging maths, breakpoints for the stacked fallback, animation of the portal (CSS steps or an animated WebP built at fetch time).
- How NPC role tags are derived from data Companion already has.

## Calls I made (not discussed; check these)

1. **Route and Quest Helper on Now:** with no scroll there's no room for both. While a route runs, a one-line route strip appears above Next up ("Step 1 of 2 · portal upper left → Sleepywood", Go to tab link). The Quest Helper card leaves Now (the game shows it on screen).
2. **The Equip window image** (cropped from the user's screenshot) is bundled with the app as `web/equip_classic.png`, since there's no source to fetch it from. It contains no player info.
3. **Portal frames** are fetched from maplestory.io on first use and cached on disk, like map pictures.
4. **Club FM's file** is refreshed with the other data files; when it's missing, This map shows monsters only and says drops aren't available.
5. **Shops' "Your shop" and "Shops you visited"** keep today's content, just under the new pills.
6. **"Keep the last 48 hovered"** for Sell or keep, plus the Clear button.
7. **Scroll success chip** in Worth picking up comes from OSMS `items.json` `scrolls[].success_rate` (e.g. Claw Attack Scroll: Intermediate 60).
8. **Beginner tab in Skills:** `JOBS` lists only the job's own groups (Hunter: Archer, Hunter); the Beginner tab reads the `beginner` family from the skills data too.
9. **Overall in Gear:** shown in the Top slot (Bottom left empty) only when its score beats the best top's plus the best bottom's; otherwise the note on the right offers it.
10. **Narrow windows** (the dashboard beside the game, under ~760 px wide) stack the columns and scroll, like the too-short fallback.
11. **Screen reading off:** Now's left column shows Your best maps (from the log) and Next up; This map follows the map set by hand in the HUD or "Wrong map?".

## Mockups

In `classic/companion/.superpowers/brainstorm/929-1794223004/` (git-ignored): `content/` holds the HTML mockups and assets (final ones: `now-v7`, `goto-v2`, `goto-town-v2`, `gear-v5`, `skills-v8`, `shops-v4`, `settings-v1`), `scripts/` the Python that generates them from the real dashboard CSS and real data.
