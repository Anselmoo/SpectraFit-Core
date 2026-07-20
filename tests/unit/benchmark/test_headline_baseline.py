"""EF-PY-08: Headline geomean/Δr² must read baseline_solver_id, not hardcoded "lmfit".

The bug: `_compute_headline_numbers` used `case.m.get("lmfit")` as the Δr²
baseline regardless of `BenchReport.baseline_solver_id`.  When the baseline is
set to, e.g., ``scipy-ls-lm`` the Δr² comparison silently fell back to lmfit
(or produced 0.0 if lmfit was absent), so the gate number was wrong.

Fix: thread ``report.baseline_solver_id`` into the Δr² lookup so the
function compares spectrafit accuracy against whichever solver is the declared
baseline.
"""

from __future__ import annotations

from oracles.bench_contract import (
    BenchReport,
    CategoryMeta,
    SolverMeta,
    SuiteCase,
    SuiteMetric,
)
from oracles.reports import _compute_headline_numbers


def _make_report(
    *,
    baseline_solver_id: str,
    spectrafit_speedup: float,
    spectrafit_r2: float,
    baseline_r2: float,
    lmfit_r2: float | None,
    include_lmfit: bool = True,
) -> BenchReport:
    """Minimal 1-case report with configurable baseline solver."""
    m: dict[str, SuiteMetric] = {
        "spectrafit": SuiteMetric(
            speedup=spectrafit_speedup,
            r2=spectrafit_r2,
            red_chi2=1.0,
            med_ms=1.0,
            param_err=0.0,
            success=True,
        ),
        baseline_solver_id: SuiteMetric(
            speedup=1.0,
            r2=baseline_r2,
            red_chi2=1.0,
            med_ms=5.0,
            param_err=0.0,
            success=True,
        ),
    }
    if include_lmfit and lmfit_r2 is not None and baseline_solver_id != "lmfit":
        m["lmfit"] = SuiteMetric(
            speedup=0.5,
            r2=lmfit_r2,
            red_chi2=1.0,
            med_ms=10.0,
            param_err=0.0,
            success=True,
        )

    solvers = [
        SolverMeta(id="spectrafit", label="spectrafit", color="#fff", soft="#eee"),
        SolverMeta(
            id=baseline_solver_id,
            label=baseline_solver_id,
            color="#fff",
            soft="#eee",
        ),
    ]

    return BenchReport(
        solvers=solvers,
        categories=[CategoryMeta(id="easy", label="Easy", n=1, hue="#fff")],
        analyzed=[],
        suite=[
            SuiteCase(
                id="EZ-001",
                name="case 1",
                category="easy",
                difficulty=0.1,
                m=m,
                winner="spectrafit",
                regression=False,
            )
        ],
        baseline_solver_id=baseline_solver_id,
    )


def test_headline_uses_baseline_solver_id_not_hardcoded_lmfit() -> None:
    """When baseline is scipy-ls-lm, Δr² is vs scipy-ls-lm, not lmfit.

    With lmfit at r2=0.50 and scipy-ls-lm at r2=0.99, the correct Δr²
    (spectrafit r2=0.9998 vs scipy-ls-lm r2=0.99) is ~0.0098.
    The old bug would compare against lmfit (r2=0.50) giving Δr² ≈ 0.4998.
    """
    report = _make_report(
        baseline_solver_id="scipy-ls-lm",
        spectrafit_speedup=2.0,
        spectrafit_r2=0.9998,
        baseline_r2=0.99,  # scipy-ls-lm: close to spectrafit
        lmfit_r2=0.50,  # lmfit: intentionally far from spectrafit
        include_lmfit=True,
    )
    geomean, max_dr2, _win_rate, _reg_ids, _harmonic, _nonfinite = (
        _compute_headline_numbers(report)
    )

    # Speedup should be 2.0 (from sf.speedup field, already relative to baseline)
    assert abs(geomean - 2.0) < 1e-9, f"Expected geomean 2.0, got {geomean}"

    # Δr² must be vs scipy-ls-lm (≈0.0098), NOT vs lmfit (≈0.4998)
    expected_dr2 = abs(0.9998 - 0.99)
    assert abs(max_dr2 - expected_dr2) < 1e-9, (
        f"Expected max_dr2 ≈ {expected_dr2:.4f} (vs scipy-ls-lm), "
        f"got {max_dr2:.4f} — baseline_solver_id not threaded through?"
    )


def test_headline_uses_lmfit_as_default_baseline() -> None:
    """When baseline_solver_id='lmfit' (default), behaviour is unchanged."""
    report = _make_report(
        baseline_solver_id="lmfit",
        spectrafit_speedup=12.0,
        spectrafit_r2=0.9998,
        baseline_r2=0.9999,  # lmfit
        lmfit_r2=None,
        include_lmfit=False,  # lmfit IS the baseline, already in m
    )
    geomean, max_dr2, _win_rate, _reg_ids, _harmonic, _nonfinite = (
        _compute_headline_numbers(report)
    )

    assert abs(geomean - 12.0) < 1e-9
    expected_dr2 = abs(0.9998 - 0.9999)
    assert abs(max_dr2 - expected_dr2) < 1e-9


def test_headline_no_lmfit_in_m_baseline_is_scipy() -> None:
    """When lmfit is absent from case.m and baseline is scipy-ls-lm, no KeyError."""
    report = _make_report(
        baseline_solver_id="scipy-ls-lm",
        spectrafit_speedup=3.0,
        spectrafit_r2=0.995,
        baseline_r2=0.994,
        lmfit_r2=None,
        include_lmfit=False,  # lmfit not present in m at all
    )
    # Must not raise; Δr² should be computed vs scipy-ls-lm
    geomean, max_dr2, _win_rate, _reg_ids, _harmonic, _nonfinite = (
        _compute_headline_numbers(report)
    )
    assert abs(geomean - 3.0) < 1e-9
    expected_dr2 = abs(0.995 - 0.994)
    assert abs(max_dr2 - expected_dr2) < 1e-9
