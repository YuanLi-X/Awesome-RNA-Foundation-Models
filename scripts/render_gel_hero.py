"""Render the README hero image (assets/gel_hero.svg) from data/papers.yaml.

GitHub shows README images through a sandboxed <img>, so web fonts never load there.
All text is therefore converted to outlines from the bundled IBM Plex Sans Condensed
(SIL OFL, assets/fonts) and every glyph is defined once and reused with <use>, which
keeps the picture identical on every viewer and the file small.

    python scripts/render_gel_hero.py
"""
from __future__ import annotations

import math
from html import escape
from pathlib import Path

import yaml
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
PAPERS = ROOT / "data" / "papers.yaml"
OUT = ROOT / "assets" / "gel_hero.svg"
FONTS = {
    "bold": ROOT / "assets" / "fonts" / "IBMPlexSansCondensed-Bold.ttf",
    "regular": ROOT / "assets" / "fonts" / "IBMPlexSansCondensed-Regular.ttf",
}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

W, H = 1280, 790
LMIN, LMAX = -0.4, math.log10(40000)        # 0.4M .. 40B, log10 of params in millions


class Outliner:
    """Turns strings into <use> references to glyph outlines defined once in <defs>."""

    def __init__(self):
        self.fonts = {k: TTFont(str(p)) for k, p in FONTS.items()}
        self.defs: dict[str, str] = {}

    def _glyph(self, weight: str, ch: str):
        font = self.fonts[weight]
        name = font.getBestCmap().get(ord(ch)) or ".notdef"
        gid = f"{weight[0]}{name}".replace(".", "_")
        if gid not in self.defs:
            pen = SVGPathPen(font.getGlyphSet())
            font.getGlyphSet()[name].draw(pen)
            self.defs[gid] = pen.getCommands()
        advance = font["hmtx"][name][0]
        return gid, advance

    def width(self, text: str, size: float, weight: str = "regular") -> float:
        upm = self.fonts[weight]["head"].unitsPerEm
        return sum(self._glyph(weight, c)[1] for c in text) * size / upm

    def text(self, text: str, x: float, y: float, size: float, fill: str, weight: str = "regular",
             anchor: str = "start", opacity: float | None = None, extra: str = "") -> str:
        upm = self.fonts[weight]["head"].unitsPerEm
        if anchor == "end":
            x -= self.width(text, size, weight)
        elif anchor == "middle":
            x -= self.width(text, size, weight) / 2
        s = size / upm
        uses, cursor = [], 0
        for c in text:
            gid, adv = self._glyph(weight, c)
            if c != " ":
                uses.append(f'<use href="#{gid}" x="{cursor}"/>')
            cursor += adv
        op = f' opacity="{opacity}"' if opacity is not None else ""
        return (f'<g transform="translate({x:.1f},{y:.1f}) scale({s:.5f},{-s:.5f})" fill="{fill}"{op}{extra}>'
                + "".join(uses) + "</g>")

    def wrap(self, text: str, size: float, max_w: float, weight: str = "regular") -> list[str]:
        lines, cur = [], ""
        for word in text.split():
            trial = f"{cur} {word}".strip()
            if self.width(trial, size, weight) > max_w and cur:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        return lines + [cur] if cur else lines

    def defs_svg(self) -> str:
        return "".join(f'<path id="{k}" d="{d}"/>' for k, d in self.defs.items())


def params_m(text) -> float | None:
    import re
    vals = [float(n) * (1000 if u == "B" else 1) for n, u in re.findall(r"(\d+(?:\.\d+)?)\s*([MB])\b", str(text or ""))]
    return max(vals) if vals else None


def render() -> None:
    records = yaml.safe_load(PAPERS.read_text(encoding="utf-8")) or []
    models = [{"name": r["name"], "release": r.get("timeline_date") or r["date"], "pm": params_m(r.get("params"))} for r in records]
    models.sort(key=lambda m: (m["release"], m["name"].lower()))
    years = sorted({m["release"][:4] for m in models})
    newest = max(models, key=lambda m: (m["release"], m["name"]))
    o = Outliner()
    body = []

    # ---- header: title left, figure legend right ----
    tx = 56
    for i, line in enumerate(["RNA foundation models,", "run on a gel."]):
        body.append(o.text(line, tx, 98 + i * 60, 58, "#FFE6BF", "bold"))
    lx_, ly_, lwid = 700, 72, 524
    legend = ("Each lane is one model, in order of first public release and grouped by year. Larger models "
              "migrate less, so their band sits nearer the well; the ladder marks parameter count from 1M to "
              "10B. A smear means the model reports no size.")
    indent = o.width("Fig. 1  ", 17, "bold")
    body.append(o.text("Fig. 1", lx_, ly_, 17, "#FFE6BF", "bold"))
    first = o.wrap(legend, 17, lwid - indent)[0]
    body.append(o.text(first, lx_ + indent, ly_, 17, "#C9C1EE"))
    rest = o.wrap(legend[len(first):].strip(), 17, lwid)
    for j, line in enumerate(rest, start=1):
        body.append(o.text(line, lx_, ly_ + j * 24, 17, "#C9C1EE"))
    body.append(o.text(f"{len(models)} models since {years[0]}. Newest: {newest['name']}, "
                       f"{MONTHS[int(newest['release'][5:7]) - 1]} {newest['release'][:4]}.",
                       lx_, ly_ + (len(rest) + 1) * 24 + 8, 16, "#8E86C6"))

    # ---- the gel: one lane per model ----
    NZ = 318                                  # top of the slab; names sit above it
    well_y, slab_b = NZ + 12, NZ + 372
    top, bottom = NZ + 46, slab_b - 58
    y_of = lambda l: top + (LMAX - max(LMIN, l)) / (LMAX - LMIN) * (bottom - top)
    x0, gap_y, right = 104, 12, 46
    lw = (W - x0 - right - gap_y * (len(years) - 1)) / len(models)
    bw = min(16, lw * .74)
    body.append(f'<rect x="46" y="{NZ}" width="{W - 56}" height="{slab_b - NZ}" rx="10" fill="url(#slab)" stroke="#3F36A3"/>')
    body.append(f'<g transform="translate(66,{NZ - 8}) rotate(-58)">{o.text("Ladder", 0, 0, 13, "#C9C1EE")}</g>')
    body.append(f'<rect x="58" y="{well_y}" width="24" height="9" rx="1.5" fill="#0B0726" stroke="#463DA8"/>')
    for l, t in [(0, "1M"), (1, "10M"), (2, "100M"), (3, "1B"), (4, "10B")]:
        yy = y_of(l)
        body.append(f'<line x1="84" x2="{W - 14}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#E7E1FF" stroke-opacity=".07"/>')
        body.append(f'<rect x="58" y="{yy - 2.5:.1f}" width="24" height="5" rx="2" fill="#E7E1FF" opacity=".8" filter="url(#glow)"/>')
        body.append(o.text(t, 40, yy + 4.5, 13, "#C9C1EE", anchor="end"))
    yi, prev, start_x, prev_end, groups = -1, None, 0.0, 0.0, []
    for i, m in enumerate(models):
        yr = m["release"][:4]
        if yr != prev:
            if prev:
                groups.append((prev, start_x, prev_end))
            yi += 1
            prev, start_x = yr, x0 + i * lw + yi * gap_y
        lx = x0 + i * lw + yi * gap_y
        cx = lx + lw / 2
        prev_end = lx + lw
        body.append(f'<rect x="{cx - bw / 2:.1f}" y="{well_y}" width="{bw:.1f}" height="9" rx="1.5" fill="#0B0726" stroke="#463DA8"/>')
        if m["pm"]:
            yy = y_of(math.log10(m["pm"]))
            body.append(f'<rect x="{cx - bw / 2:.1f}" y="{yy - 3:.1f}" width="{bw:.1f}" height="6" rx="2.5" fill="#FFB347" opacity=".85" filter="url(#glow)"/>')
        else:
            body.append(f'<rect x="{cx - bw / 2:.1f}" y="{bottom + 14:.1f}" width="{bw:.1f}" height="34" rx="3" fill="url(#smear)"/>')
        body.append(f'<g transform="translate({cx - 3:.1f},{NZ - 8}) rotate(-58)">{o.text(m["name"], 0, 0, 12.5, "#FFD9A6")}</g>')
    groups.append((prev, start_x, prev_end))
    for yr, a, b in groups:
        body.append(f'<path d="M{a + 2:.1f} {slab_b + 10}v7H{b - 2:.1f}v-7" fill="none" stroke="#8E86C6" stroke-width="1.2"/>')
        body.append(o.text(yr, (a + b) / 2, slab_b + 37, 16, "#FFE6BF", "bold", anchor="middle"))

    # call to action, bottom right
    cta = "Click to open the interactive gel"
    cw = o.width(cta, 17, "bold") + 34
    body.append(f'<rect x="{W - 40 - cw:.0f}" y="{H - 62}" width="{cw:.0f}" height="40" rx="6" fill="#FFB347"/>')
    body.append(o.text(cta, W - 40 - cw + 17, H - 36, 17, "#1A1540", "bold"))

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<title>RNA foundation models, run on a gel: one lane per model ({len(models)} models), band position by parameter count</title>
<defs>
<radialGradient id="field" cx="70%" cy="40%" r="90%"><stop offset="0" stop-color="#211A66"/><stop offset=".6" stop-color="#140F3C"/></radialGradient>
<linearGradient id="slab" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2A2187"/><stop offset="1" stop-color="#1B1560"/></linearGradient>
<linearGradient id="smear" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFB347" stop-opacity="0"/><stop offset=".45" stop-color="#FFB347" stop-opacity=".55"/><stop offset="1" stop-color="#FFB347" stop-opacity="0"/></linearGradient>
<filter id="glow" x="-60%" y="-400%" width="220%" height="900%"><feGaussianBlur stdDeviation="2.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" seed="4"/><feColorMatrix values="0 0 0 0 .75  0 0 0 0 .72  0 0 0 0 1  0 0 0 .16 0"/></filter>
{o.defs_svg()}
</defs>
<rect width="{W}" height="{H}" rx="14" fill="url(#field)"/>
<rect width="{W}" height="{H}" rx="14" filter="url(#grain)"/>
{"".join(body)}
</svg>
'''
    OUT.write_text(svg, encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(svg) // 1024} KB, {len(o.defs)} glyphs)")


if __name__ == "__main__":
    render()
