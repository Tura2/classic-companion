from types import SimpleNamespace as V

import compat


def test_windows_versions():
    w = lambda major, build: compat.windows(V(major=major, build=build), "win32")
    assert w(6, 7601)["ok"] is False and "too old" in w(6, 7601)["title"]          # Windows 7
    assert w(6, 9600)["ok"] is False                                                # 8.1
    old = w(10, 17763)                                                              # 1809
    assert old["ok"] is False and "18362" in old["detail"]
    assert w(10, 18362) == {**w(10, 18362), "ok": True, "title": "Windows 10 (build 18362)"}
    assert w(10, 22631)["title"] == "Windows 11 (build 22631)"
    assert compat.windows(platform="linux")["ok"] is False


def test_english_ocr_missing_says_what_still_reads_and_how_to_fix():
    c = compat.ocr(lambda: False)
    assert c["ok"] is False and "EXP still" in c["detail"] and "Language.OCR~~~en-US" in c["cmd"] and "English" in c["fix"]
    assert compat.ocr(lambda: True)["ok"] is True
    assert compat.ocr(lambda: None)["ok"] is None
    assert compat.ocr(lambda: 1 / 0)["ok"] is None


def test_capture_package():
    assert compat.capture(lambda n: object())["ok"] is True
    assert compat.capture(lambda n: None)["ok"] is False


def test_game_size_only_while_the_game_is_found():
    assert compat.size(None, 1000) is None
    assert compat.size([1920, 1080], 1000)["ok"] is True
    small = compat.size([1366, 705], 1000)
    assert small["ok"] is False and "1366×705" in small["title"]


def test_summary():
    good, bad, unk = compat.check("a", True, "a"), compat.check("b", False, "b"), compat.check("c", None, "c")
    assert compat.summary([good, None])["ok"] is True
    assert compat.summary([good, unk])["ok"] is None
    assert compat.summary([good, unk, bad])["ok"] is False
    assert compat.summary([good, None])["checks"] == [good]
