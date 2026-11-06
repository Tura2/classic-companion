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
            seen = game_reader.read(frame)
            if case.get("tip_region"):
                seen["quicklook"] = {"tooltips": [t["name"] for t in reader.look_for_tooltips(
                    frame, case["tip_region"], game_reader.item_names)]}
            _seen[name] = seen
        return _seen[name]
    return get


@pytest.mark.parametrize("case,name", [(c, f) for c, case in CASE_LIST.items() for f in case["expect"]])
def test_case_field(seen_case, case, name):
    assert field(seen_case(case), name) == CASE_LIST[case]["expect"][name]
