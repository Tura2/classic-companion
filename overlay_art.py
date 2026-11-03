"""
How the on-game windows look: the price labels beside a player shop, the route strip (with the
quest guide's step) by the mini map, and the prices under an item's tooltip.

Drawn with Pillow so text and rounded corners come out smooth, then shown in the see-through
overlay windows (sniper.py). Pure functions, data in and picture out, so a look can be checked
without the game running. Pixels exactly KEY are see-through; everything else covers the game.
"""
import ctypes
import math
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

KEY = (1, 2, 3)        # the overlay windows' see-through color (sniper.KEY)
SS = 3                 # shapes are drawn 3x larger, then scaled down, for smooth edges

CARD = (15, 22, 33)    # dark glass that reads over bright and dark maps alike
RIM = (5, 8, 13)       # 1 px dark rim, so cards stand out on bright backgrounds
EDGE = (46, 63, 88)
TEXT = (238, 243, 250)
MUTED = (152, 166, 186)
FAINT = (104, 120, 142)
BLUE = (77, 163, 255)
GREEN = (52, 226, 139)
AMBER = (255, 194, 75)
PURPLE = (186, 138, 255)
TONES = {"snipe": GREEN, "npc": (64, 214, 232), "fair": MUTED, "pricey": AMBER, "over": (255, 107, 91),
         "check": AMBER, "split": AMBER, "info": MUTED}
# Each price source keeps its own color on the label, the same as in the dashboard, so one site's
# number is never taken for the other's.
SOURCE_COLORS = {"MSC": BLUE, "Cozy": PURPLE}
# What a tag becomes when the label has no room for the full word
SHORT_TAGS = {"SOURCES DIFFER": "DIFFER", "OVERPRICED": "OVER", "CHECK PRICE": "CHECK", "NPC FLIP": "NPC",
              "COZY ONLY": "COZY"}


FONT_DIR = Path("C:/Windows/Fonts")
FONT_FILES = {"regular": "segoeui.ttf", "semibold": "seguisb.ttf", "bold": "segoeuib.ttf"}


@lru_cache(maxsize=64)
def font(px, weight="regular"):
    size = max(6, round(px))
    try:
        return ImageFont.truetype(str(FONT_DIR / FONT_FILES[weight]), size)
    except OSError:
        return ImageFont.load_default(size)


def dpi_scale(hwnd=None):
    """Windows display scale of the game's monitor: 1.0 at 100%, 1.25 at 125%. The monitor's,
    not the window's, because an older game is stretched by Windows to that scale."""
    if sys.platform != "win32":
        return 1.0
    try:
        u = ctypes.windll.user32
        u.MonitorFromWindow.restype = ctypes.c_void_p
        mon = u.MonitorFromWindow(ctypes.c_void_p(hwnd), 2) if hwnd else None   # 2 = nearest monitor
        x, y = ctypes.c_uint(), ctypes.c_uint()
        if mon and ctypes.windll.shcore.GetDpiForMonitor(ctypes.c_void_p(mon), 0, ctypes.byref(x), ctypes.byref(y)) == 0:
            return max(1.0, x.value / 96)
        return max(1.0, u.GetDpiForSystem() / 96)
    except Exception:
        return 1.0


def fmt(n):
    return f"{int(round(n)):,}"


def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def fit(text, f, width):
    """`text`, cut with an ellipsis to fit `width` pixels."""
    if f.getlength(text) <= width:
        return text
    while text and f.getlength(text + "…") > width:
        text = text[:-1]
    return text.rstrip() + "…"


def spaced(draw, xy, text, f, fill, spacing):
    """Draw letter-spaced caps (Pillow has no tracking); returns the width used."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=f, fill=fill, anchor="lm")
        x += f.getlength(ch) + spacing
    return x - xy[0] - spacing


def spaced_len(text, f, spacing):
    return sum(f.getlength(ch) for ch in text) + spacing * max(0, len(text) - 1)


def card(size, radius, notch=None, notch_w=0):
    """A dark rounded card (with an optional pointer) on a see-through background, drawn large
    and scaled down so its edges are smooth. notch: "left" / "right" / None."""
    w, h = size
    big = Image.new("RGB", (w * SS, h * SS), KEY)
    d = ImageDraw.Draw(big)
    x0 = notch_w if notch == "left" else 0
    x1 = w - (notch_w if notch == "right" else 0)
    box = [x0 * SS, 0, x1 * SS - 1, h * SS - 1]
    d.rounded_rectangle(box, radius * SS, fill=RIM)
    d.rounded_rectangle([box[0] + SS, SS, box[2] - SS, box[3] - SS], radius * SS - SS, fill=CARD, outline=EDGE, width=SS)
    if notch:
        cy, half = h * SS / 2, min(h * SS / 2 - radius * SS / 2, notch_w * SS)
        tip, base = (0, x0 * SS + 2 * SS) if notch == "left" else (w * SS - 1, x1 * SS - 2 * SS)
        d.polygon([(tip, cy), (base, cy - half - SS), (base, cy + half + SS)], fill=RIM)
        tip += SS if notch == "left" else -SS
        d.polygon([(tip, cy), (base + (SS if notch == "left" else -SS), cy - half),
                   (base + (SS if notch == "left" else -SS), cy + half)], fill=CARD)
    return big, d


# ---------------------------------------------------------------- shop labels
def shop_label(parts, verdict, scale=1.0, notch="left", max_w=None):
    """One price label beside a shop row: a colored verdict tag, then each source's price in that
    source's own color, so both numbers are readable at a glance and the tag says what they mean.

    parts: {"tag", "prices": [(source, number), ...], "note", "risk", "name"} (any but tag may be
    missing). No profit figure: the two prices side by side are the point, and the reader decides."""
    s = scale
    tone = TONES.get(verdict, MUTED)
    f_tag, f_small = font(10 * s, "bold"), font(11.5 * s, "bold")
    h, pad, gap = round(28 * s), round(9 * s), round(7 * s)
    notch_w = round(7 * s) if notch in ("left", "right") else 0
    track = 0.7 * s
    tag, named = parts["tag"], True

    # A price reads "Cozy 3,299": the source in its own color, the number in bright text. Short of
    # room, the source's name goes and the number itself takes the source's color.
    def price_w(p):
        return (f_small.getlength(p[0] + " ") if named else 0) + f_small.getlength(p[1])
    prices = [p for p in parts.get("prices") or [] if p[1]]
    extras = [(parts.get("note"), AMBER), (parts.get("risk"), AMBER), (parts.get("name"), FAINT)]
    extras = [e for e in extras if e[0]]

    def tag_w():
        return round(spaced_len(tag, f_tag, track) + 14 * s)

    def width():
        return (notch_w + pad + tag_w() + sum(gap + price_w(p) for p in prices)
                + sum(gap + f_small.getlength(t) for t, _ in extras) + pad)
    # Out of room: the item name, the risk word and the note go first, then the tag gets shorter,
    # then the sources' names, and only then the second price.
    while max_w and width() > max_w and extras:
        extras.pop()
    if max_w and width() > max_w:
        tag = SHORT_TAGS.get(tag, tag)
    if max_w and width() > max_w:
        named = False
    if max_w and width() > max_w and len(prices) > 1:
        prices.pop()
    w = math.ceil(width())

    big, d = card((w, h), round(8 * s), notch, notch_w)
    x = (notch_w if notch == "left" else 0) + pad
    chip_h = round(18 * s)
    d.rounded_rectangle([x * SS, (h - chip_h) * SS // 2, (x + tag_w()) * SS, (h + chip_h) * SS // 2],
                        5 * s * SS, fill=mix(CARD, tone, 0.2))
    img = big.reduce(SS)
    d = ImageDraw.Draw(img)
    cy = h / 2
    spaced(d, (x + 7 * s, cy), tag, f_tag, tone, track)
    x += tag_w()
    for source, num in prices:
        x += gap
        color = SOURCE_COLORS.get(source, MUTED)
        if named:
            d.text((x, cy), source + " ", font=f_small, fill=color, anchor="lm")
            x += f_small.getlength(source + " ")
        d.text((x, cy), num, font=f_small, fill=TEXT if named else color, anchor="lm")
        x += f_small.getlength(num)
    for text, color in extras:
        x += gap
        d.text((x, cy), text, font=f_small, fill=color, anchor="lm")
        x += f_small.getlength(text)
    return img


# ---------------------------------------------------------------- route strip and quest card
ANGLES = {"→": 0, "↘": 45, "↓": 90, "↙": 135, "←": 180, "↖": -135, "↑": -90, "↗": -45}


def _arrow(d, cx, cy, r, direction, fill):
    """A bold arrow in the direction the next portal is, diagonals included ("↗": right side, up high)."""
    angle = ANGLES.get(direction, -90)
    pts = [(-0.55, -0.15), (0.02, -0.15), (0.02, -0.45), (0.6, 0), (0.02, 0.45), (0.02, 0.15), (-0.55, 0.15)]
    a = math.radians(angle)
    d.polygon([(cx + r * (x * math.cos(a) - y * math.sin(a)), cy + r * (x * math.sin(a) + y * math.cos(a)))
               for x, y in pts], fill=fill)


def _check(d, cx, cy, r, fill, width):
    d.line([(cx - 0.42 * r, cy + 0.02 * r), (cx - 0.12 * r, cy + 0.32 * r), (cx + 0.45 * r, cy - 0.32 * r)],
           fill=fill, width=width, joint="curve")


def price_strip(prices, scale=1.0, width=None, note=None):
    """Each site's price for the item under the mouse, in that site's color, to hang under the game's
    item tooltip. prices: [(source, number), ...]; note: what an NPC pays, at the right. width: the
    tooltip's, in pixels; the strip grows past it rather than cut a number off."""
    s = scale
    f = font(12 * s, "bold")
    pad, gap = 10 * s, 14 * s
    shown = [(src, num) for src, num in prices if num] or [("", "No market price yet")]
    need = 2 * pad + sum(f.getlength((src + " " if src else "") + num) + gap for src, num in shown) \
        + (f.getlength(note) if note else -gap)
    w, h = math.ceil(max(width or 0, need)), round(30 * s)
    big, _ = card((w, h), round(7 * s))
    img = big.reduce(SS)
    d = ImageDraw.Draw(img)
    x, cy = pad, h / 2
    for src, num in shown:
        if src:
            d.text((x, cy), src + " ", font=f, fill=SOURCE_COLORS.get(src, MUTED), anchor="lm")
            x += f.getlength(src + " ")
        d.text((x, cy), num, font=f, fill=TEXT if src else MUTED, anchor="lm")
        x += f.getlength(num) + gap
    if note:
        d.text((w - pad, cy), note, font=f, fill=AMBER, anchor="rm")
    return img


STRIP_W = 250          # route strip width at 100% display scale, when it isn't sized to the mini map
SIDES = {"far left": "far left", "left side": "left", "middle": "in the middle", "right side": "right",
         "far right": "far right"}


def route_strip(nav, scale=1.0, width=None):
    """The route on the game, small: an arrow toward the portal to take (its side and height),
    where it leads, and one short bar per portal on the way with the hops left to the end. With a
    quest guide on, a line on top says what to do for the quest ("Hunt Stirge · Stranger's
    Request"); its counts are the game's own Quest Helper's business. As narrow as its words allow,
    and no wider than `width` (the mini map it sits under, in pixels), where long words get cut."""
    s = scale
    steps, i = nav["steps"], nav["i"]
    step, total = steps[i], max(1, len(steps) - 1)
    arrived = bool(step.get("arrived"))
    if arrived:
        line1, line2 = "You're there", (f"Find {step['npc']['name']}" if step.get("npc") else step["name"])
    else:
        hint = step["hint"]
        line1 = f"Portal {SIDES.get(hint['side'], hint['side'])}" + (f", {hint['height']}" if hint.get("height") else "")
        line2 = f"to {step['to']['name']}"
    quest = nav.get("quest")
    goal, qname = (quest.get("goal") or "", quest.get("name") or "") if quest else ("", "")
    r, pad = 16 * s, 10 * s
    tx = pad + 2 * r + pad
    f_main, f_sub, f_hop = font(13 * s, "bold"), font(11 * s), font(9.5 * s, "bold")
    f_goal = font(12 * s, "bold")
    left = 0 if arrived else total - i
    label = f"arrived at {nav['to']['name']}" if arrived else f"{left} hop{'s' if left != 1 else ''} to {nav['to']['name']}"
    # as wide as its words need, but no wider than the mini map it hangs under
    need = max(tx + max(f_main.getlength(line1), f_sub.getlength(line2),
                        f_hop.getlength(label) + 8 * s + total * 6 * s) + pad,
               2 * pad + f_goal.getlength(goal) + (f_sub.getlength(f"  ·  {qname}") if qname else 0))
    qh = round(22 * s) if goal else 0      # the quest's line, over the route's
    w = math.ceil(max(STRIP_W * s, need))
    w, h = min(w, math.ceil(width)) if width else w, round(54 * s) + qh
    label = fit(label, f_hop, (w - tx - pad) * 0.7)
    big, d = card((w, h), round(8 * s))
    if goal:
        d.line([(pad * SS, (qh + 1 * s) * SS), ((w - pad) * SS, (qh + 1 * s) * SS)], fill=EDGE, width=SS)
    cy = qh + round(54 * s) / 2
    tone = GREEN if arrived else BLUE
    d.ellipse([pad * SS, (cy - r) * SS, (pad + 2 * r) * SS, (cy + r) * SS], fill=tone)
    if arrived:
        _check(d, (pad + r) * SS, cy * SS, (r - 3 * s) * SS, CARD, round(4 * s * SS))
    else:
        _arrow(d, (pad + r) * SS, cy * SS, (r - 3 * s) * SS, step["hint"]["arrow"], CARD)
    # the bars share the bottom line with the label, however many hops the route has
    room = w - tx - pad - f_hop.getlength(label) - 8 * s
    seg = max(3.0, min(12.0, (room / s + 3) / total - 3))
    for k in range(total if total > 1 else 0):
        color = tone if arrived or k < i else (TEXT if k == i else EDGE)
        x0 = tx + k * (seg + 3) * s
        d.rounded_rectangle([x0 * SS, (h - 12 * s) * SS, (x0 + seg * s) * SS, (h - 8 * s) * SS], 2 * s * SS, fill=color)
    img = big.reduce(SS)
    d = ImageDraw.Draw(img)
    if goal:
        goal = fit(goal, f_goal, w - 2 * pad)
        d.text((pad, qh / 2 + 1 * s), goal, font=f_goal, fill=AMBER, anchor="lm")
        x = pad + f_goal.getlength(goal)
        if qname and w - pad - x > 40 * s:
            d.text((x, qh / 2 + 1 * s), fit(f"  ·  {qname}", f_sub, w - pad - x), font=f_sub, fill=MUTED, anchor="lm")
    room = w - tx - pad
    d.text((tx, qh + 14 * s), fit(line1, f_main, room), font=f_main, fill=GREEN if arrived else TEXT, anchor="lm")
    d.text((tx, qh + 30 * s), fit(line2, f_sub, room), font=f_sub, fill=MUTED, anchor="lm")
    d.text((w - pad, h - 10 * s), label, font=f_hop, fill=FAINT, anchor="rm")
    return img
