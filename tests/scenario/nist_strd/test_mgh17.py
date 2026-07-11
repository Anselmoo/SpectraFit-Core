"""NIST StRD MGH17 (Osborne 1) — Constant + DoubleExponential FitGraph V&V.

Model: y = b1 + b2·exp(−b4·x) + b3·exp(−b5·x)
5 free parameters, 33 observations, DOF = 28.
NIST difficulty: Higher (start-sensitive).

**Two-node composition** — spectrafit expresses the model as:

* ``bg`` — ``Constant(c=b1)``: the constant baseline.
* ``exp`` — ``DoubleExponential(A1=b2, lam1=b4, A2=b3, lam2=b5)``: the two
  exponential decay terms. Note b3 < 0 in the certified solution, so A2 has
  no lower bound (it must be free to go negative).

Total free parameters: 1 (bg.c) + 4 (exp.A1, exp.lam1, exp.A2, exp.lam2) = 5.
DOF = 33 − 5 = 28.

**Higher difficulty** — NIST Start 1 is far from the certified solution (b4=1,
b5=2 vs certified ~0.013, ~0.022). Start 1 is marked xfail because LM solvers
routinely converge to a different local minimum from that starting point.

Source: https://www.itl.nist.gov/div898/strd/nls/data/mgh17.shtml
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from spectrafit_core import (
    FitGraph,
    FitOptions,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)
from oracles.nist_strd.mgh17 import (
    CERTIFIED,
    DOF,
    N_OBS,
    RSS,
    RESIDUAL_STD_DEV,
    START1,
    START2,
    X,
    Y,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_graph(start: dict[str, float]) -> FitGraph:
    """Build the Constant + DoubleExponential FitGraph matching NIST MGH17.

    Node ``bg`` carries the constant offset b1; node ``exp`` carries the two
    exponential decay terms b2·exp(−b4·x) + b3·exp(−b5·x).

    b3 is negative in the certified solution so A2 has no min bound.
    b4 and b5 are positive rate constants so lam1/lam2 are bounded min=0.
    """
    bg_node = ModelNodeSpec(
        id="bg",
        model_type=ModelType.CONSTANT,
        parameters={
            "c": Parameter(value=start["b1"]),
        },
    )
    exp_node = ModelNodeSpec(
        id="exp",
        model_type=ModelType.DOUBLE_EXPONENTIAL,
        parameters={
            "A1": Parameter(value=start["b2"]),
            "lam1": Parameter(value=start["b4"], min=0.0),
            "A2": Parameter(value=start["b3"]),
            "lam2": Parameter(value=start["b5"], min=0.0),
        },
    )
    return FitGraph(nodes=[bg_node, exp_node])


def _measurement() -> MeasurementData:
    return MeasurementData(x=X.tolist(), y=Y.tolist())


def _project_to_nist(result) -> dict[str, float]:  # noqa: ANN001
    """Spectrafit node params → NIST b1..b5 mapping."""
    p = result.params
    return {
        "b1": p["bg.c"].value,
        "b2": p["exp.A1"].value,
        "b3": p["exp.A2"].value,
        "b4": p["exp.lam1"].value,
        "b5": p["exp.lam2"].value,
    }


_LM_OPTS = FitOptions(solver="lm", max_iterations=10000, tolerance=1e-12)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=False,
    reason=(
        "NIST MGH17 Start 1 is classified 'Higher' difficulty: b4=1, b5=2 are "
        "far from the certified solution (~0.013, ~0.022). LM solvers routinely "
        "land on a different local minimum from this starting point. If Start 1 "
        "converges (XPASS) that is acceptable — the solver reached the global minimum "
        "from the harder starting guess."
    ),
)
def test_mgh17_recovers_nist_certified_parameters_start1() -> None:
    """From NIST Start 1, spectrafit recovers all 5 certified parameters
    within 1e-3 relative tolerance.

    Marked xfail because Start 1 is documented as convergence-fragile for
    LM solvers on this 'Higher' difficulty problem (rate constants b4/b5
    start orders of magnitude too large).
    """
    result = fit(_build_graph(START1), _measurement(), _LM_OPTS)
    assert result.success is True, (
        f"MGH17 (start1) did not converge: {result.message}"
    )

    recovered = _project_to_nist(result)
    for name, (certified_val, _) in CERTIFIED.items():
        rel = abs(recovered[name] - certified_val) / abs(certified_val)
        assert rel < 1e-3, (
            f"{name} (start1): recovered {recovered[name]:.6e}, "
            f"certified {certified_val:.6e}, rel {rel:.2e}"
        )


def test_mgh17_recovers_nist_certified_parameters_start2() -> None:
    """From NIST Start 2, spectrafit recovers all 5 certified parameters
    within 1e-3 relative tolerance.

    The Constant + DoubleExponential composition must reach the certified
    solution, verifying that the multi-node Jacobian assembly produces the
    correct gradient for all five free parameters simultaneously.
    """
    result = fit(_build_graph(START2), _measurement(), _LM_OPTS)
    assert result.success is True, (
        f"MGH17 (start2) did not converge: {result.message}"
    )

    recovered = _project_to_nist(result)
    for name, (certified_val, _) in CERTIFIED.items():
        rel = abs(recovered[name] - certified_val) / abs(certified_val)
        assert rel < 1e-3, (
            f"{name} (start2): recovered {recovered[name]:.6e}, "
            f"certified {certified_val:.6e}, rel {rel:.2e}"
        )


def test_mgh17_rss_matches_nist_certified() -> None:
    """The fitted RSS lies within 1e-4 relative tolerance of certified.

    Certified RSS = 5.4648946975E-05 (real data, not machine-epsilon scale).
    """
    result = fit(_build_graph(START2), _measurement(), _LM_OPTS)
    assert result.success is True

    rss_recovered = float(result.chi2)
    rel = abs(rss_recovered - RSS) / RSS
    assert rel < 1e-4, (
        f"RSS: recovered {rss_recovered:.6e}, certified {RSS:.6e}, "
        f"rel {rel:.2e}"
    )


def test_mgh17_reduced_chi2_and_dof() -> None:
    """Reduced χ² ≈ RSS/DOF and DOF == 28 (5 free params, 33 obs)."""
    result = fit(_build_graph(START2), _measurement(), _LM_OPTS)
    assert result.success is True

    assert result.dof == DOF, f"dof={result.dof}, expected {DOF}"

    certified_red_chi2 = RSS / DOF
    recovered = float(result.reduced_chi2)
    rel = abs(recovered - certified_red_chi2) / certified_red_chi2
    assert rel < 1e-4, (
        f"reduced χ²: recovered {recovered:.6e}, "
        f"certified {certified_red_chi2:.6e}, rel {rel:.2e}"
    )


def test_mgh17_certified_stderr_within_tolerance() -> None:
    """Certified standard errors are recovered within 5e-2 relative tolerance.

    The NIST .dat file publishes standard deviations for b1..b5; these are
    the square roots of the diagonal of the covariance matrix C = σ²·(JᵀJ)⁻¹
    evaluated at the certified solution. This test checks that spectrafit's
    reported parameter standard errors agree to ≤5% relative.
    """
    result = fit(_build_graph(START2), _measurement(), _LM_OPTS)
    assert result.success is True

    p = result.params

    # Map NIST param names to the node.param keys for stderr lookup.
    stderr_map = {
        "b1": p["bg.c"].stderr,
        "b2": p["exp.A1"].stderr,
        "b3": p["exp.A2"].stderr,
        "b4": p["exp.lam1"].stderr,
        "b5": p["exp.lam2"].stderr,
    }

    for name, (_, certified_sigma) in CERTIFIED.items():
        fitted_sigma = stderr_map[name]
        assert fitted_sigma is not None, (
            f"{name}: stderr is None (covariance not computed?)"
        )
        rel = abs(fitted_sigma - certified_sigma) / certified_sigma
        assert rel < 5e-2, (
            f"{name} stderr: recovered {fitted_sigma:.6e}, "
            f"certified {certified_sigma:.6e}, rel {rel:.2e}"
        )


def test_mgh17_fixture_is_well_formed() -> None:
    """Smoke check on the embedded NIST MGH17 fixture."""
    assert N_OBS == 33
    assert DOF == 28
    assert X.shape == (33,)
    assert Y.shape == (33,)
    assert np.all(np.isfinite(X))
    assert np.all(np.isfinite(Y))
    # x runs from 0 to 320 in steps of 10.
    assert X[0] == pytest.approx(0.0)
    assert X[-1] == pytest.approx(320.0)
    # y starts at 0.844 and approaches a positive asymptote (b1 ≈ 0.375).
    assert Y[0] == pytest.approx(0.844)
    assert Y[-1] == pytest.approx(0.406)
    # Cross-check: sqrt(RSS/DOF) must equal the certified residual std dev.
    assert math.isclose(
        math.sqrt(RSS / DOF), RESIDUAL_STD_DEV, rel_tol=1e-9
    ), f"sqrt(RSS/DOF)={math.sqrt(RSS / DOF):.10e} != {RESIDUAL_STD_DEV:.10e}"
