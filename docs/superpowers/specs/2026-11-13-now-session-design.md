# Now tab: this session (kills, loot, mesos, EXP change, deaths)

Approved on mockups 2026-11-13 (`.superpowers/brainstorm/1848-1794574135/`, generator
`scripts/mock_session3.py`, last screen `content/now-session-v16.html`). Inspired by
maplestory.watch's session card.

## Why

A glance while grinding that tells you whether this map pays, and where you'd do better.
The numbers do the judging: no "good map / bad map" line anywhere.

## Goals

- Now shows, for the grind session you're in: the EXP bar change, monsters killed, loot
  picked up with counts, mesos picked up, and deaths.
- Deaths (10% of the level's EXP lost) are counted in every Companion feature that uses EXP.
- In a town, Now switches by itself to a town layout where the town map gets most of the space.

## Non-goals

- No verdict text about the map.
- No prices on the page: worth shows only in the hover tooltip.
- No potion use (negative counts) in this version: Companion has no reliable inventory
  counts yet (`invgrid` reads names, not counts).
- "Next up" is removed from Now; its SP/AP and Train suggestions are not moved anywhere new.

## Anti-goals (a failure even if it technically works)

- Counting a corner line more than once (lines stay several seconds and are read every ~1.5 s).
- Counting a misread EXP drop as a death, or a death as a misread.
- Blank gaps, page scroll, or content spilling out of a card (the user's standing UI taste:
  no page scroll, no blank gaps, long lists page with orange ◀ ▶ arrows).

## Layout (layout "C", chosen)

### While grinding (any map that isn't a town)

Two columns, as Now has today (`.now2`).

**Left: Grind** (the existing card, changed):
- Title "Grind · <map>", Pause and Start over buttons, each with its icon.
- Four stat boxes: `EXP / hour` (the label without "breaks left out"), `to level N+1`,
  `kills to level N+1` (from `Grind.kills_left`, PR #36), `grinding`.
- One line under them: "By the clock (X an hour, breaks included), level N+1 at about
  <time> · <EXP> EXP to go."
- No EXP progress bar here (it moves to This session).
- The chart (replaces the bar sparkline), filling the free height:
  - a filled line of EXP per minute for the whole session;
  - gridlines and labels at round EXP values, and clock times along the bottom;
  - a dashed average line labelled "avg 2.5K";
  - the game's tombstone at each death (hover: when, and the EXP lost).
- "Your best maps": the top 5 (now 3), with an "All maps ›" button.

**Right, top: This session** (new), taking the free height:
- Title "This session", aside "42m · since 2:58 PM".
- EXP change row: `Lv. 37`, a bar showing where the session started (dim) and what it
  gained (bright, white mark at the start), the current %, `+16.50%`. With a level-up it
  reads `Lv. 37 → 38` and the gain counts across the level.
- Deaths: the game's tombstone and a number at the end of that row, in a small red pill.
  Hover: each death's time and EXP lost. Hidden when there are none.
- Loot: dark square tiles like maplestory.watch: 32 px icon centred, count bottom right in
  white with a dark outline, no names. Mesos is the first tile (gold count, "18.4K").
  The tiles fill the card; the rest pages with the arrows.
- Hover a tile: a small game-style tooltip (`#tip.small`, about 250 px wide): name, picture,
  kind (Etc / Use / Equip), description, "You picked up N", and three numbers: MSC usual,
  NPC pays, Yours worth (MSC × N). "Not traded on the market yet" when there's no price.
- Empty: faint dashed tiles behind the words "Nothing picked up yet".
- Bottom line: `NET +18,450 mesos · 440/min`; "0 mesos so far" in grey when none.

**Right, bottom: This map** (monsters only):
- Title "This map · <map>", button "Worth picking up ›" on the right.
- One box per monster, two per row: its picture on a dark tile; three lines next to it with
  icons: gold Lv badge `Lv 34`, red heart `982 HP`, green star `66 EXP`; your kills this
  session in the box's corner ("478 killed"). No spawn count.
- "Worth picking up ›" opens a pop-up: the map's drop list, most valuable first, without
  prices, paged; hover a row for the same tooltip.

### In a town (automatic, when the map read is a town)

- Left, about 63% of the width: This map, the town map and its people (as Now shows a town
  today), with each person's NPC picture, their role (Quests / Taxi), paged with the arrows,
  never spilling out of the card.
- Right, top: **Last session · <map>**, one compact row: time, `+16.50%` (Lv.), killed,
  items, mesos, deaths (tombstone pill).
- Right, below: Grind, small: chip "not grinding"; two boxes: last session's EXP / hour,
  and time to the next level at that pace (no kills box: you're not killing); Your best
  maps with Go buttons (none marked "here"), as many as fit; "All maps ›".

### All maps pop-up

A table of every map ground on in the last 5 levels, most EXP an hour first: rank, map,
your level range, time, EXP / hour, kills / hour, mesos / hour, Go (or "here"). No deaths
column. Footnote: "EXP / hour leaves out breaks and counts what deaths cost."

## Where the numbers come from

### The corner lines (new reader)

The game prints pickup and EXP lines in the bottom-right corner, white text with a dark
outline, newest at the bottom, the stack scrolling up and fading. Seen in
`samples/raw/grind/*` (Nov 2, 1920x1080, low level):
- `You received EXP (+12)` (maybe with a bonus part, to be confirmed on samples)
- `You have gained mesos (+15)`
- `Tree Branch x1 earned. (Etc)` / `Squishy Liquid x1 earned (Etc)`

A new reader reads that area each full read and, on a quick read in between if it's cheap
enough, and turns lines into events:
- `exp(n)` → a kill. Named by matching n to the EXP of this map's monsters. If no monster
  matches, it counts as a kill without a name.
- `mesos(n)` → mesos picked up. NET is the mesos picked up (no spending is counted in this
  version).
- `item(name, count)` → loot, name matched to the game's item names.

Each line counts once. A line that's still on screen in the next read must not count again,
even after it has scrolled up a row; two identical lines in a row are two pickups. How to
tell them apart is the builder's call, settled on real samples (see below).

**Fallbacks:**
- Without readable lines, kills come from the HUD EXP gains, divided by the usual kill
  (`Grind.per_kill`), unnamed.
- Mesos then come from Grind's existing reading of the inventory window's mesos (kept as it
  is); loot stays empty rather than guessed.

**Samples needed before building the reader:** about a minute of passive pictures at the
player's current setup (1920x1200, game windowed), one a second, kept to the bottom-right
corner only. The user offered to grind while they're taken. A death in the samples would
help; it isn't required.

### Deaths

A death costs up to 10% of the level's EXP. LUK lowers the loss, a Safety Charm prevents
it, and a death in town may cost nothing. Grind already drops "EXP going down without a
level-up" as a misread; that changes (decided by the user, 2026-11-13):
- A death counts only when the EXP actually drops. Any drop of more than 0 and at most 10%
  of the level's EXP (or to 0 when less than that was left), confirmed by two reads in a
  row, with no level change, is a death.
- A drop bigger than that is still a misread.
- A death that costs no EXP (Safety Charm, town) isn't counted: Companion can't see it.
- Recorded: the time, the EXP lost, and the map.

Deaths count in:
- EXP / hour (net of what deaths cost);
- the time to level;
- this session's EXP gained and its EXP change bar (the gain shown is net);
- the chart (a tombstone, and that minute's value net of the loss);
- Your best maps and the All maps pop-up, through their EXP / hour;
- the Last session row (the tombstone pill).

Kills to level isn't changed by a death beyond the EXP left growing.

### Party quests

During a party quest Grind keeps its party quest layout (this run, EXP a run, runs to
level) in place of the four stat boxes. This session counts kills and loot there too. All
maps keeps leaving party quests out, as Your best maps does today.

### Session

The session is Grind's: it starts again on a map change unless "Keep counting across maps"
is on, and on Start over. Kills, loot, mesos and deaths belong to it. When a session ends,
its summary is what Last session shows in town. With "Keep counting across maps" on,
walking into a town doesn't end it: the town layout still shows, and the compact row reads
"This session" (still counting) instead of "Last session". Per map, the session's kills, mesos picked
up and deaths are stored with its segment in `grind.sqlite` (the `sessions` table gains
new columns: kills, mesos picked up, deaths, EXP lost; the existing `mesos_gained` from the
inventory stays as it is), so All maps can show kills / hour and mesos / hour. Mesos / hour
uses the picked-up column, and the inventory one where a row has no pickups.

### Worth (tooltip only)

- MSC usual: the market price Companion already has (`data.market`).
- NPC pays: `data.npc_price`.
- Description and kind: the game data (`cache/items.json`).
- The drop list's order by value stays as today; the value just isn't printed.

## Constraints

- Never send input to the game; reads are passive pictures.
- Test against the real game only when the user asks; ask before deleting game pictures.
- Windows only (winocr, WGC), as the rest of the reader.
- No page scroll; cards never spill; lists page with the orange arrows; the dashboard's
  existing look (real CSS in `web/index.html`).
- Pictures and icons from the game data (OSMS); the tombstone is the game's
  (`maplestory.io` `Effect/Tomb.img/land/0`), downloaded once into `cache/` like the portal
  sprite (with the same retry-later behaviour when offline).
- Branch from `origin/main`; one PR; the user audits before merge.

## Decided by the user

Layout C; town switch automatic with This map biggest; Grind small in town without kills;
no EXP bar in Grind; kills to level as a stat box; loot tiles like maplestory.watch with
icons only; tooltip small; no prices on the page; This map as monster boxes with Lv / HP /
EXP icons and kills; Worth picking up as a pop-up; All maps pop-up without deaths; the
game's tombstone; Pause / Start over with icons; "Nothing picked up yet" as the empty text;
"Next up" removed; deaths everywhere EXP is used.

## My calls (the user can overrule)

- The chart covers the whole session (not the last 30 minutes) and shows the tombstone at
  each death.
- Best maps shows 5 while grinding; as many as fit in town.
- A death is recognised from the EXP drop alone (no picture of the death dialog).
- Without readable corner lines, kills fall back to HUD gains divided by the usual kill.
  Loot then stays empty; mesos fall back to the inventory window's.
- Everything but the corner-line reader is built first; the work stops for the user's
  samples. If the lines can't be read reliably at the user's setup, the PR ships with the
  fallbacks and says so.
- The route strip that lived in Next up is not moved; routes stay on Go to and on the card
  over the game.

## Left to the builder

- How the corner-line reader finds the lines, preps the picture, and tells a new line from
  one already counted (on the real samples).
- The death tolerance.
- The chart's exact scale, label steps and colours, within the mockup's look.
- Paging sizes, empty states beyond the ones above, and the tests.
