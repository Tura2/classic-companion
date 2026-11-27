import base64
import json

from PIL import Image

import autoreport
from autoreport import Reports, Watch

SETUP = {"url": "https://reports.example/api/report", "key": "k"}


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class Post:
    def __init__(self, code=201):
        self.code, self.calls = code, []

    def __call__(self, url, json=None, headers=None, timeout=None):
        self.calls.append((url, json, headers))
        return type("R", (), {"status_code": self.code})()


def make(tmp_path, on=True, setup=SETUP, post=None, clock=None):
    flag = {"on": on}
    r = Reports(lambda: flag["on"], setup, post or Post(), tmp_path / "outbox", tmp_path / "state.json", clock or Clock())
    return r, flag


def frame(w=1920, h=1080):
    return Image.new("RGB", (w, h), (40, 60, 80))


HUD = {"windows": {"hud": [0.1, 0.95]}, "scale": 1.0, "hud": {"level": 30, "exp": 1234, "exp_pct": 12.5}}
MAP = {"name": "Henesys Hunting Ground I", "street": "Victoria Road"}


def test_nothing_is_kept_while_the_setting_is_off_or_the_build_has_no_server(tmp_path):
    for on, setup in ((False, SETUP), (True, None)):
        r, _ = make(tmp_path, on, setup)
        w = Watch(r)
        for _ in range(10):
            w.see(frame(), {**HUD, "map_missed": "Hennes Huntng"})
        assert r.pending() == 0


def test_a_title_that_names_no_map_is_reported_once_after_a_few_reads(tmp_path):
    clock = Clock()
    r, _ = make(tmp_path, clock=clock)
    w = Watch(r, lambda: {"version": "1.4.6"}, clock)
    w.see(frame(), {**HUD, "map": MAP})                     # a good read first: kept to compare
    for i in range(autoreport.MAP_MISSED_READS - 1):
        assert w.see(frame(), {**HUD, "map_missed": "Hennes Huntng"}) == []
    kept = w.see(frame(), {**HUD, "map_missed": "Hennes Huntng"})
    assert len(kept) == 1
    meta = json.loads((kept[0] / "report.json").read_text(encoding="utf-8"))
    assert meta["kind"] == "map_missed" and meta["version"] == "1.4.6"
    assert meta["frame_size"] == [1920, 1080] and "Hennes" in meta["why"]
    assert meta["history"][0]["map"] == MAP["name"]
    assert {"frame.png", "last_ok.jpg"} <= set(meta["files"])
    for _ in range(20):                                     # the same problem again: not within the hour
        w.see(frame(), {**HUD, "map_missed": "Hennes Huntng"})
    assert r.pending() == 1
    clock.t += autoreport.COOLDOWN + 1
    for _ in range(autoreport.MAP_MISSED_READS):
        w.see(frame(), {**HUD, "map_missed": "Hennes Huntng"})
    assert r.pending() == 2


def test_exp_not_read_hud_lost_and_map_lost(tmp_path):
    clock = Clock()
    r, _ = make(tmp_path, clock=clock)
    w = Watch(r, clock=clock)
    no_exp = {"windows": {"hud": [0, 0]}, "scale": 1.0, "hud": {"level": 30}, "map": MAP}
    kinds = []
    for _ in range(autoreport.EXP_MISSED_READS):
        kinds += [p.name.split("-")[2] for p in w.see(frame(), no_exp)]
    assert kinds == ["exp_missed"]
    for _ in range(autoreport.LOST_READS):
        clock.t += 2
        kinds += [p.name.split("-")[2] for p in w.see(frame(), {"windows": {}, "scale": 1.0})]
    assert kinds[-1] == "hud_lost"
    for _ in range(autoreport.LOST_READS):
        clock.t += 2
        kinds += [p.name.split("-")[2] for p in w.see(frame(), {**HUD})]
    assert kinds[-1] == "map_lost"


def test_quick_reads_and_errors_in_seen_are_not_judged(tmp_path):
    r, _ = make(tmp_path)
    w = Watch(r)
    for _ in range(20):
        w.see(frame(), {"quick": True, "map_missed": "x x x x x"})
        w.see(frame(), {"error": "black"})
    assert r.pending() == 0


def test_a_day_has_a_cap(tmp_path):
    clock = Clock()
    r, _ = make(tmp_path, clock=clock)
    for i in range(autoreport.DAY_CAP + 5):
        r.keep("map_missed", f"k{i}", {})
    assert r.pending() == autoreport.DAY_CAP


def test_a_frame_too_big_for_png_goes_as_jpeg_with_the_area_kept_sharp():
    import random
    rnd = random.Random(1)
    img = Image.frombytes("RGB", (800, 600), bytes(rnd.randrange(256) for _ in range(800 * 600 * 3)))
    files = autoreport.encode(img, [(0, 500, 800, 600)], budget=1_000_000)
    assert "frame.png" not in files and "frame.jpg" in files
    assert any(n.startswith("crop1_0_500") for n in files)
    assert sum(len(v) for v in files.values()) <= 1_000_000
    assert list(autoreport.encode(frame(320, 200))) == ["frame.png"]


def test_sending_takes_it_out_of_the_outbox_and_a_failure_keeps_it(tmp_path):
    post = Post(503)
    r, _ = make(tmp_path, post=post)
    r.keep("error", "e1", {"why": "x"}, frame(200, 100))
    assert r.send_one() is False and r.pending() == 1 and "503" in r.error
    post.code = 201
    assert r.send_one() is True and r.pending() == 0 and r.sent == 1 and r.error == ""
    url, body, headers = post.calls[-1]
    assert url == SETUP["url"] and headers["X-Companion-Key"] == "k"
    assert body["report"]["kind"] == "error"
    assert base64.b64decode(body["files"]["frame.png"])[:4] == b"\x89PNG"


def test_a_report_the_server_refuses_is_dropped_and_a_bad_key_is_kept(tmp_path):
    post = Post(400)
    r, _ = make(tmp_path, post=post)
    r.keep("error", "e1", {}, None)
    r.send_one()
    assert r.pending() == 0
    post.code = 401
    r.keep("error", "e2", {}, None)
    r.send_one()
    assert r.pending() == 1 and "key" in r.error


def test_nothing_is_sent_once_the_setting_is_turned_off(tmp_path):
    post = Post()
    r, flag = make(tmp_path, post=post)
    r.keep("error", "e1", {}, None)
    flag["on"] = False
    assert r.send_one() is False and post.calls == []


def test_the_install_id_and_cooldowns_outlive_a_restart(tmp_path):
    clock = Clock()
    r, _ = make(tmp_path, clock=clock)
    r.keep("error", "e1", {}, None)
    again, _ = make(tmp_path, clock=clock)
    assert again.install == r.install
    assert not again.may_keep("e1")


def test_numpy_numbers_and_odd_values_go_into_json():
    import numpy as np
    out = autoreport.jsonable({"s": np.float32(0.91), "t": (1, 2), "o": object()})
    json.dumps(out)
    assert abs(out["s"] - 0.91) < 1e-6 and out["t"] == [1, 2]


def test_a_read_error_is_reported_with_its_traceback(tmp_path):
    r, _ = make(tmp_path)
    w = Watch(r)
    try:
        {}["missing"]
    except KeyError as e:
        folder = w.error(frame(300, 200), e)
    meta = json.loads((folder / "report.json").read_text(encoding="utf-8"))
    assert meta["kind"] == "error" and "KeyError" in meta["seen"]["traceback"]


class Get:
    def __init__(self, want):
        self.want, self.calls = want, []

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.calls.append(params)
        want = self.want
        return type("R", (), {"status_code": 200, "json": lambda self: {"want_files": want}})()


def test_a_problem_the_server_has_enough_pictures_of_goes_without_them(tmp_path):
    post, get = Post(), Get(False)
    r = Reports(lambda: True, SETUP, post, tmp_path / "outbox", tmp_path / "state.json", Clock(), get)
    r.keep("map_missed", "map_missed:henesys", {"version": "1.4.6", "frame_size": [1920, 1080]}, frame(200, 100))
    assert r.send_one() and r.pending() == 0
    body = post.calls[-1][1]
    assert body["files"] == {} and body["report"]["count_only"] is True
    assert get.calls[-1] == {"key": "map_missed:henesys", "version": "1.4.6", "size": "1920x1080"}
    get.want = True
    r.keep("map_missed", "map_missed:other", {}, frame(200, 100))
    r.send_one()
    assert "frame.png" in post.calls[-1][1]["files"]


def test_the_server_not_answering_the_question_still_sends_the_pictures(tmp_path):
    post = Post()

    def get(*a, **k):
        raise OSError("offline")
    r = Reports(lambda: True, SETUP, post, tmp_path / "outbox", tmp_path / "state.json", Clock(), get)
    r.keep("error", "e1", {}, frame(200, 100))
    r.send_one()
    assert "frame.png" in post.calls[-1][1]["files"]


def test_one_map_misread_different_ways_is_one_problem(tmp_path):
    clock = Clock()
    r, _ = make(tmp_path, clock=clock)
    near = {"Hennes Huntng": ("Henesys Hunting Ground I", 88), "Henes Hunting": ("Henesys Hunting Ground I", 85),
            "zz": ("Ellinia", 20)}
    w = Watch(r, clock=clock, near=lambda t: near[t])
    keys = []
    for text in ("Hennes Huntng", "Henes Hunting", "zz"):
        for _ in range(autoreport.MAP_MISSED_READS):
            for p in w.see(frame(), {**HUD, "map_missed": text}):
                keys.append(json.loads((p / "report.json").read_text(encoding="utf-8"))["key"])
        w.see(frame(), {**HUD, "map": MAP})          # a good read between: the run starts over
    assert keys == ["map_missed:henesys-hunting-ground-i", "map_missed:zz"]


# ---- live 2026-11-26: switching the game's resolution sent 25 reports in 1.5 minutes. Every read
# mid-switch was another size, so another problem key, and the runs built up before kept going

def test_a_resolution_switch_sends_nothing_while_the_size_moves(tmp_path):
    clock = Clock()
    r, _ = make(tmp_path, clock=clock)
    w = Watch(r, clock=clock)
    for _ in range(3):
        w.see(frame(1920, 1200), {**HUD, "map": MAP})
        clock.t += 1.5
    for i in range(40):                                   # dragged: a new size every read, nothing read
        clock.t += 1.5
        assert w.see(frame(2074 + 7 * i, 1368 + i), {"windows": {}, "scale": 0.64}) == []
    assert r.pending() == 0


def test_after_a_switch_a_size_that_stays_broken_is_reported_once(tmp_path):
    clock = Clock()
    r, _ = make(tmp_path, clock=clock)
    w = Watch(r, clock=clock)
    w.see(frame(1920, 1200), {**HUD, "map": MAP})
    kept = []
    for _ in range(60):                                   # steady at the new size, EXP and map unread
        clock.t += 1.5
        kept += w.see(frame(2560, 1440), {"windows": {"hud": [0, 0]}, "scale": 0.64, "hud": {"level": 40}})
    kinds = sorted(p.name.split("-")[2] for p in kept)
    assert kinds == ["exp_missed", "map_lost"]


def test_one_kind_at_most_a_few_times_an_hour(tmp_path):
    clock = Clock()
    r, _ = make(tmp_path, clock=clock)
    for i in range(10):
        r.keep("map_lost", f"map_lost:{2000 + i}x1440:0.64", {})
    assert r.pending() == autoreport.KIND_HOUR
    clock.t += 3601
    assert r.keep("map_lost", "map_lost:1x1:1", {}) is not None


def test_an_open_mini_map_showing_no_name_isnt_lost(tmp_path):
    # its "+" view: just MINI MAP over the map's picture, no name to read (live 2026-11-26)
    clock = Clock()
    r, _ = make(tmp_path, clock=clock)
    w = Watch(r, clock=clock)
    w.see(frame(), {**HUD, "map": MAP})
    for _ in range(autoreport.LOST_READS * 2):
        clock.t += 1.5
        w.see(frame(), {**HUD}, extra={"map_titles": {"minimap": ["MINI MAP", 14, 17, 75, 10]}})
    assert r.pending() == 0
