"""
The game's bottom-right corner lines, as events for the grind session:
    You received EXP (+66)              -> ("exp", 66)        a kill
    You have gained mesos (+15)         -> ("mesos", 15)
    Tree Branch x1 earned. (Etc)        -> ("item", "Tree Branch", 1)

The lines stack up, newest at the bottom, and stay several seconds while new ones push them up a
row; a read comes every ~1.5 s. So each read is lined up against the last one: the lines still
showing have moved up as many rows as new lines came in at the bottom (two identical lines in a row
are told apart by that), and only those new lines count. Lines fading off the top are just gone.
"""
import re

from rapidfuzz import fuzz, process

EXP = re.compile(r"you\s+received\s+exp\s*((?:\(\s*\+?\s*[\d,.]+\s*\)\s*)+)", re.I)
MESOS = re.compile(r"you\s+have\s+gained\s+mesos\s*\(\s*\+?\s*([\d,.]+)\s*\)", re.I)
ITEM = re.compile(r"^\s*(.+?)\s+[xX×]\s*(\d+)\s+earned", re.I)
NUM = re.compile(r"\+?\s*([\d,.]+)")
SAME = 85           # two reads of one line match at least this well
ITEM_MATCH = 85     # an item line names a game item this well, or no item


def _int(text):
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def parse(text, item_names):
    """One corner line as an event, or None for anything else (chat, a misread)."""
    m = EXP.search(text)
    if m:
        parts = [_int(n) for n in NUM.findall(m.group(1))]
        total = sum(p for p in parts if p)
        return ("exp", total) if total else None
    m = MESOS.search(text)
    if m:
        n = _int(m.group(1))
        return ("mesos", n) if n else None
    m = ITEM.search(text)
    if m:
        hit = process.extractOne(m.group(1).strip(), item_names, scorer=fuzz.ratio, score_cutoff=ITEM_MATCH)
        return ("item", hit[0] if hit else None, int(m.group(2)))
    return None


class Tracker:
    """Counts each corner line once across reads."""

    def __init__(self):
        self.last = []          # the last read's lines, (text, y), top to bottom

    def _new_lines(self, new, row_h):
        """How many of `new`'s lines (from the bottom) weren't there last read."""
        old = self.last
        if not old:
            return len(new)
        for k in range(0, len(new) + 1):          # k new lines came in at the bottom
            kept = len(new) - k                   # the lines still showing, at the top of `new`
            if kept > len(old):
                continue
            if kept == 0:
                return k
            before, now = old[len(old) - kept:], new[:kept]
            if all(fuzz.ratio(a[0], b[0]) >= SAME and abs((a[1] - b[1]) - k * row_h) <= row_h / 3
                   for a, b in zip(before, now)):
                return k
        return len(new)

    def update(self, lines, row_h, item_names):
        """The events from this read's lines (text, y), top to bottom, new since the last read."""
        k = self._new_lines(lines, row_h)
        self.last = list(lines)
        out = []
        for text, _ in lines[len(lines) - k:] if k else []:
            ev = parse(text, item_names)
            if ev:
                out.append(ev)
        return out
