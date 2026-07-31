"""Unit tests for `oracles.cli._resolve_run_backends` — the --backends/--baseline
resolution behind `spc-bench run --backends spectrafit` (the fast, single-backend
smoke/gate pipeline used by CI's build:report_html:solo / regression-gate-solo jobs).
"""

from __future__ import annotations

import pytest
import typer
from oracles import cli as bench_cli
from oracles.cli import _resolve_run_backends
from typer.testing import CliRunner

runner = CliRunner()


def test_default_backends_returns_full_roster_with_lmfit_baseline() -> None:
    """No --backends/--baseline -> every available backend, baseline 'lmfit'
    (unchanged default — must not regress the existing full-suite CI jobs)."""
    resolved, baseline_id = _resolve_run_backends(None, None)
    names = {b.name for b in resolved}
    assert "spectrafit" in names
    assert baseline_id == "lmfit"


def test_single_backend_auto_derives_baseline_to_that_backend() -> None:
    """--backends spectrafit (no --baseline) -> baseline auto-resolves to 'spectrafit',
    since 'lmfit' isn't in the selected set."""
    resolved, baseline_id = _resolve_run_backends("spectrafit", None)
    assert [b.name for b in resolved] == ["spectrafit"]
    assert baseline_id == "spectrafit"


def test_explicit_baseline_overrides_auto_derivation() -> None:
    _resolved, baseline_id = _resolve_run_backends("spectrafit", "spectrafit")
    assert baseline_id == "spectrafit"


def test_multi_backend_subset_keeps_lmfit_baseline_when_present() -> None:
    pytest.importorskip("lmfit")
    resolved, baseline_id = _resolve_run_backends("spectrafit,lmfit", None)
    assert {b.name for b in resolved} == {"spectrafit", "lmfit"}
    assert baseline_id == "lmfit"


def test_unknown_backend_name_raises_bad_parameter() -> None:
    with pytest.raises(typer.BadParameter, match="unknown backend"):
        _resolve_run_backends("not-a-real-backend", None)


def test_empty_backends_value_raises_bad_parameter_instead_of_index_error() -> None:
    """`--backends ""` (or an all-comma/whitespace value) must not fall through to an
    empty `resolved` list -- that would later crash with an unhandled `IndexError` in
    the baseline-derivation branch (`resolved[0].name`) instead of a clean CLI error.
    A CI job templating `--backends "$BACKENDS"` with an empty/unset var hits this
    exact shape."""
    with pytest.raises(typer.BadParameter, match="no backend names given"):
        _resolve_run_backends("", None)
    with pytest.raises(typer.BadParameter, match="no backend names given"):
        _resolve_run_backends(",,", None)


def test_baseline_not_in_resolved_backends_raises_bad_parameter() -> None:
    """--backends spectrafit --baseline lmfit -> lmfit never ran, so the baseline
    is invalid. Without this check the engine would silently fall back to a vacuous
    speedup=1.0/Δr²=0.0 self-comparison that LOOKS like a real cross-backend gate."""
    with pytest.raises(typer.BadParameter, match="baseline 'lmfit' did not run"):
        _resolve_run_backends("spectrafit", "lmfit")


def test_run_cli_rejects_unknown_backend_before_running_the_engine(
    monkeypatch, tmp_path
) -> None:
    """`run --backends bogus` exits 2 immediately -- never reaches build_report (no
    slow fit is attempted for a typo'd backend name)."""
    monkeypatch.chdir(tmp_path)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("build_report should not be called for an unknown backend")

    monkeypatch.setattr(bench_cli, "build_report", _fail_if_called)
    result = runner.invoke(bench_cli.app, ["run", "--backends", "not-a-real-backend"])
    assert result.exit_code == 2, result.output
