"""Check the corner-line reader (notices.py) on recorded play against what was really picked up.

A sequence is a folder of frames (or strips of the corner, with map.json giving the frame size and
where the strip was cut) and truth.json, every line new in each frame, checked by eye:
    {"events": [[frame index, "mesos", 59], [frame index, "item", "Wild Boar Tooth", 1], ...]}

Run from the app folder:  python -I tools/check_corner.py [samples/raw/notices_seq] [--every N] [--show]
--every 2 looks at every 2nd frame only (a slower look); --show prints what each look counted.
Prints the events counted right, wrong, missed and counted twice, and the time per look.
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

from PIL import Image

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import gamedata  # noqa: E402
import notices  # noqa: E402


def frames(folder):
    meta = json.loads((folder / "map.json").read_text("utf-8")) if (folder / "map.json").exists() else {}
    size = tuple(meta.get("size") or (1920, 1200))
    for f in sorted(folder.glob("*_*.png")):
        im = Image.open(f).convert("RGB")
        if im.size != size:          # a strip of the corner: put it back where it was cut
            whole = Image.new("RGB", size)
            left, top = (meta["box"][:2] if "box" in meta else (size[0] - im.width, 780))
            whole.paste(im, (left, top))
            im = whole
        yield im


def key(e):
    return tuple(e[1:])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    every = int(argv.pop(argv.index("--every") + 1)) if "--every" in argv else 1
    args = [a for a in argv if not a.startswith("--")]
    folder = Path(args[0]) if args else APP / "samples" / "raw" / "notices_seq"
    truth = json.loads((folder / "truth.json").read_text("utf-8"))["events"]
    data = gamedata.GameData()
    corner = notices.Corner()
    corner.set_names(list(data.item_ids))
    got, times = [], []
    for i, im in enumerate(frames(folder)):
        if i % every:
            continue
        t = time.perf_counter()
        evs = corner.step(im, now=i * 0.5)
        times.append(time.perf_counter() - t)
        got += [[i, *e] for e in evs]
        if "--show" in sys.argv and evs:
            print(i, evs)
    want, have = Counter(key(e) for e in truth), Counter(key(e) for e in got)
    right = sum((want & have).values())
    extra, missed = have - want, want - have
    # an event counted again within a few frames of its first count is a double count, not a new one
    print(f"{len(truth)} events picked up; {right} counted right, {sum(extra.values())} counted that weren't, "
          f"{sum(missed.values())} missed")
    for k, n in extra.items():
        print("  counted, not there:", k, f"x{n}")
    for k, n in missed.items():
        print("  missed:", k, f"x{n}")
    times.sort()
    print(f"a look takes {1000 * times[len(times) // 2]:.0f} ms (median), {1000 * times[-1]:.0f} ms at most "
          f"(the first builds the item names)")


if __name__ == "__main__":
    main()
