"""
Companion's own window: what's running, a link to the dashboard, and the messages Companion writes
as it goes. It has the Companion logo in its title bar and on the taskbar, which a console window
can't: Windows Terminal shows its own icon for every program it hosts. Closing it closes Companion.

It opens first, before the game data loads, so there's something to see from the start.
"""
import ctypes
import queue
import sys
import tkinter as tk
import webbrowser

from paths import RES_DIR

if sys.platform == "win32":
    # the same physical pixels as the on-game windows, which share this window's Tk (see sniper.py)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:   # its own taskbar button with its own icon, not grouped under Python
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Tura2.Companion")
    except Exception:
        pass

KEEP_LINES = 400          # the newest messages stay; older ones scroll away
INK, BG, MUTED, GOOD = "#E8EEF8", "#16213A", "#9AA8C2", "#2EE59D"


class Messages:
    """Stands in for stdout and stderr: everything printed shows in the window (and still in a
    console, when there is one), from any thread."""

    def __init__(self, q, also):
        self.q, self.also = q, also

    def write(self, text):
        if self.also is not None:
            try:
                self.also.write(text)
            except Exception:
                pass
        if text:
            self.q.put(("text", text))
        return len(text)

    def flush(self):
        if self.also is not None:
            try:
                self.also.flush()
            except Exception:
                pass


class Window:
    def __init__(self):
        self.q = queue.Queue()
        self.url = None
        self.root = tk.Tk()
        self.root.title("Companion")
        try:
            self.root.iconbitmap(default=str(RES_DIR / "web" / "logo.ico"))
        except tk.TclError:
            pass
        self.root.after(0, self.sharp_icons)
        self.root.configure(bg=BG)
        self.root.geometry("620x360")
        self.root.minsize(420, 240)

        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=14, pady=(12, 6))
        try:
            self.logo = tk.PhotoImage(file=str(RES_DIR / "web" / "logo.png"))
            if self.logo.width() > 64:
                self.logo = self.logo.subsample(max(1, self.logo.width() // 48))
            tk.Label(top, image=self.logo, bg=BG).pack(side="left", padx=(0, 10))
        except tk.TclError:
            pass
        words = tk.Frame(top, bg=BG)
        words.pack(side="left", fill="x", expand=True)
        tk.Label(words, text="Companion", bg=BG, fg=INK, font=("Segoe UI", 15, "bold"), anchor="w").pack(fill="x")
        self.status = tk.Label(words, text="Loading game data and prices…", bg=BG, fg=MUTED,
                               font=("Segoe UI", 10), anchor="w")
        self.status.pack(fill="x")
        self.open_btn = tk.Button(top, text="Open the dashboard", state="disabled", command=self.open,
                                  font=("Segoe UI", 10, "bold"), relief="flat", padx=12, pady=4,
                                  bg="#2B5BD7", fg="white", activebackground="#3D6CE6", activeforeground="white",
                                  disabledforeground="#B7C3DD", cursor="hand2")
        self.open_btn.pack(side="right")

        self.text = tk.Text(self.root, bg="#0E1628", fg=INK, insertbackground=INK, relief="flat",
                            font=("Consolas", 9), wrap="word", padx=10, pady=8, height=10)
        self.text.pack(fill="both", expand=True, padx=14)
        self.text.configure(state="disabled")
        tk.Label(self.root, text="Keep this window open while you play: closing it closes Companion.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=14, pady=(6, 10))

        sys.stdout = Messages(self.q, sys.stdout)
        sys.stderr = Messages(self.q, sys.stderr)
        self.root.after(100, self.pump)

    # ------------------------------------------------------------ from any thread
    def ready(self, url):
        """The dashboard is up: its button works from now on."""
        self.q.put(("ready", url))

    def call(self, fn):
        """Run fn on this window's thread, where Tk (and the on-game windows) live."""
        self.q.put(("call", fn))

    def failed(self, why):
        self.q.put(("failed", why))

    # ------------------------------------------------------------ on the window's thread
    def sharp_icons(self):
        """Tk gives Windows a 32 px icon, which the taskbar stretches at 125 % and up (blurry).
        Hand it the logo.ico frames made for this screen's scale instead."""
        if sys.platform != "win32":
            return
        try:
            u32 = ctypes.windll.user32
            u32.LoadImageW.restype = ctypes.c_void_p
            u32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            u32.SendMessageW.restype = ctypes.c_void_p
            u32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
            self.root.update_idletasks()
            hwnd = int(self.root.wm_frame(), 16)
            dpi = u32.GetDpiForWindow(hwnd) or 96
            path = str(RES_DIR / "web" / "logo.ico")
            self._icons = []                       # kept: Windows doesn't copy them
            for which, metric in ((0, 49), (1, 11)):      # ICON_SMALL / SM_CXSMICON, ICON_BIG / SM_CXICON
                n = u32.GetSystemMetricsForDpi(metric, dpi) or round((16 if which == 0 else 32) * dpi / 96)
                h = u32.LoadImageW(None, path, 1, n, n, 0x10)   # IMAGE_ICON, LR_LOADFROMFILE
                if h:
                    self._icons.append(h)
                    u32.SendMessageW(hwnd, 0x80, which, h)       # WM_SETICON
        except Exception:
            pass

    def open(self):
        if self.url:
            webbrowser.open(self.url)

    def pump(self):
        try:
            while True:
                kind, value = self.q.get_nowait()
                if kind == "text":
                    self.add(value)
                elif kind == "ready":
                    self.url = value
                    self.status.configure(text=f"Running. The dashboard is at {value}", fg=GOOD)
                    self.open_btn.configure(state="normal")
                elif kind == "failed":
                    self.status.configure(text=value, fg="#FF7A7A")
                elif kind == "call":
                    try:
                        value()
                    except Exception:
                        import traceback
                        traceback.print_exc()
        except queue.Empty:
            pass
        except tk.TclError:
            return           # the window is closing
        self.root.after(100, self.pump)

    def add(self, text):
        self.text.configure(state="normal")
        self.text.insert("end", text)
        extra = int(self.text.index("end-1c").split(".")[0]) - KEEP_LINES
        if extra > 0:
            self.text.delete("1.0", f"{extra + 1}.0")
        self.text.see("end")
        self.text.configure(state="disabled")

    def run(self):
        self.root.mainloop()
