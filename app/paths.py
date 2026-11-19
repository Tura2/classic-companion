"""Where things live, both when run from source and when packaged as Companion.exe."""
import json
import os
import sys
import threading
from pathlib import Path

if getattr(sys, "frozen", False):                 # PyInstaller build
    APP_DIR = Path(sys.executable).resolve().parent   # writable: settings, cache, your data
    RES_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))  # bundled read-only files (web/)
else:
    APP_DIR = RES_DIR = Path(__file__).resolve().parent.parent     # app/'s parent: the repo folder

# Everything Companion writes stays in its own folder, each kind in its own subfolder.
DATA_DIR = APP_DIR / "data"          # your profile, settings, histories: kept on uninstall if you say so
CACHE_DIR = APP_DIR / "cache"        # downloaded game data and pictures: safe to delete
LOGS_DIR = APP_DIR / "logs"          # a log file a day, kept 7 days
DEBUG_DIR = APP_DIR / "debug"        # pictures of windows that didn't read
REPORTS_DIR = APP_DIR / "reports"    # zips made by Report a problem

# Data files that older versions kept loose next to the exe.
DATA_FILES = ("profile.json", "profile.json.bak", "config.json", "scans.sqlite", "grind.sqlite",
              "discord_outbox.json")


def migrate(app_dir=None):
    r"""Move data files an older version left loose in the app folder into data\. A file already in
    data\ wins, and the loose one is left where it is (never lost). Returns the names moved."""
    app_dir = Path(app_dir or APP_DIR)
    data = app_dir / "data"
    data.mkdir(exist_ok=True)
    moved = []
    for name in DATA_FILES:
        old, new = app_dir / name, data / name
        if old.is_file() and not new.exists():
            os.replace(old, new)
            moved.append(name)
    return moved

_write_lock = threading.Lock()


def save_json(path, data):
    """Write JSON so a crash or two threads saving at once never leave a half-written file."""
    tmp = path.with_name(path.name + ".tmp")
    with _write_lock:
        tmp.write_text(json.dumps(data, indent=2), "utf-8")
        os.replace(tmp, path)


def load_json(path, default):
    """Read a JSON file; a damaged one is kept as <name>.bad instead of being silently overwritten."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError) as e:
        bad = path.with_name(path.name + ".bad")
        try:
            os.replace(path, bad)
        except OSError:
            pass
        import applog
        applog.problem("file", f"{path.name} was damaged, so Companion started it fresh. The old one is kept as {bad.name}.", exc=e)
        return default
