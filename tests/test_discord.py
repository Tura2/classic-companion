"""Discord: who gets pinged, batching, and an outbox that never loses or repeats a sale."""
import json

import discord_link as dl


class Resp:
    def __init__(self, code=200, body=None):
        self.status_code, self._body = code, body or {}

    def json(self):
        return self._body


class Poster:
    """Stands in for requests.post: answers from a script, records what was posted."""

    def __init__(self, *answers):
        self.answers, self.posts = list(answers), []

    def __call__(self, url, json=None, timeout=None):
        self.posts.append(json)
        a = self.answers.pop(0) if self.answers else Resp(200)
        if isinstance(a, Exception):
            raise a
        return a


def sale(key, item="Bazlud", price=24999, count=1, ts=0.0):
    return {"key": key, "item": item, "count": count, "price": price, "total_sales": price, "ts": ts}


def build(sales):
    return dl.sale_message(sales, "123", "Tura1", median=lambda n: 20000, img=lambda n: None, total_today=24999)


def outbox(tmp_path, poster):
    return dl.Outbox(tmp_path / "outbox.json", lambda: "https://discord.example/webhook", poster, build)


def test_only_the_owner_is_mentioned():
    m = build([sale("a")])
    assert m["allowed_mentions"] == {"parse": [], "users": ["123"]}
    assert m["content"].startswith("<@123> sold Bazlud ×1 for 24,999 mesos")
    assert m["username"] == "Tura1"
    assert "25% above the market median" in m["embeds"][0]["description"]


def test_unknown_item_still_says_how_much():
    m = build([sale("a", item=None, price=777)])
    assert m["content"] == "<@123> sold something for +777 mesos"


def test_first_sale_goes_at_once_then_one_message_a_minute(tmp_path):
    p = Poster()
    box = outbox(tmp_path, p)
    box.add("sale", sale("s:1"), "s:1")
    assert box.pump(0) == 1
    for k in ("s:2", "s:3", "s:4"):
        box.add("sale", sale(k), k)
    assert box.pump(10) == 0                       # within a minute of the last message: held
    assert box.pump(61) == 3 and len(p.posts) == 2
    assert len(p.posts[1]["embeds"]) == 3


def test_429_waits_retry_after(tmp_path):
    p = Poster(Resp(429, {"retry_after": 2.0}))
    box = outbox(tmp_path, p)
    box.add("sale", sale("s:1"), "s:1")
    assert box.pump(0) == 0
    assert box.pump(1) == 0 and len(p.posts) == 1   # not resent before retry_after
    assert box.pump(2.5) == 1 and len(p.posts) == 2


def test_no_internet_keeps_it_on_disk_and_a_restart_sends_it_once(tmp_path):
    box = outbox(tmp_path, Poster(OSError("no internet")))
    box.add("sale", sale("s:1"), "s:1")
    assert box.pump(0) == 0
    assert json.loads((tmp_path / "outbox.json").read_text("utf-8"))["queue"]
    p = Poster()
    again = outbox(tmp_path, p)                     # the app restarted
    assert again.pump(1000) == 1 and again.pump(2000) == 0 and len(p.posts) == 1


def test_the_same_sale_twice_is_posted_once(tmp_path):
    p = Poster()
    box = outbox(tmp_path, p)
    box.add("sale", sale("s:1"), "s:1")
    box.pump(0)
    box.add("sale", sale("s:1"), "s:1")
    assert box.pump(100) == 0 and len(p.posts) == 1


def test_text_messages_go_as_they_are(tmp_path):
    p = Poster()
    box = outbox(tmp_path, p)
    box.add("text", dl.text_message("123", "Tura1", "Test from Companion"), "t:1")
    assert box.pump(0) == 1
    assert p.posts[0]["allowed_mentions"] == {"parse": [], "users": ["123"]}


def test_authorize_url_asks_only_who_you_are():
    url = dl.authorize_url("999")
    assert "response_type=token" in url and "scope=identify" in url and "client_id=999" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fdiscord" in url
