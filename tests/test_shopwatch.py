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
