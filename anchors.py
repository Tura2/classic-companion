"""
Finds the game's windows by the picture of their title, the way you'd spot them: wherever a window
has been dragged, its title bar looks the same. OCR can glue a neighbor's edge onto a title and put
it a few pixels off, and every field read from that window then shifts with it; a picture match
lands on the exact pixel.

The titles are cut from the game at a 1200 px tall game area (assets/titles/) and shrunk to other
sizes. Where a shrunk title doesn't match, the app learns the title as the game draws it at that
size (cache/titles/<height>/) the first time OCR reads it cleanly.

Pictures are compared with normalized cross-correlation (numpy only): 1.0 is the same picture, and
it doesn't care how light or dark the area is.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image

MIN_SCORE = 0.75     # a title matches at least this well...
MIN_GAP = 0.25       # ...and this much better than anywhere else more than FAR px from it
FAR = 10
NEAR = 40            # how far around a window's last place (or where OCR saw it) is looked at first
# A big area (the whole game) is searched rough first: both pictures shrunk COARSE times, then only
# around the PEAKS best spots of that at full size. ~300 ms a title over a 1920 x 1200 game before.
COARSE = 3
PEAKS = 5
BIG = 300_000        # an area of more pixels than this is searched rough first


def _fast_len(n):
    """The smallest size >= n made of 2s, 3s and 5s only: the FFT is many times quicker there
    (a 1214 px tall game area is 2 x 607, and 607 is prime)."""
    best = 2 * n
    p5 = 1
    while p5 < best:
        p35 = p5
        while p35 < best:
            p = p35
            while p < n:
                p *= 2
            best = min(best, p)
            p35 *= 3
        p5 *= 5
    return best


def ncc(img, tpl):
    """How well `tpl` matches at each place in `img` (normalized cross-correlation, from -1 to 1),
    one value per top-left corner the template fits at. Flat areas, where nothing can match, are 0."""
    img, tpl = np.asarray(img), np.asarray(tpl)
    (H, W), (th, tw) = img.shape, tpl.shape
    if H < th or W < tw:
        return np.zeros((0, 0))
    t = tpl - tpl.mean()
    tn = np.sqrt((t.astype(np.float64) ** 2).sum())
    fh, fw = _fast_len(H + th - 1), _fast_len(W + tw - 1)
    num = np.fft.irfft2(np.fft.rfft2(img, (fh, fw)) * np.fft.rfft2(t[::-1, ::-1], (fh, fw)), (fh, fw))
    num = num[th - 1:H, tw - 1:W]
    a = img.astype(np.float64)

    def window_sums(v):
        c = np.pad(v, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
        return c[th:, tw:] - c[:-th, tw:] - c[th:, :-tw] + c[:-th, :-tw]
    var = window_sums(a * a) - window_sums(a) ** 2 / (th * tw)
    den = np.sqrt(np.maximum(var, 0)) * tn
    flat = var < 1e-3 * th * tw
    return np.where(flat | (tn == 0), 0.0, num / np.where(flat, 1, den))


def _shrink(a, k):
    """The picture k times smaller, each k x k block averaged."""
    h, w = a.shape[0] // k * k, a.shape[1] // k * k
    return a[:h, :w].reshape(h // k, k, w // k, k).mean((1, 3))


def _gray(img):
    return np.asarray(img.convert("L"), dtype=np.float32)


class Titles:
    """The window titles, and where each was last seen."""

    def __init__(self, app_dir, res_dir=None):
        src = Path(res_dir or app_dir) / "assets" / "titles"
        self.boxes = json.loads((src / "boxes.json").read_text("utf-8"))
        self.base = {n: Image.open(src / f"{n}.png").convert("L") for n in self.boxes}
        self.learned = Path(app_dir) / "cache" / "titles"
        self.last = {}        # title -> its picture's top-left corner, when last found
        self.scores = {}      # title -> how well it matched, in the last find
        self._sized = {}      # (title, game height) -> the picture to look for

    def _offsets(self, name, s):
        """(dx, dy) from the title picture's corner to the OCR line's, and the line's (w, h)."""
        b = self.boxes[name]
        (lx, ly, lw, lh), (cl, ct, _, _) = b["line"], b["cut"]
        return (lx - cl) * s, (ly - ct) * s, lw * s, lh * s

    def template(self, name, height, s):
        key = (name, height)
        if key not in self._sized:
            path = self.learned / str(height) / f"{name}.png"
            if path.exists():
                pic = Image.open(path).convert("L")
            else:
                base = self.base[name]
                pic = base.resize((max(1, round(base.width * s)), max(1, round(base.height * s))), Image.BOX)
            self._sized[key] = np.asarray(pic, dtype=np.float32)
        return self._sized[key]

    @staticmethod
    def _search(g, tpl, box):
        """(x, y, score) of the best match inside box (left, top, right, bottom), or None. It has to
        match MIN_SCORE well, and MIN_GAP better than anywhere else more than FAR px away."""
        l, t, r, b = (int(round(v)) for v in box)
        l, t, r, b = max(0, l), max(0, t), min(g.shape[1], r), min(g.shape[0], b)
        if (r - l) * (b - t) > BIG and min(tpl.shape) >= 2 * COARSE:
            return Titles._rough_first(g, tpl, (l, t, r, b))
        score = ncc(g[t:b, l:r], tpl)
        if score.size == 0:
            return None
        y, x = np.unravel_index(int(np.argmax(score)), score.shape)
        best = float(score[y, x])
        yy, xx = np.ogrid[:score.shape[0], :score.shape[1]]
        far = (np.abs(yy - y) > FAR) | (np.abs(xx - x) > FAR)
        second = float(score[far].max()) if far.any() else -1.0
        if best < MIN_SCORE or best - second < MIN_GAP:
            return None
        return l + int(x), t + int(y), best

    @staticmethod
    def _rough_first(g, tpl, box):
        """_search over a big area: the PEAKS best spots on both pictures shrunk COARSE times, each
        then matched at full size around it. The runner-up the gap is measured against is the best
        of the other spots (a window's title has no near twin elsewhere that the rough look misses)."""
        l, t, r, b = box
        k = COARSE
        score = ncc(_shrink(g[t:b, l:r], k), _shrink(tpl, k))
        if score.size == 0:
            return None
        spots, score = [], score.copy()
        gap = FAR // k + 1
        for _ in range(PEAKS):
            y, x = np.unravel_index(int(np.argmax(score)), score.shape)
            if score[y, x] <= 0:
                break
            spots.append((t + y * k, l + x * k))
            score[max(0, y - gap):y + gap + 1, max(0, x - gap):x + gap + 1] = -2
        th, tw = tpl.shape
        fine = []
        for y0, x0 in spots:
            sub = ncc(g[max(0, y0 - k - 1):y0 + th + k + 1, max(0, x0 - k - 1):x0 + tw + k + 1], tpl)
            if sub.size:
                yy, xx = np.unravel_index(int(np.argmax(sub)), sub.shape)
                fine.append((float(sub[yy, xx]), max(0, x0 - k - 1) + int(xx), max(0, y0 - k - 1) + int(yy)))
        if not fine:
            return None
        best, x, y = max(fine)
        second = max((f[0] for f in fine if abs(f[1] - x) > FAR or abs(f[2] - y) > FAR), default=-1.0)
        if best < MIN_SCORE or best - second < MIN_GAP:
            return None
        return x, y, best

    def find(self, frame, s, hints=None, full=None, names=None):
        """{title: (text, x, y, w, h)}, in the shape of an OCR line, for each title found in the frame.
        Each is looked for around its last place and around where OCR saw it (`hints`: title -> OCR
        line); the whole frame is searched only for titles in `full` (None: every title). `names`
        limits the look to those titles; the others keep their last place."""
        g = _gray(frame)
        out, self.scores = {}, {}
        for name, b in self.boxes.items():
            if names is not None and name not in names:
                continue
            tpl = self.template(name, frame.height, s)
            th, tw = tpl.shape
            dx, dy, lw, lh = self._offsets(name, s)
            spots = [self.last[name]] if name in self.last else []
            if hints and name in hints:
                spots.append((hints[name][1] - dx, hints[name][2] - dy))
            hit = None
            for x0, y0 in spots:
                hit = self._search(g, tpl, (x0 - NEAR, y0 - NEAR, x0 + tw + NEAR, y0 + th + NEAR))
                if hit:
                    break
            if hit is None and (full is None or name in full):
                hit = self._search(g, tpl, (0, 0, g.shape[1], g.shape[0]))
            if hit is None:
                self.last.pop(name, None)
                continue
            x, y, self.scores[name] = hit
            self.last[name] = (x, y)
            out[name] = (b["text"], x + dx, y + dy, lw, lh)
        return out

    def learn(self, frame, name, line):
        """Keep the title as the game draws it at this frame's height, cut around an OCR line that
        read it cleanly; from now on it's what's looked for at this height."""
        s = frame.height / 1200
        dx, dy, _, _ = self._offsets(name, s)
        cl, ct, cr, cb = self.boxes[name]["cut"]
        left, top = round(line[1] - dx), round(line[2] - dy)
        box = (left, top, left + round((cr - cl) * s), top + round((cb - ct) * s))
        path = self.learned / str(frame.height) / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.convert("L").crop(box).save(path)
        self._sized.pop((name, frame.height), None)
        return path
