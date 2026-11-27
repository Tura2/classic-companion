"""Discord through the report server: what is posted, batching, and an outbox that never loses or
repeats a post; the grind and pickup posts and their switches."""
import json

import discord_link as dl

SERVER = {"url": "https://reports.example/api/report", "key": "k3y"}
CARD = "v1.123.1764240000.sig"


class Resp:
    def __init__(self, code=200, body=None):
        self.status_code, self._body = code, body or {}

    def json(self):
        return self._body


class Poster:
    """Stands in for requests.post: answers from a script, records what was posted and how."""

    def __init__(self, *answers):
        self.answers, self.posts, self.calls = list(answers), [], []

    def __call__(self, url, json=None, headers=None, timeout=None):
        self.posts.append(json)
        self.calls.append({"url": url, "headers": headers or {}})
        a = self.answers.pop(0) if self.answers else Resp(200)
        if isinstance(a, Exception):
            raise a
        return a


def sale(key, item="Bazlud", price=24999, count=1, ts=0.0):
    return {"key": key, "item": item, "count": count, "price": price, "total_sales": price, "ts": ts}


def build(sales):
    return dl.sale_data(sales, median=lambda n: 20000, item_id=lambda n: 4000000, total_today=24999)


def target():
    return {"url": "https://reports.example/api/discord", "key": "k3y", "card": CARD}


def outbox(tmp_path, poster, tgt=target):
    return dl.Outbox(tmp_path / "outbox.json", tgt, poster, build, who=lambda: "Hero1")


def card(active_s=600.0, **over):
    c = {"id": 7, "map": "Ant Tunnel I", "pq": None, "active_s": active_s, "exp_gained": 150000, "exp_hr": 108433.4,
         "level_start": 40, "level_end": 41, "pct_start": 12.0, "pct_end": 3.5, "job": "Hunter", "character": "Hero1",
         "data": {"kills_total": 512, "party": False, "mesos_picked": 21500,
                  "loot": [{"name": "Snail Shell", "count": 3}, {"name": "Horny Mushroom Cap", "count": 40},
                           {"name": "Mesos Bag", "count": 5}, {"name": "Red Potion", "count": 1}]}}
    c.update(over)
    return c


def cfg(**over):
    c = {"discord_enabled": True, "discord_card": CARD, "discord_id": "123", "discord_post_sales": True,
         "discord_post_grind": True, "discord_post_drops": True}
    c.update(over)
    return c


# ---- the outbox, posting to the server

def test_posts_go_to_the_server_with_the_card_and_key(tmp_path):
    p = Poster()
    box = outbox(tmp_path, p)
    box.add("sale", sale("s:1"), "s:1")
    assert box.pump(0) == 1
    assert p.calls[0]["url"] == "https://reports.example/api/discord"
    assert p.calls[0]["headers"] == {"X-Companion-Key": "k3y"}
    body = p.posts[0]
    assert body["card"] == CARD and body["kind"] == "sale"
    assert body["data"]["character"] == "Hero1"
    assert body["data"]["sales"] == [{"item": "Bazlud", "item_id": 4000000, "count": 1, "price": 24999, "median": 20000}]
    assert body["data"]["total_today"] == 24999


def test_nothing_goes_without_a_target(tmp_path):
    p = Poster()
    box = outbox(tmp_path, p, tgt=lambda: None)
    box.add("sale", sale("s:1"), "s:1")
    assert box.pump(0) == 0 and not p.posts and box.pending() == 1


def test_first_sale_goes_at_once_then_one_message_a_minute(tmp_path):
    p = Poster()
    box = outbox(tmp_path, p)
    box.add("sale", sale("s:1"), "s:1")
    assert box.pump(0) == 1
    for k in ("s:2", "s:3", "s:4"):
        box.add("sale", sale(k), k)
    assert box.pump(10) == 0                       # within a minute of the last message: held
    assert box.pump(61) == 3 and len(p.posts) == 2
    assert len(p.posts[1]["data"]["sales"]) == 3


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


def test_the_same_post_twice_is_posted_once(tmp_path):
    p = Poster()
    box = outbox(tmp_path, p)
    box.add("sale", sale("s:1"), "s:1")
    box.pump(0)
    box.add("sale", sale("s:1"), "s:1")
    assert box.add("drop", {"item": "Work Gloves"}, "drop:1:Work Gloves:5") is True
    assert box.add("drop", {"item": "Work Gloves"}, "drop:1:Work Gloves:5") is False
    assert box.pump(100) == 1 and len(p.posts) == 2


def test_other_posts_go_as_they_are(tmp_path):
    p = Poster()
    box = outbox(tmp_path, p)
    box.add("notice", {"what": "test"}, "n:1")
    assert box.pump(0) == 1
    assert p.posts[0] == {"card": CARD, "kind": "notice", "data": {"what": "test", "character": "Hero1"}}


def test_old_text_entries_are_dropped_on_load(tmp_path):
    (tmp_path / "outbox.json").write_text(json.dumps({"queue": [
        {"key": "t:1", "kind": "text", "item": {"content": "<@1> hi"}, "added": 0},
        {"key": "s:1", "kind": "sale", "item": sale("s:1"), "added": 0}], "sent": ["s:0"], "last_post": None}), "utf-8")
    box = outbox(tmp_path, Poster())
    assert [e["key"] for e in box.queue] == ["s:1"]
    assert box.sent == ["s:0"]


def test_401_keeps_the_queue_and_asks_to_connect_again(tmp_path):
    box = outbox(tmp_path, Poster(Resp(401)))
    box.add("notice", {"what": "test"}, "n:1")
    assert box.pump(0) == 0 and box.pending() == 1
    assert box.error == "Connect Discord again."
    box = outbox(tmp_path, Poster(Resp(403)))
    assert box.pump(1000) == 0 and box.error == "Posting is blocked for this Discord account."


def test_400_drops_the_post_it_will_never_take(tmp_path):
    p = Poster(Resp(400))
    box = outbox(tmp_path, p)
    box.add("notice", {"what": "test"}, "n:1")
    box.add("notice", {"what": "soldout"}, "n:2")
    assert box.pump(0) == 0
    assert [e["key"] for e in box.queue] == ["n:2"]
    assert box.pump(1) == 1


# ---- what is shared

def test_grind_data_needs_ten_minutes():
    assert dl.grind_data(card(599.0)) is None
    d = dl.grind_data(card(600.0))
    assert d["map"] == "Ant Tunnel I" and d["minutes"] == 10.0
    assert d["exp_gained"] == 150000 and d["exp_hr"] == 108433
    assert d["level_start"] == 40 and d["level_end"] == 41
    assert d["kills_total"] == 512 and d["party"] is False and d["mesos"] == 21500 and d["job"] == "Hunter"
    assert d["loot_top"] == [{"name": "Horny Mushroom Cap", "count": 40}, {"name": "Mesos Bag", "count": 5},
                             {"name": "Snail Shell", "count": 3}]
    pq = dl.grind_data(card(900.0, map="1st Accompaniment <2nd Stage>", pq="Kerning PQ", exp_hr=None))
    assert pq["map"] == "Kerning PQ" and "exp_hr" not in pq


def test_drop_data_over_80k_only():
    assert dl.drop_data("Work Gloves", 1, 80_000, 1082002, "Ant Tunnel I") is None
    assert dl.drop_data("Work Gloves", 1, None, 1082002, "Ant Tunnel I") is None
    assert dl.drop_data("Work Gloves", 1, 80_001.4, 1082002, "Ant Tunnel I") == {
        "item": "Work Gloves", "item_id": 1082002, "count": 1, "median": 80001, "map": "Ant Tunnel I"}


def test_share_respects_each_switch_and_the_link(tmp_path):
    box = outbox(tmp_path, Poster())
    box.setup = SERVER
    g = dl.grind_data(card())
    assert dl.share(box, cfg(discord_post_grind=False), "grind", g, "grind:7") is False
    assert dl.share(box, cfg(discord_enabled=False), "grind", g, "grind:7") is False
    assert dl.share(box, cfg(discord_card=None), "grind", g, "grind:7") is False       # an old link: no card
    assert dl.share(box, cfg(discord_post_drops=False), "drop", {"item": "X"}, "drop:x") is False
    assert dl.share(box, cfg(discord_post_sales=False), "notice", {"what": "test"}, "n:1") is True
    assert dl.share(box, cfg(), "grind", g, "grind:7") is True
    assert dl.share(box, cfg(), "grind", g, "grind:7") is False        # the same card saved final again
    box.setup = None
    assert dl.share(box, cfg(), "grind", g, "grind:8") is False


def test_ten_drops_a_day(tmp_path):
    box = outbox(tmp_path, Poster())
    box.setup = SERVER
    for i in range(10):
        assert dl.share(box, cfg(), "drop", {"item": "X"}, f"drop:{i}", today="2026-11-27") is True
    assert dl.share(box, cfg(), "drop", {"item": "X"}, "drop:10", today="2026-11-27") is False
    assert dl.share(box, cfg(), "drop", {"item": "X"}, "drop:0", today="2026-11-28") is False   # a repeat isn't counted
    assert dl.share(box, cfg(), "drop", {"item": "X"}, "drop:11", today="2026-11-28") is True
    assert outbox(tmp_path, Poster()).drops == {"date": "2026-11-28", "n": 1}   # kept on disk


def test_server_url_from_reports_url():
    assert dl.server_url(SERVER) == "https://reports.example/api/discord"
    assert dl.server_url({"url": "https://x.example/elsewhere", "key": "k"}) is None
    assert dl.server_url(None) is None


def test_fetch_setup_asks_once_and_keeps_it():
    asked = []

    def get(url, headers=None, timeout=None):
        asked.append((url, headers))
        return Resp(200, {"client_id": "999", "on": True})
    dl._SETUP.clear()
    assert dl.fetch_setup(SERVER, get) == {"client_id": "999", "on": True}
    assert dl.fetch_setup(SERVER, get) == {"client_id": "999", "on": True}
    assert asked == [("https://reports.example/api/discord", {"X-Companion-Key": "k3y"})]

    def down(url, headers=None, timeout=None):
        raise OSError("no internet")
    dl._SETUP.clear()
    assert dl.fetch_setup(SERVER, down) is None


def test_link_returns_the_card_and_says_what_went_wrong():
    p = Poster(Resp(200, {"id": "123", "name": "Tura", "card": CARD}))
    assert dl.link(SERVER, "tok", p) == {"id": "123", "name": "Tura", "card": CARD}
    assert p.posts[0] == {"link": {"token": "tok"}} and p.calls[0]["headers"] == {"X-Companion-Key": "k3y"}
    for answer, words in ((Resp(502, {"error": "Discord said 401"}), "Discord said 401"),
                          (Resp(403), "can't post"), (OSError("down"), "Couldn't reach")):
        try:
            dl.link(SERVER, "tok", Poster(answer))
            assert False, "no error"
        except ValueError as e:
            assert words in str(e)


def test_authorize_url_asks_only_who_you_are():
    url = dl.authorize_url("999")
    assert "response_type=token" in url and "scope=identify" in url and "client_id=999" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fdiscord" in url


def test_shop_notices_follow_the_sales_switch(tmp_path):
    box = outbox(tmp_path, Poster())
    box.setup = SERVER
    off = cfg(discord_post_sales=False)
    for what in ("soldout", "closed", "correction"):
        assert dl.share(box, off, "notice", {"what": what}, f"n:{what}") is False
    for what in ("connected", "test"):
        assert dl.share(box, off, "notice", {"what": what}, f"n:{what}") is True
