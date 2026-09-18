"""Render the synthetic demo's real output into a terminal SVG.

Reproducible by construction: it runs `examples/run_demo.py` and draws
whatever that prints. Nothing here is transcribed by hand, so the asset
cannot drift away from what the command actually does.

    python3 -B docs/make_demo_svg.py

The animated GIF in examples/demo/oldhand-demo.tape tells the same story;
rendering it needs VHS and a working headless browser.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img" / "demo-session.svg"

FG = "#c9d1d9"
DIM = "#8b949e"
ACCENT = "#bc8cff"
GREEN = "#3fb950"
BG = "#0d1117"
LINE = 21
PAD = 22
CHAR = 8.4


def demo_output() -> list[str]:
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"),
               PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run([sys.executable, "-B", "examples/run_demo.py"],
                          cwd=ROOT, env=env, capture_output=True, text=True,
                          check=True)
    return done.stdout.rstrip("\n").splitlines()


def colour(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith(("Before:", "After:")):
        return ACCENT
    if stripped.startswith(("Oldhand search:", "Oldhand show:")):
        return GREEN
    if stripped.startswith(("Retrieved:", "Summary:", "Title:", "Evidence:",
                            "Interpretation:", "DATABASE_URL")):
        return DIM
    return FG


def wrap(lines: list[str], width: int = 96) -> list[tuple[str, str]]:
    """Wrap to `width`, carrying each source line's colour onto its own
    continuations. Colouring after wrapping would light up the tail of a
    dim paragraph as if it were a new field."""
    out: list[tuple[str, str]] = []
    for line in lines:
        ink = colour(line)
        if len(line) <= width:
            out.append((line, ink))
            continue
        indent = " " * (len(line) - len(line.lstrip()) + 2)
        current = line
        while len(current) > width:
            cut = current.rfind(" ", 0, width)
            cut = cut if cut > len(indent) else width
            out.append((current[:cut], ink))
            current = indent + current[cut:].lstrip()
        out.append((current, ink))
    return out


def main() -> int:
    prompt = "$ oldhand search \"why can't we simplify this config loader?\""
    rows = [(prompt, FG), ("", FG)] + wrap(demo_output())
    width = int(max(len(text) for text, _ in rows) * CHAR) + PAD * 2
    height = LINE * len(rows) + PAD * 2 + 34

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="A terminal session retrieving a reviewed constraint from a local archive">',
        f'<rect width="{width}" height="{height}" rx="10" fill="{BG}"/>',
        f'<circle cx="26" cy="22" r="6" fill="#ff5f56"/>'
        f'<circle cx="46" cy="22" r="6" fill="#ffbd2e"/>'
        f'<circle cx="66" cy="22" r="6" fill="#27c93f"/>',
        '<g font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace" '
        'font-size="13.5">',
    ]
    y = PAD + 34
    for text, ink in rows:
        if text.startswith("$ "):
            parts.append(f'<text x="{PAD}" y="{y}" fill="{GREEN}">$</text>'
                         f'<text x="{PAD + int(CHAR * 2)}" y="{y}" fill="{FG}">'
                         f'{escape(text[2:])}</text>')
        elif text:
            parts.append(f'<text x="{PAD}" y="{y}" fill="{ink}" '
                         f'xml:space="preserve">{escape(text)}</text>')
        y += LINE
    parts.append("</g></svg>")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
