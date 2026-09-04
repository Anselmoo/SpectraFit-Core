#!/usr/bin/env python3
"""Check `fecl4_constraint_scenarios.json` for drift, from a `scripts/` entrypoint.

``manuscript/examples/fecl4/fecl4_constraint_scenarios.py`` is a direct
manuscript entrypoint, not a ``scripts/``-level tool: it needs the
``manuscript`` dependency group (matplotlib, by way of its sibling
``fig_fecl4_case_study.py``) and it resolves a bare ``import
fig_fecl4_case_study`` that only works when it is launched as its own script,
not imported into another process (see ``render_figures.py``'s module
docstring, "The safety boundary"). Every other ``manuscript_*`` poe task in
``pyproject.toml`` points at a ``scripts/*.py`` wrapper rather than a raw path
under ``manuscript/`` — this is that wrapper for the fecl4 constraint-scenario
drift check, run as::

    uv run python manuscript fecl4

It subprocesses the manuscript script itself (mirroring ``render_figures.py``
's ``run_one``) rather than importing or reimplementing its drift logic: the
script's own ``--check`` flag is already the source of truth for what
"drifted" means, so duplicating that logic here would be a second place for it
to go stale. The one thing this wrapper adds is a clear diagnostic — rather
than a bare traceback — when the ``manuscript`` dependency group has not been
synced into the running environment.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "manuscript/examples/fecl4/fecl4_constraint_scenarios.py"


def main() -> int:
    """Run the manuscript script's own `--check`, forwarding its output and exit status."""
    if not TARGET.exists():
        print(f"note: {TARGET.relative_to(ROOT)} not found; nothing to check")
        return 0

    proc = subprocess.run(
        [sys.executable, TARGET.name, "--check"],
        cwd=TARGET.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)

    if proc.returncode != 0 and "ModuleNotFoundError" in proc.stderr:
        print(
            "\nhint: the `manuscript` dependency group is not installed in this "
            "environment. Run `uv sync --group manuscript`, then re-run "
            "`uv run python manuscript fecl4`.",
            file=sys.stderr,
        )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
