"""
Will screen reading work on this PC? Settings → "This PC" says what's missing, in plain words, with
the fix; the problem reports (autoreport) carry it too.

  windows   Windows 10 1903 (build 18362) or newer: window capture of one window starts there
  capture   the window capture package loads
  ocr       Windows' OCR has English: titles, maps, quests and shops are read with it. A Windows
            in another language often lacks it; the HUD's level and EXP still read without it
  size      the game area is at least reader.MIN_HEIGHT tall (checked while the game is found)

system() is slow-ish (it starts Windows' OCR once): run it once, at start, off the window's thread.
"""
import importlib.util
import sys

OCR_FIX = ("Settings → Time & language → Language → add English (United States), or run this in PowerShell as "
           "administrator, then restart Companion:")
OCR_CMD = 'Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"'


def check(id, ok, title, detail="", fix="", cmd=""):
    """ok: True, False, or None when it couldn't be told. cmd: a command to copy, for the fix."""
    return {"id": id, "ok": ok, "title": title, "detail": detail, "fix": fix, "cmd": cmd}


def windows(version=None, platform=None):
    platform = platform or sys.platform
    if platform != "win32":
        return check("windows", False, "Needs Windows", "Screen reading works only in the Windows app.")
    try:
        v = version or sys.getwindowsversion()
        major, build = v.major, v.build
    except Exception:
        return check("windows", None, "Windows version unknown")
    name = "Windows 11" if major == 10 and build >= 22000 else f"Windows {major}" if major != 10 else "Windows 10"
    if major < 10:
        return check("windows", False, f"{name} is too old",
                     "Screen reading needs Windows 10 (version 1903 or newer) or Windows 11.",
                     "Update to Windows 10 or 11. The dashboard still works without screen reading.")
    if build < 18362:
        return check("windows", False, f"{name} build {build} is too old",
                     "Capturing the game's window needs Windows 10 version 1903 (build 18362) or newer.",
                     "Windows Update → install the latest feature update.")
    return check("windows", True, f"{name} (build {build})")


def capture(find_spec=importlib.util.find_spec):
    try:
        ok = find_spec("windows_capture") is not None
    except Exception:
        ok = False
    if ok:
        return check("capture", True, "Window capture is available")
    return check("capture", False, "Window capture isn't available",
                 "The window capture part of Companion didn't load.", "Install Companion again from the latest release.")


def english_ocr():
    """True / False: whether Windows' OCR can be started for English, the way the reader starts it;
    None when it can't be told (no winrt here)."""
    for mod in ("winrt.windows.media.ocr", "winsdk.windows.media.ocr"):
        try:
            ocr = __import__(mod, fromlist=["OcrEngine"])
            glob = __import__(mod.replace("media.ocr", "globalization"), fromlist=["Language"])
        except Exception:
            continue
        try:
            return ocr.OcrEngine.try_create_from_language(glob.Language("en")) is not None
        except Exception:
            return None
    return None


def ocr(probe=english_ocr):
    try:
        ok = probe()
    except Exception:
        ok = None
    if ok:
        return check("ocr", True, "English text recognition is installed")
    if ok is None:
        return check("ocr", None, "Couldn't check Windows' text recognition")
    return check("ocr", False, "Windows' English text recognition is missing",
                 "Map names, windows, quests and shops can't be read (your level and EXP still can). "
                 "This happens when Windows is in another language.", OCR_FIX, OCR_CMD)


def size(game_size, min_height):
    if not game_size:
        return None                      # no game window right now: nothing to say
    w, h = game_size
    if h >= min_height:
        return check("size", True, f"The game is {w}×{h}")
    return check("size", False, f"The game is {w}×{h}: too small to read",
                 f"Companion reads the game only at {min_height} px tall or more.",
                 "Set the game to 1920×1080 or larger (windowed). On a smaller screen, lower Windows' display "
                 "scaling or use a bigger monitor.")


def system():
    """The checks that don't change while Companion runs."""
    out = [windows()]
    if out[0]["ok"] is not False or sys.platform == "win32":
        out += [capture(), ocr()]
    return out


def summary(checks):
    """{"ok": all fine (None while something couldn't be told), "checks": [...]} for the dashboard."""
    checks = [c for c in checks if c]
    bad = [c for c in checks if c["ok"] is False]
    return {"ok": False if bad else (None if any(c["ok"] is None for c in checks) else True), "checks": checks}
