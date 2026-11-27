# Companion

A free helper for MapleStory Classic World. It shows where to train, which quests to take, the best
gear for your job, which skills to level and what's worth selling, with routes between maps. It all
runs in a browser dashboard on your PC (a second monitor works well).

Unofficial: not made or endorsed by Nexon. Open source under the [MIT license](LICENSE).

[Website](https://tura2.github.io/classic-companion/) ·
[Download](https://github.com/Tura2/classic-companion/releases/latest/download/CompanionSetup.exe) ·
[Releases](https://github.com/Tura2/classic-companion/releases) ·
[Credits](CREDITS.md)

## Install
1. Download [`CompanionSetup.exe`](https://github.com/Tura2/classic-companion/releases/latest/download/CompanionSetup.exe) and open it.
   - It installs for you only, with no admin password, into `%LOCALAPPDATA%\Programs\Companion`.
   - The setup isn't signed, so Windows may say "Windows protected your PC". Click **More info**,
     then **Run anyway**.
2. The dashboard opens at http://localhost:8765. It's reachable from this PC only.
3. A short first-run setup asks for your job and level. The **?** button opens the how-to again later.

Keep Companion's small window open while you play: closing it closes Companion.

**Updates install themselves.** When Companion starts, it checks GitHub for a newer release. If there
is one, it downloads it, verifies it, installs it and restarts; your data stays.

**Uninstall:** Windows Settings → Apps → Companion → Uninstall. It asks whether to keep your data.

## What it does
- **Now:** EXP an hour, time to level, deaths, loot and mesos while you grind, with a history of past sessions.
- **Train:** maps for your level, ranked by EXP and spawns, with the accuracy you need.
- **Quests:** what you can take now, where the NPC stands, what to hunt, and what the rewards are worth.
- **Go to:** routes between maps, drawn on the map picture with the portal to take ringed.
  The Regular Cab is one button away.
- **Gear:** the best item for your job and level in each slot, and what the whole set costs.
- **Skills:** where your next skill and ability points go, from each job's class guide.
- **Quest guide:** a chosen quest, step by step, with the route to each step.

Each tab in full: [docs/features.md](docs/features.md).

All of the above works from public game data and market prices. Companion doesn't touch the game,
read your screen or look for its window.

## Optional: screen reading and on-game labels
Two switches in Settings, **both off by default**:
- **Screen reading:** captures the game window up to 7 times a second and reads it.
  - What it reads: your level, EXP, stats, mesos, skills, quests, the map you're on, shop prices and
    your own store's sales.
  - Routes and quests then follow you on their own.
- **Draw on game:** price labels under item tooltips and on shop rows, and a route strip under the
  mini map.

It works in a window (1000 px tall or more), in full screen at any resolution, and at every UI Size
setting. It never touches game memory, files or input, and uses no keyboard hooks or automation.

**Risk:** Nexon's terms ban unauthorized third-party software, and Nexon has named screen
recognition in its enforcement policy for another of its games. No tool like this is authorized,
and a ban covers both Classic World and Global MapleStory. Companion asks you to confirm before
turning it on.

How it reads, its rules and how to tune it: [docs/screen-reading.md](docs/screen-reading.md).

**Discord (optional):** posts to your group's channel, each with its own switch: your shop's sales,
grind sessions over 10 minutes, and valuable pickups (over 80,000 mesos each).
Setup: [docs/discord.md](docs/discord.md).

## Your data
Everything stays on your PC, in Companion's folder (`%LOCALAPPDATA%\Programs\Companion`):
- `data\`: your profile, settings, prices you've seen, your grind history.
- `cache\`: downloaded game data and pictures (safe to delete).
- `logs\`: one log a day, kept 7 days.

Nothing is uploaded, except what you switch on: problem reports, and the Discord posts above if you
connect it.

## Data sources
- **Game data:** the OSMS datamine (MIT).
- **Prices:** maplestory-classic.com and Cozy Market.
- **Quests and drops:** Classic Maple Wiki and MapleClassic Wiki (CC BY-NC-SA 4.0).
- **Accuracy and skill orders:** NiaDB, credited per page.

Details, and the sites left out on purpose: [docs/data-sources.md](docs/data-sources.md).

## Help and contributing
- **Something wrong?** Use **Report a problem** in Companion's window. It makes a zip with the last 3
  days of logs and your setup, with no pictures and no character data, and opens the bug form.
- **Run from source:** Python 3.10+, then `run.bat` (or `pip install -r requirements.txt` and
  `python companion.py`).
- **Build the installer:** [Inno Setup 6.7+](https://jrsoftware.org/isinfo.php), then `build.bat`.
  The result is `dist\CompanionSetup.exe`.
- **Contributing:** see [CONTRIBUTING.md](CONTRIBUTING.md). Report security problems via [SECURITY.md](SECURITY.md).

Code: [MIT](LICENSE). Game images belong to Nexon. Downloaded data keeps its own license.
Thanks to everyone in [CREDITS.md](CREDITS.md).
