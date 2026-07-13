"""Gate coverage: regression_case_ids gate + self-vs-self pinned perf baseline.

Anti-regression for the two Vista traps the evolutionary audit named on
``feat/spectrafit-builder-dsl``:

* Trap A — the manifest already wrote ``regression_case_ids`` but
  ``spc-bench gate`` never read the list. A backend regression on a single
  case landed green. The gate now fails by default when the list is
  non-empty (tunable via ``--max-regressions``).

* Trap B — speedup was always computed vs the *current-run* baseline solver
  (lmfit). "Did *we* get slower this week?" was unanswerable. A pinned
  ``.spectrafit_reports/perf_baseline.json`` now lets the gate compare the
  current geomean against a frozen prior run, with a configurable tolerance.

Tests use ``monkeypatch.chdir(tmp_path)`` because ``REPORTS_ROOT`` is the
relative path ``Path(".spectrafit_reports")``: every helper resolves it
against CWD at call time, so a chdir gives each test an isolated reports
root without monkeypatching the module-level constant.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from oracles import cli as bench_cli
from oracles.reports import (
    read_perf_baseline,
    write_perf_baseline,
)

runner = CliRunner()


def _write_run(
    root: Path,
    *,
    run_id: str = "2026-06-08_run_001",
    category: str = "benchmark",
    geomean: float = 5.0,
    max_dr2: float = 1e-6,
    regressions: list[str] | None = None,
    baseline_solver_id: str = "lmfit",
    schema_version: str = "1.1",
) -> Path:
    """Write the three artifacts ``gate`` reads — index, results, manifest."""
    run_dir = root / category / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    # `gate` only requires `results.json` to *exist* (latest_results filters on it);
    # the gate body itself reads only manifest.json, so the payload may be a stub.
    (run_dir / "results.json").write_text("{}\n", encoding="utf-8")
    manifest = {
        "run_id": run_id,
        "date": run_id.split("_")[0],
        "category": category,
        "schema_version": schema_version,
        "baseline_solver_id": baseline_solver_id,
        "geomean_speedup_vs_baseline": geomean,
        "geomean_speedup_vs_lmfit": geomean,
        "max_abs_delta_r2": max_dr2,
        "spectrafit_win_rate": 1.0,
        "regressions": len(regressions or []),
        "regression_case_ids": list(regressions or []),
        "n_cases": 10,
        "backends": ["spectrafit", "lmfit"],
        "featured_ids": [],
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    index = [{"run_id": run_id, "category": category}]
    (root / "index.json").write_text(
        json.dumps(index, indent=2) + "\n", encoding="utf-8"
    )
    return run_dir


# ---------------------------------------------------------------------------
# Trap A — regression_case_ids gate
# ---------------------------------------------------------------------------


def test_gate_passes_on_clean_manifest(monkeypatch, tmp_path: Path) -> None:
    """No regressions, parity intact, speedup > 1× → exit 0."""
    monkeypatch.chdir(tmp_path)
    _write_run(Path(".spectrafit_reports"))
    result = runner.invoke(bench_cli.app, ["gate"])
    assert result.exit_code == 0, (result.stdout, result.stderr)
    assert "regression gate passed" in result.stdout


def test_gate_fails_when_regression_case_ids_non_empty(
    monkeypatch, tmp_path: Path
) -> None:
    """Any case in regression_case_ids fails the default gate (max_regressions=0).

    Anti-regression for trap A: the manifest already wrote this list; the gate
    used to ignore it. A new backend that crashes on a single case must not land
    green.
    """
    monkeypatch.chdir(tmp_path)
    _write_run(Path(".spectrafit_reports"), regressions=["EZ-007"])
    result = runner.invoke(bench_cli.app, ["gate"])
    assert result.exit_code == 1
    assert "REGRESSION GATE FAILED" in result.stderr
    assert "EZ-007" in result.stderr
    assert "1 case(s) regressed" in result.stderr


def test_gate_max_regressions_tunable(monkeypatch, tmp_path: Path) -> None:
    """``--max-regressions N`` lets up to N regressions through; N+1 fails.

    The escape hatch exists for a measured rollout (e.g. accepting two known
    failing cases while a fix lands); it is not a blanket waiver.
    """
    monkeypatch.chdir(tmp_path)
    _write_run(Path(".spectrafit_reports"), regressions=["EZ-007", "EZ-008"])
    ok = runner.invoke(bench_cli.app, ["gate", "--max-regressions", "2"])
    assert ok.exit_code == 0, (ok.stdout, ok.stderr)
    too_many = runner.invoke(bench_cli.app, ["gate", "--max-regressions", "1"])
    assert too_many.exit_code == 1
    assert "2 case(s) regressed (max allowed 1)" in too_many.stderr


# ---------------------------------------------------------------------------
# Trap B — self-vs-self pinned perf baseline
# ---------------------------------------------------------------------------


def test_pin_show_clear_baseline_roundtrip(monkeypatch, tmp_path: Path) -> None:
    """pin-baseline → show-baseline → clear-baseline is a complete lifecycle.

    ``show-baseline`` returns valid JSON when a pin exists and a human-readable
    "no perf baseline pinned" otherwise; ``clear-baseline`` is idempotent.
    """
    monkeypatch.chdir(tmp_path)
    _write_run(Path(".spectrafit_reports"), geomean=12.5)

    empty = runner.invoke(bench_cli.app, ["show-baseline"])
    assert empty.exit_code == 0
    assert "no perf baseline pinned" in empty.stdout

    pin = runner.invoke(bench_cli.app, ["pin-baseline"])
    assert pin.exit_code == 0, (pin.stdout, pin.stderr)
    assert "12.50x" in pin.stdout

    shown = runner.invoke(bench_cli.app, ["show-baseline"])
    assert shown.exit_code == 0
    payload = json.loads(shown.stdout)
    assert payload["geomean_speedup_vs_baseline"] == pytest.approx(12.5)
    assert payload["baseline_solver_id"] == "lmfit"
    assert payload["category"] == "benchmark"

    cleared = runner.invoke(bench_cli.app, ["clear-baseline"])
    assert cleared.exit_code == 0
    assert "perf baseline cleared" in cleared.stdout
    assert read_perf_baseline() is None

    again = runner.invoke(bench_cli.app, ["clear-baseline"])
    assert again.exit_code == 0
    assert "no perf baseline pinned" in again.stdout


def test_gate_fails_when_current_regresses_vs_pinned(
    monkeypatch, tmp_path: Path
) -> None:
    """Pin a 10× run, then a 5× run → 50% of pinned < (1 - default 10%) → fail.

    Anti-regression for trap B: a 50% perf drop that still beats lmfit overall
    must not land green.
    """
    monkeypatch.chdir(tmp_path)
    root = Path(".spectrafit_reports")
    _write_run(root, run_id="2026-06-08_run_001", geomean=10.0)
    pinned_manifest = json.loads(
        (root / "benchmark" / "2026-06-08_run_001" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    write_perf_baseline(pinned_manifest)
    # Add a slower run and re-point the index to it (overwrites the previous
    # single-entry index from the pinned run).
    _write_run(root, run_id="2026-06-08_run_002", geomean=5.0)
    # Re-point the index to the slower run only.
    (root / "index.json").write_text(
        json.dumps(
            [{"run_id": "2026-06-08_run_002", "category": "benchmark"}], indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    result = runner.invoke(bench_cli.app, ["gate"])
    assert result.exit_code == 1
    assert "regressed vs pinned baseline" in result.stderr
    assert "2026-06-08_run_001" in result.stderr


def test_gate_passes_within_perf_tolerance(monkeypatch, tmp_path: Path) -> None:
    """A 5% slowdown vs pinned with default 10% tolerance must still pass."""
    monkeypatch.chdir(tmp_path)
    root = Path(".spectrafit_reports")
    _write_run(root, run_id="2026-06-08_run_001", geomean=10.0)
    pinned_manifest = json.loads(
        (root / "benchmark" / "2026-06-08_run_001" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    write_perf_baseline(pinned_manifest)
    _write_run(root, run_id="2026-06-08_run_002", geomean=9.5)
    (root / "index.json").write_text(
        json.dumps(
            [{"run_id": "2026-06-08_run_002", "category": "benchmark"}], indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    result = runner.invoke(bench_cli.app, ["gate"])
    assert result.exit_code == 0, (result.stdout, result.stderr)
    assert "current/pinned = 95%" in result.stdout


def test_gate_skips_perf_check_on_mismatched_baseline_solver(
    monkeypatch, tmp_path: Path
) -> None:
    """A pin against ``lmfit`` must not silently grade a run against ``scipy-ls-lm``.

    Pin honesty: the pin records *which* baseline solver it was taken against;
    the gate refuses to compare across mismatched contexts and prints a notice
    instead of failing. The other failure modes still fire normally.
    """
    monkeypatch.chdir(tmp_path)
    root = Path(".spectrafit_reports")
    _write_run(root, run_id="2026-06-08_run_001", geomean=10.0)
    pinned_manifest = json.loads(
        (root / "benchmark" / "2026-06-08_run_001" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    write_perf_baseline(pinned_manifest)
    # Same speedup number, but a different baseline solver — must NOT trigger the
    # self-perf check (categories are too unlike to be comparable apples-to-apples).
    _write_run(
        root,
        run_id="2026-06-08_run_002",
        geomean=1.0,
        baseline_solver_id="scipy-ls-lm",
    )
    (root / "index.json").write_text(
        json.dumps(
            [{"run_id": "2026-06-08_run_002", "category": "benchmark"}], indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    result = runner.invoke(bench_cli.app, ["gate"])
    assert result.exit_code == 0, (result.stdout, result.stderr)
    assert "skipping self-perf check" in result.stderr


# ---------------------------------------------------------------------------
# Cycle 24 — ``spc-bench gate --json`` structured output for CI consumers
# ---------------------------------------------------------------------------


def test_gate_json_pass_emits_structured_object(monkeypatch, tmp_path: Path) -> None:
    """``--json`` on a clean run emits one parseable object on stdout; exit 0.

    The CLI must not interleave its prose echoes — a CI script piping into
    ``jq`` needs stdout to be the JSON object and nothing else.
    """
    monkeypatch.chdir(tmp_path)
    _write_run(Path(".spectrafit_reports"), geomean=12.36, max_dr2=1.3e-4)
    result = runner.invoke(bench_cli.app, ["gate", "--json"])
    assert result.exit_code == 0, (result.stdout, result.stderr)
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["baseline_solver_id"] == "lmfit"
    assert payload["regression_case_ids"] == []
    assert payload["failures"] == []
    assert payload["pinned_baseline"] is None
    # Three axes always present (no pin → no self_perf key); each carries the
    # measured value, the threshold it was checked against, and a bool.
    axes = payload["axes"]
    assert set(axes) == {"speed", "accuracy", "regressions"}
    assert axes["speed"]["value"] == pytest.approx(12.36)
    assert axes["speed"]["pass"] is True
    assert axes["accuracy"]["value"] == pytest.approx(1.3e-4)
    assert axes["regressions"]["value"] == 0


def test_gate_json_fail_lists_failures_and_regression_ids(
    monkeypatch, tmp_path: Path
) -> None:
    """A failing gate emits ``status=fail`` + populated ``failures`` and exits 1.

    The structured failure list lets a CI script post per-axis annotations
    instead of grep-scraping stderr.
    """
    monkeypatch.chdir(tmp_path)
    _write_run(
        Path(".spectrafit_reports"),
        geomean=0.5,
        max_dr2=1e-2,
        regressions=["EZ-007", "CX-013"],
    )
    result = runner.invoke(bench_cli.app, ["gate", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "fail"
    assert payload["regression_case_ids"] == ["EZ-007", "CX-013"]
    assert payload["axes"]["speed"]["pass"] is False
    assert payload["axes"]["accuracy"]["pass"] is False
    assert payload["axes"]["regressions"]["pass"] is False
    # Each broken axis surfaces a human message — three failures, one per axis.
    assert len(payload["failures"]) == 3


def test_gate_json_with_pin_includes_self_perf_axis(
    monkeypatch, tmp_path: Path
) -> None:
    """When a baseline is pinned and matches context, ``self_perf`` joins the axes.

    The ``pinned_baseline`` block carries the pin's run_id, the pinned geomean,
    the current/pinned ratio, and the floor — enough for a CI script to
    rebuild the GateBadge sparkline without re-reading manifest.json.
    """
    monkeypatch.chdir(tmp_path)
    root = Path(".spectrafit_reports")
    _write_run(root, run_id="2026-06-08_run_001", geomean=10.0)
    pinned_manifest = json.loads(
        (root / "benchmark" / "2026-06-08_run_001" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    write_perf_baseline(pinned_manifest)
    _write_run(root, run_id="2026-06-08_run_002", geomean=9.5)
    (root / "index.json").write_text(
        json.dumps(
            [{"run_id": "2026-06-08_run_002", "category": "benchmark"}], indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    result = runner.invoke(bench_cli.app, ["gate", "--json"])
    assert result.exit_code == 0, (result.stdout, result.stderr)
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert "self_perf" in payload["axes"]
    self_perf = payload["axes"]["self_perf"]
    assert self_perf["value"] == pytest.approx(0.95)
    assert self_perf["threshold"] == pytest.approx(0.9)
    assert self_perf["pass"] is True
    pin = payload["pinned_baseline"]
    assert pin is not None
    assert pin["matched"] is True
    assert pin["run_id"] == "2026-06-08_run_001"
    assert pin["pinned_geomean"] == pytest.approx(10.0)


def test_gate_json_missing_run_emits_error_object(monkeypatch, tmp_path: Path) -> None:
    """No run on disk → exit 2 + ``status=error`` payload (not human prose)."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(bench_cli.app, ["gate", "--json"])
    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert "no results" in payload["error"]


# ---------------------------------------------------------------------------
# Cycle 28 — 3-state gate (PASS / WARN / FAIL)
# ---------------------------------------------------------------------------


def test_gate_warn_band_geomean_only_exits_zero(monkeypatch, tmp_path: Path) -> None:
    """``--warn-geomean V`` between fail floor and headroom → status=warn, exit 0.

    Drift toward the speed floor without failing the job: 1.5× geomean is above
    the default fail floor (1.0×) but below the warn floor (2.0×) — so the
    job stays green but the JSON status / step-summary block lights amber.
    """
    monkeypatch.chdir(tmp_path)
    _write_run(Path(".spectrafit_reports"), geomean=1.5)
    result = runner.invoke(bench_cli.app, ["gate", "--json", "--warn-geomean", "2.0"])
    assert result.exit_code == 0, (result.stdout, result.stderr)
    payload = json.loads(result.stdout)
    assert payload["status"] == "warn"
    assert payload["axes"]["speed"]["level"] == "warn"
    assert payload["axes"]["speed"]["warn_threshold"] == pytest.approx(2.0)
    # Accuracy + regressions axes had no warn flag set → stay pass.
    assert payload["axes"]["accuracy"]["level"] == "pass"
    assert payload["axes"]["regressions"]["level"] == "pass"
    assert len(payload["warnings"]) == 1
    assert payload["failures"] == []


def test_gate_warn_dominated_by_fail(monkeypatch, tmp_path: Path) -> None:
    """A warn-band hit AND a regression case → status=fail wins; exit 1.

    Priority pin: ``fail`` always dominates ``warn`` at the per-axis level
    AND at the overall status. The amber drift signal does not mask a
    red regression.
    """
    monkeypatch.chdir(tmp_path)
    _write_run(
        Path(".spectrafit_reports"),
        geomean=1.5,  # warn-band hit on speed
        regressions=["EZ-007"],  # but a regression case → fail
    )
    result = runner.invoke(bench_cli.app, ["gate", "--json", "--warn-geomean", "2.0"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "fail"
    # Per-axis levels are independent — speed still WARN, regressions FAIL.
    assert payload["axes"]["speed"]["level"] == "warn"
    assert payload["axes"]["regressions"]["level"] == "fail"
    assert len(payload["failures"]) == 1
    assert len(payload["warnings"]) == 1


def test_gate_no_warn_flags_preserves_legacy_behaviour(
    monkeypatch, tmp_path: Path
) -> None:
    """Without any ``--warn-*`` flag, the gate is bit-for-bit binary.

    Regression-safety for Cycle 26's step-summary CI block (and any other
    pre-Cycle-28 JSON consumer): the new ``level`` field appears but never
    goes WARN, and the legacy ``pass`` boolean still mirrors it exactly.
    """
    monkeypatch.chdir(tmp_path)
    _write_run(Path(".spectrafit_reports"), geomean=12.36)
    result = runner.invoke(bench_cli.app, ["gate", "--json"])
    assert result.exit_code == 0, (result.stdout, result.stderr)
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    for axis in ("speed", "accuracy", "regressions"):
        a = payload["axes"][axis]
        assert a["level"] == "pass"
        assert a["pass"] is True
        assert a["warn_threshold"] is None
    assert payload["warnings"] == []
