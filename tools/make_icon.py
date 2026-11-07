"""Build web/logo.ico from web/logo.png, sharp at every size Windows asks for.

The 256 px logo is a leaf and a knife on a rounded tile with a wide border. Shrunk as a whole to
the taskbar's 30-40 px, the art came out tiny and smudged, and Windows stretched the nearest frame
to its size (blurry). So the small frames here are drawn again: a tile with a 1 px border, the art
cropped and filling it, shrunk once and sharpened a little. Every size Windows uses at 100-200 %
scaling is in the file, so it never has to stretch one.

Usage: python -I tools/make_icon.py   (from the companion folder)
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC, OUT = ROOT / "web" / "logo.png", ROOT / "web" / "logo.ico"
SIZES = (16, 20, 24, 28, 30, 32, 36, 40, 48, 56, 60, 64, 72, 80, 96, 128, 256)
FILL, RING, EDGE = (37, 46, 63, 255), (46, 58, 80, 255), (70, 83, 108, 255)
BIG = 96            # from this size up, the original tile is sharp enough as it is


def near(p, q, d=10):
    return all(abs(a - b) <= d for a, b in zip(p, q))


def art_of(src):
    """The leaf and knife alone, on transparency, cropped to them."""
    art = src.copy()
    px = art.load()
    w, h = art.size
    for y in range(h):
        for x in range(w):
            p = px[x, y]
            if p[3] < 200 or near(p, FILL) or near(p, RING) or near(p, EDGE):
                px[x, y] = (0, 0, 0, 0)
    return art.crop(art.getbbox())


def small(art, n):
    """A tile of n px: 1 px border, the art filling about 86 % of it."""
    k = 8                                   # draw big, shrink once: smooth tile corners
    tile = Image.new("RGBA", (n * k, n * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    r = max(2, round(n * 0.22)) * k
    d.rounded_rectangle((0, 0, n * k - 1, n * k - 1), r, fill=EDGE)
    d.rounded_rectangle((k, k, n * k - 1 - k, n * k - 1 - k), r - k, fill=FILL)
    tile = tile.resize((n, n), Image.LANCZOS)
    room = round(n * 0.86)
    a = art.copy()
    a.thumbnail((room, room), Image.LANCZOS)
    a = a.filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=0))
    tile.alpha_composite(a, ((n - a.width) // 2, (n - a.height) // 2))
    return tile


def main():
    src = Image.open(SRC).convert("RGBA")
    art = art_of(src)
    frames = [small(art, n) if n < BIG else src.resize((n, n), Image.LANCZOS) for n in SIZES]
    big = frames[-1]
    big.save(OUT, format="ICO", sizes=[(n, n) for n in SIZES], append_images=frames[:-1])
    print(OUT, "sizes", SIZES)


if __name__ == "__main__":
    main()
