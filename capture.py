"""
Screen capture for Companion.

Preferred: Windows Graphics Capture (WGC) on the game window only, the same Windows API that
OBS's "Window Capture" and Discord's window sharing use. It runs at a fixed rate (at most 7 frames
a second), sees only the game window (not your browser, chats or other apps), and keeps working
when another window covers the game. The session runs only while something is being read: it
stops 15 seconds after the last read, and right away when screen reading is turned off.

There is no fallback: if window capture can't run, nothing is captured and the reason is logged
and shown in the dashboard.

Neither touches the game process: no memory access, injection, hooks or input. Finding the game
window reads window titles and class names only; the game process is never opened.
"""
import ctypes
import os
import sys
import threading
import time

from PIL import Image

FRAME_INTERVAL_MS = 143   # at most 7 frames a second: tooltip prices still keep up with the mouse
STALE_AFTER = 3.0         # seconds without a new frame before we restart the session
IDLE_STOP = 15.0          # seconds without a read before the session is stopped

# Window classes that are never the game, even with "MapleStory" in the title: browsers and
# Electron apps (Chrome, Edge, Discord, VS Code), Firefox, Store apps, terminals, Explorer, Tk.
NOT_GAME = ("chrome_widgetwin", "mozillawindowclass", "applicationframewindow", "cascadia_hosting_window_class",
            "consolewindowclass", "cabinetwclass", "tktoplevel", "notepad", "opusapp", "xlmain")


def _windows():
    return sys.platform == "win32"


def _text(fn, hwnd):
    buf = ctypes.create_unicode_buffer(256)
    fn(ctypes.c_void_p(hwnd), buf, 256)
    return buf.value


def find_window(part):
    """HWND of the visible game window whose title contains `part` (case-insensitive), or None.

    Browser tabs, chat apps, terminals and this app's own windows are skipped, so a "MapleStory"
    tab or Discord channel is never captured instead of the game. A window whose class name says
    MapleStory wins; otherwise the front-most match does.
    """
    if not _windows() or not part:
        return None
    u, part, me, found = ctypes.windll.user32, part.lower(), os.getpid(), []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _):
        if hwnd and u.IsWindowVisible(ctypes.c_void_p(hwnd)) and part in _text(u.GetWindowTextW, hwnd).lower():
            cls = _text(u.GetClassNameW, hwnd).lower()
            pid = ctypes.c_ulong()
            u.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))   # an id only; opens nothing
            if pid.value != me and not cls.startswith(NOT_GAME):
                found.append((0 if "maplestory" in cls else 1, len(found), hwnd))
        return True
    u.EnumWindows(proto(cb), 0)
    return min(found)[2] if found else None


def foreground_window():
    if not _windows():
        return None
    f = ctypes.windll.user32.GetForegroundWindow
    f.restype = ctypes.c_void_p      # same type EnumWindows hands out, so the two compare equal
    return f()


def window_bounds(hwnd):
    """Visible bounds of a window in screen pixels; matches what WGC captures."""
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    r = RECT()
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    ok = ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(hwnd), DWMWA_EXTENDED_FRAME_BOUNDS,
                                                    ctypes.byref(r), ctypes.sizeof(r))
    if ok != 0:
        ctypes.windll.user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def client_box(hwnd):
    """The game's drawing area (no title bar or borders) as (left, top, width, height) on screen."""
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    r, p = RECT(), POINT(0, 0)
    ctypes.windll.user32.GetClientRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
    ctypes.windll.user32.ClientToScreen(ctypes.c_void_p(hwnd), ctypes.byref(p))
    return p.x, p.y, r.right, r.bottom


class GameCapture:
    def __init__(self, title_getter):
        self.title_getter = title_getter     # reads the current "game window title" setting
        self.lock = threading.Lock()         # guards the latest frame
        self.session = threading.RLock()     # guards starting and stopping the WGC session
        self.frame, self.frame_time = None, 0.0
        self.hwnd, self.control, self.started, self.last_use = None, None, 0.0, 0.0
        self.mode, self.error = "off", ""
        import importlib.util
        self.wgc_ok = _windows() and importlib.util.find_spec("windows_capture") is not None

    # ---- Windows Graphics Capture
    def _start(self, hwnd):
        from windows_capture import WindowsCapture
        self._stop()
        # Windows 11 24H2+ can pace frames itself and hide the yellow border. Older builds refuse
        # one or both when the session starts (23H2 refuses the pacing), so step down until one
        # starts; the 7-a-second limit is then kept in on_frame_arrived.
        error = None
        for interval, border in ((FRAME_INTERVAL_MS, False), (None, False), (None, None)):
            cap = WindowsCapture(cursor_capture=False, draw_border=border,
                                 minimum_update_interval=interval, window_hwnd=hwnd)

            @cap.event
            def on_frame_arrived(frame, control):
                if time.time() - self.frame_time < FRAME_INTERVAL_MS / 1000:
                    return             # keep at most 7 frames a second, whatever Windows sends
                buf = frame.frame_buffer
                img = Image.frombuffer("RGBA", (frame.width, frame.height), buf[:, :, [2, 1, 0, 3]].tobytes())
                with self.lock:
                    self.frame, self.frame_time = img.convert("RGB"), time.time()

            @cap.event
            def on_closed():
                with self.lock:
                    self.frame = None

            try:
                self.control = cap.start_free_threaded()
                break
            except Exception as e:
                error = e
        else:
            raise error
        self.hwnd, self.started = hwnd, time.time()
        self.mode = "window"

    def _stop(self):
        if self.control:
            try:
                self.control.stop()
            except Exception:
                pass
        self.control, self.hwnd = None, None
        with self.lock:
            self.frame = None
        self.mode = "off"

    def stop(self):
        """End the capture session (any thread). Waits for a read in progress to finish."""
        with self.session:
            self._stop()

    def stop_if_idle(self):
        """Called often from the UI thread: end the session once nothing has read it for a while."""
        if self.control and time.time() - self.last_use > IDLE_STOP and self.session.acquire(blocking=False):
            try:
                self._stop()
            finally:
                self.session.release()

    def _ensure(self):
        """Keep a WGC session on the game window; returns True if a fresh frame is available."""
        if not self.wgc_ok:
            self.error = "Window capture isn't available (needs Windows 10 1903+ and the windows-capture package)."
            return False
        title = self.title_getter()
        if time.time() - getattr(self, "found_at", 0) > 1.0 or title != getattr(self, "found_title", None):
            self.found_hwnd, self.found_at, self.found_title = find_window(title), time.time(), title
        hwnd = self.found_hwnd
        if not hwnd:
            if self.control:
                self._stop()
            self.error = f"No game window found with \"{self.title_getter()}\" in its title."
            return False
        with self.lock:
            fresh = self.frame is not None and time.time() - self.frame_time < STALE_AFTER
        if hwnd != self.hwnd or (not fresh and time.time() - self.started > STALE_AFTER):
            try:
                self._start(hwnd)
            except Exception as e:
                self.error = f"Window capture failed to start: {e}"
                return False
            for _ in range(20):            # wait up to 1 s for the first frame
                time.sleep(0.05)
                with self.lock:
                    if self.frame is not None:
                        return True
            self.error = "Window capture started but no frames arrived. Is the game minimized?"
            return False
        if not fresh:
            self.error = "No new frames from the game window. Is it minimized?"
        return fresh

    # ---- public
    def grab(self, region):
        """Image of a screen-coordinate region [left, top, width, height] of the game window,
        or None (with the reason in self.error and the log). Never falls back to screenshots."""
        l, t, w, h = region
        with self.session:
            self.last_use = time.time()
            if not self._ensure():
                self._log()
                return None
            wl, wt, _, _ = window_bounds(self.hwnd)
            with self.lock:
                img = self.frame
        x, y = l - wl, t - wt
        if img is None:
            self.error = "No frame from the game window yet."
        elif x < 0 or y < 0 or x + w > img.width or y + h > img.height:
            self.error = "That area is outside the game window. Select it again (did the window move?)."
        else:
            self.error = ""
            return img.crop((x, y, x + w, y + h))
        self._log()
        return None

    def grab_game(self):
        """The whole game area (what you see of the game, without the window's title bar), or None."""
        with self.session:
            self.last_use = time.time()
            if not self._ensure():
                self._log()
                return None
            wl, wt, _, _ = window_bounds(self.hwnd)
            cl, ct, cw, ch = client_box(self.hwnd)
            with self.lock:
                img = self.frame
        if img is None or cw < 100 or ch < 100:
            self.error = "No frame from the game window yet."
            self._log()
            return None
        self.error = ""
        x, y = max(0, cl - wl), max(0, ct - wt)
        return img.crop((x, y, min(img.width, x + cw), min(img.height, y + ch)))

    def _log(self):
        if self.error and self.error != getattr(self, "_last_logged", None):
            print("Capture:", self.error)
            self._last_logged = self.error
