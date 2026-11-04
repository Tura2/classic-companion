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
