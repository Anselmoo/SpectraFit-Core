"""Tests for the ``spc-bench narrate`` Typer command.

The command turns a run's ``manifest.json`` into a Markdown release-notes
paragraph deterministically — same manifest in, byte-identical paragraph out.
These tests pin three properties:

1. The prose contains every load-bearing fact (speedup, accuracy, win-rate,
   regression ids, run id, n_cases, baseline solver).
2. The output is deterministic for a fixed manifest (no clocks, no RNG, no
   set/dict-iteration order leaks).
3. The command tolerates the one-cycle legacy manifest key
   (``geomean_speedup_vs_lmfit``) so old runs on disk still narrate.
4. The command exits gracefully (exit 2, no traceback) when there is no run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from oracles import reports as reports_mod
from oracles.cli import _narrate_from_manifest, app

_RUNNER = CliRunner()


def _synthetic_manifest() -> dict:
    """A manifest mirroring the contract shape, with known fixed values.

    Hand-built (not from ``synth.build_report`` → ``write_run``) so the
    expected fragments in the assertions are pinned to fixed numbers — a
    synthetic full run would produce numbers that drift if seed math changes.
    """
    return {
        "run_id": "2026-06-06_run_012",
        "date": "2026-06-06",
        "category": "benchmark",
        "schema_version": "1.1",
        "backends": ["spectrafit", "lmfit", "jax"],
        "featured_ids": ["EZ-011"],
        "n_cases": 139,
        "geomean_speedup_vs_baseline": 12.5,
        "geomean_speedup_vs_lmfit": 12.5,
        "baseline_solver_id": "lmfit",
        "max_abs_delta_r2": 1.3e-04,
        "spectrafit_win_rate": 0.885,
        "regressions": 2,
        "regression_case_ids": ["CX-017", "OF-005"],
        "artifacts": ["results.json", "manifest.json"],
    }


def _write_manifest(tmp_path: Path, manifest: dict) -> Path:
    """Lay out ``<tmp>/<category>/<run_id>/manifest.json`` + ``index.json``."""
    cat_dir = tmp_path / manifest["category"]
    run_dir = cat_dir / manifest["run_id"]
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    # ``latest_run_dir`` reads index.json; populate it so the no-args invocation
    # finds the run rather than returning None.
    (tmp_path / "index.json").write_text(
        json.dumps([manifest], indent=2) + "\n", encoding="utf-8"
    )
    return run_dir


def test_narrate_prose_contains_every_required_fact() -> None:
    """The paragraph must spell out every headline metric the manifest carries."""
    manifest = _synthetic_manifest()
    prose = _narrate_from_manifest(manifest)
    # Speed: ``12.5×`` (one decimal, U+00D7 multiplier sign).
    assert "12.5×" in prose
    assert "geomean" in prose
    # Accuracy: scientific notation with one decimal, ``1.3e-04``.
    assert "1.3e-04" in prose
    # Win rate: one decimal percent.
    assert "88.5%" in prose
    # Suite size.
    assert "139" in prose
    # Run id (round-trip).
    assert "2026-06-06_run_012" in prose
    # Baseline solver name.
    assert "lmfit" in prose
    # Every regression id is enumerated, not truncated.
    assert "CX-017" in prose
    assert "OF-005" in prose


def test_narrate_is_deterministic_for_a_fixed_manifest() -> None:
    """Byte-identical output for the same input — no clocks / iteration leaks."""
    manifest = _synthetic_manifest()
    a = _narrate_from_manifest(manifest)
    b = _narrate_from_manifest(manifest)
    assert a == b
    # And the prose itself is a single line (release-notes paragraph), not a multi-line dump.
    assert "\n" not in a


def test_narrate_zero_regressions_says_so() -> None:
    """A clean run names the absence of regressions — not just an empty list."""
    manifest = _synthetic_manifest()
    manifest["regression_case_ids"] = []
    manifest["regressions"] = 0
    prose = _narrate_from_manifest(manifest)
    assert "No regressions" in prose


def test_narrate_legacy_geomean_key_still_works() -> None:
    """A pre-1.1 manifest (only ``geomean_speedup_vs_lmfit``) still narrates."""
    manifest = _synthetic_manifest()
    del manifest["geomean_speedup_vs_baseline"]
    prose = _narrate_from_manifest(manifest)
    assert "12.5×" in prose


def test_narrate_command_emits_paragraph_for_latest_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end CLI invocation reads ``manifest.json`` and prints the paragraph."""
    manifest = _synthetic_manifest()
    _write_manifest(tmp_path, manifest)
    monkeypatch.setattr(reports_mod, "REPORTS_ROOT", tmp_path)
    # The CLI imports ``REPORTS_ROOT`` and ``latest_run_dir`` from
    # ``oracles.reports`` at module load — patch both attributes the
    # command actually references.
    from oracles import cli as cli_mod

    monkeypatch.setattr(cli_mod, "REPORTS_ROOT", tmp_path)

    result = _RUNNER.invoke(app, ["narrate"])
    assert result.exit_code == 0, result.output
    assert "12.5×" in result.output
    assert "2026-06-06_run_012" in result.output
    assert "CX-017" in result.output


def test_narrate_command_specific_run_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--run <id>`` selects a specific run instead of the latest."""
    manifest = _synthetic_manifest()
    _write_manifest(tmp_path, manifest)
    monkeypatch.setattr(reports_mod, "REPORTS_ROOT", tmp_path)
    from oracles import cli as cli_mod

    monkeypatch.setattr(cli_mod, "REPORTS_ROOT", tmp_path)

    result = _RUNNER.invoke(app, ["narrate", "--run", manifest["run_id"]])
    assert result.exit_code == 0, result.output
    assert manifest["run_id"] in result.output


def test_narrate_command_errors_gracefully_when_no_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty reports tree → exit 2 with a stderr message, not a traceback."""
    monkeypatch.setattr(reports_mod, "REPORTS_ROOT", tmp_path)
    from oracles import cli as cli_mod

    monkeypatch.setattr(cli_mod, "REPORTS_ROOT", tmp_path)

    result = _RUNNER.invoke(app, ["narrate"])
    assert result.exit_code == 2
    # CliRunner merges stderr into output by default; the operator-facing
    # message must be present so a fresh checkout does not look like a crash.
    assert "no runs" in result.output.lower()


def test_narrate_command_errors_when_specific_run_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--run <unknown>`` exits 2 with a clear message."""
    monkeypatch.setattr(reports_mod, "REPORTS_ROOT", tmp_path)
    from oracles import cli as cli_mod

    monkeypatch.setattr(cli_mod, "REPORTS_ROOT", tmp_path)

    result = _RUNNER.invoke(app, ["narrate", "--run", "1999-01-01_run_999"])
    assert result.exit_code == 2
    assert "not found" in result.output.lower()


def test_narrate_command_output_is_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running the CLI twice on the same manifest gives byte-identical stdout."""
    manifest = _synthetic_manifest()
    _write_manifest(tmp_path, manifest)
    monkeypatch.setattr(reports_mod, "REPORTS_ROOT", tmp_path)
    from oracles import cli as cli_mod

    monkeypatch.setattr(cli_mod, "REPORTS_ROOT", tmp_path)

    r1 = _RUNNER.invoke(app, ["narrate"])
    r2 = _RUNNER.invoke(app, ["narrate"])
    assert r1.exit_code == 0
    assert r2.exit_code == 0
    assert r1.output == r2.output
