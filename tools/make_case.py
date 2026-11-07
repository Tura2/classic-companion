"""
Make a reader test case from a picture of the game.

  python -I tools/make_case.py --frame PATH --name NAME --job Hunter --keep l,t,r,b [--keep ...] [--tip l,t,r,b]

Writes samples/cases/NAME.png, the picture with everything outside the --keep boxes painted gray (so
no other player's name or chat stays in it), and samples/cases/NAME.json, whose "expect" is filled
from what the reader sees now. Correct "expect" by hand against the picture: it's what the tests
hold the reader to. samples/cases/ is never committed (the repo is public).
"""
import argparse
import ctypes
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from casekit import CASES, field, masked  # noqa: E402

# the fields a new case starts with; a case may list any dotted path into what was seen
FIELDS = ("stat.name", "stat.level", "stat.exp", "stat.str_base", "stat.dex_base", "stat.ap", "stat.acc",
          "hud.level", "inventory.mesos", "map.street", "map.name", "map.collapsed", "quest.tab",
          "quest.lines", "helper.list", "skills.levels", "skills.sp", "shop.seller", "shop.list")


def box(text):
    l, t, r, b = (int(v) for v in text.split(","))
    return [l, t, r, b]


def make_case(frame_path, name, job, keep, tip=None, expect=None, reader=None):
    """Write the case's picture and JSON; returns the case. `expect` given: written as is."""
    from PIL import Image
    CASES.mkdir(parents=True, exist_ok=True)
    picture = masked(Image.open(frame_path).convert("RGB"), keep)
    picture.save(CASES / f"{name}.png")
    if expect is None:
        reader.set_job(job)
        seen = reader.read(picture)
        expect = {f: field(seen, f) for f in FIELDS if field(seen, f) is not None}
    case = {"frame": f"{name}.png", "keep": keep, "tip_region": tip, "job": job, "expect": expect}
    (CASES / f"{name}.json").write_text(json.dumps(case, indent=2, ensure_ascii=False), "utf-8")
    return case


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1].strip())
    ap.add_argument("--frame", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--job", default="Beginner")
    ap.add_argument("--keep", action="append", type=box, required=True)
    ap.add_argument("--tip", type=box)
    a = ap.parse_args()
    if sys.platform == "win32":
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    import reader
    from gamedata import GameData
    case = make_case(a.frame, a.name, a.job, a.keep, a.tip, reader=reader.Reader(GameData()))
    print(json.dumps(case["expect"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
