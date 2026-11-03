"""Usage: python tools/scrape_cozy.py [--refresh [HOURS]] [output.json]

Build or refresh the Cozy Market price cache, cache/cozy_items.json, by hand: four pages at a time,
faster than the app, which keeps it fresh on its own in the background (see cozy.py).

Without --refresh, only items not in the file yet are fetched (and any that failed last time). With
--refresh, every price fetched more than HOURS ago (default 20) is fetched again. Safe to stop and
run again: progress is saved as it goes, and a failed fetch keeps the price the file already had.
"""
import argparse
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent   # companion/, when run from tools/
sys.path.insert(0, str(APP_DIR))
import cozy  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Build or refresh cache/cozy_items.json from Cozy Market's item pages.")
    ap.add_argument("out", nargs="?", type=Path, default=APP_DIR / "cache" / "cozy_items.json")
    ap.add_argument("--refresh", nargs="?", type=float, const=20.0, metavar="HOURS",
                    help="fetch again every price older than HOURS (default 20)")
    args = ap.parse_args()
    if not cozy.refresh(args.out, args.refresh, workers=4, delay=0.6, verbose=True):
        print("Nothing to do." + ("" if args.refresh is not None else " Use --refresh to fetch prices again."))


if __name__ == "__main__":
    main()
