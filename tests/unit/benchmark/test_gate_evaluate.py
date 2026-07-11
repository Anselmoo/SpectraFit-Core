"""Pure-function unit tests for ``oracles.cli._gate_evaluate``.

The Typer ``gate`` command was 292 LOC of interleaved I/O, threshold
arithmetic, message formatting, and exit-code dispatch. Plan C2 refactor
2/4 extracts the 3-axis decision kernel (speed / accuracy / regressions)
into a pure function that takes a manifest dict (or typed
:class:`ManifestSignals`) plus a :class:`GateThresholds` and returns a
typed :class:`GateReport` — no I/O, no print, no exit.

These tests cover the kernel only. Integration tests in
``tests/integration/benchmark/test_gate.py`` keep covering the Typer
wrapper end-to-end (filesystem fixtures, ``read_perf_baseline`` I/O,
``--json`` byte-shape).

The seven scenarios pin:

1. All-pass — the green-path baseline.
2. Speed fail — geomean below the hard floor.
3. Accuracy fail — max |Δr²| above the hard ceiling.
4. Regressions fail — case-id list longer than ``max_regressions``.
5. Mixed states — worst-of aggregation must surface ``fail`` over ``warn``.
6. ``ManifestSignals`` input — typed contract input must work the same
   as the raw dict (Pydantic-first conventions).
7. Threshold validation — bad-type inputs must raise ``ValidationError``
   at construction time, not at evaluation time.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from oracles.cli import GateAxisResult, GateReport, GateThresholds, _gate_evaluate
from oracles.bench_contract import ManifestSignals


def _manifest(
    *,
    geomean: float = 2.0,
    max_dr2: float = 1e-5,
    regression_ids: list[str] | None = None,
) -> dict:
    """Build a minimal manifest dict for kernel evaluation.

    Mirrors the on-disk shape the Typer command loads from ``manifest.json``;
    only the keys the kernel reads are populated so a forgotten contract field
    can't accidentally satisfy a test.
    """
    return {
        "geomean_speedup_vs_baseline": geomean,
        "max_abs_delta_r2": max_dr2,
        "regression_case_ids": list(regression_ids or []),
    }


def _default_thresholds() -> GateThresholds:
    """Match the Typer command's default ``min_geomean=1.0`` / ``max_dr2=1e-3`` / ``max_regressions=0``."""
    return GateThresholds(min_geomean=1.0, max_dr2=1e-3, max_regressions=0)


# ---------------------------------------------------------------------------
# 1. All axes pass — the green path baseline
# ---------------------------------------------------------------------------


def test_all_axes_pass_returns_pass_overall() -> None:
    """geomean=2.0 > 1.0, dr2=1e-5 < 1e-3, no regressions → every axis pass."""
    report = _gate_evaluate(_manifest(), _default_thresholds())
    assert isinstance(report, GateReport)
    assert report.overall == "pass"
    assert report.geomean_speedup == pytest.approx(2.0)
    assert report.max_abs_delta_r2 == pytest.approx(1e-5)
    assert report.regression_ids == []
    by_axis = {a.axis: a for a in report.axes}
    assert {"speed", "accuracy", "regressions"} == set(by_axis)
    assert all(a.state == "pass" for a in report.axes)


# ---------------------------------------------------------------------------
# 2. Speed axis fails
# ---------------------------------------------------------------------------


def test_speed_axis_fails_when_geomean_below_floor() -> None:
    """geomean=0.8 below min_geomean=1.0 → speed=fail, overall=fail."""
    report = _gate_evaluate(_manifest(geomean=0.8), _default_thresholds())
    by_axis = {a.axis: a for a in report.axes}
    assert by_axis["speed"].state == "fail"
    assert by_axis["speed"].value == pytest.approx(0.8)
    assert by_axis["speed"].threshold == pytest.approx(1.0)
    # Other axes still pass — the failure is isolated to speed.
    assert by_axis["accuracy"].state == "pass"
    assert by_axis["regressions"].state == "pass"
    assert report.overall == "fail"


# ---------------------------------------------------------------------------
# 3. Accuracy axis fails
# ---------------------------------------------------------------------------


def test_accuracy_axis_fails_when_dr2_above_ceiling() -> None:
    """max_dr2=1e-2 above max_dr2 threshold=1e-3 → accuracy=fail, overall=fail."""
    report = _gate_evaluate(_manifest(max_dr2=1e-2), _default_thresholds())
    by_axis = {a.axis: a for a in report.axes}
    assert by_axis["accuracy"].state == "fail"
    assert by_axis["accuracy"].value == pytest.approx(1e-2)
    assert by_axis["accuracy"].threshold == pytest.approx(1e-3)
    assert by_axis["speed"].state == "pass"
    assert by_axis["regressions"].state == "pass"
    assert report.overall == "fail"


# ---------------------------------------------------------------------------
# 4. Regressions axis fails
# ---------------------------------------------------------------------------


def test_regressions_axis_fails_when_count_exceeds_threshold() -> None:
    """2 regression ids vs max_regressions=0 → regressions=fail, overall=fail."""
    report = _gate_evaluate(
        _manifest(regression_ids=["EZ-007", "CX-013"]),
        _default_thresholds(),
    )
    by_axis = {a.axis: a for a in report.axes}
    assert by_axis["regressions"].state == "fail"
    assert by_axis["regressions"].value == pytest.approx(2.0)
    assert by_axis["regressions"].threshold == pytest.approx(0.0)
    assert report.regression_ids == ["EZ-007", "CX-013"]
    assert report.overall == "fail"


# ---------------------------------------------------------------------------
# 5. Mixed states — worst-of aggregation
# ---------------------------------------------------------------------------


def test_mixed_states_fail_dominates_warn() -> None:
    """speed=warn + accuracy=pass + regressions=fail → overall=fail (rank wins).

    Anti-regression for the worst-of aggregation: ``fail`` must dominate
    ``warn`` at the overall headline, just as ``warn`` dominates ``pass``.
    The amber-drift signal cannot mask a red regression.
    """
    thresholds = GateThresholds(
        min_geomean=1.0,
        max_dr2=1e-3,
        max_regressions=0,
        warn_geomean=2.0,
        warn_dr2=1e-4,
        warn_regressions=None,
    )
    # geomean=1.5: above min_geomean=1.0 (pass-band) but below warn_geomean=2.0 → warn.
    # max_dr2=1e-6: below the warn floor 1e-4 → pass.
    # regressions=1: above max_regressions=0 → fail.
    report = _gate_evaluate(
        _manifest(geomean=1.5, max_dr2=1e-6, regression_ids=["EZ-007"]),
        thresholds,
    )
    by_axis = {a.axis: a for a in report.axes}
    assert by_axis["speed"].state == "warn"
    assert by_axis["accuracy"].state == "pass"
    assert by_axis["regressions"].state == "fail"
    assert report.overall == "fail"


def test_mixed_states_warn_dominates_pass() -> None:
    """Two pass axes + one warn → overall=warn (warn rank > pass rank)."""
    thresholds = GateThresholds(
        min_geomean=1.0,
        max_dr2=1e-3,
        max_regressions=0,
        warn_geomean=2.0,
    )
    report = _gate_evaluate(_manifest(geomean=1.5), thresholds)
    by_axis = {a.axis: a for a in report.axes}
    assert by_axis["speed"].state == "warn"
    assert by_axis["accuracy"].state == "pass"
    assert by_axis["regressions"].state == "pass"
    assert report.overall == "warn"


# ---------------------------------------------------------------------------
# 6. Typed ManifestSignals input
# ---------------------------------------------------------------------------


def test_manifest_signals_input_works_like_dict() -> None:
    """A typed ``ManifestSignals`` must drive the same per-axis verdicts as the dict shape.

    The kernel signature is ``dict | ManifestSignals`` so callers with a
    parsed contract object (the FastAPI app, the trend command) can avoid
    a round-trip back to a raw dict just to gate.
    """
    signals = ManifestSignals(
        geomean_speedup_vs_baseline=0.5,
        max_abs_delta_r2=1e-5,
        spectrafit_win_rate=1.0,
        regressions=0,
    )
    report = _gate_evaluate(signals, _default_thresholds())
    by_axis = {a.axis: a for a in report.axes}
    # Speed below 1.0 → fail; other axes pass.
    assert by_axis["speed"].state == "fail"
    assert by_axis["accuracy"].state == "pass"
    assert by_axis["regressions"].state == "pass"
    assert report.overall == "fail"
    # ManifestSignals carries the count, not the ids — kernel synthesises
    # anonymous slots so the count-based axis still fires.
    signals_with_regs = ManifestSignals(
        geomean_speedup_vs_baseline=2.0,
        max_abs_delta_r2=1e-5,
        spectrafit_win_rate=1.0,
        regressions=3,
    )
    report2 = _gate_evaluate(signals_with_regs, _default_thresholds())
    by_axis2 = {a.axis: a for a in report2.axes}
    assert by_axis2["regressions"].state == "fail"
    assert by_axis2["regressions"].value == pytest.approx(3.0)
    assert len(report2.regression_ids) == 3


# ---------------------------------------------------------------------------
# 7. Threshold construction validation (Pydantic-native)
# ---------------------------------------------------------------------------


def test_threshold_validation_rejects_non_numeric_min_geomean() -> None:
    """Bad-type inputs raise ``ValidationError`` at construction time.

    Pydantic catches the type error before the kernel ever runs — the
    failure is at the boundary, not deep inside the gate computation.
    """
    with pytest.raises(ValidationError):
        GateThresholds(min_geomean="bad", max_dr2=1e-3, max_regressions=0)  # type: ignore[arg-type]


def test_threshold_validation_rejects_extra_fields() -> None:
    """``extra='forbid'`` rejects unknown keys — typo guard."""
    with pytest.raises(ValidationError):
        GateThresholds(  # type: ignore[call-arg]
            min_geomean=1.0,
            max_dr2=1e-3,
            max_regressions=0,
            min_geoman=1.0,  # typo of min_geomean
        )


def test_threshold_negative_min_geomean_is_accepted() -> None:
    """No structural bound on ``min_geomean`` — caller-defined semantics.

    The Typer command sets the default; a unit-test that passes a negative
    floor is a legitimate "always pass speed" smoke knob, not a contract
    violation.
    """
    thresholds = GateThresholds(min_geomean=-1.0, max_dr2=1e-3, max_regressions=0)
    assert thresholds.min_geomean == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# Smoke checks on the report shape (model_config = extra='forbid')
# ---------------------------------------------------------------------------


def test_gate_report_rejects_extra_fields() -> None:
    """``GateReport.model_config = extra='forbid'`` per pydantic-first conventions."""
    with pytest.raises(ValidationError):
        GateReport(  # type: ignore[call-arg]
            overall="pass",
            axes=[],
            regression_ids=[],
            geomean_speedup=1.0,
            max_abs_delta_r2=0.0,
            extra_field="boom",
        )


def test_gate_axis_result_rejects_extra_fields() -> None:
    """``GateAxisResult.model_config = extra='forbid'`` per pydantic-first conventions."""
    with pytest.raises(ValidationError):
        GateAxisResult(  # type: ignore[call-arg]
            axis="speed",
            state="pass",
            value=1.0,
            threshold=1.0,
            extra_field="boom",
        )
