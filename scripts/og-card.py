#!/usr/bin/env python3
"""Generate a per-post social card (1200x630 PNG) from the post's title.

    scripts/og-card.py                       # every post under content/posts
    scripts/og-card.py content/posts/gsoc/week-1.md

Page bundles get content/<bundle>/cover.png, which Hugo's card templates pick up
with no front matter. Flat .md posts get static/img/og-<slug>.png and the script
prints the `images:` line to paste into their front matter.

Rendering is macOS-only: qlmanage rasterises the SVG, sips crops it. qlmanage
only emits square thumbnails, so the card is drawn as the centre band of a
1200x1200 canvas and cropped back out.
"""

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parent.parent
W, H = 1200, 630
PAD = 285                      # top of the card band inside the square canvas
MARGIN = 90
BG, ACCENT, FG, DIM = "#1b1c1d", "#67a2c9", "#f4f1ef", "#999"
FONT = "SFMono-Regular, Menlo, Consolas, monospace"
MONO_ADVANCE = 0.6             # width of one glyph in a monospace em
MAX_TITLE_LINES = 3


def wrap(text, size, width=W - 2 * MARGIN):
    """Greedy word wrap using the monospace advance width."""
    per_line = max(1, int(width / (MONO_ADVANCE * size)))
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if len(candidate) > per_line and line:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def fit_title(title):
    """Largest size at which the title still fits in MAX_TITLE_LINES."""
    for size in (58, 52, 46, 40, 34):
        lines = wrap(title, size)
        if len(lines) <= MAX_TITLE_LINES:
            return size, lines
    lines = wrap(title, 34)[:MAX_TITLE_LINES]
    lines[-1] = lines[-1][:-1] + "…"
    return 34, lines


def read_title(md):
    """Pull `title:` out of the YAML front matter."""
    text = md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{md}: no front matter")
    front = text.split("---", 2)[1]
    m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', front, re.M)
    if not m:
        raise ValueError(f"{md}: no title in front matter")
    return m.group(1)


def svg(title):
    size, lines = fit_title(title)
    step = int(size * 1.28)
    # Bottom-align the title block so long and short titles share a baseline.
    first = PAD + 430 - step * (len(lines) - 1)
    body = "\n".join(
        f'    <text x="{MARGIN}" y="{first + i * step}" font-size="{size}" '
        f'font-weight="700" fill="{FG}">{escape(line)}</text>'
        for i, line in enumerate(lines)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{W}" viewBox="0 0 {W} {W}">
  <rect width="{W}" height="{W}" fill="{BG}"/>
  <rect x="0" y="{PAD}" width="{W}" height="8" fill="{ACCENT}"/>
  <g font-family="{FONT}">
    <text x="{MARGIN}" y="{PAD + 90}" font-size="30" fill="{ACCENT}">&gt;</text>
    <text x="{MARGIN + 32}" y="{PAD + 90}" font-size="30" fill="{DIM}">tushar@syfe:~$</text>
{body}
    <text x="{MARGIN}" y="{PAD + 545}" font-size="26" fill="{DIM}">Tushar Choudhary</text>
    <text x="{MARGIN}" y="{PAD + 585}" font-size="26" fill="{ACCENT}">tushar-c23.github.io</text>
  </g>
</svg>
"""


def render(title, out):
    """SVG -> square PNG (qlmanage) -> cropped card (sips)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        src = tmp / "card.svg"
        src.write_text(svg(title), encoding="utf-8")
        subprocess.run(["qlmanage", "-t", "-s", str(W), "-o", str(tmp), str(src)],
                       check=True, capture_output=True)
        square = tmp / "card.svg.png"
        if not square.exists():
            raise RuntimeError("qlmanage produced no thumbnail")
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["sips", "-c", str(H), str(W), str(square), "--out", str(out)],
                       check=True, capture_output=True)


def destination(md):
    """Bundles take cover.png; flat posts go to static/img and need front matter."""
    if md.name == "index.md":
        return md.parent / "cover.png", None
    slug = md.stem
    out = ROOT / "static" / "img" / f"og-{slug}.png"
    return out, f'images: ["/img/og-{slug}.png"]'


def posts(args):
    if args:
        return [pathlib.Path(a).resolve() for a in args]
    return sorted(p for p in (ROOT / "content" / "posts").rglob("*.md")
                  if not p.name.startswith("_index"))


def selfcheck():
    assert wrap("a b c", 58) == ["a b c"]
    # 1020px / (0.6 * 58) = 29 chars per line
    assert wrap("x" * 29 + " y", 58) == ["x" * 29, "y"]
    # A word longer than the line is kept whole rather than dropped.
    assert wrap("y" * 80, 58) == ["y" * 80]
    size, lines = fit_title("Three stores, two cursors: where an SSE consumer should resume")
    assert len(lines) <= MAX_TITLE_LINES and size in (58, 52, 46, 40, 34)
    assert "&amp;" in svg("Tom & Jerry") and "<script>" not in svg("<script>")
    assert destination(pathlib.Path("content/posts/foo/index.md"))[1] is None
    assert destination(pathlib.Path("content/posts/gsoc/week-1.md"))[1].endswith('og-week-1.png"]')
    print("selfcheck ok")


def main(argv):
    if "--selfcheck" in argv:
        return selfcheck()
    if not shutil.which("qlmanage") or not shutil.which("sips"):
        sys.exit("needs macOS qlmanage and sips")
    hints = []
    for md in posts(argv):
        title = read_title(md)
        out, hint = destination(md)
        render(title, out)
        print(f"{out.relative_to(ROOT)}  <-  {title}")
        if hint:
            hints.append(f"  {md.relative_to(ROOT)}: {hint}")
    if hints:
        print("\nFlat posts - add to front matter:")
        print("\n".join(hints))


if __name__ == "__main__":
    main(sys.argv[1:])
