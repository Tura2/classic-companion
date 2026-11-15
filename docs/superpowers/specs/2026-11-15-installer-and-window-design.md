# Installer, one folder, and a calmer Companion window

Approved by the user on 2026-11-15.

## Goals
A player who isn't technical installs Companion like any Windows app, finds all of its files in one
folder, removes it cleanly, and reads in its window only what matters to them. When something goes
wrong, one button gathers what a bug report needs.

## 1. One folder
Installed to `%LOCALAPPDATA%\Programs\Companion\` (per user, no admin prompt):

| Path | What |
|---|---|
| `Companion.exe`, `_internal\` | the program (PyInstaller one-folder build: no unpacking to `%TEMP%` on each start) |
| `data\` | `profile.json`, `config.json`, `scans.sqlite`, `grind.sqlite`, `discord_outbox.json` |
| `cache\` | downloaded game data, map pictures, icons, learned digits (as today) |
| `logs\` | `companion-YYYY-MM-DD.log`, kept 7 days |
| `debug\` | pictures of windows that didn't read (as today) |
| `reports\` | zips made by "Report a problem" |
| `unins000.exe` | the uninstaller |

`paths.py` defines `DATA_DIR`, `CACHE_DIR`, `LOGS_DIR`, `DEBUG_DIR`, `REPORTS_DIR` under `APP_DIR`. On
start, `paths.migrate()` moves the data files that used to sit loose in `APP_DIR` into `data\` (a file
already in `data\` wins; the loose one is left and logged). From source the same subfolders appear in
the repo folder; `.gitignore` covers them.

## 2. Installer and uninstaller
Inno Setup 6, `installer/companion.iss`, built by `build.bat` after PyInstaller into
`dist\CompanionSetup.exe`. The version comes from `version.py`.

- Per user, `PrivilegesRequired=lowest`, no admin prompt. Setup in English or Hebrew (picked from
  Windows' language, with a choice).
- Start-menu entry, desktop shortcut (a checkbox, ticked), "Launch Companion" on the last page.
- Same `AppId` every release: running a newer setup replaces the program and keeps `data\`.
  A running Companion is closed first (Restart Manager, plus a named mutex the app holds).
- Apps & features entry with the logo, version and publisher.
- Uninstall: closes Companion, removes the program, shortcuts, `cache\`, `logs\`, `debug\`,
  `reports\`, then asks "Also delete your Companion data (character, settings, grind history)?".
  Yes removes `data\` and the folder; No leaves `data\` for a reinstall.
- Releases ship only `CompanionSetup.exe`. The site and README Download links point at
  `releases/latest/download/CompanionSetup.exe`.

## 3. The window
The window shows lines a player acts on or wants to know, each with the time:

- Ready, with the dashboard's address.
- Character changes (name, job, level), quests completed, shop sales and corrections, deals found.
- Problems, in plain words, marked ⚠, each kind at most once every 10 minutes: no internet / data
  couldn't refresh, Cozy prices not refreshed, quest steps or drop lists unavailable, the game window
  can't be captured (the capture's own plain message), reading the game hit an error, a damaged file
  that was set aside, screen features unavailable on this PC, a Discord message failed.

Everything else goes to the log file only: download details, map/portal/tombstone pictures, mini map
titles not recognised, tracebacks, anything printed by libraries. `stdout` and `stderr` go to the log
file, not the window. Uncaught exceptions in threads are logged with their traceback and shown as one
plain problem line.

`applog.py`: `say(text)` (window + file), `log(text)` (file), `problem(kind, text, exc=None)`
(file always with the traceback; window rate-limited per kind). Old logs (over 7 days) are deleted on
start.

The window: header with logo, name, status and Open the dashboard (as today); the line list (problems
in amber); a footer with "Keep this window open while you play" and **Report a problem**.

**Report a problem** writes `reports\companion-report-YYYYMMDD-HHMMSS.zip` with the last 3 days of
logs and `info.txt` (Companion version, Windows version, screen size and scaling, settings with the
Discord fields removed), shows it selected in Explorer, and opens the GitHub issue form. No pictures
(they show other players' names) and no `profile.json`.

## Not in scope
Importing data from an old portable copy elsewhere on the PC (no users besides the maintainer yet;
copy `data` files by hand). Code signing.
