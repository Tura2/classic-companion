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

The same problem (its kind and what was misread, e.g. the title's text or the game's size and
scale) goes at most once an hour; at most 25 reports a day.

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

## Where they go

Companion → `reports-server/` (a Vercel function) → a private GitHub repository, one commit per
report under `reports/YYYY-MM-DD/<kind>/<id>/`. The app only holds an upload key, which can add
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
   then `build.bat --with-discord --with-reports`.
5. **Each player:** Settings → Problem reports → on.

Free: Vercel's Hobby plan and a private GitHub repository. A report is 1–3 MB, so 25 a day from a
few players is well inside both; GitHub suggests keeping a repository under a few GB, so delete old
days (`reports/2026-11-01/`) once they're fixed.

## Testing

`python -m pytest tests/test_autoreport.py` and `cd reports-server && node --test`.
