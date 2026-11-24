"""Draw the twenty dish illustrations for the student menu.

One set, one style: a warm cream ground, a single soft shadow, and food
built from flat shapes with the shadow doing the depth. Every dish is drawn
from its own recipe below, so the set reads as one hand rather than twenty
cliparts.

The artwork is written to static/img/dishes/<slug>.svg.
"""

from __future__ import annotations

import math
import os
import random

OUT = r"D:\Projects\MessForecast\static\img\dishes"

# --- the palette the food is drawn from -------------------------------------
GRAVY = {
    "orange": "#e2731b",
    "red": "#bf4a2b",
    "yellow": "#f0b429",
    "dal": "#eabf57",
    "brown": "#8a5a2b",
    "green": "#6d9440",
    "cream": "#f6e6c4",
    "white": "#fbf6ea",
}
VESSEL = {
    "ceramic": ("#fffdf9", "#e8dccb"),
    "terracotta": ("#d98b5f", "#b96c43"),
    "steel": ("#e7e4de", "#c3beb6"),
    "clay": ("#c8713f", "#a4582c"),
    "glass": ("#f2f6f4", "#cdd8d4"),
    "leaf": ("#5f8f45", "#437030"),
}


def rnd(seed: str) -> random.Random:
    return random.Random(int(seed.encode("utf8").hex()[:8], 16))


def head(w=400, h=300, extra=""):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img">
<defs>
  <linearGradient id="cloth" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#fdf6ea"/>
    <stop offset="1" stop-color="#f4e7d2"/>
  </linearGradient>
  <radialGradient id="pool" cx="50%" cy="50%" r="50%">
    <stop offset="0" stop-color="#c9501f" stop-opacity="0.20"/>
    <stop offset="1" stop-color="#c9501f" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="sheen" cx="38%" cy="30%" r="72%">
    <stop offset="0" stop-color="#ffffff" stop-opacity="0.55"/>
    <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
  </radialGradient>
{extra}
</defs>
<rect width="{w}" height="{h}" fill="url(#cloth)"/>
<rect width="{w}" height="{h}" fill="url(#pool)"/>
<g transform="translate(200 150) scale(1.2) translate(-200 -150)">
"""


def weave(w=400, h=300, step=26):
    """A faint woven texture so the ground reads as cloth, not a flat fill."""
    out = []
    for x in range(step, w, step):
        out.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{h}" stroke="#c9b596" stroke-opacity="0.08" stroke-width="1"/>')
    for y in range(step, h, step):
        out.append(f'<line x1="0" y1="{y}" x2="{w}" y2="{y}" stroke="#c9b596" stroke-opacity="0.08" stroke-width="1"/>')
    return "\n".join(out)


def shadow(cx=200, cy=186, rx=104, ry=26):
    return (
        f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="#8a5a2b" opacity="0.13"/>'
        f'<ellipse cx="{cx}" cy="{cy + 3}" rx="{rx * 0.72:.0f}" ry="{ry * 0.66:.0f}" fill="#8a5a2b" opacity="0.10"/>'
    )


def bowl(cx=200, cy=140, rx=96, ry=34, depth=56, kind="ceramic"):
    """A wide bowl seen from slightly above, with its food surface inside."""
    base, edge = VESSEL[kind]
    body = (
        f"M {cx - rx} {cy} "
        f"C {cx - rx} {cy + depth * 1.55}, {cx - rx * 0.55:.0f} {cy + depth}, {cx} {cy + depth} "
        f"C {cx + rx * 0.55:.0f} {cy + depth}, {cx + rx} {cy + depth * 1.55:.0f}, {cx + rx} {cy} Z"
    )
    return f"""<g>
  <path d="{body}" fill="{base}"/>
  <path d="{body}" fill="{edge}" opacity="0.22"/>
  <ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{edge}"/>
  <ellipse cx="{cx}" cy="{cy}" rx="{rx - 7}" ry="{ry - 5}" fill="#fffdf9"/>
</g>"""


def plate(cx=200, cy=150, rx=112, ry=38, kind="ceramic", rim=16):
    base, edge = VESSEL[kind]
    return f"""<g>
  <ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{edge}"/>
  <ellipse cx="{cx}" cy="{cy - 3}" rx="{rx}" ry="{ry}" fill="{base}"/>
  <ellipse cx="{cx}" cy="{cy - 3}" rx="{rx - rim}" ry="{ry - rim * 0.42:.0f}" fill="{edge}" opacity="0.30"/>
  <ellipse cx="{cx}" cy="{cy - 3}" rx="{rx - rim - 6}" ry="{ry - rim * 0.42 - 4:.0f}" fill="{base}"/>
  <ellipse cx="{cx}" cy="{cy - 3}" rx="{rx}" ry="{ry}" fill="url(#sheen)"/>
</g>"""


def glass(cx=200, top=52, w=92, h=190):
    base, edge = VESSEL["glass"]
    return f"""<g>
  <path d="M {cx - w / 2} {top} L {cx - w / 2 + 8} {top + h} Q {cx} {top + h + 12} {cx + w / 2 - 8} {top + h} L {cx + w / 2} {top} Z"
        fill="{base}" opacity="0.85"/>
  <path d="M {cx - w / 2} {top} L {cx - w / 2 + 8} {top + h} Q {cx} {top + h + 12} {cx + w / 2 - 8} {top + h} L {cx + w / 2} {top} Z"
        fill="{edge}" opacity="0.18"/>
  <rect x="{cx - w / 2}" y="{top}" width="{w}" height="9" rx="4" fill="{edge}" opacity="0.45"/>
</g>"""


def leaf(cx=200, cy=155, rx=132, ry=62):
    base, edge = VESSEL["leaf"]
    return f"""<g>
  <path d="M {cx - rx} {cy} Q {cx} {cy - ry} {cx + rx} {cy} Q {cx} {cy + ry} {cx - rx} {cy} Z" fill="{base}"/>
  <path d="M {cx - rx} {cy} Q {cx} {cy - ry} {cx + rx} {cy} Q {cx} {cy + ry} {cx - rx} {cy} Z" fill="{edge}" opacity="0.20"/>
  <path d="M {cx - rx} {cy} L {cx + rx} {cy}" stroke="{edge}" stroke-width="2" opacity="0.5"/>
  <path d="M {cx - rx * 0.6} {cy - 22} L {cx + rx * 0.6} {cy + 22}" stroke="{edge}" stroke-width="1.2" opacity="0.28"/>
  <path d="M {cx - rx * 0.6} {cy + 22} L {cx + rx * 0.6} {cy - 22}" stroke="{edge}" stroke-width="1.2" opacity="0.28"/>
</g>"""


def curry_surface(cx=200, cy=140, rx=88, ry=30, colour=GRAVY["orange"]):
    """The gravy pooled in the bowl, drawn as a lens with a darker rim."""
    return (
        f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{colour}"/>'
        f'<ellipse cx="{cx}" cy="{cy - 2}" rx="{rx - 6}" ry="{ry - 4}" fill="#ffffff" opacity="0.16"/>'
    )


def chunks(cx, cy, rx, ry, count, colours, seed, size=13, kind="cube"):
    """Chunks of something sitting in gravy."""
    r = rnd(seed)
    out = []
    for _ in range(count):
        a = r.uniform(0, math.tau)
        d = r.uniform(0.15, 0.82)
        x = cx + math.cos(a) * rx * d
        y = cy + math.sin(a) * ry * d
        c = r.choice(colours)
        s = size * r.uniform(0.78, 1.22)
        rot = r.uniform(-40, 40)
        if kind == "cube":
            out.append(
                f'<rect x="{x - s / 2:.1f}" y="{y - s / 2:.1f}" width="{s:.1f}" height="{s:.1f}" rx="{s * 0.22:.1f}" '
                f'fill="{c}" transform="rotate({rot:.0f} {x:.1f} {y:.1f})"/>'
            )
        elif kind == "round":
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{s / 2:.1f}" fill="{c}"/>')
        elif kind == "floret":
            out.append(
                f'<g transform="translate({x:.1f} {y:.1f}) rotate({rot:.0f})">'
                f'<circle cx="0" cy="0" r="{s / 2:.1f}" fill="{c}"/>'
                f'<circle cx="{-s * 0.32:.1f}" cy="{-s * 0.2:.1f}" r="{s * 0.26:.1f}" fill="{c}"/>'
                f'<circle cx="{s * 0.3:.1f}" cy="{-s * 0.24:.1f}" r="{s * 0.24:.1f}" fill="{c}"/>'
                f'<circle cx="{s * 0.26:.1f}" cy="{s * 0.26:.1f}" r="{s * 0.22:.1f}" fill="{c}"/></g>'
            )
    return "\n".join(out)


def herb(cx, cy, rx, ry, count, seed, colour=GRAVY["green"]):
    r = rnd(seed)
    out = []
    for _ in range(count):
        a = r.uniform(0, math.tau)
        d = r.uniform(0.2, 0.85)
        x = cx + math.cos(a) * rx * d
        y = cy + math.sin(a) * ry * d
        s = r.uniform(3.2, 5.4)
        rot = r.uniform(0, 360)
        out.append(
            f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{s:.1f}" ry="{s * 0.55:.1f}" fill="{colour}" '
            f'transform="rotate({rot:.0f} {x:.1f} {y:.1f})" opacity="0.95"/>'
        )
    return "\n".join(out)


def ghee_dots(cx, cy, rx, ry, count, seed):
    r = rnd(seed)
    out = []
    for _ in range(count):
        a = r.uniform(0, math.tau)
        d = r.uniform(0.1, 0.8)
        x = cx + math.cos(a) * rx * d
        y = cy + math.sin(a) * ry * d
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r.uniform(2.4, 4.4):.1f}" fill="#f6c65a" opacity="0.9"/>')
    return "\n".join(out)


def steam(cx, top=54, n=3, spread=26, colour="#ffffff"):
    out = []
    for i in range(n):
        x = cx + (i - (n - 1) / 2) * spread
        out.append(
            f'<path d="M {x:.0f} {top} q -8 -14 0 -28 q 8 -14 0 -26" fill="none" stroke="{colour}" '
            f'stroke-width="3" stroke-linecap="round" opacity="0.45"/>'
        )
    return "\n".join(out)


def grains(cx, cy, rx, ry, count, seed, colours):
    """A mound of small grains: poha, upma, rice."""
    r = rnd(seed)
    out = []
    for _ in range(count):
        a = r.uniform(0, math.tau)
        d = math.sqrt(r.uniform(0, 1)) * 0.95
        x = cx + math.cos(a) * rx * d
        y = cy + math.sin(a) * ry * d * (1 - 0.25 * d)
        s = r.uniform(2.2, 4.4)
        out.append(
            f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{s:.1f}" ry="{s * 0.55:.1f}" '
            f'fill="{r.choice(colours)}" transform="rotate({r.uniform(0, 360):.0f} {x:.1f} {y:.1f})"/>'
        )
    return "\n".join(out)


def mound(cx, cy, rx, ry, colours, layers=5):
    """A soft heap of food."""
    out = []
    for i in range(layers):
        t = i / max(layers - 1, 1)
        out.append(
            f'<ellipse cx="{cx}" cy="{cy - 10 + i * 3}" rx="{rx * (1 - t * 0.45):.1f}" ry="{ry * (1 - t * 0.42):.1f}" '
            f'fill="{colours[i % len(colours)]}"/>'
        )
    return "\n".join(out)


def veg_piece(x, y, s, colour, rot=0):
    return (
        f'<rect x="{x - s / 2:.1f}" y="{y - s / 2:.1f}" width="{s:.1f}" height="{s:.1f}" rx="{s * 0.28:.1f}" '
        f'fill="{colour}" transform="rotate({rot} {x:.1f} {y:.1f})"/>'
    )


# ---------------------------------------------------------------------------
# The twenty dishes
# ---------------------------------------------------------------------------

def draw_aloo_gobi():
    s = head() + weave()
    s += shadow(200, 196, 96, 24)
    s += bowl(200, 138, 94, 33, 54)
    s += curry_surface(200, 138, 86, 29, GRAVY["yellow"])
    s += chunks(200, 136, 74, 24, 9, ["#f6e7c4", "#eecf92"], "aloo-gobi", 15, "cube")
    s += chunks(200, 136, 74, 24, 7, ["#fbf7ea"], "aloo-gobi-f", 17, "floret")
    s += herb(200, 136, 78, 24, 10, "aloo-gobi-h")
    s += ghee_dots(200, 136, 80, 25, 5, "aloo-gobi-g")
    return s + "</g></svg>"


def draw_chana_masala():
    s = head() + weave()
    s += shadow(200, 196, 96, 24)
    s += bowl(200, 138, 94, 33, 54)
    s += curry_surface(200, 138, 86, 29, GRAVY["red"])
    s += chunks(200, 136, 76, 25, 16, ["#d9a44c", "#c79038"], "chana", 12, "round")
    s += chunks(200, 136, 76, 25, 5, ["#8f3d22", "#7c331d"], "chana-b", 14, "cube")
    s += herb(200, 136, 78, 24, 9, "chana-h")
    return s + "</g></svg>"


def draw_chapati():
    s = head() + weave()
    s += shadow(200, 188, 108, 26)
    s += plate(200, 146, 116, 40, "steel", 14)
    s += '<g opacity="0.95">'
    s += f'<ellipse cx="200" cy="142" rx="82" ry="30" fill="#e8c68d"/>'
    s += f'<ellipse cx="200" cy="138" rx="82" ry="30" fill="#f0d5a4"/>'
    s += f'<ellipse cx="200" cy="132" rx="80" ry="29" fill="#f7e2ba"/>'
    s += '<ellipse cx="200" cy="132" rx="80" ry="29" fill="#d9a45f" opacity="0.10"/>'
    for i, (dx, dy, rr) in enumerate([(-24, -4, 26), (10, 2, 30), (-4, -8, 18), (30, -6, 14), (-34, 6, 12)]):
        s += f'<ellipse cx="{200 + dx}" cy="{132 + dy}" rx="{rr}" ry="{rr * 0.34:.0f}" fill="#d9a45f" opacity="0.22"/>'
    for i in range(16):
        x = 160 + (i * 13) % 84
        y = 120 + ((i * 7) % 24)
        s += f'<circle cx="{x}" cy="{y}" r="1.8" fill="#b8863f" opacity="0.35"/>'
    s += '</g>'
    return s + "</g></svg>"


def draw_chicken_curry():
    s = head() + weave()
    s += shadow(200, 198, 96, 24)
    s += bowl(200, 140, 92, 32, 56)
    s += curry_surface(200, 140, 84, 28, "#d9621c")
    s += chunks(200, 138, 74, 23, 8, ["#e8a45c", "#f0bb78"], "chicken", 20, "cube")
    s += chunks(200, 138, 74, 23, 6, ["#8c3f1c"], "chicken-b", 15, "cube")
    s += ghee_dots(200, 138, 78, 24, 6, "chicken-g")
    s += herb(200, 138, 78, 24, 6, "chicken-h")
    return s + "</g></svg>"


def draw_curd():
    s = head() + weave()
    s += shadow(200, 194, 78, 20)
    s += bowl(200, 142, 76, 27, 44, "clay")
    s += f'<ellipse cx="200" cy="142" rx="68" ry="23" fill="{GRAVY["white"]}"/>'
    s += f'<path d="M 172 138 q 16 -12 32 -3 q 14 8 26 -2" stroke="#e3d9c6" stroke-width="4" fill="none" stroke-linecap="round"/>'
    s += f'<ellipse cx="186" cy="136" rx="22" ry="6" fill="#ffffff" opacity="0.55"/>'
    return s + "</g></svg>"


def draw_dal_tadka():
    s = head() + weave()
    s += shadow(200, 198, 96, 24)
    s += bowl(200, 140, 92, 32, 56)
    s += curry_surface(200, 140, 84, 28, GRAVY["dal"])
    s += '<path d="M 150 142 q 22 -14 40 -2 q 20 13 42 -6 q 8 -6 16 -3" stroke="#d9a83f" stroke-width="7" fill="none" stroke-linecap="round" opacity="0.85"/>'
    s += ghee_dots(200, 138, 78, 24, 9, "dal-g")
    s += chunks(200, 136, 74, 22, 4, ["#8a4a1c"], "dal-c", 8, "cube")
    s += herb(200, 138, 78, 24, 7, "dal-h")
    return s + "</g></svg>"


def draw_fried_rice():
    s = head() + weave()
    s += shadow(200, 190, 108, 26)
    s += plate(200, 148, 112, 39, "ceramic", 15)
    s += mound(200, 140, 86, 30, ["#fdf3d8", "#f8e9c4", "#f2dfb2"], 4)
    s += grains(200, 136, 78, 25, 90, "rice", ["#fffaf0", "#f7e9c9", "#efd9ae", "#ffffff"])
    for i, (x, y, c) in enumerate([(160, 128, GRAVY["green"]), (232, 132, "#e07a2a"), (200, 150, GRAVY["green"]), (246, 146, "#d8531f")]):
        s += f'<circle cx="{x}" cy="{y}" r="5.4" fill="{c}"/>'
    s += herb(200, 134, 78, 24, 12, "friedrice-h")
    return s + "</g></svg>"


def draw_idli():
    s = head() + weave()
    s += shadow(200, 196, 118, 26)
    s += leaf(200, 168, 138, 58)
    s += '<ellipse cx="170" cy="150" rx="40" ry="24" fill="#f7f1e3"/>'
    s += '<ellipse cx="170" cy="146" rx="40" ry="24" fill="#fbf6ea"/>'
    s += '<ellipse cx="228" cy="142" rx="42" ry="25" fill="#f4ecda"/>'
    s += '<ellipse cx="228" cy="137" rx="42" ry="25" fill="#fbf6ea"/>'
    s += '<ellipse cx="200" cy="126" rx="43" ry="25" fill="#f2ead6"/>'
    s += '<ellipse cx="200" cy="121" rx="43" ry="25" fill="#fbf6ea"/>'
    s += '<ellipse cx="188" cy="116" rx="14" ry="8" fill="#ffffff" opacity="0.5"/>'
    s += f'<circle cx="292" cy="160" r="22" fill="{GRAVY["orange"]}"/>'
    s += f'<circle cx="292" cy="160" r="17" fill="#e8894f" opacity="0.7"/>'
    s += f'<circle cx="112" cy="158" r="18" fill="{GRAVY["white"]}"/>'
    s += f'<circle cx="112" cy="158" r="13" fill="#efe3cd" opacity="0.8"/>'
    return s + "</g></svg>"


def draw_khichdi():
    s = head() + weave()
    s += shadow(200, 194, 96, 24)
    s += bowl(200, 140, 92, 32, 54)
    s += curry_surface(200, 140, 84, 28, "#f2cf72")
    s += grains(200, 138, 78, 24, 70, "khichdi", ["#f7dd93", "#eecd72", "#fbe7ae"])
    s += ghee_dots(200, 136, 76, 23, 7, "khi-g")
    s += herb(200, 138, 78, 24, 8, "khi-h")
    return s + "</g></svg>"


def draw_mixed_veg():
    s = head() + weave()
    s += shadow(200, 198, 96, 24)
    s += bowl(200, 140, 92, 32, 56)
    s += curry_surface(200, 140, 84, 28, "#d97f2a")
    s += chunks(200, 138, 74, 23, 7, [GRAVY["green"], "#8bb04f"], "veg1", 14, "cube")
    s += chunks(200, 138, 74, 23, 6, ["#e2c34a", "#f0d76f"], "veg2", 12, "round")
    s += chunks(200, 138, 74, 23, 5, ["#d9573f"], "veg3", 13, "cube")
    s += herb(200, 138, 78, 24, 7, "veg-h")
    return s + "</g></svg>"


def draw_paneer_curry():
    s = head() + weave()
    s += shadow(200, 198, 96, 24)
    s += bowl(200, 140, 92, 32, 56)
    s += curry_surface(200, 140, 84, 28, "#e08a24")
    s += chunks(200, 138, 74, 23, 8, ["#f7e4bd", "#f0d49d"], "paneer", 22, "cube")
    s += chunks(200, 138, 74, 23, 6, ["#a8481f"], "paneer-b", 13, "cube")
    s += ghee_dots(200, 138, 78, 24, 5, "paneer-g")
    s += herb(200, 138, 78, 24, 7, "paneer-h")
    return s + "</g></svg>"


def draw_poha():
    s = head() + weave()
    s += shadow(200, 190, 108, 26)
    s += plate(200, 148, 112, 39, "steel", 14)
    s += mound(200, 140, 88, 30, ["#efd7a4", "#e6c78c"], 3)
    s += grains(200, 136, 80, 25, 100, "poha", ["#f6e3b8", "#eccf95", "#e3bd7d", "#fbf0d2"])
    for i in range(10):
        x = 150 + (i * 19) % 100
        y = 122 + ((i * 11) % 26)
        s += f'<circle cx="{x}" cy="{y}" r="3.2" fill="#b8763a" opacity="0.75"/>'
    s += herb(200, 134, 78, 24, 10, "poha-h")
    s += '<path d="M 288 146 a 20 20 0 0 1 26 -12 l -8 20 z" fill="#f2d64a"/>'
    s += '<path d="M 288 146 a 20 20 0 0 1 26 -12 l -8 20 z" fill="#ffffff" opacity="0.25"/>'
    return s + "</g></svg>"


def draw_raita():
    s = head() + weave()
    s += shadow(200, 194, 84, 21)
    s += bowl(200, 142, 82, 29, 48, "ceramic")
    s += f'<ellipse cx="200" cy="142" rx="73" ry="24" fill="#f4f6ec"/>'
    s += '<ellipse cx="200" cy="140" rx="73" ry="24" fill="#fbfcf6"/>'
    for i, (x, y, r) in enumerate([(176, 138, 11), (212, 144, 9), (232, 134, 8)]):
        s += f'<circle cx="{x}" cy="{y}" r="{r}" fill="#a8c47f" opacity="0.8"/>'
        s += f'<circle cx="{x}" cy="{y}" r="{r * 0.55:.0f}" fill="#c4d9a4" opacity="0.9"/>'
    s += herb(200, 140, 74, 23, 6, "raita-h", "#7fa64f")
    return s + "</g></svg>"


def draw_salad():
    s = head() + weave()
    s += shadow(200, 190, 100, 25)
    s += bowl(200, 142, 92, 32, 50, "glass")
    s += f'<ellipse cx="200" cy="142" rx="84" ry="28" fill="#eef3e4"/>'
    r = rnd("salad")
    for _ in range(46):
        a = r.uniform(0, math.tau)
        d = math.sqrt(r.uniform(0, 1)) * 0.9
        x = 200 + math.cos(a) * 76 * d
        y = 142 + math.sin(a) * 23 * d
        kind = r.choice(["green", "red", "white", "green"])
        col = {"green": "#79a94a", "red": "#d3503c", "white": "#f2f6ea"}[kind]
        s += f'<rect x="{x - 6:.1f}" y="{y - 4:.1f}" width="12" height="8" rx="3" fill="{col}" transform="rotate({r.uniform(0,360):.0f} {x:.1f} {y:.1f})"/>'
    for i, (x, y) in enumerate([(168, 132), (226, 136), (198, 152)]):
        s += f'<circle cx="{x}" cy="{y}" r="9" fill="#e0523f" opacity="0.92"/>'
        s += f'<circle cx="{x}" cy="{y}" r="5" fill="#f08a72" opacity="0.8"/>'
    return s + "</g></svg>"


def draw_sambar():
    s = head() + weave()
    s += shadow(200, 198, 96, 24)
    s += bowl(200, 140, 92, 32, 56)
    s += curry_surface(200, 140, 84, 28, "#d9701f")
    s += chunks(200, 138, 74, 23, 9, ["#e9b463", "#f0c67e"], "sambar", 12, "round")
    s += chunks(200, 138, 74, 23, 7, ["#8fae52", "#6f9440"], "sambar-b", 12, "cube")
    s += ghee_dots(200, 138, 78, 24, 6, "sambar-g")
    s += herb(200, 138, 78, 24, 8, "sambar-h")
    return s + "</g></svg>"


def draw_steamed_rice():
    s = head() + weave()
    s += shadow(200, 192, 108, 26)
    s += plate(200, 152, 112, 39, "ceramic", 15)
    s += '<ellipse cx="200" cy="138" rx="88" ry="32" fill="#f4eddd"/>'
    s += '<ellipse cx="200" cy="132" rx="80" ry="30" fill="#faf5ea"/>'
    s += '<ellipse cx="200" cy="124" rx="66" ry="26" fill="#fdfaf2"/>'
    s += '<ellipse cx="200" cy="115" rx="46" ry="19" fill="#fffdf7"/>'
    s += grains(200, 132, 78, 25, 110, "steamedrice", ["#fffdf7", "#f9f4e7", "#f0e9d8", "#ffffff"])
    s += '<ellipse cx="176" cy="108" rx="24" ry="8" fill="#ffffff" opacity="0.45"/>'
    return s + "</g></svg>"


def draw_tea():
    s = head() + weave()
    s += steam(200, 34, 3, 34)
    s += shadow(200, 206, 78, 20)
    s += f'<path d="M 140 118 L 150 190 Q 200 202 250 190 L 260 118 Z" fill="{VESSEL["clay"][0]}"/>'
    s += f'<path d="M 140 118 L 150 190 Q 200 202 250 190 L 260 118 Z" fill="{VESSEL["clay"][1]}" opacity="0.20"/>'
    s += f'<path d="M 140 118 L 150 190 Q 200 202 250 190 L 260 118 Z" fill="url(#sheen)"/>'
    s += f'<ellipse cx="200" cy="118" rx="60" ry="17" fill="{VESSEL["clay"][1]}"/>'
    s += f'<ellipse cx="200" cy="119" rx="50" ry="13" fill="#a96b39"/>'
    s += f'<ellipse cx="200" cy="121" rx="44" ry="10" fill="#8a5529"/>'
    s += f'<ellipse cx="186" cy="116" rx="14" ry="5" fill="#ffffff" opacity="0.20"/>'
    s += f'<ellipse cx="200" cy="192" rx="44" ry="9" fill="{VESSEL["clay"][1]}" opacity="0.55"/>'
    return s + "</g></svg>"


def draw_upma():
    s = head() + weave()
    s += shadow(200, 190, 108, 26)
    s += plate(200, 148, 112, 39, "steel", 14)
    s += mound(200, 140, 88, 30, ["#e9c37e", "#dfb269"], 3)
    s += grains(200, 136, 80, 25, 95, "upma", ["#f0cf90", "#e5bb78", "#d9a860", "#f7e0aa"])
    for i in range(12):
        x = 152 + (i * 17) % 98
        y = 120 + ((i * 13) % 26)
        s += f'<rect x="{x - 3:.0f}" y="{y - 2:.0f}" width="6" height="4" rx="1.5" fill="#7a5a22" opacity="0.5" transform="rotate({(i * 37) % 90} {x} {y})"/>'
    s += herb(200, 134, 78, 24, 11, "upma-h")
    return s + "</g></svg>"


def draw_veg_patty():
    s = head() + weave()
    s += shadow(200, 188, 98, 24)
    s += plate(200, 152, 108, 38, "ceramic", 15)
    s += '<g transform="rotate(-7 200 126)">'
    s += '<rect x="138" y="98" width="124" height="56" rx="24" fill="#b8793a"/>'
    s += '<rect x="138" y="93" width="124" height="54" rx="24" fill="#d99a52"/>'
    s += '<rect x="144" y="99" width="112" height="16" rx="8" fill="#efbe7d" opacity="0.75"/>'
    for i in range(22):
        x = 148 + (i * 15) % 104
        y = 104 + ((i * 9) % 34)
        s += f'<circle cx="{x}" cy="{y}" r="{2 + (i % 3)}" fill="#8a5722" opacity="0.40"/>'
    s += f'<circle cx="170" cy="120" r="5.4" fill="{GRAVY["green"]}" opacity="0.85"/>'
    s += f'<circle cx="212" cy="128" r="4.4" fill="#8fae52" opacity="0.85"/>'
    s += f'<circle cx="236" cy="112" r="3.8" fill="#d9573f" opacity="0.7"/>'
    s += '</g>'
    return s + "</g></svg>"


def draw_banana_milk():
    s = head() + weave()
    s += shadow(200, 258, 56, 14)
    s += glass(200, 44, 98, 200)
    s += '<path d="M 152 86 L 160 240 Q 200 254 240 240 L 248 86 Z" fill="#f2dc9c"/>'
    s += '<path d="M 152 86 L 160 240 Q 200 254 240 240 L 248 86 Z" fill="#f9e9bf" opacity="0.6"/>'
    s += '<ellipse cx="200" cy="86" rx="48" ry="12" fill="#eecf80"/>'
    s += '<ellipse cx="200" cy="85" rx="40" ry="9" fill="#fdf3d4"/>'
    s += '<ellipse cx="176" cy="74" rx="17" ry="13" fill="#f5cf3f"/>'
    s += '<ellipse cx="176" cy="74" rx="17" ry="13" fill="#fde98f" opacity="0.45"/>'
    s += '<circle cx="176" cy="74" r="4.4" fill="#e8b62c"/>'
    s += '<circle cx="176" cy="74" r="1.8" fill="#fdf3d4"/>'
    s += '<path d="M 240 116 q 12 -7 13 -19" stroke="#ffffff" stroke-width="6" fill="none" opacity="0.35" stroke-linecap="round"/>'
    s += '<path d="M 244 176 q 9 -6 10 -15" stroke="#ffffff" stroke-width="5" fill="none" opacity="0.28" stroke-linecap="round"/>'
    return s + "</g></svg>"


DISHES = {
    "aloo-gobi": draw_aloo_gobi,
    "banana-milk": draw_banana_milk,
    "chana-masala": draw_chana_masala,
    "chapati": draw_chapati,
    "chicken-curry": draw_chicken_curry,
    "curd": draw_curd,
    "dal-tadka": draw_dal_tadka,
    "fried-rice": draw_fried_rice,
    "idli": draw_idli,
    "khichdi": draw_khichdi,
    "mixed-veg-curry": draw_mixed_veg,
    "paneer-curry": draw_paneer_curry,
    "poha": draw_poha,
    "raita": draw_raita,
    "salad": draw_salad,
    "sambar": draw_sambar,
    "steamed-rice": draw_steamed_rice,
    "tea": draw_tea,
    "upma": draw_upma,
    "veg-patty": draw_veg_patty,
}


def main():
    os.makedirs(OUT, exist_ok=True)
    for slug, fn in DISHES.items():
        svg = fn()
        path = os.path.join(OUT, f"{slug}.svg")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(svg)
        print("wrote", path, len(svg), "bytes")


if __name__ == "__main__":
    main()
