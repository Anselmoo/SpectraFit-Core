"""Gate verdict must be robust to ±10% threshold shifts. If a small change in
geomean-speedup or max-Δr² threshold flips the verdict, the threshold IS the
finding and must be reported as fragile."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oracles.bench_contract import GATE_RANK, GATE_STATES, GateState
from oracles.reports import REPORTS_ROOT


def evaluate_gate(
    geomean_speedup: float | None,
    max_abs_delta_r2: float | None,
    regression_count: int = 0,
    speed_threshold: float = 1.0,
    r2_threshold: float = 1e-3,
    regression_threshold: int = 0,
) -> GateState:
    """Pure threshold check — no I/O, no manifest access.

    Evaluates the three gate axes (speed, accuracy, regressions) using the
    provided thresholds and returns the worst-of GateState.

    Args:
        geomean_speedup: Geomean speedup value (higher is better).
        max_abs_delta_r2: Maximum absolute delta R² (lower is better).
        regression_count: Number of regressed cases (lower is better).
        speed_threshold: Fail if geomean_speedup < this (default 1.0).
        r2_threshold: Fail if max_abs_delta_r2 > this (default 1e-3).
        regression_threshold: Fail if regression_count > this (default 0).

    Returns:
        GateState: one of "pass", "warn", or "fail".
    """
    if geomean_speedup is None or max_abs_delta_r2 is None:
        return "warn"

    levels: list[GateState] = []

    # Speed axis: higher-is-better → fail if geomean < threshold
    levels.append("fail" if geomean_speedup < speed_threshold else "pass")

    # Accuracy axis: lower-is-better → fail if max_dr2 > threshold
    levels.append("fail" if max_abs_delta_r2 > r2_threshold else "pass")

    # Regressions axis: lower-is-better → fail if count > threshold
    levels.append("fail" if regression_count > regression_threshold else "pass")

    # Aggregate to worst-of via GATE_RANK
    worst_rank = max(GATE_RANK[lvl] for lvl in levels)
    return GATE_STATES[worst_rank]


def _latest_manifest() -> Path | None:
    """Find the most recent manifest.json under .spectrafit_reports/benchmark/."""
    runs = sorted(REPORTS_ROOT.glob("benchmark/*/manifest.json"), reverse=True)
    return runs[0] if runs else None


@pytest.mark.skipif(_latest_manifest() is None, reason="no run on disk")
def test_gate_robust_to_speed_threshold_perturbation():
    """Gate verdict must not flip when speed threshold moves by ±10%."""
    path = _latest_manifest()
    assert path is not None
    manifest = json.loads(path.read_text())

    baseline_verdict = manifest.get("gate_state")
    geomean = manifest.get("geomean_speedup_vs_baseline") or manifest.get(
        "geomean_speedup_vs_lmfit"
    )
    max_dr2 = manifest.get("max_abs_delta_r2")
    reg_ids = list(manifest.get("regression_case_ids") or [])

    if baseline_verdict is None:
        pytest.skip("manifest does not carry gate_state yet")
    if geomean is None or max_dr2 is None:
        pytest.skip("manifest missing geomean / max_dr2")

    # Compute the baseline verdict with default thresholds
    baseline = evaluate_gate(
        geomean_speedup=geomean,
        max_abs_delta_r2=max_dr2,
        regression_count=len(reg_ids),
        speed_threshold=1.0,
        r2_threshold=1e-3,
        regression_threshold=0,
    )
    assert baseline == baseline_verdict, (
        f"baseline evaluation mismatch: expected {baseline_verdict}, got {baseline}"
    )

    # Test ±10% perturbations on speed threshold
    for factor in (0.9, 1.0, 1.1):
        perturbed_threshold = 1.0 * factor
        verdict = evaluate_gate(
            geomean_speedup=geomean,
            max_abs_delta_r2=max_dr2,
            regression_count=len(reg_ids),
            speed_threshold=perturbed_threshold,
            r2_threshold=1e-3,
            regression_threshold=0,
        )
        assert verdict == baseline_verdict, (
            f"gate fragile on speed: threshold * {factor} (={perturbed_threshold:.3f}) "
            f"flipped {baseline_verdict} → {verdict}"
        )


@pytest.mark.skipif(_latest_manifest() is None, reason="no run on disk")
def test_gate_robust_to_r2_threshold_perturbation():
    """Gate verdict must not flip when R² threshold moves by ±10%."""
    path = _latest_manifest()
    assert path is not None
    manifest = json.loads(path.read_text())

    baseline_verdict = manifest.get("gate_state")
    geomean = manifest.get("geomean_speedup_vs_baseline") or manifest.get(
        "geomean_speedup_vs_lmfit"
    )
    max_dr2 = manifest.get("max_abs_delta_r2")
    reg_ids = list(manifest.get("regression_case_ids") or [])

    if baseline_verdict is None:
        pytest.skip("manifest does not carry gate_state yet")
    if geomean is None or max_dr2 is None:
        pytest.skip("manifest missing geomean / max_dr2")

    # Compute the baseline verdict with default thresholds
    baseline = evaluate_gate(
        geomean_speedup=geomean,
        max_abs_delta_r2=max_dr2,
        regression_count=len(reg_ids),
        speed_threshold=1.0,
        r2_threshold=1e-3,
        regression_threshold=0,
    )
    assert baseline == baseline_verdict, (
        f"baseline evaluation mismatch: expected {baseline_verdict}, got {baseline}"
    )

    # Test ±10% perturbations on R² threshold
    base_r2_threshold = 1e-3
    for factor in (0.9, 1.0, 1.1):
        perturbed_threshold = base_r2_threshold * factor
        verdict = evaluate_gate(
            geomean_speedup=geomean,
            max_abs_delta_r2=max_dr2,
            regression_count=len(reg_ids),
            speed_threshold=1.0,
            r2_threshold=perturbed_threshold,
            regression_threshold=0,
        )
        assert verdict == baseline_verdict, (
            f"gate fragile on R²: threshold * {factor} (={perturbed_threshold:.2e}) "
            f"flipped {baseline_verdict} → {verdict}"
        )


@pytest.mark.skipif(_latest_manifest() is None, reason="no run on disk")
def test_gate_robust_to_both_thresholds():
    """Gate verdict must be robust when both speed and R² thresholds move by ±10%."""
    path = _latest_manifest()
    assert path is not None
    manifest = json.loads(path.read_text())

    baseline_verdict = manifest.get("gate_state")
    geomean = manifest.get("geomean_speedup_vs_baseline") or manifest.get(
        "geomean_speedup_vs_lmfit"
    )
    max_dr2 = manifest.get("max_abs_delta_r2")
    reg_ids = list(manifest.get("regression_case_ids") or [])

    if baseline_verdict is None:
        pytest.skip("manifest does not carry gate_state yet")
    if geomean is None or max_dr2 is None:
        pytest.skip("manifest missing geomean / max_dr2")

    # Compute the baseline verdict with default thresholds
    baseline = evaluate_gate(
        geomean_speedup=geomean,
        max_abs_delta_r2=max_dr2,
        regression_count=len(reg_ids),
        speed_threshold=1.0,
        r2_threshold=1e-3,
        regression_threshold=0,
    )
    assert baseline == baseline_verdict, (
        f"baseline evaluation mismatch: expected {baseline_verdict}, got {baseline}"
    )

    # Test combined ±10% perturbations
    for speed_factor in (0.9, 1.0, 1.1):
        for r2_factor in (0.9, 1.0, 1.1):
            verdict = evaluate_gate(
                geomean_speedup=geomean,
                max_abs_delta_r2=max_dr2,
                regression_count=len(reg_ids),
                speed_threshold=1.0 * speed_factor,
                r2_threshold=1e-3 * r2_factor,
                regression_threshold=0,
            )
            assert verdict == baseline_verdict, (
                f"gate fragile on combined: speed_factor={speed_factor}, "
                f"r2_factor={r2_factor} flipped {baseline_verdict} → {verdict}"
            )
