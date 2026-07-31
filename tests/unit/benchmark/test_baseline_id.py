"""TDD red phase: ``baseline_solver_id`` field threading.

Anti-regression for the Vista Countdown's "add a 4th backend" wall: the
benchmark engine hardcoded ``by_name["lmfit"]`` as the speedup baseline at
two sites; the manifest exposed it as ``geomean_speedup_vs_lmfit``; the web
side mirrored it as ``BENCH.solvers[1]?.label``. None of those acknowledged
the baseline solver in the contract.

These tests pin the post-bump contract (1.0 → 1.1, additive):

1. ``BenchReport.baseline_solver_id`` exists with default ``"lmfit"``;
   round-trips through JSON unchanged.
2. An old ``results.json`` from before the bump still validates (Pydantic
   default fills in the missing field).
3. ``build_report(..., baseline_solver_id="lmfit")`` plumbs through to the
   per-case speedup math: ``suite[i].m["spectrafit"].speedup ==
   lmfit_med_ms / spectrafit_med_ms`` is no longer guaranteed if the
   baseline shifts, but it must equal whatever median timing the
   ``baseline_solver_id`` backend produced.
4. The CLI gate reads the canonical
   ``geomean_speedup_vs_baseline`` manifest key, with a fallback to the
   legacy ``geomean_speedup_vs_lmfit`` so old manifests on disk still gate.
"""

from __future__ import annotations

import json

import pytest
from oracles.bench_contract import SCHEMA_VERSION, BenchReport
from oracles.cases import build_specs, materialize
from oracles.cli import _gate_geomean
from oracles.engine import build_report
from oracles.migrate import migrate_payload_to_current
from oracles.reports import latest_results


def _tiny_catalog() -> list:
    """Featured case + one easy + one complex, materialized."""
    specs = build_specs()
    featured = next(s for s in specs if s.featured)
    easy = next(s for s in specs if s.category == "easy")
    complx = next(s for s in specs if s.category == "complex")
    return [materialize(s) for s in (featured, easy, complx)]


def test_bench_report_carries_baseline_solver_id_default_lmfit() -> None:
    """Default is ``"lmfit"`` and survives JSON round-trip unchanged.

    Does NOT require lmfit to be installed: ``baseline_solver_id`` is echoed
    onto the report verbatim from the ``build_report`` parameter default
    (``engine.py`` never validates it against the actual backend roster —
    ``run_suite`` falls back to ``speedup=1.0`` when the named baseline
    solver didn't run), so this only pins the default *string*, not real
    lmfit execution. Verified empirically: passes unchanged with
    ``get_backends()`` monkeypatched to spectrafit-only.
    """
    report = build_report(n_reps=1, n_mc=2, catalog=_tiny_catalog(), ngrid=[128, 256])
    assert report.baseline_solver_id == "lmfit"
    raw = report.model_dump_json(by_alias=True)
    again = BenchReport.model_validate_json(raw)
    assert again.baseline_solver_id == report.baseline_solver_id


def test_old_payload_validates_under_bumped_schema_via_pydantic_default() -> None:
    """An on-disk results.json (migrated to current) has ``baseline_solver_id`` via default.

    The 1.0→1.1 bump was additive (``baseline_solver_id`` has a default of
    ``"lmfit"``). The 1.5→1.6 bump was breaking (``timeResolved``→``globalFit``
    rename), so current on-disk files must be chain-migrated before validation.
    This test pins that the default still fills in ``baseline_solver_id`` after
    the full chain walk, regardless of which legacy version the file was written at.
    """
    latest = latest_results("benchmark")
    if latest is None:
        pytest.skip("no benchmark run on disk")
    raw = json.loads(latest.read_text(encoding="utf-8"))
    # Migrate to current schema (handles the 1.5→1.6 timeResolved→globalFit rename).
    migrated = migrate_payload_to_current(raw)
    # Strip baseline_solver_id to simulate a pre-1.1 payload shape (Pydantic default fills it).
    migrated.pop("baselineSolverId", None)
    migrated.pop("baseline_solver_id", None)
    migrated["schemaVersion"] = SCHEMA_VERSION  # already current; keep Pydantic happy
    parsed = BenchReport.model_validate(migrated)
    assert parsed.baseline_solver_id == "lmfit"


def test_engine_threads_baseline_solver_id_into_speedup_math() -> None:
    """``build_report(baseline_solver_id=…)`` is the SOLE knob for the baseline.

    Anti-regression for the hardcoded ``by_name["lmfit"]`` in engine.py: the
    parameter must reach the per-case speedup denominator. We verify by
    constructing a tiny report and asserting that the lmfit row, which is the
    baseline, reports a speedup ≈ 1.0 (the baseline is its own baseline).

    Requires lmfit: with no explicit ``backends=``, ``build_report`` defaults
    to the full roster (``get_backends()``), and the assertion only fires
    inside ``if "lmfit" in case.m`` — without lmfit installed that guard is
    never true, so the loop body never runs and the test would silently pass
    without checking anything. Skip explicitly instead of passing vacuously.
    """
    pytest.importorskip("lmfit")
    catalog = _tiny_catalog()
    report = build_report(
        n_reps=1, n_mc=2, catalog=catalog, ngrid=[128, 256], baseline_solver_id="lmfit"
    )
    # On the suite rows, lmfit's own speedup must be exactly 1.0 by construction.
    saw_lmfit = False
    for case in report.suite:
        if "lmfit" in case.m:
            saw_lmfit = True
            assert case.m["lmfit"].speedup == pytest.approx(1.0, rel=1e-9)
    assert saw_lmfit, "expected at least one suite case to carry an lmfit metric"


def test_gate_reads_canonical_key_with_legacy_fallback() -> None:
    """The CLI gate prefers the canonical key but tolerates the legacy one."""
    new_manifest = {"geomean_speedup_vs_baseline": 2.0, "max_abs_delta_r2": 1e-5}
    old_manifest = {"geomean_speedup_vs_lmfit": 2.0, "max_abs_delta_r2": 1e-5}
    assert _gate_geomean(new_manifest) == 2.0
    assert _gate_geomean(old_manifest) == 2.0


def test_build_report_with_single_backend_list_restricts_suite_metrics() -> None:
    """`backends=[spectrafit]` (no lmfit) -> every suite case's metric map has exactly
    one entry, and `baseline_solver_id="spectrafit"` makes speedup/Δr² well-defined by
    self-comparison (speedup=1.0, Δr²=0.0) instead of undefined.

    This is the engine-level behavior behind `spc-bench run --backends spectrafit`
    (the fast, single-backend smoke/gate pipeline — see oracles.cli.run).
    """
    from oracles.backends._spectrafit import SpectraFitBackend

    report = build_report(
        n_reps=1,
        n_mc=2,
        catalog=_tiny_catalog(),
        backends=[SpectraFitBackend()],
        baseline_solver_id="spectrafit",
        ngrid=[128, 256],
    )
    assert report.baseline_solver_id == "spectrafit"
    for case in report.suite:
        assert set(case.m) == {"spectrafit"}
        assert case.m["spectrafit"].speedup == pytest.approx(1.0)
