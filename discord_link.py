"""
Posting your shop's sales to the group's Discord channel (off by default; Settings → Discord).

  - Who you are: "Connect Discord" asks Discord for your user ID only (OAuth2 scope `identify`). The
    access token is used once to read the ID and dropped: it's never written anywhere.
  - Where it goes: one channel webhook, set in the build (discord.json next to build.bat: the
    webhook URL and the app's client ID). A webhook can only post; it can't read the channel.
  - Who gets pinged: only you. Every message carries allowed_mentions = {"parse": [], "users": [your
    ID]}, so it can't ping anyone else, @everyone or a role.
  - Nothing lost, nothing twice: each sale is written to discord_outbox.json before it's sent and
    stays there until Discord answers 2xx; each sale's key is remembered once sent.
"""
import json
import threading
import time
from urllib.parse import quote

from paths import APP_DIR, RES_DIR, load_json, save_json

OUTBOX = APP_DIR / "discord_outbox.json"
API = "https://discord.com/api"
BATCH_SECONDS = 60       # after a message, more sales wait this long and go together
TIMEOUT = 10
KEEP_SENT = 500          # keys of sent sales remembered, so none is posted twice
MAX_QUEUE = 200
MAX_EMBEDS = 10          # Discord's limit per message
SEND_EVERY = 2.0


def load_discord_config():
    """{"webhook", "client_id"} from discord.json bundled in the build (or next to the source), or None."""
    for folder in (RES_DIR, APP_DIR):
        cfg = load_json(folder / "discord.json", None)
        if isinstance(cfg, dict) and str(cfg.get("webhook", "")).startswith("https://") and cfg.get("client_id"):
            return {"webhook": cfg["webhook"], "client_id": str(cfg["client_id"])}
    return None


def authorize_url(client_id, port=8765):
    redirect = quote(f"http://localhost:{port}/discord", safe="")
    return (f"https://discord.com/oauth2/authorize?client_id={quote(str(client_id))}"
            f"&response_type=token&scope=identify&redirect_uri={redirect}")


def who_is(token, get=None):
    """{"id", "name"} of the Discord user the token belongs to. The token isn't kept."""
    if get is None:
        import requests
        get = requests.get
    r = get(f"{API}/users/@me", headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    if r.status_code != 200:
        raise ValueError(f"Discord said {r.status_code}")
    me = r.json()
    if not str(me.get("id", "")).isdigit():
        raise ValueError("Discord sent no user ID")
    return {"id": str(me["id"]), "name": me.get("global_name") or me.get("username") or "?"}


def _mentions(discord_id):
    return {"parse": [], "users": [str(discord_id)]}


def text_message(discord_id, character, text):
    return {"content": f"<@{discord_id}> {text}", "username": character or "Companion",
            "allowed_mentions": _mentions(discord_id)}


def _what(s):
    return f"{s['item']} ×{s.get('count') or 1}" if s.get("item") else "something"


def sale_message(sales, discord_id, character, median=lambda n: None, img=lambda n: None, total_today=None):
    """The webhook payload for one or more sales (at most MAX_EMBEDS)."""
    sales = sales[:MAX_EMBEDS]
    if len(sales) == 1:
        s = sales[0]
        content = f"<@{discord_id}> sold {_what(s)} for {s['price']:,} mesos" if s.get("item") else \
            f"<@{discord_id}> sold something for +{s['price']:,} mesos"
    else:
        content = f"<@{discord_id}> sold {len(sales)} things for {sum(s['price'] for s in sales):,} mesos"
    embeds = []
    for s in sales:
        desc = f"{s['price']:,} mesos"
        med = median(s["item"]) if s.get("item") else None
        if med:
            unit = s["price"] / (s.get("count") or 1)
            pct = round((unit - med) / med * 100)
            desc += f" · {abs(pct)}% {'above' if pct >= 0 else 'below'} the market median" if pct else " · at the market median"
        e = {"title": _what(s) if s.get("item") else "Sold something", "description": desc}
        if s.get("item") and img(s["item"]):
            e["thumbnail"] = {"url": img(s["item"])}
        if total_today:
            e["footer"] = {"text": f"Shop total today: {total_today:,}"}
        embeds.append(e)
    return {"content": content, "username": character or "Companion", "embeds": embeds,
            "allowed_mentions": _mentions(discord_id)}


class Outbox:
    """Sales and messages waiting to go to the webhook, kept on disk until Discord takes them.

    webhook(): the URL now (None: not set up). build(sales): the payload for a batch of sales.
    post(url, json=, timeout=): requests.post, or a stand-in in tests."""

    def __init__(self, path, webhook, post, build):
        self.path, self.webhook, self.post, self.build = path, webhook, post, build
        self.lock = threading.Lock()
        data = load_json(path, {}) or {}
        self.queue = list(data.get("queue") or [])
        self.sent = list(data.get("sent") or [])
        self.last_post = data.get("last_post")      # when a message last went out (None: never)
        self.next_at = 0.0
        self.error = ""
        self.tries = 0
        self.thread = None

    def _save(self):
        save_json(self.path, {"queue": self.queue, "sent": self.sent[-KEEP_SENT:], "last_post": self.last_post})

    def add(self, kind, item, key):
        """Queue a sale (`item` = the sale) or a ready payload (kind "text"). A key seen before is skipped."""
        with self.lock:
            if key in self.sent or any(e["key"] == key for e in self.queue):
                return False
            self.queue.append({"key": key, "kind": kind, "item": item, "added": time.time()})
            self.queue = self.queue[-MAX_QUEUE:]
            self._save()
            return True

    def pending(self):
        return len(self.queue)

    def pump(self, now):
        """Send what's due. Returns how many queued entries Discord took."""
        url = self.webhook()
        with self.lock:
            if not url or not self.queue or now < self.next_at:
                return 0
            first = self.queue[0]
            if first["kind"] == "sale":
                if self.last_post is not None and 0 <= now - self.last_post < BATCH_SECONDS:
                    return 0             # a message went out lately: more sales gather for the next one
                batch = [e for e in self.queue if e["kind"] == "sale"][:MAX_EMBEDS]
                payload = self.build([e["item"] for e in batch])
            else:
                batch, payload = [first], first["item"]
        try:
            r = self.post(url + ("&" if "?" in url else "?") + "wait=true", json=payload, timeout=TIMEOUT)
            code = r.status_code
        except Exception as e:      # no internet, DNS, timeout: try again later
            code, r = None, None
            self.error = f"Couldn't reach Discord ({type(e).__name__})."
        with self.lock:
            if code is not None and 200 <= code < 300:
                keys = {e["key"] for e in batch}
                self.queue = [e for e in self.queue if e["key"] not in keys]
                self.sent += [e["key"] for e in batch]
                self.last_post, self.error = now, ""
                self.tries = 0
                self._save()
                return len(batch)
            self.tries += 1
            if code == 429:
                try:
                    wait = float(r.json().get("retry_after", 5))
                except Exception:
                    wait = 5.0
                self.error = "Discord asked to slow down."
            else:
                wait = min(300.0, 5.0 * 2 ** min(self.tries, 6))
                if code is not None:
                    self.error = f"Discord answered {code}."
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
