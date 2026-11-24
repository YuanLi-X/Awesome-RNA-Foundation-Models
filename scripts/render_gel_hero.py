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

W, H = 1280, 660
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
    years = sorted({m["release"][:4] for m in models})
    newest = max(models, key=lambda m: (m["release"], m["name"]))
    o = Outliner()
    body = []

    # ---- left: title, figure legend, stats ----
    tx = 56
    for i, line in enumerate(["RNA foundation", "models, run", "on a gel."]):
        body.append(o.text(line, tx, 128 + i * 66, 66, "#FFE6BF", "bold"))
    legend = ("Each lane is a year of first public release and each band is one model. Larger models "
              "migrate less, so they sit near the wells; the ladder marks parameter count from 1M to 10B. "
              "Brighter bands hold several models of a similar size.")
    y = 336
    body.append(o.text("Fig. 1", tx, y, 18, "#FFE6BF", "bold"))
    first_indent = o.width("Fig. 1  ", 18, "bold")
    lines = o.wrap(legend, 18, 440 - first_indent)
    body.append(o.text(lines[0], tx + first_indent, y, 18, "#C9C1EE"))
    rest = o.wrap(" ".join(lines[1:]), 18, 440)
    for j, line in enumerate(rest, start=1):
        body.append(o.text(line, tx, y + j * 26, 18, "#C9C1EE"))
    y += (len(rest) + 1) * 26 + 22
    body.append(o.text(f"{len(models)} models since {years[0]}. Newest: {newest['name']}, "
                       f"{MONTHS[int(newest['release'][5:7]) - 1]} {newest['release'][:4]}.", tx, y, 17, "#8E86C6"))
    # call to action
    cta = "Click to open the interactive gel"
    cw = o.width(cta, 18, "bold") + 36
    body.append(f'<rect x="{tx}" y="{H - 106}" width="{cw:.0f}" height="44" rx="6" fill="#FFB347"/>')
    body.append(o.text(cta, tx + 18, H - 78, 18, "#1A1540", "bold"))

    # ---- right: the gel ----
    gx, gy, gw = 520, 54, W - 520 - 34
    lanes = ["Ladder"] + years
    lw = gw / (len(lanes) + .3)
    lane_x = lambda i: gx + (0 if i == 0 else (i + .3) * lw)
    top, bottom = gy + 86, H - 110
    y_of = lambda l: top + (LMAX - max(LMIN, l)) / (LMAX - LMIN) * (bottom - top)
    bw = 28
    body.append(f'<rect x="{gx}" y="{gy + 28}" width="{gw}" height="{H - gy - 28 - 30}" rx="10" fill="url(#slab)" stroke="#3F36A3"/>')
    for i, ln in enumerate(lanes):
        x = lane_x(i) + 12
        body.append(o.text(ln, x, gy + 16, 17, "#FFE6BF" if i else "#C9C1EE", "bold" if i else "regular"))
        body.append(f'<rect x="{x}" y="{gy + 44}" width="{min(lw - 24, bw + 30):.1f}" height="15" rx="2" fill="#0B0726" stroke="#463DA8"/>')
    for l, t in [(0, "1M"), (1, "10M"), (2, "100M"), (3, "1B"), (4, "10B")]:
        yy = y_of(l)
        body.append(f'<rect x="{lane_x(0) + 12}" y="{yy - 2.5:.1f}" width="{bw}" height="5" rx="2" fill="#E7E1FF" opacity=".8" filter="url(#glow)"/>')
        body.append(o.text(t, lane_x(0) + 12 + bw + 7, yy + 4.5, 13, "#C9C1EE"))
    labels = []
    gap = 15.5                                   # minimum vertical distance between two names
    for j, yr in enumerate(years):
        x = lane_x(j + 1) + 12
        lane = [m for m in models if m["release"].startswith(yr)]
        sized = sorted((m for m in lane if m["pm"]), key=lambda m: -m["pm"])
        items = []
        for m in sized:
            yy = y_of(math.log10(m["pm"]))
            body.append(f'<rect x="{x:.1f}" y="{yy - 3.5:.1f}" width="{bw}" height="7" rx="3" fill="#FFB347" opacity=".72" filter="url(#glow)"/>')
            items.append([yy, yy, m["name"], "#FFD9A6"])
        unsized = [m for m in lane if not m["pm"]]
        if unsized:
            sy = bottom + 18
            body.append(f'<rect x="{x:.1f}" y="{sy:.1f}" width="{bw}" height="{24 + len(unsized) * 6}" rx="4" fill="url(#smear)"/>')
            for k, m in enumerate(unsized):
                items.append([sy + 12 + k, sy + 12 + k, m["name"], "#A69DD6"])
        # spread names apart (1-D dodge) without leaving the gel
        lo, hi = gy + 72, H - 42
        for _ in range(200):
            moved = False
            for a, b in zip(items, items[1:]):
                d = b[1] - a[1]
                if d < gap:
                    push = (gap - d) / 2
                    a[1] -= push; b[1] += push; moved = True
            for it in items:
                it[1] = min(max(it[1], lo), hi)
            if not moved:
                break
        lx = x + bw
        for band_y, label_y, name, color in items:
            labels.append(f'<path d="M{lx + 1:.1f} {band_y:.1f}h4L{lx + 10:.1f} {label_y:.1f}h3" fill="none" stroke="#8E86C6" stroke-width=".8" opacity=".8"/>')
            labels.append(o.text(name, lx + 15, label_y + 4.2, 12, color))
    body += labels

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<title>RNA foundation models, run on a gel: {len(models)} models by release year and parameter count</title>
<defs>
<radialGradient id="field" cx="70%" cy="40%" r="90%"><stop offset="0" stop-color="#211A66"/><stop offset=".6" stop-color="#140F3C"/></radialGradient>
<linearGradient id="slab" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2A2187"/><stop offset="1" stop-color="#1B1560"/></linearGradient>
<linearGradient id="smear" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFB347" stop-opacity="0"/><stop offset=".45" stop-color="#FFB347" stop-opacity=".5"/><stop offset="1" stop-color="#FFB347" stop-opacity="0"/></linearGradient>
<filter id="glow" x="-40%" y="-400%" width="180%" height="900%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
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
