"""Record the game's bottom-right corner while you play, for checking the corner-line reader
(tools/check_corner.py) and the quick slots' counts.

  python -I tools/record_corner.py --seconds 150 --label perion

Every 0.4 s it saves the bottom-right area of the game (the corner's lines and the quick slots, nothing
else) into samples/raw/corner_<label>/, and prints the lines notices.py counts as you go. map.json
there says where the area was cut from; add truth.json (what was really picked up) to check against.
Same window capture as Companion; it only takes pictures.
"""
import argparse
import ctypes
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
if sys.platform == "win32":
    ctypes.windll.shcore.SetProcessDpiAwareness(2)     # or frames come back scaled down

from capture import GameCapture          # noqa: E402
from paths import APP_DIR, load_json     # noqa: E402
import gamedata                          # noqa: E402
import notices                           # noqa: E402

EVERY = 0.4


def area(w, h):
    """The corner's lines and the quick slots, at any window size: (left, top, right, bottom)."""
    s = h / 1200
    return (w - round(580 * s), h - round(420 * s), w, h - round(140 * s))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=150)
    ap.add_argument("--label", default="play")
    a = ap.parse_args()
    title = (load_json(APP_DIR / "config.json", {}) or {}).get("game_title") or "MapleStory"
    cap = GameCapture(lambda: title)
    out = APP_DIR / "samples" / "raw" / f"corner_{a.label}"
    out.mkdir(parents=True, exist_ok=True)
    data = gamedata.GameData()
    corner = notices.Corner()
    corner.set_names(list(data.item_ids))
    t0, i, meta, events = time.time(), 0, None, []
    while time.time() - t0 < a.seconds:
        tick = time.time()
        frame = cap.grab_game()
        if frame is not None:
            if meta is None:
                meta = {"size": list(frame.size), "box": list(area(*frame.size))}
                (out / "map.json").write_text(json.dumps(meta), "utf-8")
            frame.crop(meta["box"]).save(out / f"c_{i:04d}_{tick - t0:07.2f}.png")
            for ev in corner.step(frame, tick):
                events.append([i, *ev])
                print(f"{tick - t0:6.1f}s  #{i}  {ev}")
            i += 1
        time.sleep(max(0.0, EVERY - (time.time() - tick)))
    (out / "events.json").write_text(json.dumps(events, ensure_ascii=False), "utf-8")
    cap.stop()
    print(f"saved {i} pictures and {len(events)} events in {out}")


if __name__ == "__main__":
    main()
