"""The published wheel must contain exactly one top-level Python package:
``spectrafit_core`` (plus its compiled ``_core`` extension). ``benchmark`` and
``oracles`` are repo-internal dev tooling and must never leak into installers'
global import namespace.

The 2026-06-23 release audit confirmed the built wheel already ships only
``spectrafit_core`` (maturin excludes sibling packages by default), so the
``python-packages`` allow-list below is a GUARD that pins that behaviour against
a future maturin change — not a fix for a current leak.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_maturin_scopes_wheel_to_kernel_only() -> None:
    data = tomllib.loads(_PYPROJECT.read_text())
    maturin = data["tool"]["maturin"]
    assert maturin.get("python-source") == "python"
    assert maturin.get("python-packages") == ["spectrafit_core"], (
        "maturin must allow-list only 'spectrafit_core' so benchmark/oracles "
        "don't ship in the wheel — see Option A packaging decision 2026-06-20"
    )
