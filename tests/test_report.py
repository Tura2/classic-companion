"""Report a problem: one zip with what a bug report needs, and nothing personal."""
import datetime
import json
import zipfile

import report


def make_app(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    for day in ("2026-11-10", "2026-11-13", "2026-11-14", "2026-11-15"):
        (logs / f"companion-{day}.log").write_text(f"log of {day}", "utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.json").write_text('{"name": "Hero1"}')
    (tmp_path / "debug").mkdir()
    (tmp_path / "debug" / "last_capture.png").write_bytes(b"png")
    return tmp_path


CFG = {"screen_reading": True, "game_title": "MapleStory", "discord_enabled": True,
       "discord_id": "123456789", "discord_name": "someone"}


def test_the_zip_has_the_last_three_days_of_logs_and_info(tmp_path):
    app = make_app(tmp_path)
    path = report.make(app, CFG, now=datetime.datetime(2026, 11, 15, 19, 30, 5))
    assert path == app / "reports" / "companion-report-20261115-193005.zip"
    with zipfile.ZipFile(path) as z:
        names = sorted(z.namelist())
        assert names == ["info.txt", "logs/companion-2026-11-13.log", "logs/companion-2026-11-14.log",
                         "logs/companion-2026-11-15.log"]
        info = z.read("info.txt").decode("utf-8")
    assert info.startswith("Companion 1.") and "Platform: " in info and "Screen: " in info
    settings = json.loads(info.split("Settings:\n", 1)[1])
    assert settings["screen_reading"] is True and settings["discord_enabled"] is True


def test_nothing_personal_goes_in(tmp_path):
    app = make_app(tmp_path)
    path = report.make(app, CFG, now=datetime.datetime(2026, 11, 15, 19, 30, 5))
    with zipfile.ZipFile(path) as z:
        everything = " ".join(z.namelist()) + " ".join(z.read(n).decode("utf-8", "replace") for n in z.namelist())
    assert "profile" not in everything and ".png" not in everything
    assert "123456789" not in everything and "someone" not in everything


def test_no_logs_yet_still_makes_a_report(tmp_path):
    path = report.make(tmp_path, {}, now=datetime.datetime(2026, 11, 15, 8, 0, 0))
    with zipfile.ZipFile(path) as z:
        assert z.namelist() == ["info.txt"]
