"""The same game picture at other window sizes reads the same.

Each 1920 x 1200 case is drawn again at other heights the way Windows draws the game there: the
game's own 768 px tall picture (native.py) stretched smoothly to the window (casekit.resample).
Whatever reads at 1200 must read the same at 1050-1600; a field that doesn't is a finding, kept as
a strict xfail named after it until its fix flips it.

The redraw isn't exact: a few fields (the mini map's title, a Quest Helper line) already read
otherwise when a case is redrawn at its own 1200 px, so for those it can't tell anything and they
are skipped. And a field the redraw loses that real pictures at that size read well (checked
2026-11-18 on real 1920 x 1080 and 2560 x 1440 pictures) is marked R: the redraw's blur, not a bug.
"""
import numpy as np
import pytest
from PIL import Image

from casekit import CASES, field, load_cases, resample

HEIGHTS = (1050, 1080, 1440, 1600)


def _frame(w, h, seed=0):
    """A busy synthetic game picture: the game's own pixels stretched, as Windows does."""
    import native
    nw, nh = native.native_size(w, h)
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, (nh // 8, nw // 8, 3), dtype=np.uint8)
    game = Image.fromarray(small).resize((nw, nh), Image.NEAREST)        # sharp blocks, like UI art
    return game.resize((w, h), Image.BILINEAR)


def test_resample_roundtrip():
    f = _frame(1920, 1200)
    back = resample(f, f.height)
    assert back.size == f.size
    diff = np.abs(np.asarray(back, np.int16) - np.asarray(f, np.int16)).mean()
    assert diff <= 2, diff


def test_resample_size():
    assert resample(_frame(1920, 1200), 1050).size == (1680, 1050)
    assert resample(_frame(1920, 1200), 1440).size == (2304, 1440)


# ---------------------------------------------------------------- every case, at every height
CASE_LIST = {k: c for k, c in load_cases().items()
             if (CASES / c["frame"]).exists() and Image.open(CASES / c["frame"]).size == (1920, 1200)}

# field -> why it differs at that height (a finding in the plan), until fixed. Keyed (case, field, height).
# Findings (docs/superpowers/plans/2026-11-18-reader-bug-hunt.md):
#   F3 a player shop's price misread (131,000 as 1,311,000)   F4 a player shop's seller or rows lost, or the shop not found
#   F5 CHARACTER STAT not found at 1050-1080 (its title doesn't OCR)   F6 the mini map lost or its street misread
#   F7 Quest Helper lines dropped   F8 a part of a covered name read as the name   F9 other fields left blank
#   R  the redraw only: real pictures at that size read it (CHARACTER STAT at 1080, mesos, AP)
KNOWN = {
    ("map_ant1200", "map.name", 1080): "R",      # the redraw is lossy on the mini map title
    ("map_ant1200", "map.street", 1080): "R",
    ("fm_quest_window", "stat.name", 1080): "R",
    ("fm_quest_window", "stat.level", 1080): "R",
    ("fm_quest_window", "stat.str_base", 1080): "R",
    ("fm_quest_window", "stat.dex_base", 1080): "R",
    ("fm_quest_window", "stat.ap", 1080): "R",
    ("fm_quest_window", "stat.acc", 1080): "R",
    ("fm_quest_window", "stat.exp", 1080): "R",
    ("fm_quest_window", "inventory.mesos", 1080): "R",
    ("fm_title_glued", "stat.level", 1080): "R",
    ("fm_tooltip", "stat.name", 1050): "F8",
    ("fm_tooltip", "stat.name", 1440): "F8",
    ("fm_tooltip", "stat.level", 1080): "R",
    ("fm_tooltip", "stat.str_base", 1080): "R",
    ("fm_tooltip", "stat.dex_base", 1080): "R",
    ("fm_tooltip", "stat.ap", 1080): "R",
    ("fm_tooltip", "stat.acc", 1080): "R",
    ("fm_tooltip", "quicklook.tooltips", 1600): "F9",
    ("hunt_moved_a", "helper.list", 1080): "F7",
    ("hunt_moved_a", "helper.list", 1600): "F7",
    ("player_shop", "shop.seller", 1050): "F4",
    ("player_shop", "shop.seller", 1440): "F4",
    ("player_shop", "shop.seller", 1600): "F4",
    ("player_shop", "shop.list", 1050): "F4",
    ("player_shop", "shop.list", 1080): "F3",
    ("player_shop", "shop.list", 1440): "F3",
    ("player_shop", "shop.list", 1600): "F4",
    ("player_shop_soldout", "shop.kind", 1050): "F4",
    ("player_shop_soldout", "shop.kind", 1080): "F4",
    ("player_shop_soldout", "shop.kind", 1440): "F4",
    ("player_shop_soldout", "shop.kind", 1600): "F4",
    ("skills_1st", "skills.levels", 1050): "F9",
    ("skills_1st", "skills.levels", 1600): "F9",
    ("skills_1st", "map.street", 1080): "F6",     # read "Road": too little to name the street
    ("skills_hunter", "skills.levels", 1600): "F9",
}

_seen = {}


def _read(game_reader, name, height):
    """What's read in the case redrawn at `height` (None: the case itself, not redrawn)."""
    import reader
    key = (name, height)
    if key not in _seen:
        case = CASE_LIST[name]
        frame = Image.open(CASES / case["frame"]).convert("RGB")
        if height is not None:
            frame = resample(frame, height)
        game_reader.set_job(case["job"])
        game_reader.kept, game_reader.titles.last, game_reader.helper_depth, game_reader.reads = {}, {}, None, 0
        for _ in range(3):
            seen = game_reader.read(frame)
        if case.get("tip_region"):
            k = (height or frame.height) / 1200
            region = [v * k for v in case["tip_region"]]
            seen["quicklook"] = {"tooltips": [t["name"] for t in reader.look_for_tooltips(
                frame, region, game_reader.item_names)]}
        _seen[key] = seen
    return _seen[key]


PARAMS = [pytest.param(c, f, h, marks=[pytest.mark.xfail(strict=True, reason=KNOWN[(c, f, h)])]
                       if (c, f, h) in KNOWN else [], id=f"{c}-{f}-{h}")
          for c, case in CASE_LIST.items() for f in case["expect"] for h in HEIGHTS]


@pytest.mark.skipif(not CASE_LIST, reason="no 1920 x 1200 cases in samples/cases/ (they stay on the PC that made them)")
@pytest.mark.parametrize("case,name,height", PARAMS)
def test_case_at_height(game_reader, case, name, height):
    want = field(_read(game_reader, case, None), name)
    if field(_read(game_reader, case, 1200), name) != want:
        pytest.skip("the redraw reads this otherwise at 1200 already: it can't model this field")
    got = field(_read(game_reader, case, height), name)
    assert got == want
