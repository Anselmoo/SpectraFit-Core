"""Pre-render all gallery example scripts to regenerate their ``_static/*.png``.

Run before ``zensical build`` so the docs site always ships thumbnails that
match the scripts currently checked in (rather than stale PNGs from a
previous edit). Wired into ``poe docs_build`` (see ``pyproject.toml``):

    uv run --group docs python docs/tutorials/gallery/_render.py
    uv run --group docs zensical build --clean

Each gallery script (``fitting.py``, ``3d_fitting.py``, ``multi_dataset_1d.py``,
``multi_dataset_2d.py``, ``shared_params.py``, ``varpro_vs_lm.py``,
``confidence_intervals.py``, ``spectrafit_vs_lmfit_moderate.py``,
``spectrafit_vs_lmfit_complex.py``) is a standalone, runnable example guarded by
``if __name__ == "__main__":`` for its plotting/``savefig`` step, and
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

import os
import subprocess
import sys
from pathlib import Path

GALLERY_DIR = Path(__file__).parent

#: `<repo>/python`, the directory holding the `spectrafit_core` package.
#:
#: Each script below runs with `cwd=GALLERY_DIR` so its `from _plotting import ...`
#: sibling import resolves — but that also breaks a RELATIVE `PYTHONPATH`. CI sets
#: `PYTHONPATH=python`, which resolves from the repo root and becomes
#: `docs/tutorials/gallery/python` (nonexistent) once cwd changes, so every script
#: dies with `ModuleNotFoundError: No module named 'spectrafit_core'`.
#:
#: This was latent for as long as this renderer existed: `maturin develop` used to
#: leave an editable install in `.venv` with an ABSOLUTE `.pth`, so the module was
#: importable from any cwd. `.gitlab/65-docs.yml` stopped running `maturin develop`
#: on 2026-08-02 (the extension is now pulled from `build:ext:dev` as an artifact),
#: which removed the `.pth` and exposed the bug — GitLab job 5091149.
#:
#: Resolving to an absolute path here fixes it for CI and for anyone running this
#: script by hand from a directory other than the repo root.
PYTHON_SRC = (GALLERY_DIR.parents[2] / "python").resolve()

# Order matches the gallery's markdown pages (fitting -> 3d -> multi_dataset
# 1d/2d -> shared_params -> varpro_vs_lm -> confidence_intervals -> the two
# spectrafit-vs-lmfit tiers); not load-bearing, just readable in log output.
SCRIPTS: tuple[str, ...] = (
    "fitting.py",
    "3d_fitting.py",
    "multi_dataset_1d.py",
    "multi_dataset_2d.py",
    "shared_params.py",
    "varpro_vs_lm.py",
    "confidence_intervals.py",
    "spectrafit_vs_lmfit_moderate.py",
    "spectrafit_vs_lmfit_complex.py",
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
        # Prepend the ABSOLUTE python/ dir — see PYTHON_SRC. Prepend rather than
        # replace so an inherited PYTHONPATH (e.g. a contributor's own entries)
        # still applies.
        env = dict(os.environ)
        inherited = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{PYTHON_SRC}{os.pathsep}{inherited}" if inherited else str(PYTHON_SRC)
        )
        subprocess.run(
            [sys.executable, str(script_path)],
            cwd=GALLERY_DIR,
            check=True,
            env=env,
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
