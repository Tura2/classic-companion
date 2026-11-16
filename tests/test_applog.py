"""What Companion says goes to its window and a daily log file; details go to the file only."""
import datetime
import sys

import pytest

import applog


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def lg(tmp_path):
    seen, clock = [], Clock()
    applog.setup(tmp_path, sink=lambda kind, text: seen.append((kind, text)), clock=clock,
                 today=lambda: datetime.date(2026, 11, 15), capture_std=False)
    yield tmp_path, seen, clock
    applog.reset()


def file_text(d):
    return (d / "companion-2026-11-15.log").read_text("utf-8")


def test_say_reaches_the_window_and_the_file(lg):
    d, seen, _ = lg
    applog.say("Quest complete: Jane and the Mushroom")
    assert seen == [("say", "Quest complete: Jane and the Mushroom")]
    assert "Quest complete: Jane and the Mushroom" in file_text(d)


def test_log_goes_to_the_file_only(lg):
    d, seen, _ = lg
    applog.log("Map picture unavailable: 100000000")
    assert seen == []
    assert "Map picture unavailable" in file_text(d)


def test_a_problem_shows_once_every_ten_minutes_but_is_always_logged(lg):
    d, seen, clock = lg
    for _ in range(3):
        applog.problem("cozy", "Cozy Market prices couldn't refresh")
        clock.t += 60
    assert seen == [("problem", "Cozy Market prices couldn't refresh")]
    assert file_text(d).count("Cozy Market prices couldn't refresh") == 3
    clock.t += 600
    applog.problem("cozy", "Cozy Market prices couldn't refresh")
    assert len(seen) == 2
    applog.problem("read", "Reading the game hit an error")       # another kind isn't held back
    assert seen[-1] == ("problem", "Reading the game hit an error")


def test_a_problem_logs_its_traceback(lg):
    d, _, _ = lg
    try:
        raise ValueError("bad frame")
    except ValueError as e:
        applog.problem("read", "Reading the game hit an error", exc=e)
    text = file_text(d)
    assert "Traceback" in text and "ValueError: bad frame" in text


def test_logs_older_than_seven_days_are_deleted(tmp_path):
    for day in ("2026-11-01", "2026-11-08", "2026-11-09", "2026-11-15"):
        (tmp_path / f"companion-{day}.log").write_text("x")
    (tmp_path / "notes.txt").write_text("not a log")
    applog.setup(tmp_path, today=lambda: datetime.date(2026, 11, 15), capture_std=False)
    applog.reset()
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == ["companion-2026-11-09.log", "companion-2026-11-15.log", "notes.txt"]


def test_printed_text_lands_in_the_file_not_the_window(tmp_path):
    seen = []
    out, err = sys.stdout, sys.stderr
    try:
        applog.setup(tmp_path, sink=lambda k, t: seen.append(t), today=lambda: datetime.date(2026, 11, 15))
        print("some library chatter")
        sys.stderr.write("a warning from a library\n")
    finally:
        applog.reset()
        sys.stdout, sys.stderr = out, err
    text = (tmp_path / "companion-2026-11-15.log").read_text("utf-8")
    assert "some library chatter" in text and "a warning from a library" in text
    assert seen == []


def test_without_setup_nothing_breaks(capsys):
    applog.reset()
    applog.say("hello")
    applog.log("detail")
    applog.problem("x", "trouble")
    assert "hello" in capsys.readouterr().out
