"""Figure: Algorithm 1, solver dispatch.

Builds ``fig_algorithm_dispatch.tex`` into the vector PDF used for submission
and the 300 dpi PNG used for preview. Unlike the other three figures in this
directory, the typesetting is LaTeX rather than matplotlib: an algorithm float
is what the venue's reference papers use, and ``algorithm2e`` renders one
properly.

Reproduce from a clean clone:

    uv run --group manuscript python manuscript/examples/figures/fig_algorithm_dispatch.py

Outputs (written next to this file):
    fig_algorithm_dispatch.pdf   vector, for submission
    fig_algorithm_dispatch.png   300 dpi raster, for preview

This script needs a TeX distribution providing ``pdflatex`` and ``algorithm2e``,
and ``pdftoppm`` from poppler. That is a heavier requirement than the other
figures carry, and it is stated rather than hidden: if either is missing the
script exits with the reason and the committed PDF and PNG remain valid. They
are committed precisely so a reader without TeX is never blocked.

The pseudocode mirrors ``graph_prefers_varpro`` in
``crates/spectrafit-solver/src/dispatch.rs``. That function has four conjuncts;
an earlier version of this figure showed three, omitting the guard that keeps
variable projection from being auto-selected for simultaneous multi-dataset
graphs. Changing the Rust function invalidates this figure until it is rebuilt.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEM = "fig_algorithm_dispatch"
DPI = 300


def _require(tool: str, why: str) -> str:
    found = shutil.which(tool)
    if found is None:
        sys.exit(
            f"{STEM}: {tool!r} not found on PATH, needed to {why}.\n"
            f"The committed {STEM}.pdf and {STEM}.png are unchanged and remain "
            f"valid; install {tool} only if you need to regenerate them.",
        )
    return found


def build() -> None:
    """Typeset the algorithm float and write the PDF and PNG beside this file."""
    pdflatex = _require("pdflatex", "typeset the algorithm float")
    pdftoppm = _require("pdftoppm", "rasterise the PDF for preview")

    source = HERE / f"{STEM}.tex"
    if not source.is_file():
        sys.exit(f"{STEM}: missing source {source}")

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copy2(source, work / source.name)
        result = subprocess.run(
            [pdflatex, "-interaction=nonstopmode", "-halt-on-error", source.name],
            cwd=work,
            capture_output=True,
            text=True,
            check=False,
        )
        built = work / f"{STEM}.pdf"
        if result.returncode != 0 or not built.is_file():
            log = work / f"{STEM}.log"
            tail = log.read_text(errors="replace").splitlines()[-25:] if log.is_file() else []
            sys.exit(f"{STEM}: pdflatex failed.\n" + "\n".join(tail))

        shutil.copy2(built, HERE / f"{STEM}.pdf")
        subprocess.run(
            [pdftoppm, "-png", "-r", str(DPI), "-singlefile", str(built), str(HERE / STEM)],
            check=True,
        )

    print(f"wrote {STEM}.pdf / .png")


if __name__ == "__main__":
    build()
