"""Anti-regression: the in-repo bench CLI works via ``python -m oracles.cli``,
and NO ``spc-bench`` console script is published.

Packaging decision (Option A, 2026-06-20): the ``[project.scripts]`` entry was
removed because a console script is written into every wheel's
``entry_points.txt`` regardless of which extras the installer selected — so a
clean ``pip install spectrafit-core`` (numpy+pydantic only) would register a
``spc-bench`` that ImportErrors on ``import typer``. In-repo, the bench runs via
``python -m oracles.cli`` (under ``PYTHONPATH=python``) and ``uv run poe
benchmark``. These tests pin that contract so we never silently re-add the broken
script.
"""

from __future__ import annotations

import tomllib
from importlib.metadata import entry_points
from pathlib import Path

from oracles import cli

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_dunder_main_cli_help_returns_zero() -> None:
    """``python -m oracles.cli --help`` path: ``cli.main(['--help'])`` exits 0."""
    assert cli.main(["--help"]) == 0


def test_no_spc_bench_console_script_published() -> None:
    """Regression guard: no ``spc-bench`` console entry exists (Option A removed it)."""
    eps = entry_points(group="console_scripts")
    names = {ep.name for ep in eps}
    assert "spc-bench" not in names, (
        "spc-bench console script re-introduced — a wheel-shipped console script "
        "whose deps live in the [benchmark] extra ImportErrors on a clean install. "
        "Run the bench via 'python -m oracles.cli' / 'uv run poe benchmark'."
    )


def test_pyproject_declares_no_project_scripts() -> None:
    """``[project.scripts]`` must stay absent (the config-level invariant)."""
    data = tomllib.loads(_PYPROJECT.read_text())
    assert "scripts" not in data.get("project", {}), (
        "[project.scripts] re-added — see tests/meta/test_console_scripts.py"
    )
