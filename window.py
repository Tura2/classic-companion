"""
Companion's own window: what's running, a link to the dashboard, and the lines a player needs
(applog.say and applog.problem; details go to the log file), with Report a problem. It has the
Companion logo in its title bar and on the taskbar, which a console window can't: Windows Terminal
shows its own icon for every program it hosts. Closing it closes Companion.

It opens first, before the game data loads, so there's something to see from the start.
"""
import ctypes
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser

from paths import APP_DIR, DATA_DIR, RES_DIR, load_json
import applog

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

KEEP_LINES = 200          # the newest lines stay; older ones scroll away (all of them are in the log)
INK, BG, MUTED, GOOD, WARN = "#E8EEF8", "#16213A", "#9AA8C2", "#2EE59D", "#FFC14D"


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
        k = max(1.0, self.root.winfo_fpixels("1i") / 96)     # the screen's scaling: 1.5 at 150 %
        self.root.geometry(f"{round(640 * k)}x{round(380 * k)}")
        self.root.minsize(round(460 * k), round(260 * k))

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
                            font=("Segoe UI", 10), wrap="word", padx=10, pady=8, height=10,
                            spacing1=2, spacing3=2)
        self.text.tag_configure("time", foreground=MUTED, font=("Segoe UI", 9))
        self.text.tag_configure("problem", foreground=WARN)
        self.text.configure(state="disabled")

        foot = tk.Frame(self.root, bg=BG)
        foot.pack(side="bottom", fill="x", padx=14, pady=(6, 10))   # packed first: never squeezed out
        tk.Label(foot, text="Keep this window open while you play: closing it closes Companion.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9), anchor="w").pack(side="left", fill="x", expand=True)
        self.report_btn = tk.Button(foot, text="Report a problem", command=self.report,
                                    font=("Segoe UI", 9), relief="flat", padx=10, pady=2,
                                    bg="#26324D", fg=INK, activebackground="#33416A", activeforeground=INK,
                                    cursor="hand2")
        self.report_btn.pack(side="right")
        self.text.pack(fill="both", expand=True, padx=14)

        applog.set_sink(lambda kind, text: self.q.put((kind, text)))
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
                if kind in ("say", "problem"):
                    self.add(value, kind == "problem")
                elif kind == "ready":
                    self.url = value
                    self.status.configure(text="Running", fg=GOOD)
                    self.open_btn.configure(state="normal")
                elif kind == "failed":
                    self.status.configure(text=value, fg="#FF7A7A")
                elif kind == "call":
                    try:
                        value()
                    except Exception:
                        import traceback
                        applog.log(traceback.format_exc())
        except queue.Empty:
            pass
        except tk.TclError:
            return           # the window is closing
        self.root.after(100, self.pump)

    def report(self):
        """Report a problem: the zip is made on the side, then shown in Explorer with the form."""
        self.report_btn.configure(state="disabled", text="Making the report…")

        def work():
            try:
                import report
                path = report.send(APP_DIR, load_json(DATA_DIR / "config.json", {}))
                applog.say(f"Report saved: {path}. Attach it to the bug report that just opened.")
            except Exception as e:
                applog.problem("report", "The report couldn't be made.", exc=e)
            self.q.put(("call", lambda: self.report_btn.configure(state="normal", text="Report a problem")))
        threading.Thread(target=work, daemon=True).start()

    def add(self, text, problem=False):
        self.text.configure(state="normal")
        if self.text.index("end-1c") != "1.0":
            self.text.insert("end", "\n")
        self.text.insert("end", time.strftime("%H:%M  "), "time")
        self.text.insert("end", ("⚠ " + text) if problem else text, "problem" if problem else ())
        extra = int(self.text.index("end-1c").split(".")[0]) - KEEP_LINES
        if extra > 0:
            self.text.delete("1.0", f"{extra + 1}.0")
        self.text.see("end")
        self.text.configure(state="disabled")

    def run(self):
        self.root.mainloop()
