"""
Cozy Market prices: read from its public item pages into cache/cozy_items.json, and kept fresh.

Cozy Market (cozy.markets) publishes an item price in each item page's meta description, and lists
every one of those pages in its public sitemap.xml. robots.txt is `Allow: /` and the site has no
terms page, so this reads what the site offers to crawlers -- it does not touch /api or the
Turnstile pass, which stay the site's own gate.

The app refreshes the file when it starts and every two hours after (keep_fresh), in the background
and one page a second: the pages aren't cached and each is built for its request, so a pass takes
about half an hour rather than a burst. tools/scrape_cozy.py does the same by hand, faster.

Each page gives one number and a count -- the "usual" sale price, how many listings and sales it
was seen in, and when it was last seen. No percentiles or history (those live behind the site's own
API), so this is checked against the spread maplestory-classic.com gives and never replaces it.
"""
import html
import json
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

SITEMAP = "https://cozy.markets/sitemap.xml"
PAGE = "https://cozy.markets/items/"
UA = {"User-Agent": "companion/1.0 (personal use)"}

EVERY_HOURS = 2         # how old a price may get before the app fetches it again
CHECK_EVERY = 600       # seconds between the app's looks for prices that got that old
RETRIES = 3
SAVE_EVERY = 25         # write progress this often, so a stop costs little
NO_PRICE = "no price line"

# Cozy writes the line several ways, and each part is optional depending on the item's data:
#   "Iron Ore usually sells for about 299 mesos on the ... Free Market. Spotted in 20154 shop
#    listings and 13303 sales, last on Nov 1, 2026."
#   "Arrows for Bows usually sells for about 1 meso on ..."          (singular)
#   "Reinforced Safe usually sells for about 300,000 mesos on ... Spotted in 32 shop listings,
#    last on ..."                                                     (no sales yet)
#   "Blood Sneak on the ... Free Market: its listings and sales. Spotted in 1 sale, last on ..."
#    (no price published at all)
# An item with no sales yet gets an asking price instead, and Cozy says so: "is usually listed for
# about" rather than "usually sells for about". That number is what sellers want, not what buyers
# paid, so it is kept with basis "listed" and is not shown as a sale price.
DATE = r"(?P<last>[A-Z][a-z]{2} \d{1,2}, \d{4})"
DESC = re.compile(
    r"^(?P<name>.+?) (?:usually sells for about (?P<price>[\d,]+) mesos? on the"
    r"|is usually listed for about (?P<listed>[\d,]+) mesos? on the"
    r"|on the) "
    r"MapleStory Classic Free Market[.:]"
    r"(?: Spotted in )?"
    r"(?:(?P<listings>[\d,]+) shop listings?)?"
    r"(?: and )?"
    r"(?:(?P<sales>[\d,]+) sales?)?"
    r", last on " + DATE + r"\."
)


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def age_hours(stamp):
    try:
        then = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return float("inf")
    return (datetime.now(timezone.utc) - then).total_seconds() / 3600


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def item_ids():
    xml = get(SITEMAP)
    return [int(i) for i in re.findall(r"<loc>https://cozy\.markets/items/(\d+)</loc>", xml)]


def meta(html_text, prop):
    m = re.search(rf'<meta (?:name|property)="{prop}" content="([^"]*)"', html_text)
    return html.unescape(m.group(1)) if m else None


def parse(page):
    """One item page -> {name, price, basis, listings, sales, last}, or None if it has no price.

    `basis` is "sold" when the number is what buyers paid, "listed" when it's only what sellers are
    asking (an item with no sales yet). Callers must not treat the two as the same number."""
    m = DESC.match(meta(page, "description") or "")
    if not m or not (m["price"] or m["listed"]):
        return None                      # no price published at all
    num = lambda s: int(s.replace(",", "")) if s else None
    return {"name": m["name"], "price": num(m["price"] or m["listed"]),
            "basis": "sold" if m["price"] else "listed",
            "listings": num(m["listings"]), "sales": num(m["sales"]), "last": m["last"]}


def wanted(row, older_than):
    """Does this row need fetching? Failures always do; rows with a price (or with none published)
    only when they're older than `older_than` hours, if that's given."""
    if not row or (row.get("error") and row["error"] != NO_PRICE):
        return True
    return older_than is not None and age_hours(row.get("fetched")) > older_than


def refresh(path, older_than=None, workers=4, delay=0.6, stop=None, verbose=False, say=print, on_save=None):
    """Fetch every item page that needs it (see wanted) into the JSON file at `path`, `workers`
    pages at a time, each worker waiting `delay` seconds between pages and longer when the site
    pushes back. A failed fetch keeps the price the file already had. Safe to stop and run again:
    progress is saved as it goes. Returns how many pages were read."""
    stop = stop or threading.Event()
    data = json.loads(path.read_text("utf-8")) if path.exists() else {}
    out = data.get("items", {})
    for row in out.values():             # rows from before fetch times were kept: the file's own date
        if row and "fetched" not in row and "error" not in row:
            row["fetched"] = data.get("updatedAt")
    ids = item_ids()
    todo = [i for i in ids if wanted(out.get(str(i)), older_than)]
    if not todo:
        return 0
    say(f"Cozy Market: {len(ids)} items, {len(ids) - len(todo)} up to date, {len(todo)} to fetch.")
    lock, pace = threading.Lock(), [delay]
    counts = {"ok": 0, "odd": 0, "fail": 0}
    started, saved, queue = time.time(), [0], list(todo)

    def fetch(item_id):
        key, error = str(item_id), None
        for attempt in range(RETRIES):
            if stop.is_set():
                return
            try:
                row = parse(get(f"{PAGE}{item_id}"))
                with lock:
                    out[key] = {**row, "fetched": now()} if row else {"error": NO_PRICE, "fetched": now()}
                    counts["ok" if row else "odd"] += 1
                break
            except urllib.error.HTTPError as e:
                error = f"HTTP {e.code}"
                if e.code in (429, 503):
                    # the site is asking to slow down: every worker slows down, not just this one
                    with lock:
                        pace[0] = min(pace[0] * 1.5, 10.0)
                    time.sleep(2 ** attempt * 2)
                elif attempt < RETRIES - 1:
                    time.sleep(2 ** attempt)
            except Exception as e:
                error = str(e)[:80]
                if attempt < RETRIES - 1:
                    time.sleep(2 ** attempt)
        else:
            with lock:
                if "price" not in out.get(key, {}):
                    out[key] = {"error": error}
                counts["fail"] += 1
        time.sleep(pace[0])

    def worker():
        while not stop.is_set():
            with lock:
                if not queue:
                    return
                item_id = queue.pop(0)
            fetch(item_id)
            with lock:
                n = counts["ok"] + counts["odd"] + counts["fail"]
                if n - saved[0] >= SAVE_EVERY:
                    saved[0] = n
                    save(path, data, out)
                    if on_save:
                        on_save()       # the app uses the prices so far, not only after the pass
                    if verbose:
                        rate = n / max(time.time() - started, 1e-9)
                        say(f"  {n}/{len(todo)}  ({rate:.1f}/s, ~{(len(todo) - n) / rate / 60:.1f} min left, "
                            f"delay {pace[0]:.1f}s)")

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        stop.set()
        say("\nStopped. Progress is saved; run again to continue.")
    with lock:
        # a whole pass: items gone from the site go from the file too, unless the sitemap came back
        # much shorter than what's known (a partly read sitemap would wipe good prices)
        if not stop.is_set() and len(ids) >= len(out) / 2:
            listed = {str(i) for i in ids}
            for key in [k for k in out if k not in listed]:
                del out[key]
        save(path, data, out)
    n = counts["ok"] + counts["odd"] + counts["fail"]
    say(f"Cozy Market: read {n} pages in {(time.time() - started) / 60:.0f} min "
        f"({counts['fail']} failed, {counts['odd']} without a price). Prices as of {data['updatedAt']}.")
    return n


def save(path, data, out):
    """Write the file. Its date is when the oldest price in it was fetched, so it never claims to be
    fresher than its stalest price."""
    data["items"] = out
    stamps = [v["fetched"] for v in out.values() if v and "price" in v and v.get("fetched")]
    data["updatedAt"] = min(stamps) if stamps else now()
    data["source"] = "cozy.markets item pages (public meta descriptions, via sitemap.xml)"
    data["note"] = ("One price per item: Cozy's 'usual' sale price, listing/sale counts and the day "
                    "it was last seen. No percentiles or history -- those are behind the site's API, "
                    "so this is checked against the maplestory-classic.com spread and never replaces it.")
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), "utf-8")
    tmp.replace(path)


def keep_fresh(data, hours=EVERY_HOURS):
    """The app's Cozy prices, never much older than `hours`: when it starts, and every CHECK_EVERY
    seconds after, it fetches the prices that got that old, one page a second in the background, so
    the work is spread out instead of coming in bursts. Restarting fetches nothing that's still
    fresh. A finished pass goes straight into the market's prices. Run in a daemon thread; a failed
    pass (no internet) keeps the old prices and tries again at the next look."""
    from gamedata import COZY_FILE, Cozy
    while True:
        try:
            reload = lambda: setattr(data.market, "cozy", Cozy())
            if refresh(COZY_FILE, older_than=hours, workers=1, delay=1.0, on_save=reload):
                reload()
        except Exception as e:
            print("Cozy Market prices not refreshed:", e)
        time.sleep(CHECK_EVERY)
