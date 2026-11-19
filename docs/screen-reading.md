# Screen reading and on-game labels

Both are optional and **off by default**. Turning either on is at your own risk: see the risk note below.

## The two switches
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

   In a window, the game has to be at least 1000 px tall (a 1920×1080 game or larger; the reader was
   measured at 1920×1200). Smaller, its text reads wrong, so reading pauses and the dashboard says
   so until the game is made bigger. Full screen works at every resolution the game offers (it's
   shown at your monitor's size), and every UI Size setting, "ideal" included. A quest joins In progress or Done only once three reads in a
   row agree on it, and a Quest Helper count changes once two reads agree, so one misread doesn't
   end up in your quests; a quest put in In progress by mistake has a Not in progress button.
   Windows are looked for again on every read, wherever you dragged them; a window whose title
   didn't read this time still counts if its title is pixel for pixel where it was.
   The reader measures how big the game drew its UI (from the status bar at the bottom) and
   scales with it. The HUD's
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
`debug/last_ocr.txt` (in Companion's folder) with the game and adjust "Fine-tuning" in Settings.

[Back to the README](../README.md)
