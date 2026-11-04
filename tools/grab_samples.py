"""
Save pictures of the game, the way Companion's screen reading sees it, as samples for the reader.

  python tools/grab_samples.py                 one picture now, into samples/raw/
  python tools/grab_samples.py --every 5 -n 12 one every 5 seconds, 12 in all
  python tools/grab_samples.py --label minimap a word added to the file names

Uses the same window capture as Companion (Windows Graphics Capture of the game window only), and
the same "game window title" setting (config.json, default "MapleStory"). Each picture is the game's
drawing area, without the window's title bar, saved as PNG with its size in the name. Nothing is
sent anywhere: the pictures stay in samples/raw/ until you choose to share them.
"""
import argparse
import ctypes
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# On a screen scaled above 100%, Windows otherwise reports the game window in scaled pixels, and
# the picture comes out as the window's top-left corner, title bar and all, instead of the whole
# game: the same pixels Companion uses come only with the same DPI awareness it sets
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

from capture import GameCapture          # noqa: E402
from paths import APP_DIR, load_json     # noqa: E402

OUT = APP_DIR / "samples" / "raw"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[1].strip())
    ap.add_argument("--every", type=float, default=0, help="seconds between pictures")
    ap.add_argument("-n", type=int, default=1, help="how many pictures")
    ap.add_argument("--label", default="", help="a word for the file names, such as minimap")
    a = ap.parse_args()
    title = (load_json(APP_DIR / "config.json", {}) or {}).get("game_title") or "MapleStory"
    cap = GameCapture(lambda: title)
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        for i in range(max(1, a.n)):
            if i:
                time.sleep(max(0.5, a.every))
            frame = None
            for _ in range(20):                 # the first frame takes a moment to arrive
                frame = cap.grab_game()
                if frame is not None:
                    break
                time.sleep(0.25)
            if frame is None:
                print("No picture of the game:", cap.error or f"no window with {title!r} in its title.")
                return 1
            name = f"{datetime.now():%Y%m%d_%H%M%S}_{frame.width}x{frame.height}{'_' + a.label if a.label else ''}.png"
            frame.save(OUT / name)
            print("Saved", OUT / name)
    finally:
        cap.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
