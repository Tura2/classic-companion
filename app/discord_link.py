"""
Posting to the group's Discord channel, through the report server (off by default; Settings → Discord).

  - Who you are: "Connect Discord" asks Discord for your user ID only (OAuth2 scope `identify`). The
    token goes once to the report server, which asks Discord whose it is, drops it, and hands back a
    signed card. The card is all Companion keeps; the token is never written anywhere.
  - Where it goes: the report server (reports.json's address, /api/discord). The channel's webhook
    stays on the server: it isn't in the exe.
  - What goes: plain fields (a sale, a fixed notice, a grind session, a valuable pickup). The server
    builds the message, and it can tag only you: no @everyone, no roles, no one else, no links.
  - Each kind has its own switch: your shop's sales, grind sessions over 10 minutes, and items
    picked up worth over 80,000 mesos each (the market median), at most 10 of those a day.
  - Nothing lost, nothing twice: each post is written to discord_outbox.json before it's sent and
    stays there until the server takes it; each post's key is remembered once sent.
"""
import threading
import time
from urllib.parse import quote

from paths import DATA_DIR, load_json, save_json

OUTBOX = DATA_DIR / "discord_outbox.json"
TIMEOUT = 10
BATCH_SECONDS = 60       # after a message, more sales wait this long and go together
KEEP_SENT = 500          # keys of sent posts remembered, so none is posted twice
MAX_QUEUE = 200
MAX_SALES = 10           # Discord's limit of embeds per message
SEND_EVERY = 2.0

GRIND_SHARE_MIN = 600    # seconds of grinding before a session is shared
DROP_SHARE_MIN = 80_000  # a pickup is shared when one is worth more than this (market median)
DROPS_A_DAY = 10
KINDS = ("sale", "notice", "grind", "drop")
SWITCH = {"sale": "discord_post_sales", "grind": "discord_post_grind", "drop": "discord_post_drops"}

_SETUP = {}              # server URL -> {"client_id", "on"}, once it answered


def server_url(reports_cfg):
    """The Discord endpoint beside the report endpoint, or None."""
    url = str((reports_cfg or {}).get("url") or "")
    return url[: -len("/api/report")] + "/api/discord" if url.endswith("/api/report") else None


def _headers(reports_cfg):
    return {"X-Companion-Key": reports_cfg["key"]}


def fetch_setup(reports_cfg, get=None):
    """{"client_id", "on"} from the server (asked once per run), or None when it can't be asked."""
    url = server_url(reports_cfg)
    if not url:
        return None
    if url in _SETUP:
        return _SETUP[url]
    if get is None:
        import requests
        get = requests.get
    try:
        r = get(url, headers=_headers(reports_cfg), timeout=TIMEOUT)
        body = r.json() if r.status_code == 200 else None
    except Exception:
        return None
    if not isinstance(body, dict) or not str(body.get("client_id", "")).isdigit():
        return None
    _SETUP[url] = {"client_id": str(body["client_id"]), "on": bool(body.get("on"))}
    return _SETUP[url]


def link(reports_cfg, token, post=None):
    """The server asks Discord whose `token` is: {"id", "name", "card"}. ValueError says what went wrong."""
    url = server_url(reports_cfg)
    if not url:
        raise ValueError("Discord isn't set up in this build.")
    if post is None:
        import requests
        post = requests.post
    try:
        r = post(url, json={"link": {"token": token}}, headers=_headers(reports_cfg), timeout=TIMEOUT)
    except Exception as e:
        raise ValueError(f"Couldn't reach the server ({type(e).__name__}).")
    try:
        body = r.json()
    except Exception:
        body = {}
    if r.status_code == 403:
        raise ValueError("This Discord account can't post.")
    if r.status_code != 200 or not isinstance(body, dict) or not body.get("card"):
        why = body.get("error") if isinstance(body, dict) else None
        raise ValueError(f"The server couldn't ask Discord who you are ({why or r.status_code}).")
    return {"id": str(body.get("id", "")), "name": body.get("name") or "?", "card": str(body["card"])}


def authorize_url(client_id, port=8765):
    redirect = quote(f"http://localhost:{port}/discord", safe="")
    return (f"https://discord.com/oauth2/authorize?client_id={quote(str(client_id))}"
            f"&response_type=token&scope=identify&redirect_uri={redirect}")


def linked(cfg):
    return bool(cfg.get("discord_enabled") and cfg.get("discord_card"))


# ---- what a post carries: plain fields, the server writes the message

def sale_data(sales, median=lambda n: None, item_id=lambda n: None, total_today=None):
    out = []
    for s in sales[:MAX_SALES]:
        e = {"item": s.get("item"), "item_id": None, "count": s.get("count") or 1, "price": s["price"], "median": None}
        if s.get("item"):
            med = median(s["item"])
            e["item_id"] = item_id(s["item"])
            e["median"] = round(med) if med else None
        out.append(e)
    return {"sales": out, "total_today": total_today}


def grind_data(card):
    """A finished grind session's post (Grind.on_final's card), or None under GRIND_SHARE_MIN."""
    active = card.get("active_s") or 0
    name = card.get("pq") or card.get("map")
    if active < GRIND_SHARE_MIN or not name:
        return None
    data = card.get("data") or {}
    loot = sorted(data.get("loot") or [], key=lambda x: -(x.get("count") or 0))[:3]
    mesos = data.get("mesos_picked") or data.get("mesos_change")
    d = {"map": name, "minutes": round(active / 60, 1), "exp_gained": card.get("exp_gained") or 0,
         "level_start": card.get("level_start"), "level_end": card.get("level_end"),
         "party": bool(data.get("party")), "loot_top": [{"name": x["name"], "count": x.get("count") or 1} for x in loot]}
    if card.get("exp_hr"):
        d["exp_hr"] = round(card["exp_hr"])
    if data.get("kills_total"):
        d["kills_total"] = data["kills_total"]
    if mesos and mesos > 0:
        d["mesos"] = mesos
    if card.get("job"):
        d["job"] = card["job"]
    return d


def drop_data(name, count, median, item_id=None, map_name=None):
    """A pickup's post when one is worth more than DROP_SHARE_MIN, else None."""
    if not name or not median or median <= DROP_SHARE_MIN:
        return None
    return {"item": name, "item_id": item_id, "count": int(count or 1), "median": round(median), "map": map_name}


class Outbox:
    """Posts waiting to go to the server, kept on disk until it takes them.

    target(): {"url", "key", "card"} now (None: not set up or not linked). build(sales): a sale
    batch's data. who(): your character's name, added to every post. post(url, json=, headers=,
    timeout=): requests.post, or a stand-in in tests."""

    def __init__(self, path, target, post, build, who=lambda: None):
        self.path, self.target, self.post, self.build, self.who = path, target, post, build, who
        self.lock = threading.Lock()
        data = load_json(path, {}) or {}
        self.queue = [e for e in (data.get("queue") or []) if e.get("kind") in KINDS]   # older kinds can't go now
        self.sent = list(data.get("sent") or [])
        self.last_post = data.get("last_post")      # when a message last went out (None: never)
        self.drops = data.get("drops") or {"date": "", "n": 0}
        self.next_at = 0.0
        self.error = ""
        self.tries = 0
        self.thread = None
        self.setup = None                           # reports.json's {"url", "key"} when set up

    def _save(self):
        save_json(self.path, {"queue": self.queue, "sent": self.sent[-KEEP_SENT:], "last_post": self.last_post,
                              "drops": self.drops})

    def add(self, kind, item, key):
        """Queue a sale (`item` = the sale) or another post's data. A key seen before is skipped."""
        with self.lock:
            if key in self.sent or any(e["key"] == key for e in self.queue):
                return False
            self.queue.append({"key": key, "kind": kind, "item": item, "added": time.time()})
            self.queue = self.queue[-MAX_QUEUE:]
            self._save()
            return True

    def drop_room(self, today):
        with self.lock:
            return self.drops.get("date") != today or self.drops.get("n", 0) < DROPS_A_DAY

    def count_drop(self, today):
        with self.lock:
            self.drops = {"date": today, "n": (self.drops.get("n", 0) if self.drops.get("date") == today else 0) + 1}
            self._save()

    def pending(self):
        return len(self.queue)

    def pump(self, now):
        """Send what's due. Returns how many queued entries the server took."""
        t = self.target()
        with self.lock:
            if not t or not self.queue or now < self.next_at:
                return 0
            first = self.queue[0]
            if first["kind"] == "sale":
                if self.last_post is not None and 0 <= now - self.last_post < BATCH_SECONDS:
                    return 0             # a message went out lately: more sales gather for the next one
                batch = [e for e in self.queue if e["kind"] == "sale"][:MAX_SALES]
                data = self.build([e["item"] for e in batch])
            else:
                batch, data = [first], dict(first["item"])
            data["character"] = self.who()
            payload = {"card": t["card"], "kind": first["kind"], "data": data}
        try:
            r = self.post(t["url"], json=payload, headers={"X-Companion-Key": t["key"]}, timeout=TIMEOUT)
            code = r.status_code
        except Exception as e:      # no internet, DNS, timeout: try again later
            code, r = None, None
            self.error = f"Couldn't reach the server ({type(e).__name__})."
        with self.lock:
            keys = {e["key"] for e in batch}
            if code is not None and 200 <= code < 300:
                self.queue = [e for e in self.queue if e["key"] not in keys]
                self.sent += [e["key"] for e in batch]
                self.last_post, self.error = now, ""
                self.tries = 0
                self._save()
                return len(batch)
            if code == 400:              # it will never be taken: drop it, go on
                self.queue = [e for e in self.queue if e["key"] not in keys]
                self.error = "The server refused a post (400)."
                self._save()
                return 0
            self.tries += 1
            if code == 429:
                try:
                    wait = float(r.json().get("retry_after", 5))
                except Exception:
                    wait = 5.0
                self.error = "Discord asked to slow down."
            else:
                wait = min(300.0, 5.0 * 2 ** min(self.tries, 6))
                if code == 401:
                    self.error = "Connect Discord again."
                elif code == 403:
                    self.error = "Posting is blocked for this Discord account."
                elif code is not None:
                    self.error = f"The server answered {code}."
            self.next_at = now + wait
            return 0

    def start(self):
        """Send in the background, never on the reader's thread."""
        if self.thread:
            return

        def run():
            while True:
                try:
                    self.pump(time.time())
                except Exception as e:
                    self.error = f"Sending failed: {e}"
                time.sleep(SEND_EVERY)
        self.thread = threading.Thread(target=run, daemon=True, name="discord")
        self.thread.start()


def share(box, cfg, kind, data, key, today=None):
    """Queue a post if Discord is set up, linked and on, and the kind's switch is on. Pickups: at most
    DROPS_A_DAY a day. Returns whether it was queued."""
    if box is None or not box.setup or not linked(cfg) or data is None:
        return False
    if SWITCH.get(kind) and not cfg.get(SWITCH[kind]):
        return False
    if kind == "drop":
        today = today or time.strftime("%Y-%m-%d")
        if not box.drop_room(today):
            return False
        if not box.add(kind, data, key):
            return False
        box.count_drop(today)
        return True
    return box.add(kind, data, key)
