"""Build assets/corner_font.json: the font of the game's bottom-right corner lines ("You received EXP
(+46)", "Wild Boar Tooth x1 earned. (Etc)"), which notices.py reads.

The game draws those lines in Arial 12 px with Windows' GDI, not smoothed (checked 2026-11-14: every
pixel of a line un-stretched to the game's own size matches GDI's drawing, see native.py), so each
character is a fixed little picture and a line is those pictures side by side, each moved on by its
width (GDI adds no kerning). This draws each character once and keeps its picture and width.

Windows only (it uses GDI). Run from the app folder:  python -I tools/make_corner_font.py
"""
import ctypes
import ctypes.wintypes as w
import json
import sys
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parent.parent
OUT = APP / "assets" / "corner_font.json"
FACE, PX = "Arial", 12
CHARS = [chr(i) for i in range(32, 127)] + [chr(i) for i in range(160, 256)]
W, H, PAD = 600, 24, 8

gdi = ctypes.windll.gdi32
gdi.CreateCompatibleDC.restype, gdi.CreateCompatibleDC.argtypes = w.HDC, [w.HDC]
gdi.CreateFontW.restype = w.HFONT
gdi.CreateFontW.argtypes = [ctypes.c_int] * 5 + [w.DWORD] * 8 + [w.LPCWSTR]
gdi.CreateDIBSection.restype = w.HBITMAP
gdi.CreateDIBSection.argtypes = [w.HDC, ctypes.c_void_p, w.UINT, ctypes.POINTER(ctypes.c_void_p), w.HANDLE, w.DWORD]
gdi.SelectObject.restype, gdi.SelectObject.argtypes = w.HGDIOBJ, [w.HDC, w.HGDIOBJ]
gdi.TextOutW.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int, w.LPCWSTR, ctypes.c_int]
gdi.SetTextColor.argtypes = gdi.SetBkColor.argtypes = [w.HDC, w.DWORD]
gdi.GetTextExtentPoint32W.argtypes = [w.HDC, w.LPCWSTR, ctypes.c_int, ctypes.c_void_p]
gdi.GetTextMetricsW.argtypes = [w.HDC, ctypes.c_void_p]


class BMIH(ctypes.Structure):
    _fields_ = [("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG), ("biPlanes", w.WORD),
                ("biBitCount", w.WORD), ("biCompression", w.DWORD), ("biSizeImage", w.DWORD),
                ("biXPelsPerMeter", w.LONG), ("biYPelsPerMeter", w.LONG), ("biClrUsed", w.DWORD),
                ("biClrImportant", w.DWORD)]


class TEXTMETRIC(ctypes.Structure):
    _fields_ = [(n, w.LONG) for n in ("tmHeight", "tmAscent", "tmDescent", "tmInternalLeading", "tmExternalLeading",
                                       "tmAveCharWidth", "tmMaxCharWidth", "tmWeight", "tmOverhang",
                                       "tmDigitizedAspectX", "tmDigitizedAspectY")] + \
               [(n, ctypes.c_wchar) for n in ("tmFirstChar", "tmLastChar", "tmDefaultChar", "tmBreakChar")] + \
               [(n, ctypes.c_byte) for n in ("tmItalic", "tmUnderlined", "tmStruckOut", "tmPitchAndFamily", "tmCharSet")]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", w.LONG), ("cy", w.LONG)]


class Gdi:
    def __init__(self):
        self.dc = gdi.CreateCompatibleDC(None)
        bi = BMIH(ctypes.sizeof(BMIH), W, -H, 1, 32, 0, 0, 0, 0, 0, 0)
        self.bits = ctypes.c_void_p()
        gdi.SelectObject(self.dc, gdi.CreateDIBSection(self.dc, ctypes.byref(bi), 0, ctypes.byref(self.bits), None, 0))
        # height -PX: a 12 px em; quality 3: NONANTIALIASED_QUALITY
        gdi.SelectObject(self.dc, gdi.CreateFontW(-PX, 0, 0, 0, 400, 0, 0, 0, 0, 0, 0, 3, 0, FACE))
        gdi.SetTextColor(self.dc, 0xFFFFFF)
        gdi.SetBkColor(self.dc, 0)
        self.tm = TEXTMETRIC()
        gdi.GetTextMetricsW(self.dc, ctypes.byref(self.tm))

    def draw(self, text, x=PAD):
        ctypes.memset(self.bits, 0, W * H * 4)
        gdi.TextOutW(self.dc, x, 0, text, len(text))
        a = np.ctypeslib.as_array((ctypes.c_uint8 * (W * H * 4)).from_address(self.bits.value)).reshape(H, W, 4)
        return a[: self.tm.tmHeight, :, 0] > 127

    def width(self, text):
        s = SIZE()
        gdi.GetTextExtentPoint32W(self.dc, text, len(text), ctypes.byref(s))
        return s.cx


def build():
    g = Gdi()
    glyphs = {}
    for c in CHARS:
        m = g.draw(c)
        cols = np.nonzero(m.any(0))[0]
        x0, x1 = (int(cols.min()), int(cols.max()) + 1) if len(cols) else (PAD, PAD)
        glyphs[c] = [g.width(c), x0 - PAD, ["".join("#" if v else "." for v in row) for row in m[:, x0:x1]]]
    return g, {"face": FACE, "px": PX, "height": g.tm.tmHeight, "glyphs": glyphs}


def check(g, font):
    """Lines put together from the glyphs are exactly what GDI draws for the whole line."""
    import random
    import notices
    f = notices.Font(font)
    random.seed(1)
    tests = ["You received EXP (+46)", "Wild Boar Tooth x1 earned. (Etc)", "You have gained mesos (+1,059)"]
    tests += ["".join(random.choice(CHARS) for _ in range(30)) for _ in range(300)]
    bad = 0
    for t in tests:
        want = g.draw(t)
        got = np.zeros_like(want)
        m = f.mask(t, pad=PAD)
        got[:, :m.shape[1]] = m[:, :want.shape[1]]
        if not (want == got).all() or g.width(t) != f.width(t):
            bad += 1
    return bad, len(tests)


if __name__ == "__main__":
    sys.path.insert(0, str(APP))
    sys.path.insert(0, str(APP / "app"))
    gd, font = build()
    OUT.write_text(json.dumps(font, ensure_ascii=False, separators=(",", ":")), "utf-8")
    bad, n = check(gd, font)
    print(f"wrote {OUT.name}: {len(font['glyphs'])} characters, {font['height']} px tall; "
          f"{n - bad} of {n} test lines put together exactly as GDI draws them")
