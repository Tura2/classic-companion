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
- Never use data from a site that asks not to be scraped (see "Not used, on purpose" in the README).

## Getting set up
Companion runs on Windows (it uses Windows OCR and window capture).

```bat
git clone https://github.com/Tura2/classic-companion
cd classic-companion
python -m pip install -r requirements.txt -r requirements-dev.txt
python companion.py          rem dashboard at http://localhost:8765
python -m pytest -q          rem the tests
```

`build.bat` builds `dist\Companion.exe`. You don't need `discord.json` to build or test; without
it Discord just says "Not set up in this build".

## Where things live
| File | What it does |
|---|---|
| `companion.py` | Entry point, the small app window |
| `sniper.py` | The dashboard server and API, ties everything together |
| `web/index.html` | The whole dashboard (one page) |
| `gamedata.py` | Downloads and indexes game data |
| `advisor.py`, `trust.py` | Training/gear advice, price verdicts |
| `capture.py`, `window.py` | Finding and capturing the game window |
| `reader.py`, `anchors.py`, `hudexp.py` | Reading the game's windows from the picture |
| `overlay_art.py` | Drawing labels over the game |
| `shopwatch.py`, `grind.py`, `cozy.py`, `discord_link.py` | Shop sales, EXP tracking, Cozy prices, Discord |
| `tools/` | One-off scripts (building `builds.json`, scraping, reader test cases) |
| `tests/` | pytest suite |

## Reporting a bug
Open an issue with the **Bug report** form. For a misread, attach `debug/last_capture.png` and
`debug/last_ocr.txt` (crop out other players' names and chat first).

## Sending a change
1. Fork, then branch from `main`: `fix/short-name` or `feat/short-name`.
2. Keep the PR to one thing. Add or update a test when you change behaviour.
3. Run `python -m pytest -q` before pushing. CI runs it too, on Windows.
4. Commit messages in the style already used: `fix(reader): what changed and why`,
   `feat(shops): ...`, `docs: ...`.
5. If the change is user-visible, update the README in the same PR. The README is the manual:
   plain words, no hype, risks stated as they are.
6. Open the PR and fill in the template.

## Pictures of the game
Screenshots for reader test cases (`samples/raw/`, `samples/cases/`) stay on your PC and are
git-ignored on purpose: they show other players' names and chat. If a case is needed in the repo,
crop it to the one window and blank out names first.

## Never commit
`discord.json`, `config.json`, `profile.json`, `*.sqlite`, `cache/`, `debug/`, or anything with a
token or webhook URL. If you leak one by mistake, tell the maintainer right away (see SECURITY.md).

## Code of conduct
Be kind. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

By contributing you agree your contribution is released under the [MIT license](LICENSE).
