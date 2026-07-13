"""A non-finite |Δr²| must FAIL the accuracy gate, not silently pass.

Regression guard for the release-audit finding (2026-06-23): the accuracy axis
compared `max_abs_delta_r2 > threshold`, and `NaN > 1e-3` is False → silent
PASS; the manifest write then coerced the NaN to 0.0 via `_sanitize`, erasing
the evidence. The fix carries the offending case-ids in a list the sanitizer
cannot destroy and fails the axis when it is non-empty.
"""

from __future__ import annotations

import math

from oracles.reports import (
    _compute_default_gate_state,
    _compute_headline_numbers,
)
from oracles.cli import GateThresholds, build_gate_report


def _suite_metric(*, r2: float, speedup: float = 5.0):
    from oracles.bench_contract import SuiteMetric

    # Use model_construct to bypass the finite validator so we can inject a NaN
    # r² into the report for testing — mirrors how a degenerate backend outcome
    # (e.g. ss_res=inf → r2=-inf sentinel stored as NaN by a raw dict path) can
    # produce a non-finite |Δr²| downstream.
    return SuiteMetric.model_construct(
        speedup=speedup, r2=r2, red_chi2=1.0, med_ms=2.0, param_err=0.05, success=True
    )


def _report_with_dr2(sf_r2: float, base_r2: float = 0.99):
    """A one-case BenchReport (non-optfn) with the given spectrafit/baseline r²."""
    from oracles.bench_contract import BenchReport, CategoryMeta, SolverMeta, SuiteCase

    case = SuiteCase.model_construct(
        id="GH-001",
        name="GH-001",
        category="easy",
        difficulty=0.1,
        m={"spectrafit": _suite_metric(r2=sf_r2), "lmfit": _suite_metric(r2=base_r2, speedup=1.0)},
        winner="spectrafit",
        regression=False,
        winner_reason=None,
    )
    return BenchReport.model_construct(
        schema_version="1.7",
        solvers=[
            SolverMeta(id="spectrafit", label="SpectraFit", color="#f00", soft="#fee"),
            SolverMeta(id="lmfit", label="lmfit", color="#00f", soft="#eef"),
        ],
        categories=[CategoryMeta(id="easy", label="Easy", n=1, hue="#ccc")],
        analyzed=[],
        suite=[case],
        baseline_solver_id="lmfit",
        manifest=None,
        trust_block=None,
        panels=[],
        inference=None,
        git_commit=None,
        git_branch=None,
        run_timestamp_unix=None,
    )


def test_headline_collects_nonfinite_dr2_case_ids() -> None:
    report = _report_with_dr2(sf_r2=math.nan)
    geomean, max_dr2, _win, _reg, _harm, nonfinite_ids = _compute_headline_numbers(report)
    assert nonfinite_ids == ["GH-001"], "the NaN-r² case must be flagged, not dropped"
    assert math.isfinite(max_dr2), "max_abs_delta_r2 must stay finite (max over finite deltas)"


def test_finite_case_has_empty_nonfinite_list() -> None:
    report = _report_with_dr2(sf_r2=0.989)
    *_rest, nonfinite_ids = _compute_headline_numbers(report)
    assert nonfinite_ids == []


def test_gate_state_fails_accuracy_on_nonfinite() -> None:
    # max_dr2 is finite/small, but a non-empty nonfinite list must still FAIL.
    assert _compute_default_gate_state(5.0, 0.0, [], ["GH-001"]) == "fail"
    assert _compute_default_gate_state(5.0, 0.0, [], []) == "pass"


def test_cli_gate_fails_on_nonfinite_manifest_field() -> None:
    """The on-disk (dict) gate path must fail accuracy when the list is non-empty,
    even though `max_abs_delta_r2` reads as a sanitized 0.0."""
    manifest = {
        "geomean_speedup_vs_baseline": 12.0,
        "max_abs_delta_r2": 0.0,  # sanitized from NaN — looks like a perfect pass
        "regression_case_ids": [],
        "nonfinite_dr2_case_ids": ["GH-001"],
        "baseline_solver_id": "lmfit",
    }
    report = build_gate_report(manifest, GateThresholds())
    accuracy = next(a for a in report.axes if a.axis == "accuracy")
    assert accuracy.state == "fail"
    assert report.overall == "fail"
