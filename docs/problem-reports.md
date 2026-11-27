# Problem reports, sent on their own

Off by default. Settings → **Problem reports** turns it on, in a build made with `--with-reports`.

## What gets reported, and when

Each full read of the game (about every 1.5 s) is checked by `app/autoreport.py` (`Watch.see`):

| kind | when | sharp crop if the picture is too big |
|---|---|---|
| `map_missed` | the mini map's title read, but named no map, 3 reads in a row | the mini map |
| `exp_missed` | the HUD found, its EXP not read, 5 reads in a row | the HUD |
| `hud_lost` | the HUD read in the last 10 minutes, then not for 10 reads | the HUD |
| `map_lost` | the mini map read in the last 10 minutes, the HUD still there, then not for 10 reads | the mini map |
| `shop_unread` | a player shop found, none of its items read | |
| `error` | a read raised an exception (with the traceback) | |

Each report has a **key**: one problem. For a map it's the map name closest to the misread title
(so "Hennes Huntng" and "Henes Hunting" are one problem, `map_missed:henesys-hunting-ground-i`),
else the title's text; for the HUD and the mini map, the game's size and UI scale; for an error, its
type and line. On each PC the same key goes at most once an hour, at most 25 reports a day.

A report is a folder:

- `report.json`: why, what this read saw (`seen`), the last 15 reads in short (`history`), the
  reader's title picture scores and places, the game area's size and UI scale, the screen and its
  scaling, Companion's version and settings (without Discord), the character's name, job, level and
  map, and the log's last 80 lines.
- `frame.png`: the game as Companion saw it, full size (`frame.jpg` plus PNG crops of the area that
  matters when PNG would be over ~3 MB).
- `last_ok.jpg`: the last frame where the map and the EXP both read, to compare.

Reports wait in `data/report_outbox/` until the server takes them (retries with backoff; at most
40 wait, none older than a week).

## One entry per problem: `index.json`

The server keeps `index.json` at the reports repository's root, one entry per key: how many times,
first and last seen, versions, screen sizes, players, and where its kept reports are. Only the
first **3** reports of a problem keep their pictures (up to 6, one more for each screen size it
wasn't seen at). Before sending, Companion asks the server (`GET ?key=&version=&size=`) whether
it still wants this problem's pictures; when not, the report goes as a count only (a few hundred
bytes). So the repository grows with the number of different problems, not with how often they
happen; sort `index.json` by `count` for what to fix first.

**Fixed:** add `"fixed": {"version": "1.4.7"}` to the entry. Reports from older versions then only
count; one from 1.4.7 or later sets `"back"` and keeps 3 more with pictures, so you see the fix
didn't hold.

## Where they go

Companion → `reports-server/` (a Vercel function) → a private GitHub repository, one commit per
kept report under `reports/YYYY-MM-DD/<kind>/<id>/`, and `index.json` updated in the same commit. The app only holds an upload key, which can add
reports and nothing else; the GitHub token lives only on Vercel.

## Setting it up (once)

1. **The private repository.** On GitHub, a new **private** repository, e.g. `companion-reports`,
   with a README (so `main` exists).
2. **A token for it.** GitHub → Settings → Developer settings → Fine-grained tokens → Generate:
   *Only select repositories* → `companion-reports`; *Permissions* → Contents: **Read and write**.
   Nothing else.
3. **The server.** Vercel → Add New → Project → import `classic-companion`, **Root Directory**
   `reports-server`, no framework. Environment variables:
   - `UPLOAD_KEY`: a long random string (e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`)
   - `GITHUB_TOKEN`: the token from step 2
   - `REPORTS_REPO`: `Tura2/companion-reports`

   Deploy. The address is `https://<project>.vercel.app/api/report`.
4. **The build.** Next to `build.bat`, `reports.json` (never committed):
   ```json
   {"url": "https://<project>.vercel.app/api/report", "key": "<UPLOAD_KEY>"}
   ```
   then `build.bat --with-reports`. The same file turns on Discord (see [discord.md](discord.md)).
5. **Each player:** Settings → Problem reports → on.

Free: Vercel's Hobby plan and a private GitHub repository. A report is 1–3 MB, so 25 a day from a
few players is well inside both; GitHub suggests keeping a repository under a few GB, so delete old
days (`reports/2026-11-01/`) once they're fixed.

**The key is public in practice.** It's inside every release, so the server guards itself:
- **Day caps (UTC), changeable in Vercel:**
  - `DAY_STORED` 100 reports keep pictures, and after that they only count;
  - `DAY_NEW_KEYS` 50 new problems;
  - `DAY_PER_INSTALL` 25 from one install;
  - `DAY_TOTAL` 1000.

  Over the last three, a report is refused for now and Companion tries again later. The counters
  sit in `index.json` under `"#day"`.
- **Real pictures only:** a `.png` must be a PNG and a `.jpg` a JPEG.
- **Callers:** one caller (IP) gets 30 calls in 10 minutes.
- **`REPORTS_MODE`:** `count` keeps no pictures, and `off` pauses everything (Companion keeps its
  reports).
- **Changing the key:** `UPLOAD_KEY` may hold several keys, comma-separated. Ship a release with
  the new key, and drop the old one later.

## Testing

`python -m pytest tests/test_autoreport.py` and `cd reports-server && node --test`.
