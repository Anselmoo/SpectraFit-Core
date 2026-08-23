"""Figure: Listing 1, the composable model API in use.

Builds ``fig_code_compose.tex`` into the vector PDF used for submission
and the 300 dpi PNG used for preview. Unlike the other three figures in this
directory, the typesetting is LaTeX rather than matplotlib: a typeset code
listing keeps the example legible in a Word document, which is a poor host for
fenced code, and ``listings`` renders one properly.

Reproduce from a clean clone:

    uv run --group manuscript python manuscript/examples/figures/fig_code_compose.py

Outputs (written next to this file):
    fig_code_compose.pdf   vector, for submission
    fig_code_compose.png   300 dpi raster, for preview

This script needs a TeX distribution providing ``pdflatex`` and ``listings``,
and ``pdftoppm`` from poppler. That is a heavier requirement than the other
figures carry, and it is stated rather than hidden: if either is missing the
script exits with the reason and the committed PDF and PNG remain valid. They
are committed precisely so a reader without TeX is never blocked.

The code in the listing is executed rather than illustrative. Run against the
built extension on 2026-08-15 it returns ``r_squared`` 0.999198 on a seeded
Gaussian, with parameters keyed ``peak1.sigma``, ``peak1.center`` and
``peak1.amplitude``. A change to the public API invalidates this listing until
it has been re-run and regenerated.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEM = "fig_code_compose"
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
    """Typeset the code listing and write the PDF and PNG beside this file."""
    pdflatex = _require("pdflatex", "typeset the code listing")
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
