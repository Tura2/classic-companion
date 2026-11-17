"""The installer's side panel art (tools/make_installer_art.py) and the files companion.iss expects."""
import re
import sys
from pathlib import Path

from PIL import Image

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP / "tools"))
import make_installer_art as art  # noqa: E402

ISS = (APP / "installer" / "companion.iss").read_text("utf-8")


def test_panel_is_the_asked_size_with_dark_edges_and_the_logo_inside():
    logo = Image.open(APP / "web" / "logo.png").convert("RGBA")
    for w, h in art.SIZES:
        panel = art.side(w, h, logo)
        assert panel.size == (w, h)
        assert panel.getpixel((0, h - 1)) == art.EDGE
        # the logo's bright orange leaf is somewhere in the middle band, never at the edges
        mid = panel.crop((0, int(h * 0.25), w, int(h * 0.6))).getcolors(w * h)
        assert any(r > 200 and 60 < g < 200 and b < 90 for _, (r, g, b) in mid)


def test_iss_uses_exactly_the_generated_files():
    names = {f"side-{w}x{h}.png" for w, h in art.SIZES}
    image_line = re.search(r"^WizardImageFile=(.+)$", ISS, re.M).group(1)
    assert {Path(p).name for p in image_line.split(",")} == names
    assert set(re.findall(r"'(side-\d+x\d+\.png)'", ISS)) == names   # SideArtFor in [Code]
    for name in names:
        assert (APP / "installer" / "art" / name).is_file()
    assert (APP / "installer" / "art" / "DotGothic16-Latin.ttf").is_file()
