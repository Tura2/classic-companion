"""Full screen on a monitor of another shape, and windows at the frame's edge (the bug hunt's Task 4).

A 1920 x 1200 case is shown the way full screen shows it on a wider or taller monitor: the game's own
picture stretched to the monitor's height (or width), black bars round it. The capture cuts the bars
off; what's read must be what the case reads, and what's drawn on screen must land on the game.
"""
import types

import numpy as np
import pytest
from PIL import Image

import capture
from casekit import CASES, field, load_cases, native_picture
from test_native import boxed

CASE_LIST = load_cases()
READ = ("fm_quest_window", "skills_1st", "hunt_moved_a", "player_shop")
have = pytest.mark.skipif(not all((CASES / f"{c}.png").exists() for c in READ), reason="no cases on this PC")

# (monitor, the picture's left, width, top, height): a 16:10 game on a 16:9 monitor (bars at the
# sides, the game's picture scaled up to 1440 tall) and on a 4:3 one (bars above and below, 1:1)
LAYOUTS = {
    "pillarbox": ((2560, 1440), 128.75, 2302.5, 0.0, 1440),     # centred, as the game is
    "letterbox": ((1920, 1440), 0.0, 1920, 120.0, 1200),
}

_frames, _reads = {}, {}


def full_screen(case, layout):
    key = (case, layout)
    if key not in _frames:
        size, left, width, top, height = LAYOUTS[layout]
        nat = native_picture(Image.open(CASES / f"{case}.png").convert("RGB"))
        _frames[key] = boxed(nat, size, left, width, top, height)
    return _frames[key]


def read3(game_reader, frame, job):
    game_reader.set_job(job)
    game_reader.kept, game_reader.titles.last, game_reader.helper_depth, game_reader.reads = {}, {}, None, 0
    for _ in range(3):
        seen = game_reader.read(frame)
    return seen


@have
@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_the_capture_gives_back_the_games_picture(layout):
    size, left, width, top, height = LAYOUTS[layout]
    area = capture.game_area(full_screen("fm_quest_window", layout), (0, 0), (0, 0, *size), full=True)
    x0, w, y0, h = area.info["game_area"]
    assert abs(w - width) <= 1 and abs(h - height) <= 1
    assert abs(area.width - width) <= 4 and abs(area.height - height) <= 4     # a dark and a part-lit pixel each side


# (case, layout) -> the finding that makes it read otherwise, until fixed
KNOWN = {("fm_quest_window", "letterbox"): "F6: the mini map lost", ("fm_quest_window", "pillarbox"): "F9: mesos blank",
         ("skills_1st", "pillarbox"): "F6: the street misread", ("hunt_moved_a", "letterbox"): "F7: a Quest Helper line dropped",
         ("player_shop", "letterbox"): "F4: the seller misread", ("player_shop", "pillarbox"): "F4: the seller lost"}


@have
@pytest.mark.parametrize("case,layout", [
    pytest.param(c, lay, marks=[pytest.mark.xfail(strict=True, reason=KNOWN[c, lay])] if (c, lay) in KNOWN else [])
    for c in READ for lay in sorted(LAYOUTS)])
def test_full_screen_reads_what_the_window_does(game_reader, case, layout):
    size = LAYOUTS[layout][0]
    job = CASE_LIST[case]["job"]
    if case not in _reads:
        _reads[case] = read3(game_reader, Image.open(CASES / f"{case}.png").convert("RGB"), job)
    area = capture.game_area(full_screen(case, layout), (0, 0), (0, 0, *size), full=True)
    seen = read3(game_reader, area, job)
    for name in CASE_LIST[case]["expect"]:
        if name.startswith("quicklook"):
            continue
        assert field(seen, name) == field(_reads[case], name), name


# ---- what's drawn on the game: the tooltip prices and the route strip are placed in screen pixels

@pytest.mark.xfail(strict=True, reason="F1: overlays ignore the bars cut off in full screen")
def test_a_tooltip_in_full_screen_is_placed_over_the_game(monkeypatch):
    """A tooltip read at x 500 of the cut frame is at 127 + 500 on a 2560 x 1440 monitor showing a
    1920 x 1200 game between bars of 128.75 px (the capture keeps one dark pixel)."""
    import sniper
    nat = np.clip(np.random.default_rng(3).integers(40, 250, (768, 1228, 3)), 0, 255).astype(float)
    nat[-40:] = 120
    shot = boxed(nat, (2560, 1440), 128.75, 2302.5)
    frame = capture.game_area(shot, (0, 0), (0, 0, 2560, 1440), full=True)
    cut = 127                                     # the capture cuts int(128.75) - 1 px of bar
    assert frame.width < 2560
    monkeypatch.setattr(sniper, "client_box", lambda hwnd: (0, 0, 2560, 1440))
    app = types.SimpleNamespace(capture=types.SimpleNamespace(hwnd=1))
    tips = sniper.App.tips_on_screen(app, [{"box": [500, 300, 700, 500]}], frame)
    assert tips[0]["screen"][0] == 500 + cut


# ---- windows at the frame's edge

@have
@pytest.mark.xfail(strict=True, reason="F2: with its (base+gear) cut off, a stat's total is taken for its base")
def test_a_window_mostly_past_the_right_edge_reads_nothing_wrong(game_reader):
    """CHARACTER STAT dragged so only its first 130 px show: no error, and every field it gives is
    the true one (or none)."""
    src = Image.open(CASES / "fm_quest_window.png").convert("RGB")
    want = read3(game_reader, src, "Hunter").get("stat") or {}
    x = 778 - 3                                   # the window's left edge, about
    frame = Image.new("RGB", src.size, (128, 128, 128))
    frame.paste(src.crop((x, 600, x + 130, 1200)), (src.width - 130, 600))
    got = read3(game_reader, frame, "Hunter").get("stat") or {}
    wrong = {k: v for k, v in got.items() if v is not None and k in want and v != want[k]}
    assert not wrong


@have
def test_a_window_mostly_below_the_bottom_reads_nothing_wrong(game_reader):
    """ITEM INVENTORY dragged down so only its title and tabs show: no error, no wrong mesos."""
    src = Image.open(CASES / "fm_quest_window.png").convert("RGB")
    want = read3(game_reader, src, "Hunter").get("inventory") or {}
    frame = Image.new("RGB", src.size, (128, 128, 128))
    frame.paste(src.crop((380, 630, 720, 690)), (380, src.height - 60))
    got = read3(game_reader, frame, "Hunter").get("inventory") or {}
    assert got.get("mesos") in (None, want.get("mesos"))
