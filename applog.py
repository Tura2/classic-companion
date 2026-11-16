"""
What Companion tells you, and what it keeps for a bug report.

  say(text)                  a line for Companion's window, also written to the log file
  log(text)                  the log file only: details a player doesn't need to see
  problem(kind, text, exc)   always logged (with the traceback); shown in the window in plain words,
                             at most once every 10 minutes for each kind, so a repeating error
                             doesn't flood it

The log is logs\\companion-YYYY-MM-DD.log, one file a day, kept 7 days. Everything printed (by
Companion or a library) and every uncaught error goes to the file, not the window.
Before setup() (tests, the --report command) say() and problem() just print.
"""
import datetime
import sys
import threading
import time
import traceback
from pathlib import Path

KEEP_DAYS = 7
QUIET_S = 600          # a problem of the same kind shows again after 10 minutes


class _State:
    def __init__(self):
        self.dir = None
        self.sink = None
        self.clock = time.time
        self.today = datetime.date.today
        self.last = {}
        self.lock = threading.RLock()
        self.std = None


_s = _State()


def setup(log_dir, sink=None, clock=None, today=None, capture_std=True):
    """Start writing to log_dir. sink(kind, text) gets the window's lines ("say" / "problem")."""
    _s.dir = Path(log_dir)
    _s.dir.mkdir(parents=True, exist_ok=True)
    _s.sink = sink
    _s.clock = clock or time.time
    _s.today = today or datetime.date.today
    _s.last = {}
    _cleanup()
    if capture_std:
        _s.std = (sys.stdout, sys.stderr, threading.excepthook, sys.excepthook)
        sys.stdout = _ToLog("out", sys.stdout)
        sys.stderr = _ToLog("err", sys.stderr)
        threading.excepthook = _thread_error
        sys.excepthook = lambda t, e, tb: _crash(e)


def set_sink(sink):
    """The window attaches here once it exists."""
    _s.sink = sink


def reset():
    """Back to printing (tests)."""
    if _s.std:
        sys.stdout, sys.stderr, threading.excepthook, sys.excepthook = _s.std
    _s.__init__()


def log(text):
    _write("info", text)


def say(text):
    _write("say", text)
    _show("say", text)


def problem(kind, text, exc=None):
    detail = ""
    if exc is not None:
        detail = "\n" + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).rstrip()
    _write("warn", f"[{kind}] {text}{detail}")
    with _s.lock:
        now = _s.clock()
        if now - _s.last.get(kind, -1e18) < QUIET_S:
            return
        _s.last[kind] = now
    _show("problem", text)


# ------------------------------------------------------------------ inside
def _path():
    return _s.dir / f"companion-{_s.today():%Y-%m-%d}.log"


def _write(level, text):
    if _s.dir is None:
        return
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    lines = str(text).rstrip("\n").split("\n")
    body = f"{stamp} {level:5} {lines[0]}\n" + "".join(f"               {ln}\n" for ln in lines[1:])
    with _s.lock:
        try:
            with open(_path(), "a", encoding="utf-8") as f:
                f.write(body)
        except OSError:
            pass


def _show(kind, text):
    if _s.dir is None:
        print(text)
        return
    if _s.sink:
        try:
            _s.sink(kind, text)
        except Exception:
            pass


def _cleanup():
    oldest = _s.today() - datetime.timedelta(days=KEEP_DAYS - 1)
    for p in _s.dir.glob("companion-*.log"):
        try:
            day = datetime.date.fromisoformat(p.stem[len("companion-"):])
        except ValueError:
            continue
        if day < oldest:
            try:
                p.unlink()
            except OSError:
                pass


def _crash(e):
    problem("crash", "Something went wrong inside Companion. It's in the log: Report a problem sends it.", exc=e)


def _thread_error(args):
    if args.exc_type is SystemExit:
        return
    _crash(args.exc_value)


class _ToLog:
    """Stands in for stdout / stderr: whole lines go to the log file (and to the console, when
    Companion was started from one)."""

    def __init__(self, level, console):
        self.level, self.console, self.buf = level, console, ""

    def write(self, text):
        if self.console is not None:
            try:
                self.console.write(text)
            except Exception:
                pass
        self.buf += text
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            if line.strip():
                _write(self.level, line)
        return len(text)

    def flush(self):
        if self.console is not None:
            try:
                self.console.flush()
            except Exception:
                pass
