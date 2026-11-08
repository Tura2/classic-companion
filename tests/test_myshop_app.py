"""Your store's sales through the app: listed in the dashboard, posted only when Discord is on."""
from types import SimpleNamespace

import sniper
from shopwatch import ShopWatch


class Box:
    def __init__(self):
        self.added = []

    def add(self, kind, item, key):
        self.added.append((kind, key))
        return True


def app(**cfg):
    sent = []
    state = {"profile": {}, "outbox": Box(), "discord_send": sent.append}
    return SimpleNamespace(state=state, sent=sent, shopwatch=ShopWatch(),
                           cfg={"screen_reading": True, "sound": False, "discord_post_sales": True, **cfg})


def seen(total, hud=True, items=None):
    items = items if items is not None else [{"name": "Bazlud", "text": "Bazlud", "count": 1, "price": 450000, "sold": False}]
    return {"myshop": {"title": "Scrolls", "mesos": 1, "items": items,
                       "panel": {"total_sales": total, "total_received": 0, "rows": []}},
            **({"hud": {"level": 32}} if hud else {})}


def run(a, totals, t0=0):
    for i, t in enumerate(totals):
        sniper.handle_myshop(a, seen(t) if t is not None else {"hud": {"level": 32}}, t0 + 6 * i)


def test_a_sale_is_listed_and_posted_once():
    a = app(discord_enabled=True, discord_id="123")
    run(a, [0, 0, 450000, 450000, 450000])
    assert [s["item"] for s in a.state["myshop"]["sales"]] == ["Bazlud"]
    assert a.state["outbox"].added == [("sale", a.state["myshop"]["sales"][0]["key"])]


def test_discord_off_still_lists_the_sale():
    a = app(discord_enabled=False)
    run(a, [0, 0, 450000, 450000])
    assert len(a.state["myshop"]["sales"]) == 1 and a.state["outbox"].added == []


def test_an_hour_of_steady_reads_sends_nothing():
    a = app(discord_enabled=True, discord_id="123")
    run(a, [0] * 600)
    assert a.state["outbox"].added == [] and a.sent == []


def test_one_misread_total_sends_nothing():
    a = app(discord_enabled=True, discord_id="123")
    run(a, [0, 0, 4500000, 0, 0])
    assert a.state["outbox"].added == []


def test_status_says_why_the_store_isnt_watched():
    a = app()
    sniper.handle_myshop(a, None, 0)
    assert a.state["myshop"]["reason"] == "Can't see the game: is it minimized?"
    a.cfg["screen_reading"] = False
    sniper.handle_myshop(a, None, 1)
    assert a.state["myshop"]["reason"] == "Screen reading is off."


def test_shop_closed_pings_once():
    a = app(discord_enabled=True, discord_id="123")
    run(a, [0, 0])
    for i in range(6):        # the store and the HUD gone: the login screen
        sniper.handle_myshop(a, {"windows": {}}, 20 + i)
    assert len([m for m in a.sent if "closed" in m]) == 1


def test_a_wrong_sale_gets_a_correction_on_discord():
    a = app(discord_enabled=True, discord_id="123")
    items = [{"name": "Mokbi Throwing Stars", "text": "Mokbi Throwing Stars", "count": 1, "price": 1100, "sold": False}]

    def look(total, mesos, rows_left=True):
        return {"myshop": {"title": "Scrolls", "mesos": mesos, "items": items if rows_left else [],
                           "panel": {"total_sales": total, "total_received": 0, "rows": []} if total is not None else None},
                "hud": {"level": 32}}
    reads = [look(5245, 1000)] * 2 + [look(None, 1000)] * 2 + [look(None, 1000 + round(1100 * 0.97), False)] * 2         + [look(5245, 2067, False)] * 2
    for i, r in enumerate(reads):
        sniper.handle_myshop(a, r, 6 * i)
    assert [k for k, _ in a.state["outbox"].added] == ["sale"]
    assert len([m for m in a.sent if m.startswith("correction: Mokbi Throwing Stars")]) == 1
    assert a.state["myshop"]["sales"] == []
