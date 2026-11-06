import shutil
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "tools"))


@pytest.fixture(scope="session")
def game_reader(tmp_path_factory):
    """One Reader for the whole run, on the cached game data (no downloads), learning HUD digit
    shapes into a copy so the real cache/hud_digits.json is never changed by a test."""
    import gamedata
    import reader
    real_fetch = gamedata.fetch_json
    gamedata.fetch_json = lambda url, name, max_age: real_fetch(url, name, 10 ** 12)
    digits = tmp_path_factory.mktemp("cache") / "hud_digits.json"
    if reader.DIGITS_FILE.exists():
        shutil.copy(reader.DIGITS_FILE, digits)
    reader.DIGITS_FILE = digits
    try:
        return reader.Reader(gamedata.GameData())
    finally:
        gamedata.fetch_json = real_fetch
