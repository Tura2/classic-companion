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
    APP_DIR = RES_DIR = Path(__file__).resolve().parent

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
        print(f"{path.name} was unreadable ({e}). Kept it as {bad.name} and started fresh.")
        return default
