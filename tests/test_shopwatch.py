"""Sales in your own store: only a Total Sales rise two reads agree on is a sale."""
from shopwatch import ShopWatch


def store(total=0, items=None, mesos=1000, rows=None, panel=True):
    items = items if items is not None else [{"name": "Bazlud", "text": "Bazlud", "count": 1, "price": 24999, "sold": False},
                                             {"name": "Emerald Earrings", "text": "Emerald Earrings", "count": 1,
                                              "price": 12999, "sold": False}]
    return {"title": "Scrolls", "mesos": mesos, "items": items,
            "panel": {"total_sales": total, "total_received": round(total * 0.97), "rows": rows or []} if panel else None}


def feed(w, reads, t0=0.0):
    out = []
    for i, r in enumerate(reads):
        out += w.update(r, t0 + i * 6)
    return out


def test_one_rise_is_not_yet_a_sale_two_are():
    w = ShopWatch()
    assert feed(w, [store(0), store(0), store(24999)]) == []
    sales = w.update(store(24999), 30)
    assert len(sales) == 1 and sales[0]["price"] == 24999 and sales[0]["total_sales"] == 24999
    assert sales[0]["key"].endswith(":24999")
    assert w.update(store(24999), 36) == []          # the same total again: nothing new


def test_drop_and_jump_are_misreads():
    w = ShopWatch()
    feed(w, [store(5000), store(5000)])
    assert feed(w, [store(500), store(500)], 20) == []                          # a total doesn't go down
    assert feed(w, [store(99_000_000), store(99_000_000)], 40) == []            # far beyond what's listed
    assert w.status["total"] == 5000


def test_new_store_session_is_not_a_sale():
    w = ShopWatch()
    feed(w, [store(50000), store(50000)])
    first = w.status["session"]
    assert feed(w, [None, None, None, store(0), store(0)], 20) == []
    assert w.status["session"] != first and w.status["total"] == 0
    sales = feed(w, [store(12999), store(12999)], 60)
    assert len(sales) == 1 and sales[0]["key"].startswith(w.status["session"] + ":")


def test_item_named_from_the_panel_rows():
    w = ShopWatch()
    feed(w, [store(0), store(0)])
    row = [{"name": "Bazlud", "count": 1, "price": 24999}]
    sales = feed(w, [store(24999, rows=row), store(24999, rows=row)], 20)
    assert sales[0]["item"] == "Bazlud" and sales[0]["count"] == 1


def test_item_named_by_its_price():
    w = ShopWatch()
    feed(w, [store(0), store(0)])
    # two bundles of Emerald Earrings: its row stays (more are left), the total says which row
    sales = feed(w, [store(25998), store(25998)], 20)
    assert sales[0]["item"] == "Emerald Earrings" and sales[0]["count"] == 2


def test_two_rows_fit_the_one_that_sold_out_wins():
    w = ShopWatch()
    two = [{"name": "Bazlud", "text": "Bazlud", "count": 1, "price": 5000, "sold": False},
           {"name": "Blue Bamboo Hat", "text": "Blue Bamboo Hat", "count": 1, "price": 5000, "sold": False}]
    feed(w, [store(0, items=two), store(0, items=two)])
    after = [two[0], {**two[1], "sold": True}]
    sales = feed(w, [store(5000, items=after), store(5000, items=after)], 20)
    assert sales[0]["item"] == "Blue Bamboo Hat"


def test_unreadable_detail_still_a_sale():
    w = ShopWatch()
    feed(w, [store(0), store(0)])
    sales = feed(w, [store(777), store(777)], 20)
    assert sales[0]["item"] is None and sales[0]["price"] == 777


def test_without_the_panel_the_mesos_and_rows_tell():
    w = ShopWatch()
    feed(w, [store(panel=False, mesos=1000), store(panel=False, mesos=1000)])
    after = [{"name": "Bazlud", "text": "Bazlud", "count": 1, "price": 24999, "sold": True},
             {"name": "Emerald Earrings", "text": "Emerald Earrings", "count": 1, "price": 12999, "sold": False}]
    got = 1000 + round(24999 * 0.97)
    sales = feed(w, [store(panel=False, mesos=got, items=after), store(panel=False, mesos=got, items=after)], 20)
    assert len(sales) == 1 and sales[0]["item"] == "Bazlud" and sales[0]["price"] == 24999


def test_a_row_lost_to_a_misread_is_not_a_sale():
    w = ShopWatch()
    feed(w, [store(panel=False), store(panel=False)])
    fewer = store(panel=False)["items"][:1]
    assert feed(w, [store(panel=False, items=fewer), store(panel=False, items=fewer)], 20) == []


def test_sold_out_reported_once():
    w = ShopWatch()
    feed(w, [store(0), store(0)])
    gone = [{**i, "sold": True} for i in store()["items"]]
    feed(w, [store(63996, items=gone), store(63996, items=gone), store(63996, items=gone)], 20)
    assert w.events == ["soldout"]
    assert w.status["sales"] and w.status["watching"]


# the live test of 2026-11-07: "buy" listed Orange 1 for 20 (twice), Orange 1 for 222,222 and
# Red Potion 1 for 5; SpookSy bought one Orange, then the other
LIVE = [{"name": "Orange", "text": "Orange", "count": 1, "price": 20, "sold": False},
        {"name": "Orange", "text": "Orange", "count": 1, "price": 20, "sold": False},
        {"name": "Orange", "text": "Orange", "count": 1, "price": 222222, "sold": False},
        {"name": "Red Potion", "text": "Red Potion", "count": 1, "price": 5, "sold": False}]


def test_live_sale_names_the_orange_from_the_sold_row():
    w = ShopWatch()
    feed(w, [store(0, LIVE), store(0, LIVE)])
    after = [LIVE[1], LIVE[2], LIVE[3]]                 # the sold row went gray (not read as for sale)
    rows = [{"name": "Orange", "count": 1}]
    sales = feed(w, [store(20, after, rows=rows), store(20, after, rows=rows)], 20)
    assert [(s["item"], s["count"], s["price"]) for s in sales] == [("Orange", 1, 20)]
    rows2 = rows + [{"name": "Orange", "count": 1}]
    sales = feed(w, [store(40, after[1:], rows=rows2), store(40, after[1:], rows=rows2)], 40)
    assert [(s["item"], s["count"], s["price"]) for s in sales] == [("Orange", 1, 20)]


def test_same_named_rows_dont_hide_each_other_without_the_rows():
    """No SOLD ITEMS rows read: the Orange row that went gray is what sold, not 4 Red Potions."""
    w = ShopWatch()
    feed(w, [store(0, LIVE), store(0, LIVE)])
    after = [LIVE[1], LIVE[2], LIVE[3]]
    sales = feed(w, [store(20, after), store(20, after)], 20)
    assert [(s["item"], s["count"]) for s in sales] == [("Orange", 1)]


def test_two_items_that_fit_and_nothing_sold_out_names_nothing():
    w = ShopWatch()
    feed(w, [store(0, LIVE), store(0, LIVE)])
    sales = feed(w, [store(20, LIVE), store(20, LIVE)], 20)
    assert len(sales) == 1 and sales[0]["item"] is None


def test_a_sale_told_from_the_mesos_box_isnt_told_again_when_the_panel_returns():
    """The panel lost, a row sold out and the mesos box went up by it; then the panel was found
    again with Total Sales showing it. One sale, not two, and the next one still counts."""
    w = ShopWatch()
    after = [LIVE[2], LIVE[3]]
    feed(w, [store(40, after, mesos=768883), store(40, after, mesos=768883)])
    gone = [LIVE[2]]                                      # the Red Potion row sold out
    sales = feed(w, [store(None, after, mesos=768883, panel=False)] * 2
                 + [store(None, gone, mesos=768888, panel=False)] * 2, 20)
    assert [(s["item"], s["price"]) for s in sales] == [("Red Potion", 5)]
    assert feed(w, [store(45, gone, mesos=768888), store(45, gone, mesos=768888)], 60) == []
    assert w.status["total"] == 45 and w.take_fixes() == []
    more = feed(w, [store(50, gone, mesos=768893), store(50, gone, mesos=768893)], 80)
    assert [s["price"] for s in more] == [5]              # the next one still counts


def test_a_partial_sale_waits_for_the_panel():
    """Live, 2026-11-07: a Red Potion (5) sold from a row of several, the row didn't change, the
    mesos box went up 5. Not told from the box; told when the panel shows Total Sales 40 -> 45."""
    w = ShopWatch()
    after = [LIVE[2], LIVE[3]]
    feed(w, [store(40, after, mesos=768883), store(40, after, mesos=768883)])
    lost = [store(None, after, mesos=768883, panel=False)] * 2 + [store(None, after, mesos=768888, panel=False)] * 6
    assert feed(w, lost, 20) == []
    sales = feed(w, [store(45, after, mesos=768888), store(45, after, mesos=768888)], 80)
    assert [(s["item"], s["price"]) for s in sales] == [("Red Potion", 5)]


MOKBI = [{"name": "Mokbi Throwing Stars", "text": "Mokbi Throwing Stars", "count": 1, "price": 1100, "sold": False},
         {"name": "Elixir", "text": "Elixir", "count": 5, "price": 3745, "sold": False}]


def test_mesos_that_only_fit_a_price_are_not_a_sale():
    """Live, 2026-11-08: the panel lost, the mesos box went up 6,402 (= 6,600 before the fee, a
    multiple of the Mokbi row's price) though no row changed; Total Sales later showed only 2,253."""
    w = ShopWatch()
    feed(w, [store(5245, MOKBI, mesos=665292), store(5245, MOKBI, mesos=665292)])
    lost = [store(None, MOKBI, mesos=665292, panel=False)] * 2 + [store(None, MOKBI, mesos=671694, panel=False)] * 6
    assert feed(w, lost, 20) == []
    sales = feed(w, [store(7498, MOKBI, mesos=671694), store(7498, MOKBI, mesos=671694)], 80)
    assert [s["price"] for s in sales] == [2253] and w.take_fixes() == []


def test_a_sale_the_panel_doesnt_show_is_taken_back():
    w = ShopWatch()
    feed(w, [store(5245, MOKBI, mesos=665292), store(5245, MOKBI, mesos=665292)])
    gone = MOKBI[1:]                                     # misread: the Mokbi row seemed to go
    sales = feed(w, [store(None, MOKBI, mesos=665292, panel=False)] * 2
                 + [store(None, gone, mesos=666359, panel=False)] * 2, 20)
    assert [s["item"] for s in sales] == ["Mokbi Throwing Stars"]
    real = feed(w, [store(5245 + 400, MOKBI, mesos=666359), store(5245 + 400, MOKBI, mesos=666359)], 60)
    fixes = w.take_fixes()
    assert [f["wrong"][0]["item"] for f in fixes] == ["Mokbi Throwing Stars"] and fixes[0]["real"] == 400
    assert [s["price"] for s in real] == [400]           # what did sell is still told
    assert [s["price"] for s in w.status["sales"]] == [400]
    later = feed(w, [store(5245 + 3745 + 400, MOKBI, mesos=1), store(5245 + 3745 + 400, MOKBI, mesos=1)], 80)
    assert [s["price"] for s in later] == [3745]         # nothing left over to swallow later sales


def test_the_panel_back_with_no_rise_takes_the_sale_back():
    w = ShopWatch()
    feed(w, [store(5245, MOKBI, mesos=665292), store(5245, MOKBI, mesos=665292)])
    gone = MOKBI[1:]
    feed(w, [store(None, MOKBI, mesos=665292, panel=False)] * 2 + [store(None, gone, mesos=666359, panel=False)] * 2, 20)
    assert feed(w, [store(5245, MOKBI, mesos=666359)] * 2, 60) == []
    assert len(w.take_fixes()) == 1 and w.status["sales"] == []


def test_the_row_going_gray_a_read_late_still_tells_it():
    w = ShopWatch()
    feed(w, [store(None, MOKBI, mesos=1000, panel=False)] * 2)
    gone = [{**MOKBI[0], "sold": True}, MOKBI[1]]
    got = 1000 + round(1100 * 0.97)
    sales = feed(w, [store(None, MOKBI, mesos=got, panel=False)] * 2 + [store(None, gone, mesos=got, panel=False)] * 2, 20)
    assert [(s["item"], s["price"]) for s in sales] == [("Mokbi Throwing Stars", 1100)]


def test_mesos_baseline_follows_while_the_panel_is_open():
    w = ShopWatch()
    after = [LIVE[2], LIVE[3]]
    feed(w, [store(0, after, mesos=1000), store(0, after, mesos=1000)])
    feed(w, [store(5, after, mesos=1005), store(5, after, mesos=1005)], 20)    # told from the panel
    assert feed(w, [store(None, after, mesos=1005, panel=False)] * 3, 40) == []  # panel lost: no repeat
