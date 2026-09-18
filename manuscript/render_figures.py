#!/usr/bin/env python3
"""Regenerate every manuscript figure in one shot.

Regenerating the paper's figures used to mean remembering which scripts exist,
which directory each has to run from, and which need a TeX toolchain. They
live in two directories (``manuscript/examples/figures/`` and
``manuscript/examples/fecl4/``); some are pure matplotlib, some shell out to
``pdflatex`` + ``pdftoppm``; all of them write a PDF and a 300 dpi PNG beside
themselves. Getting one wrong used to mean a stale image shipped silently.
It no longer can: ``manuscript/render_manuscript.py --check`` sha256s every
*registered* figure's raster against ``.render-manifest.json``, so a miss is
now a failed gate. This script is the other half of that guarantee — the one
command that regenerates the inputs to that gate.

**Discovery, not a list.** A hardcoded file list is exactly what went stale in
``scripts/build_fair_package.py`` (it named 20 files and missed 46 real
inputs). This globs ``fig_*.py`` in both figure directories instead, so a new
figure script is picked up the next time this runs, with no second place to
remember to update. Not every ``fig_*.py`` is a figure the manuscript prints —
some are appendix or standalone (see ``manuscript-state.json``'s registered
``figures`` list) — so this reports what it found and what it ran rather than
assuming every discovered script belongs to the paper.

**The safety boundary.** ``manuscript/examples/fecl4/fecl4_constraint_scenarios.py``
sits beside ``fig_constraint_grid.py`` and is imported by it (safe — its JSON
write is behind ``if __name__ == "__main__"``). It must never be *executed* as
a script here: running it re-times seven fits and rewrites
``fecl4_constraint_scenarios.json``, moving every millisecond quoted in the
manuscript's Table 2. The guard is not a name on a "do not run" list — it is
structural: this script only ever globs and executes ``fig_*.py``, and
``fecl4_constraint_scenarios.py`` does not match that pattern. Widening the
glob (e.g. to ``*.py``) would defeat the one property this script exists to
guarantee, so don't.

**Each figure runs from its own directory.** Several resolve inputs relative
to ``__file__`` (``fig_ladder_stability.py`` reads ``../ladder/`` and
``../seed-sweep/``; ``fig_model_graph.py`` reads ``../fecl4/``;
``fig_architecture.py`` climbs to the repo root for ``crates/``) or import a
sibling module by bare name (``fig_constraint_grid.py`` does
``import fecl4_constraint_scenarios``, which only resolves because Python adds
a script's own directory to ``sys.path`` when it is run directly). Both are
why each figure is launched as its own subprocess with its own directory on
``sys.path`` and as the current working directory, not imported into this
process.

**TeX is optional.** ``fig_algorithm_dispatch.py``, ``fig_code_compose.py``,
``fig_code_constraints.py`` and ``fig_code_benchmark.py`` need ``pdflatex``
(with ``algorithm2e``) and ``pdftoppm`` from poppler. Rather than hardcode
that list a second time, this detects the requirement from the script's own
source — every one of them calls ``_require("pdflatex", ...)``, so grepping
for the literal string ``pdflatex`` finds exactly the same four scripts
without a list that can drift from ``scripts/``. When either tool is missing,
those figures are skipped with a clear reason, not failed — their PDF and PNG
are committed, so a reader without TeX is never blocked.

Usage::

    python manuscript/render_figures.py                  # render in place
    python manuscript/render_figures.py --check           # report drift only
    python manuscript/render_figures.py --only nist        # subset by name

``--check`` renders every figure into an isolated copy of the repository (real
directories for the two writable figure trees, read-only symlinks for
everything else a figure might legitimately read — the ``ladder/``,
``seed-sweep/`` and ``nist_unimplemented/`` siblings, and the repo root for
``fig_architecture.py``'s crate manifests) and reports which figures *would*
change without writing a single byte into the working tree.

Exit status is non-zero if any attempted figure fails; skipped (missing-TeX)
figures do not count as failures.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FIGURE_DIRS: tuple[Path, ...] = (
    ROOT / "manuscript/examples/figures",
    ROOT / "manuscript/examples/fecl4",
)
STATE_FILE = ROOT / "manuscript/draft/manuscript-state.json"

# Tools the TeX-typeset figures need. Which *scripts* need them is discovered
# from source (see module docstring), not listed here — this tuple only names
# the tools themselves, which genuinely have no other source of truth.
TEX_TOOLS: tuple[str, ...] = ("pdflatex", "pdftoppm")

# The two figure directories are copied, writable, into the --check tree; every
# other entry anywhere in the repository is symlinked in read-only. This is
# what lets fig_architecture.py's climb to the repo root for `crates/`, and
# fig_ladder_stability.py's reach into the `../ladder/` and `../seed-sweep/`
# siblings, resolve correctly inside --check without this script having to
# know about either dependency by name.
WRITABLE_DIR_NAMES = frozenset({"figures", "fecl4"})


@dataclass
class FigureResult:
    """The outcome of attempting to render one figure script."""

    script: Path
    status: str  # "ok" | "failed" | "skipped"
    seconds: float
    changed: bool | None  # None when status != "ok"
    detail: str = ""


def discover(only: str | None) -> list[Path]:
    """Glob every figure script, then narrow with --only if given.

    The glob is the safety boundary described in the module docstring: it is
    always ``fig_*.py``, never widened, regardless of --only. --only only ever
    removes candidates that the glob already found; it cannot add one back.
    """
    found: list[Path] = []
    for d in FIGURE_DIRS:
        found.extend(sorted(d.glob("fig_*.py")))
    for script in found:
        matches_boundary = script.name.startswith("fig_") and script.suffix == ".py"
        assert matches_boundary, f"discovery invariant violated: {script} does not match fig_*.py"
    if only is None:
        return found
    pattern = only if any(c in only for c in "*?[") else f"*{only}*"
    return [s for s in found if fnmatch.fnmatch(s.stem, pattern)]


def registered_figures() -> dict[str, dict[str, Any]]:
    """Map a figure script's expected PNG (repo-relative) to its manuscript entry.

    Empty, with a note, if the state file is missing rather than raising — this
    script's job is to render figures, and a missing state file is
    render_manuscript.py's problem to report, not a reason to refuse to run.
    """
    if not STATE_FILE.exists():
        print(f"note: {STATE_FILE.relative_to(ROOT)} not found; cannot report registration")
        return {}
    state = json.loads(STATE_FILE.read_text())
    return {fig["files"]["raster_300dpi"]: fig for fig in state.get("figures", [])}


def needs_tex(script: Path) -> bool:
    """Detect a TeX dependency from the script's own source (see docstring)."""
    return all(tool in script.read_text() for tool in TEX_TOOLS)


def missing_tex_tools() -> list[str]:
    """Return the names of any TEX_TOOLS not found on PATH."""
    return [tool for tool in TEX_TOOLS if shutil.which(tool) is None]


def sha256_of(path: Path) -> str | None:
    """Return a file's sha256, or None if it does not exist."""
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_check_tree(tmp: Path) -> dict[str, Path]:
    """Mirror the repo into `tmp`.

    Real copies of the writable figure dirs, read-only symlinks for everything
    else. Returns {dir_name: temp_path} for "figures" and "fecl4", which is
    where a discovered script's temp-tree twin lives.
    """
    for entry in ROOT.iterdir():
        if entry.name == "manuscript":
            continue
        (tmp / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())

    man_dst = tmp / "manuscript"
    man_dst.mkdir()
    for entry in (ROOT / "manuscript").iterdir():
        if entry.name == "examples":
            continue
        (man_dst / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())

    ex_dst = man_dst / "examples"
    ex_dst.mkdir()
    mapping: dict[str, Path] = {}
    for entry in (ROOT / "manuscript/examples").iterdir():
        if entry.name in WRITABLE_DIR_NAMES:
            dst = ex_dst / entry.name
            shutil.copytree(entry, dst, ignore=shutil.ignore_patterns("__pycache__"))
            mapping[entry.name] = dst
        else:
            (ex_dst / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
    return mapping


def _reproducible_env() -> dict[str, str]:
    """The child's environment, pinned so a re-render is byte-identical.

    Only the PNG is hashed for the changed/unchanged verdict, and PNGs were
    already stable. The PDFs were not: matplotlib stamps `/CreationDate` and
    pdfTeX stamps `/CreationDate`, `/ModDate` and a trailer `/ID`, so every run
    rewrote all ten vector files with identical content and a new timestamp.
    `git status` then showed ten modified figures after a no-op render, which
    trains a reader to ignore exactly the diff that would reveal a real change.

    Both toolchains honour SOURCE_DATE_EPOCH, so one variable fixes both. The
    value is the project's own epoch rather than `now`; it only has to be
    constant. PYTHONHASHSEED is pinned for the same reason -- set iteration order
    leaked into at least one committed JSON sidecar.
    """
    env = dict(os.environ)
    env.setdefault("SOURCE_DATE_EPOCH", "1700000000")  # 2023-11-14, arbitrary but fixed
    env.setdefault("PYTHONHASHSEED", "0")
    return env


def run_one(script: Path, run_dir: Path, real_png: Path) -> FigureResult:
    """Execute one figure script and report whether its PNG changed.

    `run_dir` is both its cwd and its __file__-relative base. Comparison is
    against `real_png` — the working-tree location whose hash is the one that
    matters, whether or not this run happened to write there directly (it does
    not, in --check mode).
    """
    before = sha256_of(real_png)
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, script.name],
        cwd=run_dir,
        capture_output=True,
        text=True,
        check=False,
        env=_reproducible_env(),
    )
    elapsed = time.monotonic() - started
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or proc.stdout).strip().splitlines()[-15:])
        return FigureResult(script, "failed", elapsed, None, detail=tail)

    after_png = run_dir / f"{script.stem}.png"
    after = sha256_of(after_png)
    if after is None:
        return FigureResult(
            script,
            "failed",
            elapsed,
            None,
            detail=f"script exited 0 but wrote no {after_png.name}",
        )
    return FigureResult(script, "ok", elapsed, changed=(before != after))


def render(scripts: list[Path], check: bool) -> list[FigureResult]:
    """Run every discovered script, in --check isolation if requested."""
    results: list[FigureResult] = []
    missing = missing_tex_tools()

    tmp_ctx = tempfile.TemporaryDirectory(prefix="render_figures_check_") if check else None
    mapping: dict[str, Path] = {}
    try:
        if tmp_ctx is not None:
            mapping = build_check_tree(Path(tmp_ctx.name))

        for script in scripts:
            real_png = script.with_suffix(".png")
            if needs_tex(script) and missing:
                results.append(
                    FigureResult(
                        script,
                        "skipped",
                        0.0,
                        None,
                        detail=f"missing on PATH: {', '.join(missing)}",
                    ),
                )
                continue
            run_dir = mapping[script.parent.name] if check else script.parent
            results.append(run_one(script, run_dir, real_png))
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()
    return results


def report(results: list[FigureResult], registered: dict[str, dict[str, Any]], check: bool) -> int:
    """Print the per-figure and summary report; return the process exit status."""
    mode = "would change (--check)" if check else "changed"
    ok = [r for r in results if r.status == "ok"]
    failed = [r for r in results if r.status == "failed"]
    skipped = [r for r in results if r.status == "skipped"]

    width = max((len(r.script.name) for r in results), default=0)
    for r in results:
        rel = r.script.relative_to(ROOT).parent.as_posix()
        fig = registered.get(f"{rel}/{r.script.stem}.png")
        tag = f"Figure {fig['number']}" if fig else "not registered"
        name = r.script.name.ljust(width)
        if r.status == "ok":
            change = mode if r.changed else "unchanged"
            print(f"  ok      {name}  {r.seconds:5.1f}s  {change:<22} [{tag}]")
        elif r.status == "skipped":
            print(f"  skipped {name}  {'':>6}  {r.detail:<22} [{tag}]")
        else:
            print(f"  FAILED  {name}  {r.seconds:5.1f}s  [{tag}]")
            for line in r.detail.splitlines():
                print(f"            {line}")

    print()
    print(
        f"{len(results)} figure(s) discovered: {len(ok)} ok, "
        f"{len(failed)} failed, {len(skipped)} skipped",
    )
    changed = [r for r in ok if r.changed]
    if changed:
        label = "would change" if check else "changed"
        print(f"{len(changed)} figure(s) {label}:")
        for r in changed:
            rel = r.script.relative_to(ROOT).parent.as_posix()
            fig = registered.get(f"{rel}/{r.script.stem}.png")
            note = (
                f" — Figure {fig['number']}, re-run manuscript/render_manuscript.py" if fig else ""
            )
            print(f"  {r.script.stem}.png{note}")
    if failed:
        names = ", ".join(r.script.name for r in failed)
        print(f"FAILED: {names}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    """Discover, render and report on every manuscript figure script."""
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="render into an isolated copy of the repo; report drift, touch nothing",
    )
    ap.add_argument(
        "--only",
        metavar="PATTERN",
        default=None,
        help="only run scripts whose stem matches PATTERN (substring, or glob if it has * ? [)",
    )
    args = ap.parse_args()

    scripts = discover(args.only)
    if not scripts:
        print(f"no fig_*.py matched --only {args.only!r}", file=sys.stderr)
        return 1

    registered = registered_figures()
    print(f"discovered {len(scripts)} figure script(s):")
    for s in scripts:
        rel = s.relative_to(ROOT).parent.as_posix()
        fig = registered.get(f"{rel}/{s.stem}.png")
        tag = f"Figure {fig['number']} ({fig['id']})" if fig else "not in manuscript-state.json"
        print(f"  {s.relative_to(ROOT)}  [{tag}]")
    print()

    missing = missing_tex_tools()
    if missing:
        print(f"note: {', '.join(missing)} not on PATH — TeX-based figures will be skipped\n")

    results = render(scripts, args.check)
    return report(results, registered, args.check)


if __name__ == "__main__":
    raise SystemExit(main())
