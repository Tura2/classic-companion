# Credits

Companion stands on the work of many people. Thank you.

## Maintainer
- [@Tura2](https://github.com/Tura2): author and maintainer.

## Contributors
Everyone who sent code, bug reports, reader samples or ideas:
see [the contributors graph](https://github.com/Tura2/classic-companion/graphs/contributors).
Opened a useful issue or tested a release? Add yourself to the list below in your PR, or ask and
we will.

<!-- One line each: - [@handle](https://github.com/handle): what you helped with -->

## Data sources
| Source | Used for | License / terms |
|---|---|---|
| [OSMS Data Explorer](https://github.com/ohmi69/osms_datamine_dashboard) by ohmi69 | Game data: maps, monsters, items, quests, NPCs, portals | MIT |
| [maplestory-classic.com](https://maplestory-classic.com) | Market prices (`market.json`) | Public file |
| [Cozy Market](https://cozy.markets) | Second market price per item | Public pages, robots allows all |
| [NiaDB](https://meowdb.com/msclassic) | ACC values, SP order per job (class guides) | Single facts, credited as their reuse page asks |
| [Classic Maple Wiki](https://classicmaple.wiki) contributors, much from [MapleClassic Wiki](https://mapleclassic.wiki) | Quest steps, turn-in NPCs, monster drops | CC BY-NC-SA 4.0 (non-commercial) |
| [MapleClassic Wiki](https://mapleclassic.wiki), via [Club FM](https://github.com/maplefm/maplefm.github.io)'s public `data/itemguide.json` | Every monster's drop list ("Worth picking up" on Now) | CC BY-NC-SA 4.0 (non-commercial) |
| [maplestory.io](https://maplestory.io) | The game's portal picture, drawn on route maps | Game image (Nexon) |

## Inspiration
Community tools whose issues taught us the rules the app follows:
MapleCompass and Maple Classic Exp Overlay.

## Libraries
[Pillow](https://python-pillow.org), [Requests](https://requests.readthedocs.io),
[RapidFuzz](https://github.com/rapidfuzz/RapidFuzz), [winocr](https://github.com/GitHub30/winocr),
[windows-capture](https://github.com/NiiightmareXD/windows-capture), [NumPy](https://numpy.org),
[PyInstaller](https://pyinstaller.org), [pytest](https://pytest.org).

## What the MIT license doesn't cover
The [MIT license](LICENSE) covers Companion's own source code and documentation. It does not cover:

- Game images and names (item pictures, the window title pictures in `assets/titles/`, the Maple Leaf
  and Steely Throwing Knives pictures in the logo). These belong to Nexon. Fine for personal use;
  don't sell them.
- Data the app downloads at run time from third parties (see Data sources above). Each keeps its own
  license; for example, Classic Maple Wiki content is CC BY-NC-SA 4.0 and must not be used commercially.

## Game
MapleStory and all game images belong to Nexon. Companion is an unofficial fan tool, not
affiliated with or endorsed by Nexon.
