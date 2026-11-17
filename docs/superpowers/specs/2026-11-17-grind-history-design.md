# Grind history: a card for every session

2026-11-17. Approved on mockups: `classic/companion/.superpowers/brainstorm/781-1794912311/scripts/mock_history2.py`
(git-ignored, in the main checkout, not this worktree).

## Why

Now shows the session you're in. Once it ends, Companion keeps only per-map totals (`sessions` table:
EXP, time, levels, kills, mesos). The EXP chart, loot, kills per monster, potions and deaths live in
memory and are lost. The user wants to look back at past sessions "more fully", like maplestory.watch's
session card, but in Companion's look.

## Goals

- Every grind session is saved in full when it ends (and along the way, so a crash loses at most a minute).
- A **Grind history** pop-up, opened from a **History ›** button on the Grind card (beside **All maps ›**),
  lists past sessions newest first, **8 a page**, paged with the orange ◀ ▶ arrows.
- Each list row holds only the important data: **map, day + start time, level (orange tile "Lv. 36→37"),
  time grinding, EXP gained, EXP / hour**, and a **Lucide `chevron-down`** icon.
- Clicking a row (or its chevron) opens it: the open session fills the pop-up, the other rows hide, the
  chevron turns up; clicking it again goes back to the list. One open at a time. No scrolling.
- The open view: map picture; four boxes (best minute, killed + a minute, net mesos, deaths + EXP lost);
  the EXP-per-minute chart with a dotted line at each level-up; the EXP bar from start to end with a
  LEVEL UP mark per level; loot (picked up − drunk, potions below zero in red); net mesos line
  (picked up, potions cost, a minute); kills per monster with the monster's picture and a bar; a death line.

## Non-goals

- No History tab (option B was turned down), no sharing/exporting an image, no deleting sessions (later, if asked).
- No new reading of the game: everything comes from what Grind already gets.

## Anti-goals

- A page that scrolls, or gaps (the user's standing UI rule).
- Little walk-through sessions cluttering the list.
- Making the dashboard slow: the list must stay quick with hundreds of sessions.

## Approaches considered

- **A. Save a full card per session (picked).** A new table holds one row per session with its details as JSON;
  updated every minute while it runs and once when it ends.
- B. Rebuild cards from the per-map `sessions` rows. No new saving, but no chart, loot or kills per monster:
  doesn't meet the ask.
- Placement: **pop-up with a list and expand chevrons (picked)** over a History tab or a one-card-at-a-time pop-up.

## Design

**What a session is.** The same as Now's "This session": it starts with `Grind._new_session` and ends on a map
change (unless "keep counting across maps" is on), on **Start over**, or when Companion closes. A PQ run is a
session like any other, named by the PQ.

**Storage.** New table `history` in `grind.sqlite`:
`id, start, end, map_id, map, pq, level_start, pct_start, level_end, pct_end, exp_gained, active_s, exp_hr, data TEXT`
where `data` is JSON:

- `minutes`: EXP per minute from the first minute (`t0` + `vals`, as `_chart` makes it), deaths netted as today.
- `levelups`: `[{ts, level}]`, the time each new level was first read.
- `kills`: `[{name, count}]` and `party_kills`; `kills_total`.
- `loot` / `used`: `[{name, count}]` as Grind keeps them (item ids/images looked up when shown).
- `mesos_picked`, `mesos_change` (inventory read), `potions_cost` if known.
- `deaths`: `[{ts, lost}]`.
- `maps`: the maps the session's EXP came on (for "keep counting across maps" sessions), the first one is the title.
- `job` (from the profile at save time).

Saved with the same rhythm as segments: upserted at most once a minute while EXP comes, and on
end / Start over / close. **A session is saved only once it has 2 minutes of grinding (`active_s` ≥ 120) and
EXP above 0**; shorter ones are dropped (no clutter from walking through maps).

**Older sessions.** Rows of the old `sessions` table from before the update are shown in the same list,
each as its own row (they're per map), marked older; opening one shows its totals and a note that the
full story wasn't kept then. They are never rewritten.

**API.** `GET /api/history?page=N` → `{total, page, pages, rows:[short row]}` (8 a page, newest first, old rows
merged by start time). `GET /api/history/<id>` → the full card, with item ids/pictures and monster pictures
resolved server-side the way Now's session view does (`session_view`), and the map picture via `/api/mapimg`.

**UI.** In `web/index.html`: the History › button on the Grind card in all its states (grinding, not grinding,
town), the pop-up built like **All maps** (`.pop`/`.popwin`), rows as in the mockup, the open view reusing Now's
classes (`.xbar`, `.tomb`, loot slots, `.pager`). The chevron is Lucide's `chevron-down` inlined as SVG
(no icon library is added). Tooltips on loot slots: "Picked up N · used M", as Now does. Plain words, no prices.

**Numbers.** EXP / hour = the session's `exp_hr` as Now computes it (cumulative over grinding time, breaks over
60 s left out). Best minute = max of `minutes`. **Net mesos = mesos picked up** (corner lines), else the
inventory change, else "—". **No potion cost** (my call: Companion has no shop price it may use — OSMS's
`price` is the sell-back price, Club FM has none, the KB's are MeowDB's — and the user's rule is no prices on
the page). Potions show as drunk counts in the loot grid; the mockup's "potions cost" is dropped.

## Calls made after the builder check (the user can overturn any)

- **Idle ends a session:** 30 minutes with no EXP gain ends the session (saved as it stood); the next gain
  starts a new one. This changes Now too ("This session" restarts after a long AFK or a log-out on the same
  map). Without it, one card could span a night of zero minutes.
- **Party quests:** a run's time and EXP / hour are its wall time, as Now's PQ panel and `pq_summary` already
  count them, and the 2-minute rule uses that time. Entering a PQ always starts a new session, even with
  "keep counting across maps" on.
- **The session in progress isn't in the list:** it's on Now. It appears once it ends. A row left without an
  end by a crash is closed at its last save on the next start.
- **Character:** each row stores the character name (from the profile). The list shows it on each row only
  when the history holds more than one character.
- The old `sessions` rows count as "older" when they start before the `history` table was created; the
  2-minute rule hides old walk-through rows too. The new method doesn't reuse the name `Grind.history()`.

## Left to the builder

- Exact JSON field names and the merge of old/new rows in one paged query.
- How the chart draws (SVG polyline/area like the mockup).
- Where in `sniper`/`companion` the job comes from at save time.
- Tests: a session's lifecycle (save every minute, end on map change, Start over, under-2-minutes dropped),
  the API paging with mixed old/new rows, and the card's numbers from a known event stream.
