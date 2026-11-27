# Contributing to Companion

Thanks for helping! Bug reports, reader samples, translations, docs and code are all welcome.

## Ground rules (not negotiable)
Companion must stay a tool that only **looks**. A PR that breaks any of these will not be merged,
however useful:

- No reading game memory or files, no injection, no hooks into the game process.
- No keyboard/mouse input to the game, no macros, no automation of play.
- No keyboard hooks or global hotkeys. Everything is controlled from the dashboard.
- Screen capture only through Windows Graphics Capture on the game window, only while the user
  turned screen reading on.
- On-game windows stay click-through and never take focus.
- Safe by default: anything new that reads the screen or sends data out is **off** until the user
  turns it on, with the risk spelled out.
- Never use data from a site that asks not to be scraped (see "Not used, on purpose" in docs/data-sources.md).

## Getting set up
Companion runs on Windows (it uses Windows OCR and window capture).

```bat
git clone https://github.com/Tura2/classic-companion
cd classic-companion
python -m pip install -r requirements.txt -r requirements-dev.txt
python companion.py          rem dashboard at http://localhost:8765
python -m pytest -q          rem the tests
```

`build.bat` builds the installer, `dist\CompanionSetup.exe` (needs [Inno Setup 6.7 or newer](https://jrsoftware.org/isinfo.php): `winget install JRSoftware.InnoSetup`). You don't need `reports.json` to build or test; without
it, problem reports are hidden and Discord says "Not set up in this build".

To try the installer's look without a full build, compile a test build with any folder as the payload.
It has its own AppId, folder and shortcut names, so it never touches a real install:
`ISCC /DTestBuild /DSourceDir=C:\some\folder /Oout installer\companion.iss`. Its side picture comes from
`tools/make_installer_art.py` (run it again after changing `web/logo.png`).

## Where things live
`companion.py` in the root is the entry point; the app's modules are in `app/`.

| File | What it does |
|---|---|
| `companion.py` | Entry point, the small app window |
| `app/sniper.py` | The dashboard server and API, ties everything together |
| `web/index.html` | The whole dashboard (one page) |
| `app/gamedata.py` | Downloads and indexes game data |
| `app/advisor.py` | Training and gear advice |
| `app/trust.py` | What a read may save to your profile, checked against the game's rules |
| `app/capture.py`, `app/window.py` | Finding and capturing the game window |
| `app/native.py` | The game's own pixels and how big it drew its UI (the reader's scale) |
| `app/reader.py`, `app/anchors.py` | Reading the game's windows from the picture; finding them by their titles |
| `app/hudnative.py`, `app/hudexp.py` | The HUD's level and EXP |
| `app/invgrid.py`, `app/quickslots.py`, `app/notices.py` | Inventory items and quick slots told by their picture; the corner's pickup lines |
| `app/overlay_art.py` | Drawing labels over the game |
| `app/grind.py`, `app/party.py` | EXP an hour, sessions and deaths (`grind.sqlite`); a kill's EXP split in a party |
| `app/shopwatch.py`, `app/cozy.py`, `app/discord_link.py` | Your shop's sales, Cozy prices, Discord |
| `app/paths.py` | Companion's folder and its subfolders (data, cache, logs, debug, reports) |
| `app/applog.py`, `app/report.py`, `app/updater.py` | What the small window says and the daily logs, Report a problem, self-update |
| `app/version.py`, `installer/companion.iss`, `build.bat` | The version, the Inno Setup installer and the build |
| `tools/` | One-off scripts (building `builds.json`, scraping Cozy, the icon, reader test cases) |
| `tests/` | pytest suite |

## Reporting a bug
Open an issue with the **Bug report** form and attach the zip from **Report a problem** in Companion's window. For a misread, also attach `debug/last_capture.png` and
`debug/last_ocr.txt` (crop out other players' names and chat first).

## Sending a change
1. Fork, then branch from `main`: `fix/short-name` or `feat/short-name`.
2. Keep the PR to one thing. Add or update a test when you change behaviour.
3. Run `python -m pytest -q` before pushing. CI runs it too, on Windows.
4. Commit messages in the style already used: `fix(reader): what changed and why`,
   `feat(shops): ...`, `docs: ...`.
5. If the change is user-visible, update the README or its page in `docs/` (features, screen-reading, discord, data-sources) in the same PR. Together they are the manual:
   plain words, no hype, risks stated as they are.
6. Open the PR and fill in the template.

## Pictures of the game
Screenshots for reader test cases (`samples/raw/`, `samples/cases/`) stay on your PC and are
git-ignored on purpose: they show other players' names and chat. If a case is needed in the repo,
crop it to the one window and blank out names first.

## Never commit
`reports.json`, `discord.json`, `data/`, `cache/`, `debug/`, `logs/`, `reports/`, or anything with a
token or webhook URL. If you leak one by mistake, tell the maintainer right away (see SECURITY.md).

## Code of conduct
Be kind. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

By contributing you agree your contribution is released under the [MIT license](LICENSE).
