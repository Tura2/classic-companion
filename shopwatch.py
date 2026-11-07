"""
Sales in your own store, from what the reader sees of it (reader.read_my_shop).

The SOLD ITEMS panel's Total Sales is one number that only goes up while the store is open: when
it goes up, something sold. A change counts only once two reads in a row agree on it, and a total
that goes down, or jumps by more than the whole store could be worth, is a misread and dropped.
Total back to 0 after the store was gone is a new store session, not a sale.

Without the panel, the mesos box under your character going up (by what you received, after the
3% fee) and a listed row selling tell the same thing, more slowly.

What sold comes from the panel's new rows, else from the listed rows whose count went down; when
neither says, the sale is still reported, without an item.
"""
FM_FEE = 0.03
MIN_CAP = 10_000_000       # a rise above this and 10x the listed value is a misread
GONE_READS = 3             # reads without the store before a total of 0 counts as a new session


def _listed_value(items):
    return sum((i.get("price") or 0) for i in items or [] if not i.get("sold"))


def _rows(items):
    """{(row text, price, per bundle, nth such row): (bundle price, items per bundle, item name)} for
    the rows still for sale. Two rows of the same item (two "Orange" rows, at 20 and 222,222) are
    kept apart. A row's "1 for 12,999 mesos" is one bundle; how many bundles are left is the number on
    its icon, which isn't read, so a row sells partly without changing here."""
    out, seen = {}, {}
    for i in items or []:
        if i.get("sold") or not i.get("price"):
            continue
        k = (i.get("text") or i.get("name"), i["price"], i["count"])
        seen[k] = seen.get(k, 0) + 1
        out[k + (seen[k],)] = (i["price"], i["count"], i.get("name"))
    return out


class ShopWatch:
    def __init__(self):
        self.session = None        # when this store session was first seen (its id)
        self.base = None           # confirmed Total Sales
        self.pending = None        # a new total waiting for a second read
        self.mesos = None          # confirmed mesos box (for when the panel is closed)
        self.mesos_pending = None
        self.items = None          # the rows as last confirmed
        self.items_pending = None
        self.panel_rows = []       # the panel's rows as last confirmed
        self.credit = 0            # sales already told from the mesos box, not yet in a Total Sales seen
        self.gone = 0              # reads in a row without the store
        self.sales = []
        self.events = []           # "soldout", once per session
        self.watching = False
        self.last_seen = None

    @property
    def status(self):
        return {"watching": self.watching, "session": self.session, "total": self.base or 0,
                "sales": list(self.sales), "last_seen": self.last_seen}

    def _new_session(self, now):
        self.session = str(int(now * 1000))
        self.base = self.pending = self.mesos = self.mesos_pending = None
        self.items = self.items_pending = None
        self.panel_rows = []
        self.credit = 0
        self.events = [e for e in self.events if e != "soldout"]

    def update(self, read, now):
        """What one read saw (None: the store isn't on screen). Returns the sales it confirmed."""
        if read is None:
            self.watching = False
            self.gone += 1
            self.pending = self.mesos_pending = self.items_pending = None
            return []
        self.watching, self.last_seen = True, now
        if self.session is None:
            self._new_session(now)
        panel = read.get("panel")
        total = panel.get("total_sales") if panel else None
        if total == 0 and self.base and self.gone >= GONE_READS:
            self._new_session(now)       # the store was closed and opened again
        self.gone = 0
        items_before = self.items
        self._confirm_items(read.get("items"))
        cap = max(MIN_CAP, 10 * _listed_value(items_before or read.get("items")))
        sales = []
        if total is not None:
            if self.base is None:
                if self.pending == total:
                    self.base, self.pending = total, None
                    self.panel_rows = list(panel.get("rows") or [])
                else:
                    self.pending = total
            elif total <= self.base or total - self.base > cap:
                self.pending = None
            elif self.pending == total:
                delta = total - self.base
                rows = list(panel.get("rows") or [])
                told = min(self.credit, delta)       # already told from the mesos box while the panel was lost
                self.credit -= told
                if delta - told > max(1, 0.01 * delta):
                    delta -= told
                    item, count = self._from_rows(rows, delta) or self._from_items(items_before, self.items, delta)                         or (None, None)
                    sales.append({"key": f"{self.session}:{total}", "item": item, "count": count, "price": delta,
                                  "total_sales": total, "ts": now})
                self.base, self.pending, self.panel_rows = total, None, rows
            else:
                self.pending = total
            m = read.get("mesos")             # keep the mesos box's baseline current for when the panel is lost
            if m is not None and m != self.mesos:
                if self.mesos_pending == m:
                    self.mesos, self.mesos_pending = m, None
                else:
                    self.mesos_pending = m
        else:
            sales += self._from_mesos(read.get("mesos"), items_before, cap, now)
        self.sales += sales
        if self.items is not None and items_before and not _rows(self.items) and _rows(items_before) \
                and "soldout" not in self.events:
            self.events.append("soldout")
        return sales

    def _confirm_items(self, items):
        if items is None:
            return
        snap = _rows(items)
        if self.items is not None and snap == _rows(self.items):
            self.items_pending = None
        elif self.items_pending == snap:          # the same new rows two reads in a row
            self.items, self.items_pending = items, None
        else:
            self.items_pending = snap

    def _from_rows(self, rows, delta):
        """(item, how many) from the SOLD ITEMS rows that weren't there before (compared as a
        multiset: the panel may list newest first or last). None unless it's one item."""
        old = [(r.get("name"), r.get("count")) for r in self.panel_rows]
        new = []
        for r in rows:
            key = (r.get("name"), r.get("count"))
            if key in old:
                old.remove(key)
            elif r.get("name"):
                new.append(key)
        names = {n for n, _ in new}
        if len(names) != 1:
            return None
        counts = [c for _, c in new]
        return new[0][0], sum(counts) if all(counts) else None

    @staticmethod
    def _from_items(before, after, delta, tol=0):
        """(item, how many) for a sale worth `delta`: the one row whose price it's a whole multiple of
        (within tol, a share, for amounts worked back from the fee), preferring a row that has just
        sold out (gone gray, or gone). None if no single row explains it."""
        if not before:
            return None
        b, a = _rows(before), _rows(after) if after is not None else {}
        fits = []
        for text, (price, per, name) in b.items():
            k = round(delta / price)
            if k >= 1 and abs(k * price - delta) <= tol * delta:
                fits.append((text not in a, name or text[0], k * (per or 1)))
        if len(fits) > 1:
            fits = [f for f in fits if f[0]] or fits
        if len({f[1] for f in fits}) == 1 and len({f[2] for f in fits}) == 1:
            return fits[0][1], fits[0][2]      # two rows of the same item at the same price
        return None

    def _from_mesos(self, mesos, items_before, cap, now):
        if mesos is None:
            return []
        if self.mesos is None:
            if self.mesos_pending == mesos:
                self.mesos, self.mesos_pending = mesos, None
            else:
                self.mesos_pending = mesos
            return []
        if mesos <= self.mesos or mesos - self.mesos > cap:
            self.mesos_pending = None
            return []
        if self.mesos_pending != mesos:
            self.mesos_pending = mesos
            return []
        received = mesos - self.mesos
        gross = round(received / (1 - FM_FEE))
        found = self._from_items(items_before, self.items, gross, tol=0.002)
        self.mesos, self.mesos_pending = mesos, None
        if not found:
            return []      # the mesos box alone could be anything (a trade, a misread): needs a row too
        if self.base is not None:
            self.credit += gross      # Total Sales will show it too once the panel is seen again
        return [{"key": f"{self.session}:m{mesos}", "item": found[0], "count": found[1], "price": gross,
                 "total_sales": None, "ts": now}]
