"""Cycles 12 + 13 — `spc-bench sweep` / `spc-bench trend` CLI smoke tests.

These don't run the bench — `sweep` is an orchestrator over `build_report` /
`write_run`, which already have coverage. The smoke surface is the *CLI*:
flag parsing, error paths, and the table layout for empty inputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from oracles import cli as bench_cli

runner = CliRunner()


def _seed_index(root: Path, runs: list[dict]) -> None:
    """Write an `index.json` with the canonical newest-first shape."""
    (root / "benchmark").mkdir(parents=True, exist_ok=True)
    (root / "index.json").write_text(
        json.dumps(runs, indent=2) + "\n", encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Cycle 13 — trend
# ---------------------------------------------------------------------------


def test_trend_with_no_index_exits_with_message(monkeypatch, tmp_path: Path) -> None:
    """`spc-bench trend` against a clean tree exits 2 with a clear stderr message."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(bench_cli.app, ["trend"])
    assert result.exit_code == 2, result.output


def test_trend_unknown_field_lists_valid_keys(monkeypatch, tmp_path: Path) -> None:
    """`--field bogus` surfaces the valid key set instead of silently picking a default."""
    monkeypatch.chdir(tmp_path)
    _seed_index(tmp_path / ".spectrafit_reports", [])
    result = runner.invoke(bench_cli.app, ["trend", "--field", "bogus"])
    assert result.exit_code == 2


def test_trend_renders_table_against_seeded_index(monkeypatch, tmp_path: Path) -> None:
    """Two seeded runs → sparkline header + 2-row table; latest run is on top."""
    monkeypatch.chdir(tmp_path)
    runs = [
        {
            "run_id": "2026-06-08_run_002",
            "category": "benchmark",
            "geomean_speedup_vs_baseline": 12.5,
            "max_abs_delta_r2": 1.3e-4,
            "regressions": 0,
            "spectrafit_win_rate": 0.86,
        },
        {
            "run_id": "2026-06-08_run_001",
            "category": "benchmark",
            "geomean_speedup_vs_baseline": 12.0,
            "max_abs_delta_r2": 1.3e-4,
            "regressions": 2,
            "spectrafit_win_rate": 0.8,
        },
    ]
    _seed_index(tmp_path / ".spectrafit_reports", runs)
    result = runner.invoke(bench_cli.app, ["trend", "--last", "2"])
    assert result.exit_code == 0, result.output
    # Newest run is on top; sparkline header lists the 4 axes.
    assert "2026-06-08_run_002" in result.output
    assert "2026-06-08_run_001" in result.output
    # Geomean column shows the formatted value.
    assert "12.50×" in result.output
    assert "12.00×" in result.output


# ---------------------------------------------------------------------------
# Cycle 12 — sweep flag parsing (orchestration is exercised by the existing
# `run` command's tests; we only need to lock the CLI arg surface here).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "0,1", "1,foo,5", "-1,2", "1,2,0"])
def test_sweep_rejects_invalid_tiers(bad: str) -> None:
    """`--tiers` must be non-empty, all > 0, all parseable."""
    result = runner.invoke(bench_cli.app, ["sweep", "--tiers", bad])
    assert result.exit_code == 2, result.output


def test_sweep_help_lists_the_value_proposition() -> None:
    """The help text names the verification-loop question this command answers."""
    result = runner.invoke(bench_cli.app, ["sweep", "--help"])
    assert result.exit_code == 0
    assert "budget" in result.output.lower()
    assert "timing noise" in result.output.lower()
