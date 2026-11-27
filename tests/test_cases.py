"""The reader against real game pictures with known true values (samples/cases/, kept on this PC only)."""
import pytest
from PIL import Image

from casekit import CASES, field, load_cases

CASE_LIST = load_cases()
if not CASE_LIST:
    pytest.skip("no cases in samples/cases/ (they stay on the PC that made them)", allow_module_level=True)

_seen = {}


@pytest.fixture
def seen_case(game_reader):
    """What the reader sees in a case, read once per run; plus the quick tooltip look in its tip_region."""
    def get(name):
        if name not in _seen:
            import reader
            case = CASE_LIST[name]
            frame = Image.open(CASES / case["frame"]).convert("RGB")
            game_reader.set_job(case["job"])
            # a fresh look, then the same screen read three times in a row, as the app does every
            # 1.5 s: what's kept between reads (windows' places, the mini map's search) settles
            game_reader.kept, game_reader.titles.last, game_reader.helper_depth, game_reader.reads = {}, {}, None, 0
            game_reader.active_ids = set(case.get("active", ()))     # the quests the app knows you have going
            for _ in range(3):
                seen = game_reader.read(frame)
            if case.get("tip_region"):
                seen["quicklook"] = {"tooltips": [t["name"] for t in reader.look_for_tooltips(
                    frame, case["tip_region"], game_reader.item_names)]}
            _seen[name] = seen
        return _seen[name]
    return get


@pytest.mark.parametrize("case,name", [(c, f) for c, case in CASE_LIST.items() for f in case["expect"]])
def test_case_field(seen_case, case, name):
    got, want = field(seen_case(case), name), CASE_LIST[case]["expect"][name]
    if name in CASE_LIST[case].get("subset", []):
        # what's read must be true; what can't be read may be left out, never guessed
        if isinstance(want, dict):
            assert got is not None and all(k in want and want[k] == v for k, v in got.items()), (got, want)
        else:
            assert got is not None and all(v in want for v in got), (got, want)
        return
    known = CASE_LIST[case].get("known", {})
    if got != want and name in known:
        pytest.xfail(known[name])        # a known limit, said why in the case; a pass shows as a pass
    assert got == want


# the whole-frame title search (live round, F5) never invents a stat window: cases with none
NO_STAT = ["map_ant1200", "fs600_hud"] + [n for n, c in CASE_LIST.items()
                                          if "stat.level" in c["expect"] and c["expect"]["stat.level"] is None]


@pytest.mark.parametrize("name", [n for n in dict.fromkeys(NO_STAT) if n in CASE_LIST])
def test_whole_frame_search_adds_no_window(seen_case, name):
    assert not seen_case(name).get("stat")


# tooltip boxes measured by eye on real pictures (case "tips"): a price card goes under the box
@pytest.mark.parametrize("name", [n for n, c in CASE_LIST.items() if c.get("tips")])
def test_tooltip_boxes(game_reader, name):
    case = CASE_LIST[name]
    f = Image.open(CASES / case["frame"]).convert("RGB")
    got = {t["name"]: t["box"] for t in game_reader.look_for_tooltips(f, [0, 0, f.width, f.height])}
    for want in case["tips"]:
        assert want["name"] in got, got
        assert abs(got[want["name"]][0] - want["left"]) <= 4, (want, got[want["name"]])
        assert abs(got[want["name"]][3] - want["bottom"]) <= 6, (want, got[want["name"]])


def test_hud_sprite_level_isnt_overwritten_by_the_stat_window(game_reader, monkeypatch):
    # the HUD's level read off its own sprites is exact; a stat window misreading 38 as 33 (a cut
    # digit, as ACC 83 -> 33) must not overwrite it and mark it exact
    import reader
    if "stat_1080_glued" not in CASE_LIST:
        pytest.skip("no case")
    real = reader.read_stat
    monkeypatch.setattr(reader, "read_stat", lambda *a, **k: {**real(*a, **k), "level": 33})
    f = Image.open(CASES / "stat_1080_glued.png").convert("RGB")
    game_reader.kept, game_reader.titles.last, game_reader.reads = {}, {}, 0
    for _ in range(3):
        seen = game_reader.read(f)
    assert seen["stat"]["level"] == 33 and seen["hud"]["level"] == 38


def test_tooltip_bottom_doesnt_run_into_lines_below(game_reader):
    # lines under a tooltip that aren't on its navy (a window's rows below it, 22 px apart) don't
    # carry its bottom down with them (final review, 2026-11-19)
    import native
    import reader
    if "tips_fs1080" not in CASE_LIST:
        pytest.skip("no case")
    f = Image.open(CASES / "tips_fs1080.png").convert("RGB")
    l, t, r, b = 1130, 450, 2100, 920
    lines = reader.ocr(f.crop((l, t, r, b)), 1, l, t)
    lines += [("Row of a window below", 1220.0, 836.0 + 22 * k, 160.0, 16.0) for k in range(3)]
    tips = reader.read_tooltips(lines, f, native.ui_scale(f), game_reader.item_names)
    blue = next(t for t in tips if t["name"] == "Blue Jean Shorts")
    assert abs(blue["box"][3] - 822) <= 6, blue["box"]


# no window of any kind is invented by the whole-frame search on pictures that have none (review)
@pytest.mark.parametrize("name", [n for n in ("map_ant1200", "fs600_hud") if n in CASE_LIST])
def test_whole_frame_search_adds_no_window_of_any_kind(seen_case, name):
    seen = seen_case(name)
    assert not any(seen.get(k) for k in ("stat", "inventory", "skills", "quest"))
    assert not (seen.get("helper") or {}).get("quests")
