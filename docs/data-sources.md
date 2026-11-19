# Data sources

Where every piece of data comes from, and what's left out on purpose.

- Game data: OSMS Data Explorer (MIT), github.com/ohmi69/osms_datamine_dashboard. Refreshed every 12h.
- Updates: Companion's own latest release on GitHub (api.github.com/repos/Tura2/classic-companion),
  asked once each time the installed Companion starts.
- Prices: maplestory-classic.com/market.json. Refreshed every 30 min. The file is rebuilt once a day
  (~07:00 UTC), so intraday moves aren't in it.
- Second prices: Cozy Market (cozy.markets) item pages, read into `cache/cozy_items.json` by the
  app itself (`app/cozy.py`): when it starts and every 10 minutes after, it fetches again any price
  older than two hours, in the background and one page a second (the pages aren't cached, so a full
  pass is spread over about half an hour rather than a burst). Cozy publishes one number per item -- its usual sale price, the listing
  and sale counts, and the day it was last seen -- in each page's meta description, and lists every
  page in its public sitemap; robots allows all and the site has no terms page. Its `/api` (behind a
  browser check) is not used. Labels and the dashboard show both prices, MSC in blue and Cozy in
  purple. Cozy has no spread, so the verdict against Cozy uses maplestory-classic.com's spread moved
  to Cozy's price, and a verdict is claimed only when both agree. Prices Cozy only has for items no
  one bought yet (asking prices) are left out. Cozy names an item's male and female versions the
  same; for those the busier one's price is used. The dashboard footer shows when Cozy's prices were
  fetched; older than two weeks, they are left out. By hand, and faster:
  `python tools/scrape_cozy.py --refresh` fetches every price again (about 5 minutes). Without the
  file the app works on maplestory-classic.com alone.
- ACC to never miss: NiaDB's Classic accuracy values (meowdb.com/msclassic), interpolated.
- Every monster's drop list (This map on Now): MapleClassic Wiki (mapleclassic.wiki), CC BY-NC-SA 4.0,
  via Club FM's public data (github.com/maplefm/maplefm.github.io, `data/itemguide.json`), credited
  under the list. Rates only where players counted them; optional, the app runs without it.
- The game's portal picture: maplestory.io (Map.wz/MapHelper.img/portal/game/pv), fetched once and
  kept in `cache/portal.webp`. Classic's Equipment Inventory picture is bundled (`web/equip_classic.png`).
- Quest steps, who takes each quest back, and monster drops: Classic Maple Wiki contributors
  (classicmaple.wiki/data), much of it from MapleClassic Wiki (mapleclassic.wiki), CC BY-NC-SA 4.0.
  Downloaded and refreshed like the game data, reformatted for the dashboard, credited with links
  on each quest. Non-commercial: Companion is free.
- SP order per job: NiaDB's class guides (meowdb.com/msclassic/guides), credited on the Skills
  tab with a link to each guide, as NiaDB's reuse page asks for single facts. Using NiaDB's
  prices or crawling the site would need their permission first (contact@meowdb.com).
- Game images belong to Nexon. Fine for personal use; don't sell them. The logo is the game's own Maple Leaf
  and Steely Throwing Knives item pictures, on a badge.

Not used, on purpose: MesoWatch (meso.watch) says its price data isn't free to copy, disallows its
data files in robots.txt and names crawlers and AI agents on a full disallow, so nothing of its is
read here. maplestory.watch sits entirely behind a Cloudflare challenge. NiaDB (meowdb.com) asks
tools to get permission before using its API or data files. Any of them can be added once its owner
says yes.

[Back to the README](../README.md)
