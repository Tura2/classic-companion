"""Starting Companion while it's already running opens the running one's dashboard instead of a
second copy (two copies drew every label twice and wrote one grind history from two trackers)."""
import companion


def test_the_first_copy_runs():
    assert companion.hold_single_instance(create=lambda: (1, 0)) is True


def test_a_second_copy_sees_the_first():
    assert companion.hold_single_instance(create=lambda: (1, companion.ALREADY_EXISTS)) is False


def test_no_mutex_at_all_still_runs():
    def broken():
        raise OSError("no kernel32")
    assert companion.hold_single_instance(create=broken) is True


def test_the_running_dashboard_is_opened(monkeypatch):
    opened = []
    up = {companion.PORT + 1}                    # the first copy took the next port
    monkeypatch.setattr(companion.webbrowser, "open", opened.append)
    url = companion.show_running(alive=lambda port: port in up)
    assert url == f"http://localhost:{companion.PORT + 1}" and opened == [url]


def test_nothing_answering_opens_nothing(monkeypatch):
    opened = []
    monkeypatch.setattr(companion.webbrowser, "open", opened.append)
    assert companion.show_running(alive=lambda port: False) is None and opened == []


class Started(Exception):
    pass


def run_main(monkeypatch, argv):
    """main() with another copy running: whether it went on to start (it reached the data folder)."""
    shown = []
    monkeypatch.setattr(companion, "hold_single_instance", lambda: False)
    monkeypatch.setattr(companion, "show_running", lambda: shown.append(1))
    monkeypatch.setattr(companion.paths, "migrate", lambda: (_ for _ in ()).throw(Started()))
    monkeypatch.setattr(companion.sys, "argv", ["Companion.exe", *argv])
    try:
        companion.main()
    except Started:
        return True, shown
    return False, shown


def test_main_hands_over_to_the_running_copy(monkeypatch):
    assert run_main(monkeypatch, []) == (False, [1])


def test_a_second_copy_on_purpose(monkeypatch):
    """The release's smoke test runs the new build beside the installed Companion."""
    assert run_main(monkeypatch, ["--second-copy", "--no-update", "--no-browser"]) == (True, [])
