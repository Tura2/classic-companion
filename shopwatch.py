"""
Sales in your own store, from what the reader sees of it (reader.read_my_shop).

The SOLD ITEMS panel's Total Sales is one number that only goes up while the store is open: when
it goes up, something sold. A change counts only once two reads in a row agree on it, and a total
that goes down, or jumps by more than the whole store could be worth, is a misread and dropped.
Total back to 0 after the store was gone is a new store session, not a sale.

Without the panel, the mesos box under your character going up (by what you received, after the
3% fee) tells it only together with a listed row that sold out (went gray or went away) and whose
price fits: the mesos box alone could be anything (a trade, a misread), and so could a price that
merely fits. A row that sells only part of its stock doesn't change, so that sale waits for the
panel. When the panel is read again its Total Sales is the truth: a sale told from the mesos box
that it doesn't show was wrong, and is taken back (see `fixes`).

What sold comes from the panel's new rows, else from the listed rows whose count went down; when
neither says, the sale is still reported, without an item.
"""
FM_FEE = 0.03
MIN_CAP = 10_000_000       # a rise above this and 10x the listed value is a misread
GONE_READS = 3             # reads without the store before a total of 0 counts as a new session
MESOS_WAIT = 20.0          # seconds a mesos rise waits for the row that sold to go gray


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
        self.mesos_items = None    # the rows when the mesos baseline was set
        self.mesos_wait = None     # when an unexplained mesos rise was first confirmed
        self.items = None          # the rows as last confirmed
        self.items_pending = None
        self.panel_rows = []       # the panel's rows as last confirmed
        self.credit = 0            # sales already told from the mesos box, not yet in a Total Sales seen
        self.told = []             # those sales
        self.fixes = []            # sales told wrongly, for whoever posted them: {"key", "wrong", "real"}
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
        self.mesos_items = self.mesos_wait = None
        self.items = self.items_pending = None
        self.panel_rows = []
        self.credit = 0
        self.told = []
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
            elif total < self.base or total - self.base > cap or (total == self.base and not self.credit):
                self.pending = None
            elif self.pending == total:
                delta = total - self.base
                rows = list(panel.get("rows") or [])
                if self.credit:                      # told from the mesos box while the panel was lost
                    if delta >= self.credit - max(1, 0.01 * self.credit):
                        delta = max(0, delta - self.credit)
                    else:                            # Total Sales doesn't show them: they didn't sell
                        self.fixes.append({"key": f"{self.session}:fix{total}", "wrong": list(self.told),
                                           "real": delta, "ts": now})
                        keys = {t["key"] for t in self.told}
                        self.sales = [x for x in self.sales if x["key"] not in keys]
                    self.credit, self.told = 0, []
                if delta > max(1, 0.01 * delta):
                    item, count = self._from_rows(rows, delta) or self._from_items(items_before, self.items, delta)                         or (None, None)
                    sales.append({"key": f"{self.session}:{total}", "item": item, "count": count, "price": delta,
                                  "total_sales": total, "ts": now})
                self.base, self.pending, self.panel_rows = total, None, rows
            else:
                self.pending = total
            m = read.get("mesos")             # keep the mesos box's baseline current for when the panel is lost
            if m is not None and m != self.mesos:
                if self.mesos_pending == m:
                    self._set_mesos(m)
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

    def _set_mesos(self, m):
        self.mesos, self.mesos_pending, self.mesos_items, self.mesos_wait = m, None, self.items, None

    @staticmethod
    def _from_items(before, after, delta, tol=0, sold_out=False):
        """(item, how many) for a sale worth `delta`: the one row whose price it's a whole multiple of
        (within tol, a share, for amounts worked back from the fee), preferring a row that has just
        sold out (gone gray, or gone); with sold_out, only such a row. None if no single row explains it."""
        if not before or (sold_out and after is None):
            return None
        b, a = _rows(before), _rows(after) if after is not None else {}
        fits = []
        for text, (price, per, name) in b.items():
            k = round(delta / price)
            if k >= 1 and abs(k * price - delta) <= tol * delta:
                fits.append((text not in a, name or text[0], k * (per or 1)))
        if sold_out:
            fits = [f for f in fits if f[0]]
        elif len(fits) > 1:
            fits = [f for f in fits if f[0]] or fits
        if len({f[1] for f in fits}) == 1 and len({f[2] for f in fits}) == 1:
            return fits[0][1], fits[0][2]      # two rows of the same item at the same price
        return None

    def _from_mesos(self, mesos, items_before, cap, now):
        if mesos is None:
            return []
        if self.mesos is None:
            if self.mesos_pending == mesos:
                self._set_mesos(mesos)
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
        found = self._from_items(self.mesos_items or items_before, self.items, gross, tol=0.002, sold_out=True)
        if not found:      # the mesos box alone could be anything (a trade, a misread): needs a row that sold out
            if self.mesos_wait is None:
                self.mesos_wait = now
            if now - self.mesos_wait >= MESOS_WAIT:
                self._set_mesos(mesos)      # no row went: not a sale we can tell; the panel will say
            return []
        self._set_mesos(mesos)
        sale = {"key": f"{self.session}:m{mesos}", "item": found[0], "count": found[1], "price": gross,
                "total_sales": None, "ts": now}
        if self.base is not None:
            self.credit += gross      # Total Sales will show it too once the panel is seen again
            self.told.append(sale)
        return [sale]

    def take_fixes(self):
        out, self.fixes = self.fixes, []
        return out
