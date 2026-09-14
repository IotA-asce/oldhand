#!/usr/bin/env python3
"""Regenerate the README charts from the measured numbers.

The figures in the README are not drawn by hand and not screenshots. They are
generated from the data literals below, so a number in the README cannot drift
away from the number it is meant to show: change the data, re-run this, commit
the result.

    python docs/charts.py

Output is self-contained SVG in docs/img/. Each figure carries its own dark
background, so it renders identically in GitHub's light and dark themes
without needing a second copy and a <picture> element.

Every value here comes from the evaluation described in the paper, over a
293-record archive across four collections.
"""

from __future__ import annotations

import pathlib

OUT = pathlib.Path(__file__).resolve().parent / "img"

# --------------------------------------------------------------------------
# Visual language
# --------------------------------------------------------------------------

BG = "#0d1117"
EDGE = "#21262d"
GRID = "#1c2128"
FG = "#e6edf3"
DIM = "#8b949e"
MUTE = "#6e7681"

BLUE = "#58a6ff"
GREEN = "#3fb950"
RED = "#f85149"
AMBER = "#d29922"
PURPLE = "#bc8cff"
CYAN = "#39c5cf"
PINK = "#f778ba"

FONT = ("-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,"
        "Arial,sans-serif")
MONO = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,monospace"

W = 880
PAD = 30


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def text(x, y, s, size=12, fill=FG, weight=400, anchor="start",
         font=FONT, opacity=None, spacing=None):
    o = f' opacity="{opacity}"' if opacity is not None else ""
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    return (f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" '
            f'fill="{fill}" font-weight="{weight}" text-anchor="{anchor}"'
            f'{o}{ls}>{esc(s)}</text>')


def card(height: int, title: str, subtitle: str, body: str,
         footer: str = "") -> str:
    foot = ""
    if footer:
        foot = text(PAD, height - 18, footer, 11, MUTE)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" viewBox="0 0 {W} {height}" role="img" aria-label="{esc(title)}">
<rect x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" rx="10" fill="{BG}" stroke="{EDGE}"/>
{text(PAD, 34, title, 15, FG, 600)}
{text(PAD, 54, subtitle, 12, DIM)}
{body}
{foot}
</svg>
"""


def write(name: str, svg: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(svg, encoding="utf-8", newline="\n")
    print(f"  {name}")


# --------------------------------------------------------------------------
# 1. Importance inflation
# --------------------------------------------------------------------------

def inflation() -> None:
    """recall@5 against the share of records marked critical."""
    pts = [(0, 92), (10, 67), (25, 33), (50, 17), (75, 17)]
    H = 358
    x0, x1 = PAD + 42, W - PAD - 18
    y0, y1 = 100, H - 92

    def px(share):
        return x0 + (x1 - x0) * share / 75

    def py(val):
        return y1 - (y1 - y0) * val / 100

    b = []
    for v in (0, 25, 50, 75, 100):
        y = py(v)
        b.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" '
                 f'stroke="{GRID}" stroke-width="1"/>')
        b.append(text(x0 - 12, y + 4, f"{v}%", 11, MUTE, anchor="end"))

    area = " ".join(f"{px(s):.1f},{py(v):.1f}" for s, v in pts)
    b.append(f'<defs><linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">'
             f'<stop offset="0" stop-color="{RED}" stop-opacity="0.30"/>'
             f'<stop offset="1" stop-color="{RED}" stop-opacity="0.02"/>'
             f'</linearGradient></defs>')
    b.append(f'<polygon points="{px(0):.1f},{y1} {area} {px(75):.1f},{y1}" '
             f'fill="url(#g1)"/>')
    b.append(f'<polyline points="{area}" fill="none" stroke="{RED}" '
             f'stroke-width="2.5" stroke-linejoin="round"/>')

    for s, v in pts:
        cx, cy = px(s), py(v)
        b.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4.5" fill="{BG}" '
                 f'stroke="{RED}" stroke-width="2.5"/>')
        dx = 22 if s == 0 else 0
        b.append(text(cx + dx, cy - 15, f"{v}%", 12, FG, 600, "middle"))
        b.append(text(cx, y1 + 22, f"{s}%", 11, DIM, anchor="middle"))

    b.append(text((x0 + x1) / 2, y1 + 46,
                  "share of the archive marked critical", 11, MUTE,
                  anchor="middle"))

    # the point where it has already gone
    b.append(f'<line x1="{px(25):.1f}" y1="{py(33):.1f}" x2="{px(25):.1f}" '
             f'y2="{y0 - 8}" stroke="{AMBER}" stroke-width="1" '
             f'stroke-dasharray="3 3" opacity="0.5"/>')
    b.append(text(px(25) + 10, y0 + 4,
                  "at one record in four, worse than no metadata at all",
                  11, AMBER))

    write("inflation.svg", card(
        H, "A label on everything ranks nothing",
        "recall@5 as importance labels inflate. Everything else held constant.",
        "\n".join(b),
        "The answer records themselves are never promoted. 12 queries with known answers."))


# --------------------------------------------------------------------------
# 2. The scoring budget
# --------------------------------------------------------------------------

def budget() -> None:
    """Text relevance against every metadata contribution combined."""
    parts = [("topic overlap", 12, BLUE), ("risk", 6, PURPLE),
             ("durability", 6, CYAN), ("status", 6, GREEN),
             ("evidence", 5, AMBER), ("scope", 5, PINK),
             ("importance", 4, RED)]
    total = sum(p[1] for p in parts)
    H = 286
    x0 = PAD + 96
    x1 = W - PAD - 20
    scale = (x1 - x0) / 60.0

    b = []
    for v in range(0, 61, 10):
        x = x0 + v * scale
        b.append(f'<line x1="{x:.1f}" y1="96" x2="{x:.1f}" y2="196" '
                 f'stroke="{GRID}" stroke-width="1"/>')
        b.append(text(x, 214, str(v), 10, MUTE, anchor="middle"))

    # text relevance
    b.append(text(PAD, 124, "text", 12, FG, 600))
    b.append(f'<rect x="{x0}" y="106" width="{60 * scale:.1f}" height="28" '
             f'rx="4" fill="{GREEN}" opacity="0.85"/>')
    b.append(text(x0 + 60 * scale - 10, 125, "60", 13, "#0d1117", 700,
                  anchor="end"))

    # metadata, stacked
    b.append(text(PAD, 172, "metadata", 12, FG, 600))
    cur = x0
    for label, val, col in parts:
        w = val * scale
        b.append(f'<rect x="{cur:.1f}" y="154" width="{w:.1f}" height="28" '
                 f'rx="3" fill="{col}" opacity="0.85"/>')
        if val >= 5:
            b.append(text(cur + w / 2, 173, str(val), 11, "#0d1117", 700,
                          anchor="middle"))
        cur += w + 1.5

    b.append(f'<line x1="{cur:.1f}" y1="148" x2="{cur:.1f}" y2="196" '
             f'stroke="{DIM}" stroke-width="1" stroke-dasharray="3 3"/>')
    b.append(text(cur + 8, 192, f"{total} total", 11, DIM))

    # legend
    lx = x0
    for label, val, col in parts:
        b.append(f'<rect x="{lx}" y="236" width="9" height="9" rx="2" '
                 f'fill="{col}" opacity="0.85"/>')
        b.append(text(lx + 14, 245, label, 10.5, DIM))
        lx += 22 + len(label) * 5.6

    write("budget.svg", card(
        H, "Metadata breaks ties. It never decides the ranking.",
        "Every positive label combined, against the text-relevance range.",
        "\n".join(b),
        "lore selftest fails the build if the metadata ceiling ever reaches the text weight."))


# --------------------------------------------------------------------------
# 3. Before and after
# --------------------------------------------------------------------------

def beforeafter() -> None:
    rows = [("recall@1", 64, 80), ("recall@3", 77, 98), ("recall@5", 82, 98),
            ("MRR", 71, 89), ("sub-document reach", 36, 82)]
    H = 344
    x0 = PAD + 140
    x1 = W - PAD - 70
    top = 92
    step = 38

    b = []
    for i, (label, before, after) in enumerate(rows):
        y = top + i * step
        b.append(text(PAD, y + 15, label, 12, FG, 500))
        b.append(f'<rect x="{x0}" y="{y + 3}" width="{x1 - x0}" height="18" '
                 f'rx="4" fill="{GRID}"/>')
        wb = (x1 - x0) * before / 100
        wa = (x1 - x0) * after / 100
        b.append(f'<rect x="{x0}" y="{y + 3}" width="{wa:.1f}" height="18" '
                 f'rx="4" fill="{GREEN}" opacity="0.30"/>')
        b.append(f'<rect x="{x0}" y="{y + 3}" width="{wb:.1f}" height="18" '
                 f'rx="4" fill="{DIM}" opacity="0.55"/>')
        b.append(f'<line x1="{x0 + wa:.1f}" y1="{y}" x2="{x0 + wa:.1f}" '
                 f'y2="{y + 24}" stroke="{GREEN}" stroke-width="2"/>')
        shown = f"{after / 100:.2f}" if label == "MRR" else f"{after}%"
        was = f"{before / 100:.2f}" if label == "MRR" else f"{before}%"
        b.append(text(x1 + 12, y + 16, shown, 12, GREEN, 600))
        b.append(text(x0 + wb - 8, y + 16, was, 11, FG, 500, anchor="end",
                      opacity=0.75))

    b.append(f'<rect x="{PAD}" y="{top + len(rows) * step + 4}" width="9" '
             f'height="9" rx="2" fill="{DIM}" opacity="0.55"/>')
    b.append(text(PAD + 14, top + len(rows) * step + 13,
                  "immediately after migration", 10.5, DIM))
    b.append(f'<rect x="{PAD + 176}" y="{top + len(rows) * step + 4}" '
             f'width="9" height="9" rx="2" fill="{GREEN}" opacity="0.5"/>')
    b.append(text(PAD + 190, top + len(rows) * step + 13,
                  "after the findings in this repository were applied", 10.5,
                  DIM))

    write("beforeafter.svg", card(
        H, "What the findings were worth",
        "293 records, four collections. Same archive, same tooling.",
        "\n".join(b),
        "The query set also widened from one collection to four, so the later figure is a strictly harder task."))


# --------------------------------------------------------------------------
# 4. The aggregate conceals the collections
# --------------------------------------------------------------------------

def collections() -> None:
    rows = [("S3", 8, 100, 100), ("S1", 7, 100, 100),
            ("W", 23, 78, 96), ("S2", 8, 50, 100)]
    H = 332
    x0 = PAD + 116
    x1 = W - PAD - 118
    top = 94
    step = 42

    b = []
    for i, (name, q, r1, r3) in enumerate(rows):
        y = top + i * step
        b.append(text(PAD, y + 14, name, 13, FG, 600, font=MONO))
        b.append(text(PAD + 34, y + 14, f"{q} queries", 11, MUTE))
        b.append(f'<rect x="{x0}" y="{y + 2}" width="{x1 - x0}" height="20" '
                 f'rx="4" fill="{GRID}"/>')
        w3 = (x1 - x0) * r3 / 100
        w1 = (x1 - x0) * r1 / 100
        b.append(f'<rect x="{x0}" y="{y + 2}" width="{w3:.1f}" height="20" '
                 f'rx="4" fill="{BLUE}" opacity="0.28"/>')
        col = RED if r1 < 60 else (AMBER if r1 < 90 else GREEN)
        b.append(f'<rect x="{x0}" y="{y + 2}" width="{w1:.1f}" height="20" '
                 f'rx="4" fill="{col}" opacity="0.9"/>')
        b.append(text(x1 + 12, y + 17, f"r@1 {r1}%", 11.5, col, 600))
        b.append(text(x1 + 74, y + 17, f"r@3 {r3}%", 11.5, BLUE, 500))

    y = top + len(rows) * step + 2
    b.append(f'<line x1="{PAD}" y1="{y}" x2="{W - PAD}" y2="{y}" '
             f'stroke="{EDGE}"/>')
    b.append(text(PAD, y + 22,
                  "S2 sits at 50% recall@1 and 100% recall@3. Three rounds of rewriting moved recall@1 by zero,",
                  11, DIM))
    b.append(text(PAD, y + 38,
                  "because the displacing records are genuine neighbours losing by two points out of eighty.",
                  11, DIM))

    write("collections.svg", card(
        H, "Read the collections, not the average",
        "The same archive, broken out. The aggregate is 80% recall@1.",
        "\n".join(b)))


# --------------------------------------------------------------------------
# 5. Detector precision
# --------------------------------------------------------------------------

def precision() -> None:
    H = 268
    cols, size, gap = 15, 26, 7
    x0, y0 = PAD, 96
    b = []
    for i in range(29):
        r, c = divmod(i, cols)
        x = x0 + c * (size + gap)
        y = y0 + r * (size + gap)
        real = i < 4
        b.append(
            f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="5" '
            f'fill="{GREEN if real else "#161b22"}" '
            f'fill-opacity="{0.9 if real else 1}" '
            f'stroke="{GREEN if real else EDGE}" stroke-width="1"/>')

    lx = x0 + cols * (size + gap) + 26
    b.append(f'<rect x="{lx}" y="{y0 + 2}" width="11" height="11" rx="3" '
             f'fill="{GREEN}" opacity="0.9"/>')
    b.append(text(lx + 17, y0 + 12, "4 genuine defects", 12, FG, 600))
    b.append(text(lx + 17, y0 + 30,
                  "including summaries asserting claims", 10.5, DIM))
    b.append(text(lx + 17, y0 + 44, "their own bodies had retracted", 10.5,
                  DIM))

    b.append(f'<rect x="{lx}" y="{y0 + 62}" width="11" height="11" rx="3" '
             f'fill="#161b22" stroke="{EDGE}"/>')
    b.append(text(lx + 17, y0 + 72, "25 false positives", 12, DIM, 600))
    b.append(text(lx + 17, y0 + 90, "from seven distinct causes", 10.5, DIM))

    b.append(text(PAD, 208, "13.8%", 26, AMBER, 700, font=MONO))
    b.append(text(PAD + 88, 200, "precision on a first pass.", 12, FG))
    b.append(text(PAD + 88, 216,
                  "Read the record before acting on the report.", 11, DIM))

    write("precision.svg", card(
        H, "Your first pass of any heuristic mostly measures itself",
        "Every item flagged across a full reconciliation of the archive.",
        "\n".join(b),
        "Detection is automated. Resolution is not: an auto-retirement facility was wrong on two of its four real candidates."))


# --------------------------------------------------------------------------
# 6. Architecture
# --------------------------------------------------------------------------

def architecture() -> None:
    """Canonical Markdown, derived index, returned summaries."""
    H = 272
    # Three panels with 70px gutters, so arrow labels never touch a border.
    ax, aw = PAD, 270            # 30  .. 300
    bx, bw = 370, 210            # 370 .. 580
    cx, cw = 650, W - PAD - 650  # 650 .. 850
    top, ph = 94, 116
    mid = top + ph / 2
    b = []

    def panel(x, w, stroke, dashed=False):
        d = ' stroke-dasharray="5 4"' if dashed else ""
        return (f'<rect x="{x}" y="{top}" width="{w}" height="{ph}" rx="9" '
                f'fill="#0f141b" stroke="{stroke}"{d} stroke-width="1.5"/>')

    b.append(f'<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" '
             f'markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
             f'<path d="M0 0 L10 5 L0 10 z" fill="{DIM}"/></marker></defs>')

    # canonical
    b.append(panel(ax, aw, GREEN))
    b.append(text(ax + 16, top - 10, "CANONICAL", 10, GREEN, 700,
                  spacing="1.2"))
    for i in range(3):
        b.append(f'<rect x="{ax + 16 + i * 10}" y="{top + 24 + i * 7}" '
                 f'width="70" height="54" rx="5" fill="#161b22" '
                 f'stroke="{EDGE}"/>')
    b.append(text(ax + 120, top + 38, "Markdown", 13, FG, 600))
    b.append(text(ax + 120, top + 56, "one file per record", 11, DIM))
    b.append(text(ax + 120, top + 72, "YAML frontmatter", 11, DIM))
    b.append(text(ax + 120, top + 96, "readable without Lore", 10.5, GREEN,
                  opacity=0.85))

    # derived
    b.append(panel(bx, bw, MUTE, dashed=True))
    b.append(text(bx + 16, top - 10, "DERIVED", 10, MUTE, 700, spacing="1.2"))
    cyx, cyy, rx, ch = bx + 44, top + 34, 26, 30
    b.append(f'<path d="M{cyx - rx} {cyy} v{ch} a{rx} 9 0 0 0 {rx * 2} 0 '
             f'v-{ch}" fill="#161b22" stroke="{EDGE}"/>')
    b.append(f'<ellipse cx="{cyx}" cy="{cyy}" rx="{rx}" ry="9" '
             f'fill="#1c2128" stroke="{EDGE}"/>')
    b.append(text(bx + 84, top + 38, "SQLite", 13, FG, 600))
    b.append(text(bx + 84, top + 56, "FTS5 + BM25", 11, DIM))
    b.append(text(bx + 84, top + 72, ".lore/lore.db", 11, DIM, font=MONO))
    b.append(text(bx + 16, top + 96, "delete it and you lose nothing", 10.5,
                  MUTE))

    # returned
    b.append(panel(cx, cw, BLUE))
    b.append(text(cx + 16, top - 10, "RETURNED", 10, BLUE, 700, spacing="1.2"))
    for i in range(3):
        y = top + 18 + i * 26
        b.append(f'<rect x="{cx + 16}" y="{y}" width="{cw - 32}" height="20" '
                 f'rx="4" fill="#161b22" stroke="{EDGE}"/>')
        b.append(f'<rect x="{cx + 24}" y="{y + 6}" width="{78 - i * 20}" '
                 f'height="7" rx="3" fill="{BLUE}" '
                 f'opacity="{0.85 - i * 0.22:.2f}"/>')
    b.append(text(cx + 16, top + 102, "ranked summaries, ~500 tokens", 10.5,
                  BLUE, opacity=0.85))

    # arrows, centred in the gutters
    for gap_l, gap_r, label in ((ax + aw, bx, "rebuild"), (bx + bw, cx, "search")):
        c = (gap_l + gap_r) / 2
        b.append(f'<line x1="{c - 20}" y1="{mid}" x2="{c + 18}" y2="{mid}" '
                 f'stroke="{DIM}" stroke-width="1.5" marker-end="url(#a)"/>')
        b.append(text(c, mid - 12, label, 10, DIM, anchor="middle", font=MONO))

    # the return path
    ry = top + ph + 22
    b.append(f'<path d="M{cx + 60} {top + ph + 6} v{ry - top - ph - 6} '
             f'H{ax + 140} v-16" fill="none" stroke="{EDGE}" '
             f'stroke-width="1.5" marker-end="url(#a)"/>')
    b.append(text((cx + 60 + ax + 140) / 2, ry + 18,
                  "lore show, opens the record", 10, MUTE, anchor="middle",
                  font=MONO))

    write("architecture.svg", card(
        H, "The Markdown is the archive. The index is a cache.",
        "The dependency points one way, and that is the whole design.",
        "\n".join(b)))


# --------------------------------------------------------------------------
# 7. Where the project is
# --------------------------------------------------------------------------

def stages() -> None:
    """Three stages on one track. Only the first is finished."""
    items = [
        ("STAGE ONE", "Complete", GREEN, "done",
         ["one archive, 293 records", "every number in this repository",
          "written up as a paper"]),
        ("STAGE TWO", "Running now", AMBER, "active",
         ["five independent archives", "pinned at v0.4.0",
          "exports in about two weeks"]),
        ("STAGE THREE", "The goal", MUTE, "todo",
         ["findings that survive", "an archive nobody here wrote",
          "starting with: does anyone search unprompted?"]),
    ]
    H = 228
    b = []
    colw = (W - PAD * 2) / 3
    ty = 108

    b.append(f'<line x1="{PAD + 14}" y1="{ty}" x2="{W - PAD - 14}" y2="{ty}" '
             f'stroke="{EDGE}" stroke-width="2"/>')
    done_x = PAD + 14 + colw
    b.append(f'<line x1="{PAD + 14}" y1="{ty}" x2="{done_x:.0f}" y2="{ty}" '
             f'stroke="{GREEN}" stroke-width="2"/>')

    for i, (name, state, col, kind, lines) in enumerate(items):
        cx = PAD + 14 + colw * i
        x = PAD + colw * i
        if kind == "done":
            b.append(f'<circle cx="{cx:.0f}" cy="{ty}" r="9" fill="{col}"/>')
            b.append(f'<path d="M{cx - 4:.0f} {ty} l3 3.5 l5.5 -6" '
                     f'fill="none" stroke="{BG}" stroke-width="2" '
                     f'stroke-linecap="round" stroke-linejoin="round"/>')
        elif kind == "active":
            b.append(f'<circle cx="{cx:.0f}" cy="{ty}" r="13" fill="{col}" '
                     f'opacity="0.18"/>')
            b.append(f'<circle cx="{cx:.0f}" cy="{ty}" r="9" fill="{BG}" '
                     f'stroke="{col}" stroke-width="3"/>')
            b.append(f'<circle cx="{cx:.0f}" cy="{ty}" r="3.5" fill="{col}"/>')
        else:
            b.append(f'<circle cx="{cx:.0f}" cy="{ty}" r="9" fill="{BG}" '
                     f'stroke="{EDGE}" stroke-width="2"/>')

        b.append(text(x, ty - 26, name, 10, col, 700, spacing="1.3"))
        b.append(text(x, ty + 36, state, 13, FG if kind != "todo" else DIM,
                      600))
        for j, line in enumerate(lines):
            b.append(text(x, ty + 58 + j * 17, line, 11, DIM))

    write("stages.svg", card(
        H, "Every number here came from one archive",
        "That cannot be fixed by working on that archive, so this is now a measurement programme.",
        "\n".join(b)))


if __name__ == "__main__":
    print("writing charts to docs/img/")
    inflation()
    budget()
    beforeafter()
    collections()
    precision()
    architecture()
    stages()
    print("done")
