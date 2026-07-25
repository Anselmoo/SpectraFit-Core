#!/usr/bin/env python3
r"""Coverage Atlas — three languages, one continent.

Reads Python pytest-cov XML, Rust cargo-llvm-cov LCOV, and Web vitest LCOV.
Fuses them into a single hierarchical map of the codebase: files sized by
lines-of-code, colored by coverage percentage, organized by language continent.

The boring report ("83.5% lines") becomes a navigable atlas: dark coastlines
are unexplored, bright peaks are well-charted, and you can fly across language
boundaries without leaving the page.

Usage:
    python scripts/coverage_atlas.py \\
        --python coverage.xml \\
        --rust target/llvm-cov/lcov.info \\
        --web web/coverage/lcov.info \\
        --out coverage-atlas.html
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileCov:
    """One file's coverage profile, normalized to project-relative paths."""

    path: str
    language: str  # python | rust | web
    lines_total: int
    lines_hit: int
    uncovered_ranges: list[tuple[int, int]]


def _relpath(absolute_or_relative: str, root: Path, also_try: list[Path]) -> str | None:
    """Best-effort project-relative path; drops files outside any known root.

    Tries the project root first, then each entry in ``also_try`` (e.g. the
    ``web/`` subdir for vitest's lcov which uses paths relative to ``web/``).
    Returns ``None`` for anything we can't place on the continent.
    """
    candidate = Path(absolute_or_relative)
    # Already project-relative?
    plain = (root / candidate).resolve()
    try:
        return str(plain.relative_to(root.resolve()))
    except ValueError:
        pass
    # Absolute path → try each root
    if candidate.is_absolute():
        for base in [root, *also_try]:
            try:
                return str(candidate.resolve().relative_to(base.resolve()))
            except (ValueError, OSError):
                continue
        return None
    # Relative path → try each also_try as the prefix
    for base in also_try:
        try:
            rel_to_subroot = (base / candidate).resolve().relative_to(root.resolve())
            return str(rel_to_subroot)
        except (ValueError, OSError):
            continue
    return None


def _collapse_to_ranges(line_nums: list[int]) -> list[tuple[int, int]]:
    """Compress sorted line numbers into ``(start, end)`` inclusive ranges."""
    if not line_nums:
        return []
    ordered = sorted(set(line_nums))
    ranges: list[tuple[int, int]] = []
    start = end = ordered[0]
    for ln in ordered[1:]:
        if ln == end + 1:
            end = ln
        else:
            ranges.append((start, end))
            start = end = ln
    ranges.append((start, end))
    return ranges


def parse_lcov(
    path: Path, language: str, root: Path, also_try: list[Path]
) -> list[FileCov]:
    """Parse an LCOV ``.info`` file into FileCov records."""
    if not path.exists():
        return []
    files: list[FileCov] = []
    current_file: str | None = None
    da_records: list[tuple[int, int]] = []
    for line in path.read_text().splitlines():
        if line.startswith("SF:"):
            current_file = line[3:]
            da_records = []
        elif line.startswith("DA:"):
            parts = line[3:].split(",")
            if len(parts) >= 2:
                da_records.append((int(parts[0]), int(parts[1])))
        elif line.startswith("end_of_record"):
            if current_file and da_records:
                rel = _relpath(current_file, root, also_try)
                if rel:
                    total = len(da_records)
                    hit = sum(1 for _, h in da_records if h > 0)
                    uncov = _collapse_to_ranges([ln for ln, h in da_records if h == 0])
                    files.append(FileCov(rel, language, total, hit, uncov))
            current_file = None
            da_records = []
    return files


def parse_cobertura(path: Path, language: str, root: Path) -> list[FileCov]:
    """Parse a pytest-cov XML (Cobertura format) into FileCov records."""
    if not path.exists():
        return []
    files: list[FileCov] = []
    tree = ET.parse(path)
    for cls in tree.iter("class"):
        filename = cls.get("filename", "")
        rel = _relpath(filename, root, also_try=[])
        if not rel:
            continue
        lines = list(cls.iter("line"))
        if not lines:
            continue
        total = len(lines)
        hit = sum(1 for ln in lines if int(ln.get("hits", "0")) > 0)
        uncov = _collapse_to_ranges(
            [
                int(ln.get("number", "0"))
                for ln in lines
                if int(ln.get("hits", "0")) == 0
            ],
        )
        files.append(FileCov(rel, language, total, hit, uncov))
    return files


def build_atlas(files: list[FileCov]) -> dict:
    """Build a flat list of leaves (one per file) with rolled-up totals."""
    leaves = [
        {
            "name": Path(f.path).name,
            "path": f.path,
            "lang": f.language,
            "total": f.lines_total,
            "hit": f.lines_hit,
            "uncov": f.uncovered_ranges,
            "value": f.lines_total,
        }
        for f in files
        if f.lines_total > 0
    ]
    return {
        "leaves": leaves,
        "totals": {
            "total": sum(f["total"] for f in leaves),
            "hit": sum(f["hit"] for f in leaves),
            "by_lang": {
                lang: {
                    "total": sum(f["total"] for f in leaves if f["lang"] == lang),
                    "hit": sum(f["hit"] for f in leaves if f["lang"] == lang),
                    "files": sum(1 for f in leaves if f["lang"] == lang),
                }
                for lang in {f["lang"] for f in leaves}
            },
        },
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Pangaea — Coverage Atlas</title>
<style>
:root {
    --bg: oklch(0.13 0.012 260);
    --ink: oklch(0.97 0.005 250);
    --ink-2: oklch(0.78 0.01 250);
    --ink-3: oklch(0.58 0.012 250);
    --line: oklch(0.27 0.012 258);
    --surface: oklch(0.17 0.012 260);
    --surface-2: oklch(0.21 0.013 260);
}
html, body {
    margin: 0; padding: 0; background: var(--bg); color: var(--ink);
    font-family: "Inter Tight", system-ui, -apple-system, sans-serif;
    height: 100vh; overflow: hidden; letter-spacing: -0.005em;
}
header {
    display: flex; align-items: baseline; gap: 14px;
    padding: 22px 32px 14px; border-bottom: 1px solid var(--line);
}
h1 { margin: 0; font-size: 26px; font-weight: 700; letter-spacing: -0.025em; }
.subtitle { color: var(--ink-2); font-size: 13.5px; }
.total {
    margin-left: auto; font-size: 32px; font-weight: 700;
    font-family: "IBM Plex Mono", ui-monospace, monospace; letter-spacing: -0.02em;
}
.continent-legend {
    display: flex; gap: 18px; padding: 10px 32px 16px; font-size: 12px;
    color: var(--ink-2); border-bottom: 1px solid var(--line);
    align-items: center;
}
.legend-chip { display: inline-flex; align-items: center; gap: 7px; font-weight: 600; }
.legend-chip::before {
    content: ""; width: 11px; height: 11px; border-radius: 2.5px;
}
.legend-chip[data-lang="python"]::before { background: oklch(0.67 0.16 255); }
.legend-chip[data-lang="rust"]::before { background: oklch(0.67 0.16 35); }
.legend-chip[data-lang="web"]::before { background: oklch(0.67 0.16 160); }
.legend-meta { color: var(--ink-3); margin-left: auto; font-size: 11.5px; }
main {
    display: grid; grid-template-columns: 1fr 380px;
    height: calc(100vh - 110px);
}
#atlas { background: var(--bg); display: block; width: 100%; height: 100%; }
aside {
    background: var(--surface); border-left: 1px solid var(--line);
    padding: 26px 26px 32px; overflow-y: auto; font-size: 13px;
}
rect.cell {
    cursor: pointer;
    transition: opacity 0.18s ease, stroke-width 0.18s ease;
    stroke: oklch(0.13 0.012 260); stroke-width: 0.5;
}
rect.cell:hover {
    opacity: 0.82; stroke: var(--ink); stroke-width: 1.5;
}
text.cell-label {
    font-size: 10.5px; fill: var(--ink); pointer-events: none;
    font-family: "IBM Plex Mono", ui-monospace, monospace; letter-spacing: 0;
    paint-order: stroke; stroke: oklch(0.13 0.012 260 / 0.6); stroke-width: 2;
}
.detail-empty {
    color: var(--ink-3); font-style: italic; text-align: center;
    padding: 32px 0;
}
.detail-title {
    font-size: 15px; font-weight: 700; word-break: break-all;
    margin-bottom: 4px; line-height: 1.3;
}
.detail-meta {
    color: var(--ink-2); font-size: 11.5px; margin-bottom: 14px;
    font-family: "IBM Plex Mono", ui-monospace, monospace;
}
.detail-bar {
    height: 9px; border-radius: 4.5px; background: var(--surface-2);
    overflow: hidden; margin: 12px 0 6px;
}
.detail-bar-fill { height: 100%; transition: width 0.25s ease; }
.detail-pct {
    font-size: 28px; font-weight: 700; letter-spacing: -0.02em;
    font-family: "IBM Plex Mono", ui-monospace, monospace;
}
.detail-h {
    font-size: 10.5px; color: var(--ink-3); text-transform: uppercase;
    letter-spacing: 0.07em; margin: 22px 0 8px; font-weight: 700;
}
.detail-range {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 11.5px; color: var(--ink-2);
    padding: 3px 8px 3px 0; border-bottom: 1px solid var(--line);
}
.detail-range:last-child { border-bottom: none; }
.lang-badge {
    display: inline-block; padding: 1px 7px; border-radius: 3px;
    font-size: 9.5px; font-weight: 700; letter-spacing: 0.05em;
    text-transform: uppercase; margin-right: 6px; vertical-align: 2px;
}
.lang-badge[data-lang="python"] { background: oklch(0.27 0.04 255); color: oklch(0.78 0.12 255); }
.lang-badge[data-lang="rust"]   { background: oklch(0.27 0.04 35);  color: oklch(0.78 0.12 35); }
.lang-badge[data-lang="web"]    { background: oklch(0.27 0.04 160); color: oklch(0.78 0.12 160); }
</style>
</head>
<body>
<header>
    <h1>Pangaea</h1>
    <span class="subtitle">your codebase as one continent</span>
    <span class="total" id="total-pct"></span>
</header>
<div class="continent-legend">
    <span class="legend-chip" data-lang="python">Python</span>
    <span class="legend-chip" data-lang="rust">Rust</span>
    <span class="legend-chip" data-lang="web">Web</span>
    <span class="legend-meta">deep = unexplored · bright = well-charted · area = lines of code</span>
</div>
<main>
    <svg id="atlas"></svg>
    <aside id="detail">
        <div class="detail-empty">hover any region to chart it</div>
    </aside>
</main>

<script>
const ATLAS = __ATLAS_JSON__;

document.getElementById("total-pct").textContent =
    ATLAS.totals.total ? `${(ATLAS.totals.hit / ATLAS.totals.total * 100).toFixed(1)}%` : "—";

const HUES = { python: 255, rust: 35, web: 160 };

function colorFor(file) {
    const hue = HUES[file.lang] || 0;
    const cov = file.total ? file.hit / file.total : 1;
    // 0% → deep, almost black; 100% → bright peak
    const L = 0.22 + cov * 0.50;
    const C = 0.03 + cov * 0.16;
    return `oklch(${L.toFixed(3)} ${C.toFixed(3)} ${hue})`;
}

// Squarified treemap (Bruls/Huijbregts/van Wijk, 2000), pragmatic implementation.
function squarify(items, w, h) {
    const placed = [];
    items = items.slice().sort((a, b) => b.value - a.value);

    function recur(rect, row) {
        if (!row.length) return;
        const total = row.reduce((s, i) => s + i.value, 0);
        const wide = rect.w >= rect.h;
        const halfSize = total / 2;
        let acc = 0, splitAt = 1;
        for (let i = 0; i < row.length; i++) {
            acc += row[i].value;
            if (acc >= halfSize) { splitAt = i + 1; break; }
        }
        const head = row.slice(0, splitAt);
        const tail = row.slice(splitAt);
        const headTotal = head.reduce((s, i) => s + i.value, 0);
        const headFrac = total > 0 ? headTotal / total : 1;

        const headRect = wide
            ? { x: rect.x, y: rect.y, w: rect.w * headFrac, h: rect.h }
            : { x: rect.x, y: rect.y, w: rect.w, h: rect.h * headFrac };
        const tailRect = wide
            ? { x: rect.x + rect.w * headFrac, y: rect.y, w: rect.w * (1 - headFrac), h: rect.h }
            : { x: rect.x, y: rect.y + rect.h * headFrac, w: rect.w, h: rect.h * (1 - headFrac) };

        layoutStripe(headRect, head);
        if (tail.length) recur(tailRect, tail);
    }
    function layoutStripe(rect, row) {
        const total = row.reduce((s, i) => s + i.value, 0) || 1;
        const wide = rect.w >= rect.h;
        let pos = 0;
        for (const item of row) {
            const frac = item.value / total;
            const cell = wide
                ? { x: rect.x + rect.w * pos, y: rect.y, w: rect.w * frac, h: rect.h }
                : { x: rect.x, y: rect.y + rect.h * pos, w: rect.w, h: rect.h * frac };
            placed.push({ ...item, ...cell });
            pos += frac;
        }
    }
    recur({ x: 0, y: 0, w, h }, items);
    return placed;
}

function render() {
    const svg = document.getElementById("atlas");
    const rect = svg.getBoundingClientRect();
    const W = Math.max(400, rect.width);
    const H = Math.max(300, rect.height);
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = "";

    const placed = squarify(ATLAS.leaves, W, H);
    for (const cell of placed) {
        const r = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        r.setAttribute("x", cell.x.toFixed(1));
        r.setAttribute("y", cell.y.toFixed(1));
        r.setAttribute("width", Math.max(0, cell.w - 0.5).toFixed(1));
        r.setAttribute("height", Math.max(0, cell.h - 0.5).toFixed(1));
        r.setAttribute("fill", colorFor(cell));
        r.setAttribute("class", "cell");
        r.addEventListener("mouseover", () => showDetail(cell));
        r.addEventListener("click", () => showDetail(cell));
        svg.appendChild(r);

        if (cell.w > 70 && cell.h > 22) {
            const cov = cell.total ? Math.round(cell.hit / cell.total * 100) : 100;
            const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
            t.setAttribute("x", (cell.x + 7).toFixed(1));
            t.setAttribute("y", (cell.y + 17).toFixed(1));
            t.setAttribute("class", "cell-label");
            const trimmed = cell.name.length > 22 ? cell.name.slice(0, 21) + "…" : cell.name;
            t.textContent = `${trimmed}  ${cov}%`;
            svg.appendChild(t);
        }
    }
}

function showDetail(cell) {
    const aside = document.getElementById("detail");
    const cov = cell.total ? (cell.hit / cell.total) * 100 : 100;
    const ranges = cell.uncov || [];
    const fmtRange = ([a, b]) => a === b ? `line ${a}` : `lines ${a}–${b}`;

    aside.innerHTML = `
        <div class="detail-title">
            <span class="lang-badge" data-lang="${cell.lang}">${cell.lang}</span>${cell.path}
        </div>
        <div class="detail-meta">${cell.total} lines · ${cell.hit} hit · ${cell.total - cell.hit} unexplored</div>
        <div class="detail-pct">${cov.toFixed(1)}%</div>
        <div class="detail-bar">
            <div class="detail-bar-fill" style="width: ${cov}%; background: ${colorFor(cell)}"></div>
        </div>
        <div class="detail-h">${ranges.length} unexplored region${ranges.length === 1 ? "" : "s"}</div>
        ${ranges.length
            ? ranges.slice(0, 60).map(r => `<div class="detail-range">${fmtRange(r)}</div>`).join("") +
              (ranges.length > 60 ? `<div class="detail-range">… +${ranges.length - 60} more</div>` : "")
            : '<div class="detail-empty">fully charted</div>'}
    `;
}

window.addEventListener("resize", render);
render();
</script>
</body>
</html>
"""


def main() -> int:
    """CLI entrypoint: fuse pytest-cov + cargo-llvm-cov + vitest LCOV into one HTML atlas."""
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n", 1)[0])
    ap.add_argument("--python", type=Path, default=Path("coverage.xml"))
    ap.add_argument("--rust", type=Path, default=Path("target/llvm-cov/lcov.info"))
    ap.add_argument("--web", type=Path, default=Path("web/coverage/lcov.info"))
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--out", type=Path, default=Path("coverage-atlas.html"))
    args = ap.parse_args()

    root = args.root.resolve()
    web_root = root / "web"

    all_files: list[FileCov] = []
    all_files += parse_cobertura(args.python, "python", root)
    all_files += parse_lcov(args.rust, "rust", root, also_try=[])
    all_files += parse_lcov(args.web, "web", root, also_try=[web_root])

    if not all_files:
        print(
            "No coverage data found. Tried:",
            args.python,
            args.rust,
            args.web,
            sep="\n  ",
        )
        return 1

    atlas = build_atlas(all_files)
    html = HTML_TEMPLATE.replace("__ATLAS_JSON__", json.dumps(atlas))
    args.out.write_text(html)

    totals = atlas["totals"]
    pct = totals["hit"] / totals["total"] * 100 if totals["total"] else 0.0
    print(f"Pangaea → {args.out}  ({len(atlas['leaves'])} files, {pct:.1f}% charted)")
    for lang in sorted(totals["by_lang"]):
        b = totals["by_lang"][lang]
        lp = b["hit"] / b["total"] * 100 if b["total"] else 0.0
        print(
            f"  {lang:8s}  {b['files']:4d} files  {b['hit']}/{b['total']} = {lp:.1f}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
