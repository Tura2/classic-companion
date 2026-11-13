"""
The Item Inventory's open tab, slot by slot: which item sits in each, told by its picture, so Sell or
keep knows your whole bag without hovering every item.

The window is found by its title (anchors.Titles, "inventory"); from the title's place the tabs and
the 5 x 6 slots sit at fixed offsets. At a 1200 px tall game area the game draws its 32 px item icons
1.5625 times as big, in 50 px slots. Each slot is compared with the icons of the open tab's items
(Etc, Use = potions, ammo and scrolls, Equip, Set-up), downloaded once into cache/icons/:
  - a shortlist: the icons closest in colour, and the ones that fit best set at the slot's top right;
  - each shortlisted icon is slid over the slot, and the best fit wins.
The count is drawn over the icon's bottom left, so the slot's bottom 19 px aren't compared (counts
aren't read yet: an item read here has no count, like one hovered). A slot already seen is
remembered, so only new or moved items cost anything.

Some icons are the same picture (Wild Boar Tooth and Fire Boar's Tooth, the Chaos scrolls for a
hat): when another item fits almost as well, the slot says both ("alt"), never a guess.
"""
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

K = 1.5625                      # icon size in the game at a 1200 px tall game area, over the icon file's
SLOT, BAND = 50, 19             # a slot, and its bottom band where the count is drawn
COLS, ROWS = 5, 6
GRID_X, GRID_Y = -2, 62         # the first slot's top left, from the title line's (x, y), at 1200 px
STEP_X, STEP_Y = 56.25, 53.2
TAB_Y = 38                      # the tabs' middle, below the title line
TABS = {"Equip": 18, "Use": 70, "Setup": 121, "Etc": 173, "Cash": 225, "Deco": 277}
KINDS = {"Equip": ("Equipment",), "Use": ("Consumable", "scrolls"), "Setup": ("Setup",), "Etc": ("Etc",)}
BG = np.array([225., 223., 213.])   # an empty slot
INK = 60            # a pixel this far (summed over R, G, B) from the slot colour is part of an item
EMPTY = 120         # fewer such pixels above the count: an empty slot
SHORT = 15          # icons per shortlist
SHIFT = 3           # how far an icon may sit past the slot's edge
WORST = 60          # a best fit worse than this: no item known here
UNSURE = 1.25       # another item fitting within this factor of the best one: say both
RETRY = 600         # a tab whose icons didn't all download is tried again after this many seconds
RED = 30            # the open tab is red: its red over its green by more than this


def open_tab(frame, title, s):
    """The inventory's open tab ("Etc", "Use", ...) from the title line (text, x, y, w, h); None
    when no tab looks open."""
    x, y = title[1], title[2]
    best, name = RED, None
    for tab, dx in TABS.items():
        cx, cy = x + dx * s, y + TAB_Y * s
        box = (round(cx - 16 * s), round(cy - 5 * s), round(cx + 16 * s), round(cy + 5 * s))
        px = np.asarray(frame.crop(box).convert("RGB"), dtype=float).reshape(-1, 3)
        if len(px):
            red = px[:, 0].mean() - px[:, 1].mean()
            if red > best:
                best, name = red, tab
    return name


def grid_box(title, s):
    """The frame area holding every slot."""
    x, y = title[1] + GRID_X * s, title[2] + GRID_Y * s
    return (round(x), round(y), round(x + (STEP_X * (COLS - 1) + SLOT) * s), round(y + (STEP_Y * (ROWS - 1) + SLOT) * s))


def slots(grid):
    """[(slot number, the slot above its count as an array)] from the grid's picture (any size: it
    is brought to the 1200 px size first). Numbered left to right, top to bottom, from 0."""
    w = round(STEP_X * (COLS - 1) + SLOT)
    h = round(STEP_Y * (ROWS - 1) + SLOT)
    if grid.size != (w, h):
        grid = grid.resize((w, h), Image.BILINEAR)
    a = np.asarray(grid.convert("RGB"), dtype=float)
    out = []
    for r in range(ROWS):
        for c in range(COLS):
            x, y = round(STEP_X * c), round(STEP_Y * r)
            out.append((r * COLS + c, a[y:y + SLOT - BAND, x:x + SLOT]))
    return out


def _hist(px):
    """A coarse colour histogram (4 x 4 x 4) of some pixels."""
    if not len(px):
        return np.zeros(64)
    q = (np.asarray(px) // 64).astype(int)
    h = np.bincount(q[:, 0] * 16 + q[:, 1] * 4 + q[:, 2], minlength=64).astype(float)
    return h / h.sum()


def _fit(top, base, comp, ty, tx):
    """How far the slot is from the icon set at (ty, tx) on an empty slot (mean over the slot)."""
    H, W = top.shape[:2]
    h, w = comp.shape[:2]
    y0, x0, y1, x1 = max(0, ty), max(0, tx), min(H, ty + h), min(W, tx + w)
    if y1 - y0 < 4 or x1 - x0 < 4:
        return 1e9
    inside = np.abs(comp[y0 - ty:y1 - ty, x0 - tx:x1 - tx] - top[y0:y1, x0:x1]).sum()
    return (base.sum() - base[y0:y1, x0:x1].sum() + inside) / (H * W)


def best_fit(top, comp, base=None):
    """The icon's best place on the slot, every SHIFT px past an edge allowed: (cost, ty, tx). Every
    second place first, then the places around the best of them."""
    if base is None:
        base = np.abs(top - BG).sum(2)
    H, W = top.shape[:2]
    h, w = comp.shape[:2]
    ys, xs = range(-SHIFT, max(-SHIFT, SLOT - h + SHIFT) + 1), range(-SHIFT, max(-SHIFT, W - w + SHIFT) + 1)
    best = min((_fit(top, base, comp, ty, tx), ty, tx) for ty in ys[::2] for tx in xs[::2])
    _, by, bx = best
    return min([best] + [(_fit(top, base, comp, by + dy, bx + dx), by + dy, bx + dx)
                         for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0)])


class Bag:
    """Reads inventory tabs. `items`: {kind: [(item id, name)]} for the kinds in KINDS; `icon_url`:
    item id -> its icon's URL; icons are kept in `icon_dir`."""

    def __init__(self, items, icon_url, icon_dir):
        self.items, self.icon_url, self.dir = items, icon_url, icon_dir
        self.books, self.memo, self.retry = {}, {}, {}

    def _get(self, iid):
        path = self.dir / f"{iid:08d}.png"
        if not path.exists():
            import requests
            try:
                r = requests.get(self.icon_url(iid), timeout=15)
                if r.ok:
                    path.write_bytes(r.content)
            except requests.RequestException:
                return None
        return path if path.exists() else None

    def book(self, tab):
        """The icons a tab's items can have, each at the game's size on an empty slot:
        [(id, name, picture, colour histogram)]. Downloads the missing ones the first time."""
        if tab in self.books and time.time() < self.retry.get(tab, float("inf")):
            return self.books[tab]
        self.dir.mkdir(parents=True, exist_ok=True)
        want = [x for kind in KINDS.get(tab, ()) for x in self.items.get(kind, [])]
        with ThreadPoolExecutor(16) as ex:
            paths = list(ex.map(lambda x: self._get(x[0]), want))
        book = []
        for (iid, name), path in zip(want, paths):
            if path is None:
                continue
            try:
                im = Image.open(path).convert("RGBA")
            except OSError:
                continue
            im = im.resize((max(1, round(im.width * K)), max(1, round(im.height * K))), Image.BILINEAR)
            a = np.asarray(im, dtype=float)
            al = a[..., 3:] / 255
            book.append((iid, name, a[..., :3] * al + BG * (1 - al), _hist(a[..., :3][a[..., 3] > 128])))
        self.books[tab] = book
        if len(book) < 0.9 * len(want):      # offline, or the site failed: try the rest again later
            self.retry[tab] = time.time() + RETRY
            self.memo = {k: v for k, v in self.memo.items() if k[0] != tab}
        else:
            self.retry.pop(tab, None)
        return book

    def match(self, top, tab):
        """What's in one slot: None when empty, else {"name", "id", "cost", "alt"} ("name" None
        when nothing fits)."""
        ink = np.abs(top - BG).sum(2) > INK
        if ink.sum() < EMPTY:
            return None
        key = (tab, hashlib.blake2b(top.astype(np.uint8).tobytes(), digest_size=12).digest())
        if key in self.memo:
            return self.memo[key]
        book = self.book(tab)
        base = np.abs(top - BG).sum(2)
        by_colour = sorted(book, key=lambda ic: np.abs(ic[3] - _hist(top[ink])).sum())[:SHORT]
        rows, cols = np.where(ink.sum(1) >= 2)[0], np.where(ink.sum(0) >= 2)[0]
        t0, r0 = (rows.min(), cols.max()) if len(rows) and len(cols) else (0, SLOT - 1)
        by_corner = sorted(book, key=lambda ic: _fit(top, base, ic[2], t0, r0 + 1 - ic[2].shape[1]))[:SHORT]
        fits = sorted((best_fit(top, ic[2], base)[0], ic[1], ic[0])
                      for ic in {ic[0]: ic for ic in by_colour + by_corner}.values())
        out = {"name": None, "id": None, "cost": None, "alt": None}
        if fits and fits[0][0] <= WORST:
            cost, name, iid = fits[0]
            other = next((f for f in fits[1:] if f[1] != name), None)
            out = {"name": name, "id": iid, "cost": round(cost, 1),
                   "alt": other[1] if other and other[0] <= cost * UNSURE else None}
        self.memo[key] = out
        if len(self.memo) > 2000:
            self.memo.pop(next(iter(self.memo)))
        return out

    def read(self, grid, tab):
        """[{"slot", "name", "id", "cost", "alt"}] for the items in the open tab's visible slots."""
        if tab not in KINDS:
            return []
        out = []
        for i, top in slots(grid):
            m = self.match(top, tab)
            if m and m["name"]:
                out.append({"slot": i, **m})
        return out
