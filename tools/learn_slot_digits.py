"""Build the slot-count digit templates (slotdigits.py) from the game's own digit pictures
(UI/Basic.img/ItemNo/0-9, 8 x 11 px, via maplestory.io), and check them on the inventory samples whose
counts are known. Run from the app folder:  python -I tools/learn_slot_digits.py [--write]

A digit is drawn 1.5625 times as big at a 1200 px tall game. Each template pixel is the class
(slotdigits.DARK outline / LIGHT fill) the digit has there whether it's scaled sharp or smooth; where
those disagree (its edges) or the picture is see-through, it's "don't care"."""
import base64
import io
import json
import sys
from pathlib import Path

import numpy as np
import requests
from PIL import Image

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
import anchors  # noqa: E402
import invgrid  # noqa: E402
import slotdigits  # noqa: E402

URL = "https://maplestory.io/api/wz/GMS/83/UI/Basic.img/ItemNo/{d}"
SCALE = 1.5625
CASES = APP / "samples" / "cases"
# counts read off the sample pictures by eye, slot by slot (None: empty)
COUNTS = {
    "inventory_use": [572, 800, 800, 800, 800, 800, 800, 800, 800, 225, 65, 92, 7, 3, 80, 5, 54, 8, 4, 7, 4, 4, 6, 2, 1,
                      65, 20, 22, None, None],
    "inventory_etc": [89, 29, 31, 1, 133, 96, 25, 35, 110, 84, 16, 3, 70, 60, 4, 200, 18, 24, 200, 64, 1, 1, 2, 1, 1,
                      36, 2, None, None, None],
}


def sprite(d):
    r = requests.get(URL.format(d=d), timeout=15)
    r.raise_for_status()
    return Image.open(io.BytesIO(base64.b64decode(r.json()["value"]))).convert("RGBA")


def template(im):
    w, h = round(im.width * SCALE), round(im.height * SCALE)
    out = []
    for resample in (Image.NEAREST, Image.BILINEAR):
        a = np.asarray(im.resize((w, h), resample), dtype=int)
        cls = slotdigits.classes(Image.fromarray(a[..., :3].astype(np.uint8)))
        cls[a[..., 3] < 200] = 0                  # see-through: the icon behind
        out.append(cls)
    return np.where(out[0] == out[1], out[0], 0).astype(np.uint8)


def slot_pictures(case):
    f = Image.open(CASES / f"{case}.png").convert("RGB")
    t = anchors.Titles(APP, res_dir=APP)
    title = t.find(f, 1.0, None, {"inventory"})["inventory"]
    x0, y0, _, _ = invgrid.grid_box(title, 1.0)
    out = []
    for i in range(30):
        r, c = divmod(i, invgrid.COLS)
        x, y = x0 + round(invgrid.STEP_X * c), y0 + round(invgrid.STEP_Y * r)
        out.append(f.crop((x, y, x + invgrid.SLOT, y + invgrid.SLOT)))
    return out


def check(digits):
    ok = bad = 0
    for case, counts in COUNTS.items():
        for i, (pic, want) in enumerate(zip(slot_pictures(case), counts)):
            got = digits.read(pic)
            if got == want:
                ok += 1
            else:
                bad += 1
                print(f"  {case} slot {i}: read {got}, is {want}")
    return ok, bad


def real_templates(guides):
    """Templates cut from the samples' own pixels: each known count's digits located with the sprite
    templates (guides), the game's 17 x w window cut there; a pixel kept where most samples of the
    digit agree on it and the sprite doesn't say otherwise."""
    cuts = {}
    for case, counts in COUNTS.items():
        for pic, n in zip(slot_pictures(case), counts):
            if n is None:
                continue
            cls = slotdigits.band(pic)
            x = 0
            for ch in str(n):
                g = guides[ch]
                h, w = g.shape
                best = max((slotdigits.score(cls[y:y + h], g, xx), xx, y)
                           for xx in range(x, x + 6) for y in range(0, cls.shape[0] - h + 1))
                _, bx, by = best
                win = cls[by:by + h, bx:bx + w]
                if win.shape == g.shape:
                    cuts.setdefault(ch, []).append(win)
                x = bx + w - 1
    out = {}
    for ch, wins in cuts.items():
        g = guides[ch]
        stack = np.stack(wins)
        votes = [(stack == k).sum(0) for k in (0, slotdigits.DARK, slotdigits.LIGHT)]
        top = np.argmax(np.stack(votes), 0).astype(np.uint8)
        sure = np.max(np.stack(votes), 0) >= max(1, 0.75 * len(wins))
        keep = sure & (top > 0) & ((g == 0) | (g == top))
        out[ch] = np.where(keep, top, 0).astype(np.uint8)
    return out, {ch: len(w) for ch, w in cuts.items()}


if __name__ == "__main__":
    guides = {str(d): template(sprite(d)) for d in range(10)}
    tpls, n = real_templates(guides)
    print("samples per digit:", n)
    for d, t in tpls.items():
        print(d, t.shape, "care", int((t > 0).sum()))
    tmp = APP / "cache" / "slot_digits.try.json"
    tmp.write_text(json.dumps({d: t.tolist() for d, t in tpls.items()}), "utf-8")
    ok, bad = check(slotdigits.Digits(tmp))
    print(f"known counts: {ok} right, {bad} wrong")
    if "--write" in sys.argv and bad == 0:
        slotdigits.FILE.write_text(json.dumps({d: t.tolist() for d, t in tpls.items()}), "utf-8")
        print("wrote", slotdigits.FILE)
