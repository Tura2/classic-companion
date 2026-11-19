"""
Report a problem: a zip with what a bug report needs, made from Companion's window.

reports\\companion-report-YYYYMMDD-HHMMSS.zip holds the last 3 days of logs and info.txt (Companion's
version, Windows, the screen, and the settings without who you are on Discord). Never the profile
(your character) and never pictures: they show other players' names.
"""
import datetime
import json
import platform
import subprocess
import sys
import webbrowser
import zipfile
from pathlib import Path

from version import VERSION

DAYS = 3
ISSUE_URL = "https://github.com/Tura2/classic-companion/issues/new?template=bug_report.yml"
PERSONAL = ("discord_id", "discord_name")


def make(app_dir, cfg, now=None):
    app_dir = Path(app_dir)
    now = now or datetime.datetime.now()
    out = app_dir / "reports"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"companion-report-{now:%Y%m%d-%H%M%S}.zip"
    first = (now.date() - datetime.timedelta(days=DAYS - 1)).isoformat()
    logs = sorted(p for p in (app_dir / "logs").glob("companion-*.log")
                  if p.stem[len("companion-"):] >= first) if (app_dir / "logs").is_dir() else []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("info.txt", info(cfg, now))
        for p in logs:
            z.write(p, f"logs/{p.name}")
    return path


def info(cfg, now):
    settings = {k: v for k, v in (cfg or {}).items() if k not in PERSONAL}
    return "\n".join([
        f"Companion {VERSION}",
        f"Made {now:%Y-%m-%d %H:%M:%S}",
        f"Platform: {platform.platform()}",
        f"Screen: {screen()}",
        "Settings:",
        json.dumps(settings, indent=2, ensure_ascii=False, default=str),
    ])


def screen():
    if sys.platform != "win32":
        return "unknown"
    try:
        import ctypes
        u32 = ctypes.windll.user32
        w, h = u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
        dpi = u32.GetDpiForSystem() if hasattr(u32, "GetDpiForSystem") else 96
        return f"{w}x{h} at {round(dpi / 96 * 100)}% scaling (main screen)"
    except Exception as e:
        return f"unknown ({e})"


def send(app_dir, cfg):
    """The window's button: make the zip, show it selected in Explorer, open the bug report form."""
    path = make(app_dir, cfg)
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
    webbrowser.open(ISSUE_URL)
    return path
