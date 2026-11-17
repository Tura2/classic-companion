"""
The installer's side panel: the pixel logo glowing on Companion's dark HUD colours, at the sizes Inno
Setup picks from for 100% / 125% / 150% / 200% screens. Run it after changing web/logo.png:

    python tools/make_installer_art.py      ->  installer/art/side-*.png
"""
from pathlib import Path

from PIL import Image

APP = Path(__file__).resolve().parent.parent
OUT = APP / "installer" / "art"

# Inno's welcome/finish image area (164:314) at each scale, from its WizardImageFile help page.
SIZES = [(202, 386), (269, 515), (336, 643), (430, 824)]
CENTER = (0x3A, 0x4B, 0x66)   # the glow behind the logo
EDGE = (0x1A, 0x21, 0x30)     # the HUD's darkest blue, at the panel's edges
GLOW_Y = 0.42                 # the logo sits a little above the middle


def side(width, height, logo):
    """One side panel: a soft round glow fading to the edge colour, the logo crisp in it."""
    cx, cy = width / 2, height * GLOW_Y
    reach = width * 0.95
    panel = Image.new("RGB", (width, height))
    px = panel.load()
    for y in range(height):
        for x in range(width):
            t = min(1.0, ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / reach)
            px[x, y] = tuple(round(c + (e - c) * t) for c, e in zip(CENTER, EDGE))
    # logo.png draws each art pixel as a 2x2 block (a 128-cell grid): scaling by half-steps of a
    # cell keeps the pixel art sharp. Aim for about 62% of the panel's width.
    cells = logo.width // 2
    per_cell = max(1.0, round(width * 0.62 / cells * 2) / 2)
    size = round(cells * per_cell)
    art = logo.resize((size, size), Image.NEAREST)
    panel.paste(art, (round(cx - size / 2), round(cy - size / 2)), art)
    return panel


def main():
    logo = Image.open(APP / "web" / "logo.png").convert("RGBA")
    OUT.mkdir(parents=True, exist_ok=True)
    for w, h in SIZES:
        path = OUT / f"side-{w}x{h}.png"
        side(w, h, logo).save(path)
        print(path.relative_to(APP))


if __name__ == "__main__":
    main()
