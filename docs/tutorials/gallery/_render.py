"""Pre-render all gallery example scripts to regenerate their ``_static/*.png``.

Run before ``zensical build`` so the docs site always ships thumbnails that
match the scripts currently checked in (rather than stale PNGs from a
previous edit). Wired into ``poe docs_build`` (see ``pyproject.toml``):

    uv run --group docs python docs/tutorials/gallery/_render.py
    uv run --group docs zensical build --clean

Each gallery script (``fitting.py``, ``3d_fitting.py``, ``multi_dataset_1d.py``,
``multi_dataset_2d.py``, ``shared_params.py``) is a standalone, runnable example
guarded by ``if __name__ == "__main__":`` for its plotting/``savefig`` step, and
each already writes to ``docs/tutorials/gallery/_static/<name>.png`` via the
shared ``_plotting.savefig`` helper. Rather than importing and refactoring
each script to expose a common entry function (invasive: two of the five run
top-level fit/print code unconditionally, only guarding the plot), this
just re-executes each script the same way a contributor would from the
command line: ``python <script>.py``, run as a subprocess with this
directory as the working directory so the scripts' own
``from _plotting import ...`` sibling import resolves.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

GALLERY_DIR = Path(__file__).parent

# Order matches the gallery's markdown pages (fitting -> 3d -> multi_dataset
# 1d/2d -> shared_params); not load-bearing, just readable in log output.
SCRIPTS: tuple[str, ...] = (
    "fitting.py",
    "3d_fitting.py",
    "multi_dataset_1d.py",
    "multi_dataset_2d.py",
    "shared_params.py",
)


def render_all(scripts: tuple[str, ...] = SCRIPTS) -> list[Path]:
    """Run each gallery script as ``__main__``, returning the PNG paths written.

    Raises:
        subprocess.CalledProcessError: if any script exits non-zero.
    """
    written: list[Path] = []
    for script in scripts:
        script_path = GALLERY_DIR / script
        print(f"[gallery] rendering {script} ...")
        subprocess.run(
            [sys.executable, str(script_path)],
            cwd=GALLERY_DIR,
            check=True,
        )
        png_path = GALLERY_DIR / "_static" / f"{script_path.stem}.png"
        if not png_path.exists():
            msg = f"{script} ran but did not write expected {png_path}"
            raise FileNotFoundError(msg)
        written.append(png_path)
        print(f"[gallery]   -> {png_path}")
    return written


def main() -> None:
    """Render every gallery script and report the PNGs written."""
    written = render_all()
    print(f"\n[gallery] wrote {len(written)} PNG(s) to {GALLERY_DIR / '_static'}")


if __name__ == "__main__":
    main()
