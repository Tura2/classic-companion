"""
What a test case checks, shared by tools/make_case.py and tests/: a field is a dotted path into what
Reader.read saw ("stat.name"), plus a few fields computed from it ("helper.list").
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw

APP = Path(__file__).resolve().parent.parent
CASES = APP / "samples" / "cases"
MASK = (128, 128, 128)       # everything outside a case's kept boxes


def masked(frame, keep):
    """The frame with only the kept boxes left: no other player's name or chat stays in a case."""
    out = Image.new("RGB", frame.size, MASK)
    for l, t, r, b in keep:
        out.paste(frame.crop((l, t, r, b)), (l, t))
    return out


def computed(seen, name):
    """The fields that aren't a plain path into what was seen. KeyError if `name` isn't one."""
    if name == "helper.list":
        h = seen.get("helper")
        return None if h is None else [[q["quest"], [[n["what"], n["have"], n["need"]] for n in q["needs"]]]
                                       for q in h["quests"]]
    if name == "helper.quests":
        h = seen.get("helper")
        return None if h is None else [q["quest"] for q in h["quests"]]
    if name == "helper.counts":
        h = seen.get("helper")
        return None if h is None else {f'{q["quest"]} | {n["what"]}': n["have"] for q in h["quests"] for n in q["needs"]}
    if name == "shop.list":
        sh = seen.get("shop")
        return None if sh is None else [[i["name"], i["price"]] for i in sh["items"] if not i["sold"]]
    if name == "quest.lines":
        qw = seen.get("quest")
        return None if qw is None else [e["line"] for e in qw["quests"] if e.get("line")]
    if name == "myshop.list":
        sh = seen.get("myshop")
        return None if sh is None else [[i["name"] or i["text"], i["count"], i["price"]] for i in sh["items"]]
    if name == "myshop.sold":
        p = (seen.get("myshop") or {}).get("panel")
        return None if p is None else [[r["name"], r["count"]] for r in p["rows"]]
    if name == "myshop.totals":
        p = (seen.get("myshop") or {}).get("panel")
        return None if p is None else [p["total_sales"], p["total_received"]]
    raise KeyError(name)


def field(seen, name):
    """The value at a dotted path of what was seen, or None where a key is missing."""
    try:
        return computed(seen, name)
    except KeyError:
        pass
    v = seen
    for part in name.split("."):
        if not isinstance(v, dict) or part not in v:
            return None
        v = v[part]
    return v


def load_cases():
    """{name: case} for every case JSON in samples/cases/."""
    return {p.stem: json.loads(p.read_text("utf-8")) for p in sorted(CASES.glob("*.json"))}
