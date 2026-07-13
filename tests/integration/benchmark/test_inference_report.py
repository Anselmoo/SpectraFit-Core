"""Integration tests for ``compute_inference`` calibration + speed_inference fields.

Task 5.4: verify that after implementation ``InferenceBlock.calibration`` and
``InferenceBlock.speed_inference`` are populated with meaningful statistical results.

Two fixture families:
- ``good``: ~N(0,1) pulls (well-calibrated) + per-case speedups all > 1×
  → calibration.passed is True AND speed_inference.passed is True.
- ``bad``: pulls with inflated σ (coverage clearly outside 68.27%) + speedups
  straddling 1× (not consistently faster) → both passed is False.
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from oracles.bench_contract import (
    AccuracyDist,
    BackendProfile,
    BenchReport,
    CategoryMeta,
    Featured,
    InferenceConfig,
    PeakACS,
    Point2D,
    SolverFit,
    SolverMeta,
    SpreadPt,
    StabilityEntry,
    SuiteCase,
    SuiteMetric,
    TimingDist,
    Uncertainty,
    Warmup,
    WarmupPt,
    Summary,
)
from oracles.inference_report import compute_inference


# ---------------------------------------------------------------------------
# Minimal fixture builders
# ---------------------------------------------------------------------------

def _timing(med: float) -> TimingDist:
    """Timing distribution centred at ``med`` ms."""
    vals = [med * 0.95, med, med * 1.05]
    return TimingDist(
        raw=vals,
        median=med,
        mean=med,
        p5=vals[0],
        p25=vals[0],
        p75=vals[2],
        p95=vals[2],
        iqr=vals[2] - vals[0],
        cv=0.05,
    )


def _summary(speedup: float = 1.0) -> Summary:
    return Summary(
        r2=0.99,
        chi2=1.0,
        red_chi2=1.0,
        rmse=0.01,
        mae=0.01,
        n_iter=20,
        med_ms=10.0,
        iqr_ms=0.5,
        cv=0.05,
        speedup=speedup,
        success=True,
        aic=-100.0,
        bic=-95.0,
        d_aic=0.0,
        d_bic=0.0,
    )


def _backend_profile(
    med_ms: float,
    pulls: list[float],
    history_source: Literal["real", "reconstructed"] = "reconstructed",
) -> BackendProfile:
    spread = SpreadPt(n=10, mean=0.99, sd=0.001)
    stab = StabilityEntry(
        r2=[spread], rmse=[spread], red_chi2=[spread], iters=[spread]
    )
    return BackendProfile(
        fit=SolverFit(
            params=[PeakACS(a=1.0, c=0.0, s=0.5)], curve=[1.0], resid=[0.0]
        ),
        conv=[1.0, 0.5],
        grad=[0.1, 0.05],
        history_source=history_source,
        timing=_timing(med_ms),
        accuracy=AccuracyDist(raw=[0.99], median=0.99, p5=0.98, p25=0.99, p75=0.99),
        summary=_summary(),
        param_err=[0.05],
        ecdf_resid=[Point2D(x=0.0, y=0.0)],
        ecdf_time=[Point2D(x=0.0, y=0.0)],
        warmup=Warmup(
            curve=[Point2D(x=1.0, y=10.0)],
            pts=[WarmupPt(n=1, per_run=10.0)],
            hot_throughput=100.0,
            cold_ms=10.0,
            hot_ms=10.0,
        ),
        scaling=[Point2D(x=100.0, y=10.0)],
        uncertainty=Uncertainty(
            pulls=pulls,
            coverage=sum(1 for p in pulls if abs(p) < 1.0) / len(pulls) if pulls else None,
            sigma=[0.5] * len(pulls) if pulls else [],
        ),
        param_spread=[spread],
        stability=stab,
    )


def _featured(
    case_id: str,
    subject_med_ms: float,
    baseline_med_ms: float,
    subject_pulls: list[float],
) -> Featured:
    """One deep-dive case with a subject (real history) and a baseline."""
    subject_profile = _backend_profile(
        subject_med_ms, subject_pulls, history_source="real"
    )
    baseline_profile = _backend_profile(
        baseline_med_ms, [], history_source="reconstructed"
    )
    return Featured(
        id=case_id,
        name=case_id,
        category="easy",
        x=[0.0, 1.0],
        ref=[1.0, 2.0],
        guess=[1.1, 2.1],
        truth=[PeakACS(a=1.0, c=0.0, s=0.5)],
        noise=0.01,
        baseline=0.0,
        profiles={
            "spectrafit": subject_profile,
            "lmfit": baseline_profile,
        },
        peaks=[],
        param_names=["a", "c", "s"],
        corr=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        n_grid=[128, 256],
        schedule=[1, 2, 5],
        runs_sched=[1, 2, 5],
        cross_n=256.0,
    )


def _bench_report(
    analyzed: list[Featured],
    suite: list[SuiteCase],
) -> BenchReport:
    return BenchReport(
        solvers=[
            SolverMeta(id="spectrafit", label="SpectraFit", color="#f00", soft="#fee"),
            SolverMeta(id="lmfit", label="lmfit", color="#00f", soft="#eef"),
        ],
        categories=[CategoryMeta(id="easy", label="Easy", n=len(suite), hue="#ccc")],
        analyzed=analyzed,
        suite=suite,
        baseline_solver_id="lmfit",
    )


def _raw_sink_for_cases(
    cases: list[tuple[str, float, float]],
) -> dict[tuple[str, str], dict[str, list[float]]]:
    """Build a raw sink from (case_id, subject_ms, baseline_ms) triples.

    Subject is always 'spectrafit'; baseline is 'lmfit'. The timing arrays
    have 5 reps each so the speedup CI is non-degenerate.
    """
    sink: dict[tuple[str, str], dict[str, list[float]]] = {}
    for idx, (cid, subj_ms, base_ms) in enumerate(cases):
        # Deterministic per-case seed. ``hash(cid)`` is salted by PYTHONHASHSEED
        # and varies per process, which made the ≈1× "bad" fixture flaky: the
        # geomean-speedup CI lower bound straddled 1.0 unpredictably (one run gave
        # geomean=1.02, ci_lo=1.00 → excludes_one=True → passed=True, wrong sign).
        # An index-derived seed makes both fixtures reproducible across processes.
        rng = np.random.default_rng(seed=20260619 + idx)
        subj_t = (subj_ms * (1.0 + rng.normal(0, 0.05, 5))).tolist()
        base_t = (base_ms * (1.0 + rng.normal(0, 0.05, 5))).tolist()
        subj_r2 = rng.uniform(0.97, 0.999, 5).tolist()
        base_r2 = rng.uniform(0.97, 0.999, 5).tolist()
        sink[cid, "spectrafit"] = {"timing": subj_t, "r2": subj_r2}
        sink[cid, "lmfit"] = {"timing": base_t, "r2": base_r2}
    return sink


# ---------------------------------------------------------------------------
# Fixture 1: well-calibrated + consistently faster → both passed True
# ---------------------------------------------------------------------------

def _good_fixture():
    """~N(0,1) pulls (n=2100, ≥ min_pulls) + 3 cases where subject is 5× faster.

    Expected: calibration.passed True, speed_inference.passed True.

    Pull count note: the σ-calibration gate (wire W10) is a **CI-inclusion TOST** —
    it passes only when the *entire* Clopper–Pearson CI of empirical coverage lies
    within ``nominal ± equivalence_margin`` (±0.03). At small n the coverage CI is
    far wider than the ±0.03 band (≈±0.14 at n=60), so *no* seed can pass — proving
    calibration-equivalence genuinely requires a large sample. 2100 well-calibrated
    pulls give a coverage CI of ≈[0.659, 0.700], comfortably inside [0.6527, 0.7127].
    """
    rng = np.random.default_rng(20260617)
    # 3 cases × 700 pulls each = 2100 pulls total across analyzed — enough for the
    # CI-inclusion TOST band (see the pull-count note above).
    n_cases = 3
    n_pulls_each = 700
    pulls_per_case = [rng.standard_normal(n_pulls_each).tolist() for _ in range(n_cases)]

    case_ids = [f"EZ-{i:03d}" for i in range(1, n_cases + 1)]
    # subject ~2 ms, baseline ~10 ms → speedup ≈ 5×
    case_timings = [(cid, 2.0, 10.0) for cid in case_ids]

    analyzed = [
        _featured(cid, subject_med_ms=2.0, baseline_med_ms=10.0, subject_pulls=pulls)
        for cid, pulls in zip(case_ids, pulls_per_case)
    ]
    suite = [
        SuiteCase(
            id=cid,
            name=cid,
            category="easy",
            difficulty=0.1,
            m={
                "spectrafit": SuiteMetric(
                    speedup=5.0, r2=0.99, red_chi2=1.0, med_ms=2.0, param_err=0.05, success=True
                ),
                "lmfit": SuiteMetric(
                    speedup=1.0, r2=0.99, red_chi2=1.0, med_ms=10.0, param_err=0.05, success=True
                ),
            },
            winner="spectrafit",
            regression=False,
        )
        for cid in case_ids
    ]
    report = _bench_report(analyzed, suite)
    raw_sink = _raw_sink_for_cases(case_timings)
    cfg = InferenceConfig(
        equivalence_margin=1e-3,
        bootstrap_b=500,
        seed=20260617,
        fdr_q=0.05,
        min_pulls=20,
    )
    return report, raw_sink, cfg


# ---------------------------------------------------------------------------
# Fixture 2: inflated-σ pulls + straddling speedups → both passed False
# ---------------------------------------------------------------------------

def _bad_fixture():
    """Inflated-σ pulls (coverage clearly < 68.27%) + speedups ≈ 1× (no winner).

    Inflated σ → coverage significantly below nominal → binomial test rejects.
    Speedups ≈ 1.0 → geomean CI straddles 1 → excludes_one=False.
    """
    rng = np.random.default_rng(20260618)
    n_cases = 3
    n_pulls_each = 30
    # Inflate σ by 2× so true coverage ≈ 95% of N(0,1) falls in [-1,1] but
    # since pulls ← N(0, 2), only ~50% lie in [-1, 1] (well below 68.27%).
    # Actually with σ=2, about 38% fall in [-1,1] — fails the binomial test easily.
    pulls_per_case = [(rng.standard_normal(n_pulls_each) * 2.0).tolist() for _ in range(n_cases)]

    case_ids = [f"BD-{i:03d}" for i in range(1, n_cases + 1)]
    # subject ≈ baseline, genuinely STRADDLING 1× (no consistent winner): per-case
    # speedup = baseline_ms / subject_ms spans {≈0.91, 1.0, ≈1.10}. The geomean sits
    # at 1× and its bootstrap CI lower bound clearly includes 1 (excludes_one=False),
    # so the verdict is robust to the 5% timing noise rather than balanced exactly on
    # 1.0 (which made the old equal-timing fixture a noise coin-flip).
    straddle_baseline_ms = [9.0, 10.0, 11.0]
    case_timings = [
        (cid, 10.0, base_ms) for cid, base_ms in zip(case_ids, straddle_baseline_ms)
    ]

    analyzed = [
        _featured(cid, subject_med_ms=10.0, baseline_med_ms=10.0, subject_pulls=pulls)
        for cid, pulls in zip(case_ids, pulls_per_case)
    ]
    suite = [
        SuiteCase(
            id=cid,
            name=cid,
            category="easy",
            difficulty=0.1,
            m={
                "spectrafit": SuiteMetric(
                    speedup=1.0, r2=0.99, red_chi2=1.0, med_ms=10.0, param_err=0.05, success=True
                ),
                "lmfit": SuiteMetric(
                    speedup=1.0, r2=0.99, red_chi2=1.0, med_ms=10.0, param_err=0.05, success=True
                ),
            },
            winner="spectrafit",
            regression=False,
        )
        for cid in case_ids
    ]
    report = _bench_report(analyzed, suite)
    raw_sink = _raw_sink_for_cases(case_timings)
    cfg = InferenceConfig(
        equivalence_margin=1e-3,
        bootstrap_b=500,
        seed=20260618,
        fdr_q=0.05,
        min_pulls=20,
    )
    return report, raw_sink, cfg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_calibration_and_speed_inference_pass_for_well_calibrated_fast_subject():
    """Well-calibrated pulls + large speedup → both tests pass."""
    report, raw_sink, cfg = _good_fixture()
    ib = compute_inference(report, raw_sink, config=cfg)

    assert ib.calibration is not None, "calibration must be populated"
    assert ib.speed_inference is not None, "speed_inference must be populated"

    # Pulls were drawn from N(0,1) at n=2100; coverage ≈ 0.68 and its Clopper–Pearson
    # CI fits inside the ±0.03 equivalence band → CI-inclusion TOST (W10) passes.
    assert ib.calibration.passed is True, (
        f"expected calibration.passed=True for N(0,1) pulls; "
        f"n={ib.calibration.n}, coverage={ib.calibration.coverage:.3f}, "
        f"p={ib.calibration.binomial_p:.4f}"
    )
    assert not ib.calibration.skipped, "calibration must not be skipped (n ≥ min_pulls)"

    # Subject is 5× faster in every case → geomean CI should exclude 1×
    assert ib.speed_inference.passed is True, (
        f"expected speed_inference.passed=True for 5× speedup; "
        f"geomean={ib.speed_inference.geomean_speedup:.2f}, "
        f"ci_lo={ib.speed_inference.ci_lo:.2f}"
    )
    assert not ib.speed_inference.skipped, "speed_inference must not be skipped"

    # Structural sanity
    assert ib.calibration.n >= 20, "must have aggregated ≥ 20 pulls"
    assert ib.speed_inference.geomean_speedup > 1.0


def test_calibration_and_speed_inference_fail_for_bad_fixture():
    """Inflated-σ pulls + tie speedups → both tests fail (passed=False)."""
    report, raw_sink, cfg = _bad_fixture()
    ib = compute_inference(report, raw_sink, config=cfg)

    assert ib.calibration is not None, "calibration must be populated"
    assert ib.speed_inference is not None, "speed_inference must be populated"

    # Coverage for N(0,2) ≈ 38% in [-1,1] — well below 68.27% → binomial rejects
    assert ib.calibration.passed is False, (
        f"expected calibration.passed=False for N(0,2) pulls; "
        f"n={ib.calibration.n}, coverage={ib.calibration.coverage:.3f}, "
        f"p={ib.calibration.binomial_p:.4f}"
    )

    # Subject ≈ baseline timing → geomean CI straddles 1× → excludes_one=False
    assert ib.speed_inference.passed is False, (
        f"expected speed_inference.passed=False for ≈1× speedup; "
        f"geomean={ib.speed_inference.geomean_speedup:.2f}, "
        f"ci_lo={ib.speed_inference.ci_lo:.2f}"
    )


def test_calibration_skipped_when_no_analyzed():
    """Empty analyzed list → calibration.skipped is True (no-pass-by-absence)."""
    cfg = InferenceConfig(
        equivalence_margin=1e-3, bootstrap_b=200, seed=42, fdr_q=0.05, min_pulls=20
    )
    report = BenchReport(
        solvers=[
            SolverMeta(id="spectrafit", label="SpectraFit", color="#f00", soft="#fee"),
            SolverMeta(id="lmfit", label="lmfit", color="#00f", soft="#eef"),
        ],
        categories=[CategoryMeta(id="easy", label="Easy", n=0, hue="#ccc")],
        analyzed=[],
        suite=[],
        baseline_solver_id="lmfit",
    )
    raw_sink: dict = {}
    ib = compute_inference(report, raw_sink, config=cfg)
    assert ib.calibration is not None, "calibration must be populated even when empty"
    assert ib.calibration.skipped is True, "empty analyzed → skipped=True"
    assert ib.calibration.passed is False, "skipped means passed=False"


def test_speed_inference_skipped_when_no_raw_sink():
    """Empty raw sink → speed_inference.skipped is True."""
    cfg = InferenceConfig(
        equivalence_margin=1e-3, bootstrap_b=200, seed=42, fdr_q=0.05, min_pulls=20
    )
    report = BenchReport(
        solvers=[
            SolverMeta(id="spectrafit", label="SpectraFit", color="#f00", soft="#fee"),
            SolverMeta(id="lmfit", label="lmfit", color="#00f", soft="#eef"),
        ],
        categories=[CategoryMeta(id="easy", label="Easy", n=0, hue="#ccc")],
        analyzed=[],
        suite=[],
        baseline_solver_id="lmfit",
    )
    raw_sink: dict = {}
    ib = compute_inference(report, raw_sink, config=cfg)
    assert ib.speed_inference is not None, "speed_inference must be populated even when empty"
    assert ib.speed_inference.skipped is True, "no raw sink → skipped=True"
    assert ib.speed_inference.passed is False
