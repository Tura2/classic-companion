# Potions used, on Now's This session card

## Why
While grinding, the player wants to see what the session really cost and earned, the way maplestory.watch does: the loot picked up, and the potions drunk as minus counts (its lemon tile at −298). Loot and mesos come from the corner's lines (PR #43). Potions drunk aren't in those lines; they show as the quick slots' counts going down.

## Goals
- Every potion (any Use item) drunk from the quick slots this session is counted, by name.
- On Now, each item has one tile in the loot grid: picked up minus drunk. Below zero it is a red "used" tile, as in mockup A (`.superpowers/brainstorm/1283-1794677723/content/potions-used.html`, picked 2026-11-14).

## Non-goals
- Items used from the inventory window rather than the quick slots.
- Any money in NET: NET stays mesos only. No prices on the page; worth stays in the hover tooltip.
- Reading counts on inventory tabs. The same digit reader can do that later.

## Anti-goals
- A potion counted that wasn't drunk: from a misread, a slot changed, or an item moved. A missed count is better than a wrong one.
- Any input sent to the game: the reading only takes pictures, as everywhere else.

## Approaches
- **A. In the loot, as minus counts (picked).** One tile per item, net count, red below zero. It's compact and reads like maplestory.watch. A potion both picked up and drunk shows only the difference; the tooltip gives both numbers.
- B. A separate "Used" row under the loot. Clearer, but it costs a row in a card that must not scroll.
- (Not considered further: using the inventory's Use-tab counts. The tab is only read while it's open, which is rare while grinding.)

## How (decided)
- **Reading** (proven 2026-11-14 on samples):
  - The quick slots are un-stretched to the game's own pixels (`native.py`).
  - Counts are matched exactly against the game's own ItemNo digit sprites (8×11; "1" is 5 wide, the others step 8 px). The best digit wins at each place, by the share of its pixels within 6 levels; that tolerates a selection frame over part of a digit.
  - Result on samples: 55 of 55 known inventory counts and every quick-slot count in 6 frames read right. The digit sprites ship in `assets/`.
- **Naming a slot's item:** its icon on native pixels against the Use items' icons (the same OSMS icons `invgrid` uses), matched at the game's own size.
- **Counting:**
  - Each corner look (every 0.4 s, same loop and frame as the corner lines) reads the 12 quick slots (a 4×3 grid; the count sits at a slot's bottom left): item and count.
  - An empty slot keeps its item's icon and shows 0 (player, 2026-11-14), so drinking the last potion is an ordinary 1 → 0 drop.
  - A slot whose item stays the same and whose count falls by k counts k drunk of that item, once two looks agree on the new count.
  - A count going up isn't counted: pickups come from the corner lines.
  - A slot changing item, or an unreadable look, sets that slot's baseline again.
- **Storing:** `Grind.add_used(name, n, now)` next to `add_loot`, kept per session the same way. `summary()` adds `used`.
- **Showing:**
  - `session_view` merges loot and used into one list, with a net count per item.
  - Order: mesos first, then positive items, then items at zero or below.
  - A tile below zero gets the red "used" look from mockup A. Its tooltip says "Picked up N · used M".

## Calls I made (check these)
- **A potion picked up and drunk equally shows a 0 tile in grey.** The alternative is hiding it, but that hides real activity.
- **Two looks must agree** before a count change counts. This adds ~0.4 s of delay and guards against a misread.
- **Only Use items get named.** A skill's or Etc item's slot is ignored. That includes a skill's own number at a slot's top right, such as the zero-job speed skill's 2 → 1 (player, 2026-11-15): only the bottom-left count is read.
- **No new UI beyond the tile style**, so no new strings except the tooltip line.

## Left to the builder
- The exact geometry of the 12 slots in native pixels, relative to the bottom-right corner (measured on samples).
- How icons are fetched and cached: reuse `invgrid`'s cache.
- Tests: synthetic quick-slot frames built from the sprites, like the corner tests, plus a check tool on recorded play once one exists. `tools/record_corner.py` already saves the quick slots.

## Unknown until a live check
- Counts of four digits or more.
- How the 0 of an empty slot is drawn (assumed the same ItemNo digit).
