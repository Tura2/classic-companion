# Samples

Pictures of the game, for building and testing the reader against what the game really draws.
`tools/grab_samples.py` saves them into `samples/raw/` (kept out of git: a picture can show a
character's name and chat; only crops cleared for sharing are committed).

## Wanted now (2026-11-18, the reader bug hunt)

Each picture is for a finding in `docs/superpowers/plans/2026-11-18-reader-bug-hunt.md` (F#).
Take them with `python tools/grab_samples.py --label <label>` unless it says "whole screen"
(Win+PrtSc: the on-game labels are windows of their own, which the game capture leaves out).
Reading only works from 1000 px tall, so the sizes that matter are 1080, 1200 and 1440.

**A. At 1920x1080 and at 2560x1440, windowed** (W is 1080 or 1440; one set per size):

1. `res-W-stat`: CHARACTER STAT with Detail open and a stat that has a gear bonus ("147 (137+10)"),
   the mini map open, Quest Helper with 2-3 quests, the inventory showing mesos. F2, F6, F7, F9
2. `res-W-shop`: inside someone's player shop, prices of 4 digits and more, one row sold out. F3, F4
3. `res-W-soldout`: a player shop with everything sold out. F4
4. `res-W-tooltip`: the stat window open and an item's tooltip over its name. F8
5. `res-W-skills`: the skills window on your job's tab. F9
6. `res-W-street`: the mini map on three streets (a town, Victoria Road, Warning Street). F6

**B. Full screen with bars** (the game at 1920x1200, full screen, on the 2560x1440 monitor),
Companion running with on-game labels on:

7. `fullscreen-tooltip`: stat window and inventory open, hovering an item. Then a whole-screen
   shot of the same: where the price card sits next to the tooltip. F1
8. `fullscreen-route`: a route started (Go to). Then a whole-screen shot: where the route strip
   sits under the mini map. F1

**C. UI Size** (Settings, Graphics), at 1920x1200 windowed, for every UI Size the game offers:

9. `ui-size-N` (N the setting's value): the same screen each time without moving any window:
   stat window (Detail open), inventory, mini map, Quest Helper, skills, a tooltip. F10

**D. Two monitors with different scaling** (only if you have them), whole-screen shots:

10. `dpi-game100`: the game on the 100 % monitor, Companion on the 125 % one, a tooltip hovered
    and a route started. Then `dpi-game125` with the two swapped.

Keep each picture until it's made into a masked case (`tools/make_case.py`); ask before any is deleted.

## Measured (2026-11-04, MapleStory Classic World, windowed, a 2560x1440 screen at 125%)

The game offers 800x600, 1024x768, 1280x720, 1366x768, 1920x1080, 1920x1200 and 2560x1440;
there is no 1600x900. Boxes are (left, top, right, bottom) in the game's drawing area, with the
mini map in its usual top-left corner, open, on Kerning City.

**The UI scales with the window's height from 1920x1080 up, and not below it.** From 768 px tall
down to 600, the UI stays at one size, about two thirds of the 1200 px one, so `frame.height /
1200` is right at 1080 px and taller and wrong below (0.50 at 600 px tall where the UI is at
0.67). Reading pauses under 1000 px tall, so nothing reads at the wrong size today.

| game area | height / 1200 | WORLD button | its size / 51 | mini map frame | LV tiles |
|---|---|---|---|---|---|
| 2560x1440 | 1.20 | (340, 14, 402, 31), 62x17 | 1.22 | (5, 15, 411, 402) | 19x23 |
| 1920x1200 | 1.00 | (284, 12, 335, 26), 51x14 | 1.00 | (4, 12, 343, 335) | 16x19, 19 px apart |
| 1920x1080 | 0.90 | (255, 10, 302, 23), 47x13 | 0.92 | (3, 11, 308, 301) | 14x17 |
| 1366x768, 1280x720, 1024x768, 800x600 | 0.64 to 0.50 | (181, 7, 215, 17), 34x10, the same at all four | 0.67 | | not found |

- **WORLD button**: orange (221, 153, 17) with cream letters, not MapleCompass's (240, 167, 21).
  Its top is the mini map frame's top (within a pixel), and its right edge is 8 px inside the
  frame's right edge at the 1200 px size (6 at 1080, 9 at 1440): an anchor for the mini map's
  right side and top at every map name's width (the frame is 280 to 340 px wide, by its title).
- **LV tiles**: orange, 16x19 px and 19 px apart at the 1200 px size, scaling with the height.
- **UI Size setting**: not checked in this round.
