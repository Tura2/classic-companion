# Samples

Pictures of the game, for building and testing the reader against what the game really draws.
`tools/grab_samples.py` saves them into `samples/raw/` (kept out of git: a picture can show a
character's name and chat; only crops cleared for sharing are committed).

## Wanted now (for the mini map anchor and the UI size)

Take each with the game windowed or borderless, at the resolution you play at:

1. `--label minimap-open`: the mini map open, in a town (its title shows street and map name).
2. `--label minimap-collapsed`: the mini map collapsed to its one-line bar.
3. `--label minimap-moved`: the mini map dragged away from its usual corner.
4. `--label helper`: the Quest Helper open with two or three tracked quests, next to the mini map.
5. `--label quest`: the Quest window (Q) open on In Progress.
6. `--label tooltip`: the mouse over an item in the inventory, its tooltip showing.
7. `--label ui-size-N`: the same screen at each of the game's UI Size settings (Settings,
   Graphics), N being the setting's name, without moving the window.
8. `--label res-WxH`: the same screen at each resolution the game offers.

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
