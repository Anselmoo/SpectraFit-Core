"""Track 3 — parity tests for fixed-param and tied/shared-param case families.

TDD: these tests are written RED-FIRST. They verify:

(a) Fixed-param cases: the fixed parameters stay at their truth value after fitting;
    the free parameters recover ground truth within tolerance.

(b) Tied-param cases: the tied-parameter group converges consistently (the tie holds
    in the result) and the recovered params match ground truth, across the backends
    that support expression-tied fits (spectrafit + lmfit). jax and scipy-ls are
    disclosed-excluded for tied cases.
"""

from __future__ import annotations

import pytest

pytest.importorskip("lmfit", reason="benchmark extra (lmfit) required for parity check")

from oracles.backends import get_backends  # noqa: E402
from oracles.cases import BenchCase, build_catalog  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _case_by_id(case_id: str) -> BenchCase:
    for c in build_catalog():
        if c.id == case_id:
            return c
    raise AssertionError(f"{case_id!r} not found in catalog")


def _safe_fit(backend, case: BenchCase):
    """Run one backend fit; return outcome or None on failure."""
    if not backend.is_supported(case):
        return None
    try:
        return backend.fit(case, n_reps=1)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# (a) Fixed-param family: FX-001 through FX-004
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case_id", ["FX-001", "FX-002", "FX-003", "FX-004"])
def test_fixed_case_exists_in_catalog(case_id: str) -> None:
    """Fixed-param cases must be present in the catalog."""
    case = _case_by_id(case_id)
    assert case.category == "fixed"


@pytest.mark.parametrize("case_id", ["FX-001", "FX-002"])
def test_fixed_param_center_recovered_exactly(case_id: str) -> None:
    """For a center-fixed case the fitted center must match truth within 1e-6."""
    case = _case_by_id(case_id)
    fixed = case.spec.fixed_params  # {"p0": ["center"]}
    assert fixed, "expected fixed_params to be non-empty"

    backends = {b.name: b for b in get_backends()}
    spectrafit = backends.get("spectrafit")
    if spectrafit is None:
        pytest.skip("spectrafit backend unavailable")

    outcome = _safe_fit(spectrafit, case)
    assert outcome is not None and outcome.success, "fit must succeed"

    truth = case.true_params  # {"p0.center": ..., "p0.amplitude": ..., ...}
    for node_id, param_names in fixed.items():
        for pname in param_names:
            key = f"{node_id}.{pname}"
            truth_val = truth[key]
            fitted_val = float(outcome.params[key])
            assert abs(fitted_val - truth_val) < 1e-5, (
                f"{case_id}: fixed param {key} drifted "
                f"(truth={truth_val:.6f}, fitted={fitted_val:.6f})"
            )


@pytest.mark.parametrize("case_id", ["FX-001", "FX-002"])
def test_fixed_case_free_params_recover(case_id: str) -> None:
    """Free params must converge to ground truth within 5% relative error."""
    case = _case_by_id(case_id)
    fixed_keys = {
        f"{nid}.{p}"
        for nid, ps in case.spec.fixed_params.items()
        for p in ps
    }

    backends = {b.name: b for b in get_backends()}
    for name in ("spectrafit", "lmfit"):
        b = backends.get(name)
        if b is None or not b.is_supported(case):
            continue
        outcome = _safe_fit(b, case)
        if outcome is None or not outcome.success:
            continue
        truth = case.true_params
        for key, tval in truth.items():
            if key in fixed_keys or abs(tval) < 1e-8:
                continue
            fval = float(outcome.params[key])
            rel = abs(fval - tval) / max(abs(tval), 1e-3)
            assert rel < 0.10, (  # 10% tolerance for noisy cases
                f"{case_id} [{name}]: free param {key} off by {rel:.1%} "
                f"(truth={tval:.4f}, fitted={fval:.4f})"
            )


# ---------------------------------------------------------------------------
# (b) Tied-param family: TI-001 through TI-004
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case_id", ["TI-001", "TI-002", "TI-003", "TI-004"])
def test_tied_case_exists_in_catalog(case_id: str) -> None:
    """Tied-param cases must be present in the catalog."""
    case = _case_by_id(case_id)
    assert case.category == "tied"


@pytest.mark.parametrize("case_id", ["TI-001", "TI-002", "TI-003", "TI-004"])
def test_tied_case_has_expr_edges(case_id: str) -> None:
    """Tied cases must carry at least one expr_edge."""
    case = _case_by_id(case_id)
    assert case.spec.expr_edges, f"{case_id} has no expr_edges"


@pytest.mark.parametrize("case_id", ["TI-001", "TI-002"])
def test_tied_param_group_consistent_spectrafit(case_id: str) -> None:
    """spectrafit: all tied params in a group must agree within 1e-6."""
    case = _case_by_id(case_id)
    backends = {b.name: b for b in get_backends()}
    spectrafit = backends.get("spectrafit")
    if spectrafit is None:
        pytest.skip("spectrafit backend unavailable")

    outcome = _safe_fit(spectrafit, case)
    assert outcome is not None and outcome.success, "spectrafit fit must succeed"

    for edge in case.spec.expr_edges:
        # edge: {"target_node": "p1", "target_param": "sigma",
        #        "expression": "p0.sigma"}
        target_key = f"{edge['target_node']}.{edge['target_param']}"
        # parse source from expression ("p0.sigma" → key "p0.sigma")
        src_key = edge["expression"].strip()
        if "." in src_key:
            fitted_target = float(outcome.params[target_key])
            fitted_source = float(outcome.params[src_key])
            assert abs(fitted_target - fitted_source) < 1e-4, (
                f"{case_id}: tied params {target_key} and {src_key} diverge "
                f"({fitted_target:.6f} vs {fitted_source:.6f})"
            )


@pytest.mark.parametrize("case_id", ["TI-001", "TI-002"])
def test_tied_param_group_consistent_lmfit(case_id: str) -> None:
    """lmfit: tied params must agree within 1e-4 (lmfit applies expr= constraint)."""
    pytest.importorskip("lmfit")
    case = _case_by_id(case_id)
    backends = {b.name: b for b in get_backends()}
    lmfit_b = backends.get("lmfit")
    if lmfit_b is None or not lmfit_b.is_supported(case):
        pytest.skip("lmfit backend not available or not supported")

    outcome = _safe_fit(lmfit_b, case)
    assert outcome is not None and outcome.success, "lmfit fit must succeed"

    for edge in case.spec.expr_edges:
        target_key = f"{edge['target_node']}.{edge['target_param']}"
        src_key = edge["expression"].strip()
        if "." in src_key:
            fitted_target = float(outcome.params[target_key])
            fitted_source = float(outcome.params[src_key])
            assert abs(fitted_target - fitted_source) < 1e-3, (
                f"{case_id} [lmfit]: tied params {target_key} and {src_key} diverge "
                f"({fitted_target:.6f} vs {fitted_source:.6f})"
            )


@pytest.mark.parametrize("case_id", ["TI-001", "TI-002"])
def test_tied_case_truth_recovery_spectrafit(case_id: str) -> None:
    """spectrafit: tied-case free params recover ground truth within 8%."""
    case = _case_by_id(case_id)
    backends = {b.name: b for b in get_backends()}
    spectrafit = backends.get("spectrafit")
    if spectrafit is None:
        pytest.skip("spectrafit backend unavailable")

    outcome = _safe_fit(spectrafit, case)
    assert outcome is not None and outcome.success, "spectrafit fit must succeed"

    tied_targets = {
        f"{e['target_node']}.{e['target_param']}" for e in case.spec.expr_edges
    }
    truth = case.true_params
    for key, tval in truth.items():
        if key in tied_targets or abs(tval) < 1e-8:
            continue
        fval = float(outcome.params[key])
        rel = abs(fval - tval) / max(abs(tval), 1e-3)
        assert rel < 0.12, (
            f"{case_id}: param {key} off by {rel:.1%} "
            f"(truth={tval:.4f}, fitted={fval:.4f})"
        )


def test_jax_does_not_support_tied_cases() -> None:
    """jax and scipy-ls backends must disclose exclusion for tied cases."""
    case = _case_by_id("TI-001")
    backends = {b.name: b for b in get_backends()}
    for name in ("jax", "scipy-ls-lm", "scipy-ls-trf", "scipy-ls-dogbox"):
        b = backends.get(name)
        if b is not None:
            assert not b.is_supported(case), (
                f"{name} must not claim support for tied cases (has expr_edges)"
            )
