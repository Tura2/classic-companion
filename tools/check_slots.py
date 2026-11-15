"""Check the quick-slot reader (quickslots.py) on real frames against counts checked by eye.

The frames are samples/cases/notices_*.png, the bottom-right quarter of a 1920 x 1200 game frame
(pasted back at (960, 600)), taken 2026-11-14 while grinding: the counts only went up (pickups), and
the speed skill's own number went 2 -> 1, which isn't a count.

Run from the app folder:  python -I tools/check_slots.py [--names]
"""
import sys
import time
from pathlib import Path

from PIL import Image

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import quickslots  # noqa: E402

CASES = APP / "samples" / "cases"
EARLY, LATER = {4: 93, 5: 145, 7: 52, 9: 65}, {4: 94, 5: 145, 7: 52, 9: 66}
TRUTH = {"012": EARLY, "020": EARLY, "027": LATER, "044": LATER, "050": LATER, "065": LATER}


def frames():
    for n in TRUTH:
        quarter = Image.open(CASES / f"notices_{n}.png").convert("RGB")
        whole = Image.new("RGB", (1920, 1200))
        whole.paste(quarter, (960, 600))
        yield n, whole


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    digits, right, times = quickslots.Digits(), 0, []
    for n, f in frames():
        t = time.perf_counter()
        got = digits.read_all(f)
        times.append(time.perf_counter() - t)
        want = [TRUTH[n].get(s) for s in range(12)]
        right += got == want
        print(n, "right" if got == want else "WRONG", {s: c for s, c in enumerate(got) if c is not None})
    print(f"{right} of {len(TRUTH)} frames read right; {1000 * sorted(times)[len(times) // 2]:.1f} ms a read")


if __name__ == "__main__":
    main()
