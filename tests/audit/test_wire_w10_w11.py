"""Task 5.5 — wires W10/W11: σ-calibration + speed inference + gate axes.

W10 passes iff ``calibration.passed is True`` and the record is not skipped.
W11 passes iff ``speed_inference.passed is True`` and the record is not skipped.
When the argument is ``None`` OR the record's ``.skipped`` is ``True``, the wire
returns ``"skipped"`` (no pass-by-absence, mirror W9).
"""

from __future__ import annotations

from oracles.bench_contract import CalibrationResult, SpeedInferenceResult
from oracles.cli import (
    GateThresholds,
    _gate_evaluate,
)
from oracles.audit.wires import (
    ALL_WIRES,
    wire_w10_sigma_calibration,
    wire_w11_speed_inference,
)


# ---------------------------------------------------------------------------
# Minimal fixture helpers
# ---------------------------------------------------------------------------


def _make_calibration(
    *,
    passed: bool,
    skipped: bool = False,
    coverage: float = 0.68,
    binomial_p: float = 0.8,
    ks_p: float = 0.4,
    n: int = 50,
    nominal: float = 0.6827,
    alpha: float = 0.025,
) -> CalibrationResult:
    """Build a minimal CalibrationResult fixture."""
    return CalibrationResult(
        n=n,
        coverage=coverage,
        coverage_ci_lo=coverage - 0.05,
        coverage_ci_hi=coverage + 0.05,
        nominal=nominal,
        binomial_p=binomial_p,
        ks_stat=0.1,
        ks_p=ks_p,
        alpha=alpha,
        passed=passed,
        skipped=skipped,
    )


def _make_speed_inference(
    *,
    passed: bool,
    skipped: bool = False,
    geomean_speedup: float = 9.5,
    ci_lo: float = 7.0,
    ci_hi: float = 12.0,
    sign_p: float = 0.01,
    wilcoxon_p: float = 0.01,
    alpha: float = 0.025,
) -> SpeedInferenceResult:
    """Build a minimal SpeedInferenceResult fixture."""
    return SpeedInferenceResult(
        geomean_speedup=geomean_speedup,
        ci_lo=ci_lo,
        ci_hi=ci_hi,
        excludes_one=True,
        sign_p=sign_p,
        wilcoxon_p=wilcoxon_p,
        alpha=alpha,
        passed=passed,
        skipped=skipped,
    )


# ---------------------------------------------------------------------------
# Wire W10: σ-calibration — tri-state (pass / fail / skipped)
# ---------------------------------------------------------------------------


def test_w10_pass_when_calibration_passed_true() -> None:
    cal = _make_calibration(passed=True)
    results = wire_w10_sigma_calibration(calibration=cal)
    assert len(results) == 1
    r = results[0]
    assert r.wire_id == "W10"
    assert r.status == "pass"
    # Evidence must carry coverage and binomial p (primary)
    assert "coverage" in r.evidence.lower() or "binomial" in r.evidence.lower()


def test_w10_fail_when_calibration_passed_false() -> None:
    cal = _make_calibration(passed=False, coverage=0.45, binomial_p=0.001)
    results = wire_w10_sigma_calibration(calibration=cal)
    assert len(results) == 1
    r = results[0]
    assert r.wire_id == "W10"
    assert r.status == "fail"
    assert "binomial" in r.evidence.lower() or "coverage" in r.evidence.lower()


def test_w10_skipped_when_calibration_is_none() -> None:
    results = wire_w10_sigma_calibration(calibration=None)
    assert len(results) == 1
    r = results[0]
    assert r.wire_id == "W10"
    assert r.status == "skipped"
    # No pass-by-absence
    evidence_lower = r.evidence.lower()
    assert (
        "not asserted" in evidence_lower
        or "absent" in evidence_lower
        or "skipped" in evidence_lower
        or "no pass" in evidence_lower
    )


def test_w10_skipped_when_calibration_skipped_flag_true() -> None:
    """A CalibrationResult with skipped=True → wire skipped (not a pass)."""
    cal = _make_calibration(passed=False, skipped=True)
    results = wire_w10_sigma_calibration(calibration=cal)
    r = results[0]
    assert r.status == "skipped"


def test_w10_default_arg_is_none() -> None:
    """Calling wire_w10_sigma_calibration() with no args must return skipped."""
    results = wire_w10_sigma_calibration()
    assert results[0].status == "skipped"


def test_w10_evidence_includes_ks_p() -> None:
    """Evidence string for W10 must carry the KS p (secondary diagnostic)."""
    cal = _make_calibration(passed=True, ks_p=0.42)
    results = wire_w10_sigma_calibration(calibration=cal)
    evidence = results[0].evidence.lower()
    assert "ks" in evidence or "p=" in evidence or "0.42" in evidence


def test_w10_is_registered_in_all_wires() -> None:
    assert wire_w10_sigma_calibration in ALL_WIRES


# ---------------------------------------------------------------------------
# Wire W11: speed inference — tri-state (pass / fail / skipped)
# ---------------------------------------------------------------------------


def test_w11_pass_when_speed_passed_true() -> None:
    sp = _make_speed_inference(passed=True)
    results = wire_w11_speed_inference(speed_inference=sp)
    assert len(results) == 1
    r = results[0]
    assert r.wire_id == "W11"
    assert r.status == "pass"
    # Evidence must carry geomean speedup and CI
    evidence_lower = r.evidence.lower()
    assert (
        "speedup" in evidence_lower
        or "geomean" in evidence_lower
        or "ci" in evidence_lower
    )


def test_w11_fail_when_speed_passed_false() -> None:
    sp = _make_speed_inference(passed=False, geomean_speedup=0.8, ci_lo=0.5, ci_hi=1.2)
    results = wire_w11_speed_inference(speed_inference=sp)
    assert len(results) == 1
    r = results[0]
    assert r.wire_id == "W11"
    assert r.status == "fail"
    evidence_lower = r.evidence.lower()
    assert "speedup" in evidence_lower or "geomean" in evidence_lower


def test_w11_skipped_when_speed_inference_is_none() -> None:
    results = wire_w11_speed_inference(speed_inference=None)
    assert len(results) == 1
    r = results[0]
    assert r.wire_id == "W11"
    assert r.status == "skipped"
    evidence_lower = r.evidence.lower()
    assert (
        "not asserted" in evidence_lower
        or "absent" in evidence_lower
        or "skipped" in evidence_lower
        or "no pass" in evidence_lower
    )


def test_w11_skipped_when_speed_inference_skipped_flag_true() -> None:
    """A SpeedInferenceResult with skipped=True → wire skipped (not a pass)."""
    sp = _make_speed_inference(passed=False, skipped=True)
    results = wire_w11_speed_inference(speed_inference=sp)
    r = results[0]
    assert r.status == "skipped"


def test_w11_default_arg_is_none() -> None:
    """Calling wire_w11_speed_inference() with no args must return skipped."""
    results = wire_w11_speed_inference()
    assert results[0].status == "skipped"


def test_w11_evidence_includes_sign_wilcoxon_p() -> None:
    """Evidence string for W11 must carry sign and/or Wilcoxon p (secondary diagnostics)."""
    sp = _make_speed_inference(passed=True, sign_p=0.003, wilcoxon_p=0.007)
    results = wire_w11_speed_inference(speed_inference=sp)
    evidence = results[0].evidence.lower()
    assert "sign" in evidence or "wilcoxon" in evidence or "p=" in evidence


def test_w11_is_registered_in_all_wires() -> None:
    assert wire_w11_speed_inference in ALL_WIRES


# ---------------------------------------------------------------------------
# Gate axes: sigma_calibration + speed_inference
# ---------------------------------------------------------------------------


def _minimal_manifest(*, geomean: float = 10.0, max_dr2: float = 1e-5) -> dict:
    """A manifest dict with no regressions and green speed/accuracy axes."""
    return {
        "geomean_speedup_vs_baseline": geomean,
        "max_abs_delta_r2": max_dr2,
        "regression_case_ids": [],
    }


def _default_thresholds() -> GateThresholds:
    return GateThresholds(
        min_geomean=1.0,
        max_dr2=1e-3,
        max_regressions=0,
    )


def test_gate_sigma_calibration_fails_when_calibration_failed() -> None:
    """Gate fails when calibration record is present and passed=False."""
    cal = _make_calibration(passed=False, coverage=0.45, binomial_p=0.001)
    manifest = _minimal_manifest()
    report = _gate_evaluate(manifest, _default_thresholds(), calibration=cal)
    assert report.overall == "fail"
    cal_axis = next((a for a in report.axes if a.axis == "sigma_calibration"), None)
    assert cal_axis is not None
    assert cal_axis.state == "fail"


def test_gate_sigma_calibration_passes_when_calibration_passed() -> None:
    """Gate passes (all-green) when calibration record is present and passed=True."""
    cal = _make_calibration(passed=True)
    manifest = _minimal_manifest()
    report = _gate_evaluate(manifest, _default_thresholds(), calibration=cal)
    assert report.overall == "pass"
    cal_axis = next((a for a in report.axes if a.axis == "sigma_calibration"), None)
    assert cal_axis is not None
    assert cal_axis.state == "pass"


def test_gate_sigma_calibration_absent_when_none() -> None:
    """When calibration is None the sigma_calibration axis is not included (no pass-by-absence)."""
    manifest = _minimal_manifest()
    report = _gate_evaluate(manifest, _default_thresholds(), calibration=None)
    cal_axis = next((a for a in report.axes if a.axis == "sigma_calibration"), None)
    assert cal_axis is None
    assert report.overall == "pass"


def test_gate_speed_inference_fails_when_speed_failed() -> None:
    """Gate fails when speed_inference record is present and passed=False."""
    sp = _make_speed_inference(passed=False, geomean_speedup=0.8, ci_lo=0.5, ci_hi=1.2)
    manifest = _minimal_manifest()
    report = _gate_evaluate(manifest, _default_thresholds(), speed_inference=sp)
    assert report.overall == "fail"
    sp_axis = next((a for a in report.axes if a.axis == "speed_inference"), None)
    assert sp_axis is not None
    assert sp_axis.state == "fail"


def test_gate_speed_inference_passes_when_speed_passed() -> None:
    """Gate passes (all-green) when speed_inference record is present and passed=True."""
    sp = _make_speed_inference(passed=True)
    manifest = _minimal_manifest()
    report = _gate_evaluate(manifest, _default_thresholds(), speed_inference=sp)
    assert report.overall == "pass"
    sp_axis = next((a for a in report.axes if a.axis == "speed_inference"), None)
    assert sp_axis is not None
    assert sp_axis.state == "pass"


def test_gate_speed_inference_absent_when_none() -> None:
    """When speed_inference is None the axis is not included (no pass-by-absence)."""
    manifest = _minimal_manifest()
    report = _gate_evaluate(manifest, _default_thresholds(), speed_inference=None)
    sp_axis = next((a for a in report.axes if a.axis == "speed_inference"), None)
    assert sp_axis is None
    assert report.overall == "pass"


# ---------------------------------------------------------------------------
# Skipped-flag branch: axis absent (no pass-by-absence, no false fail)
# ---------------------------------------------------------------------------


def test_gate_sigma_calibration_absent_when_skipped_flag_true() -> None:
    """CalibrationResult with skipped=True must NOT produce a sigma_calibration axis.

    The gate must treat a skipped record identically to None — the axis is simply
    absent from ``GateReport.axes``.  This closes the uncovered branch where the
    inference block is present in results.json but the calibration run was skipped
    (e.g. too few cases, Monte-Carlo disabled).
    """
    cal = _make_calibration(passed=False, skipped=True)
    manifest = _minimal_manifest()
    report = _gate_evaluate(manifest, _default_thresholds(), calibration=cal)
    cal_axis = next((a for a in report.axes if a.axis == "sigma_calibration"), None)
    assert cal_axis is None, (
        "sigma_calibration axis must be absent when calibration.skipped is True"
    )
    assert report.overall == "pass"


def test_gate_speed_inference_absent_when_skipped_flag_true() -> None:
    """SpeedInferenceResult with skipped=True must NOT produce a speed_inference axis.

    Same invariant as the calibration skipped-flag branch: the axis is absent, not
    a fail — closing the parallel uncovered branch for W11.
    """
    sp = _make_speed_inference(passed=False, skipped=True)
    manifest = _minimal_manifest()
    report = _gate_evaluate(manifest, _default_thresholds(), speed_inference=sp)
    sp_axis = next((a for a in report.axes if a.axis == "speed_inference"), None)
    assert sp_axis is None, (
        "speed_inference axis must be absent when speed_inference.skipped is True"
    )
    assert report.overall == "pass"
