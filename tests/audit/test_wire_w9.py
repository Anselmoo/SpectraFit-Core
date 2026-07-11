"""Task 4.5 — wire W9: nested-model adequacy + gate axis.

W9 passes iff ``nested_adequacy.recovered_true_order_bic is True`` (BIC governs
the wire; AIC is reported for transparency but does not control the verdict).
When ``nested_adequacy`` is ``None`` the wire is ``skipped`` (no pass-by-absence).
"""

from __future__ import annotations

from oracles.bench_contract import NestedAdequacy, SelectionStats
from oracles.cli import (
    GateThresholds,
    _gate_evaluate,
)
from oracles.audit.wires import ALL_WIRES, wire_w9_nested_adequacy


# ---------------------------------------------------------------------------
# Minimal fixture helpers
# ---------------------------------------------------------------------------

def _make_selection_stats() -> SelectionStats:
    """Minimal SelectionStats for fixture use."""
    return SelectionStats(
        lrt_stat=5.0,
        lrt_p=0.02,
        f_stat=4.5,
        f_p=0.04,
        d_aic=-3.0,
        d_bic=-2.0,
    )


def _make_nested_adequacy(
    *,
    recovered_true_order_bic: bool,
    recovered_true_order_aic: bool = True,
    true_order: int = 3,
    reduced_rejected: bool = True,
    over_not_preferred_aic: bool = False,
    over_not_preferred_bic: bool = True,
    selected_order_aic: int = 4,
    selected_order_bic: int = 3,
) -> NestedAdequacy:
    return NestedAdequacy(
        true_order=true_order,
        reduced_rejected=reduced_rejected,
        over_not_preferred_aic=over_not_preferred_aic,
        over_not_preferred_bic=over_not_preferred_bic,
        selected_order_aic=selected_order_aic,
        selected_order_bic=selected_order_bic,
        recovered_true_order_aic=recovered_true_order_aic,
        recovered_true_order_bic=recovered_true_order_bic,
        reduced_vs_true=_make_selection_stats(),
        true_vs_over=_make_selection_stats(),
    )


# ---------------------------------------------------------------------------
# Wire W9: tri-state (pass / fail / skipped)
# ---------------------------------------------------------------------------

def test_w9_pass_when_bic_recovers_true_order() -> None:
    na = _make_nested_adequacy(recovered_true_order_bic=True)
    results = wire_w9_nested_adequacy(nested_adequacy=na)
    assert len(results) == 1
    r = results[0]
    assert r.wire_id == "W9"
    assert r.status == "pass"
    assert "bic" in r.evidence.lower()


def test_w9_fail_when_bic_does_not_recover_true_order() -> None:
    na = _make_nested_adequacy(
        recovered_true_order_bic=False,
        recovered_true_order_aic=True,
        selected_order_bic=4,  # ≠ true_order=3: consistent with non-recovery
    )
    results = wire_w9_nested_adequacy(nested_adequacy=na)
    assert len(results) == 1
    r = results[0]
    assert r.wire_id == "W9"
    assert r.status == "fail"
    # Evidence should mention both AIC and BIC so the disagreement is visible.
    assert "bic" in r.evidence.lower()
    assert "aic" in r.evidence.lower()


def test_w9_skipped_when_nested_adequacy_is_none() -> None:
    results = wire_w9_nested_adequacy(nested_adequacy=None)
    assert len(results) == 1
    r = results[0]
    assert r.wire_id == "W9"
    assert r.status == "skipped"
    # No pass-by-absence: skipped must not claim the evidence is present.
    assert "not asserted" in r.evidence.lower() or "absent" in r.evidence.lower() or "skipped" in r.evidence.lower()


def test_w9_default_arg_is_none() -> None:
    """Calling wire_w9_nested_adequacy() with no args must return skipped."""
    results = wire_w9_nested_adequacy()
    assert results[0].status == "skipped"


def test_w9_evidence_includes_aic_bic_split() -> None:
    """Both AIC and BIC verdicts must appear in the evidence string."""
    na = _make_nested_adequacy(
        recovered_true_order_bic=True,
        recovered_true_order_aic=False,
    )
    results = wire_w9_nested_adequacy(nested_adequacy=na)
    evidence = results[0].evidence.lower()
    assert "aic" in evidence
    assert "bic" in evidence


def test_w9_is_registered_in_all_wires() -> None:
    assert wire_w9_nested_adequacy in ALL_WIRES


# ---------------------------------------------------------------------------
# Gate axis: model_selection
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


def test_gate_model_selection_fails_when_bic_false() -> None:
    """Gate fails when nested_adequacy is present and BIC does not recover true order."""
    na = _make_nested_adequacy(recovered_true_order_bic=False, selected_order_bic=4)
    manifest = _minimal_manifest()
    report = _gate_evaluate(manifest, _default_thresholds(), nested_adequacy=na)
    assert report.overall == "fail"
    ms_axis = next((a for a in report.axes if a.axis == "model_selection"), None)
    assert ms_axis is not None
    assert ms_axis.state == "fail"


def test_gate_model_selection_passes_when_bic_true() -> None:
    """Gate passes (all-green) when nested_adequacy is present and BIC recovers true order."""
    na = _make_nested_adequacy(recovered_true_order_bic=True)
    manifest = _minimal_manifest()
    report = _gate_evaluate(manifest, _default_thresholds(), nested_adequacy=na)
    assert report.overall == "pass"
    ms_axis = next((a for a in report.axes if a.axis == "model_selection"), None)
    assert ms_axis is not None
    assert ms_axis.state == "pass"


def test_gate_model_selection_absent_when_nested_adequacy_none() -> None:
    """When nested_adequacy is None the model_selection axis is not included."""
    manifest = _minimal_manifest()
    report = _gate_evaluate(manifest, _default_thresholds(), nested_adequacy=None)
    ms_axis = next((a for a in report.axes if a.axis == "model_selection"), None)
    assert ms_axis is None
    # The gate must still pass (no regression introduced).
    assert report.overall == "pass"


def test_gate_model_selection_default_absent() -> None:
    """Calling _gate_evaluate without nested_adequacy must not add the axis."""
    manifest = _minimal_manifest()
    report = _gate_evaluate(manifest, _default_thresholds())
    names = [a.axis for a in report.axes]
    assert "model_selection" not in names
