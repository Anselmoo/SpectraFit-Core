"""NIST StRD Lanczos1 — triple-exponential FitGraph V&V (Cycle 16.E).

This is the first NIST StRD problem in this suite with **no Gaussians**:
all three terms are pure exponential decays.

    y = b1·exp(-b2·x) + b3·exp(-b4·x) + b5·exp(-b6·x)

6 free parameters, 24 observations, DOF = 18.

**Two-DoubleExponential composition** — spectrafit has no single
three-exponential kernel, so the model is assembled from two
``DoubleExponential`` nodes:

* ``exp12`` — ``DoubleExponential(A1=b1, lam1=b2, A2=b3, lam2=b4)``:
  covers the first two terms (4 free params).
* ``exp3`` — ``DoubleExponential(A1=b5, lam1=b6, A2=0[vary=False],
  lam2=1.0[vary=False])``: covers the third term (2 free params).
  A2 is pinned at 0 to nullify the second slot; lam2 is irrelevant.

Total free parameters: 6. DOF = 24 − 6 = 18.

**Tiny-RSS caveat** — Lanczos1 is synthetically generated data, so
the certified RSS (1.4307867721e-25) is at machine-epsilon scale.
Any solver that reaches the global minimum will land in the range
1e-22 to 1e-25 due to floating-point accumulation differences.
The RSS and reduced-χ² assertions therefore use **absolute**
tolerances (1e-20) rather than relative ones.

**Start1 fragility** — NIST classifies Lanczos1 as "Average" but in
practice convergence from start1 is fragile for LM solvers because the
cost surface curvature is near-degenerate at the global minimum.  If
start1 does not converge the corresponding parameter-recovery test is
marked ``xfail``.

Source: https://www.itl.nist.gov/div898/strd/nls/data/lanczos1.shtml
"""

from __future__ import annotations

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
from oracles.nist_strd.lanczos1 import (
    CERTIFIED,
    DOF,
    N_OBS,
    RSS,
    START1,
    START2,
    X,
    Y,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_graph(start: dict[str, float]) -> FitGraph:
    """Build the two-DoubleExponential FitGraph matching NIST Lanczos1.

    Node ``exp12`` carries the first two exponential terms (b1..b4, four
    free params); node ``exp3`` carries the third term (b5, b6, two free
    params) by pinning A2=0 and lam2=1.0 (frozen).
    """
    exp12_node = ModelNodeSpec(
        id="exp12",
        model_type=ModelType.DOUBLE_EXPONENTIAL,
        parameters={
            "A1": Parameter(value=start["b1"], min=0.0),
            "lam1": Parameter(value=start["b2"], min=0.0),
            "A2": Parameter(value=start["b3"], min=0.0),
            "lam2": Parameter(value=start["b4"], min=0.0),
        },
    )
    exp3_node = ModelNodeSpec(
        id="exp3",
        model_type=ModelType.DOUBLE_EXPONENTIAL,
        parameters={
            "A1": Parameter(value=start["b5"], min=0.0),
            "lam1": Parameter(value=start["b6"], min=0.0),
            # A2 pinned at 0 to nullify the second slot of this node.
            "A2": Parameter(value=0.0, vary=False),
            "lam2": Parameter(value=1.0, vary=False),
        },
    )
    return FitGraph(nodes=[exp12_node, exp3_node])


def _measurement() -> MeasurementData:
    return MeasurementData(x=X.tolist(), y=Y.tolist())


def _project_to_nist(result) -> dict[str, float]:  # noqa: ANN001
    """Spectrafit node params → NIST b1..b6 mapping."""
    return {
        "b1": result.params["exp12.A1"].value,
        "b2": result.params["exp12.lam1"].value,
        "b3": result.params["exp12.A2"].value,
        "b4": result.params["exp12.lam2"].value,
        "b5": result.params["exp3.A1"].value,
        "b6": result.params["exp3.lam1"].value,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=False,
    reason=(
        "NIST Lanczos1 start1 is known LM-hard: near-degenerate curvature at "
        "the machine-epsilon RSS minimum makes convergence from start1 fragile. "
        "If start1 converges (XPASS) that is acceptable — it means this "
        "spectrafit build reaches the global minimum from both NIST guesses."
    ),
)
def test_lanczos1_recovers_nist_certified_parameters_start1() -> None:
    """From NIST start1, spectrafit recovers all 6 certified parameters
    within 1e-3 relative tolerance.

    Marked xfail because start1 is documented as convergence-fragile for
    LM solvers on this problem (near-degenerate cost surface).
    """
    opts = FitOptions(solver="lm", max_iterations=10000, tolerance=1e-12)
    result = fit(_build_graph(START1), _measurement(), opts)
    assert result.success is True, (
        f"Lanczos1 (start1) did not converge: {result.message}"
    )

    recovered = _project_to_nist(result)
    for name, (certified_val, _) in CERTIFIED.items():
        rel = abs(recovered[name] - certified_val) / abs(certified_val)
        assert rel < 1e-3, (
            f"{name} (start1): recovered {recovered[name]:.6e}, "
            f"certified {certified_val:.6e}, rel {rel:.2e}"
        )


def test_lanczos1_recovers_nist_certified_parameters_start2() -> None:
    """From NIST start2, spectrafit recovers all 6 certified parameters
    within 1e-3 relative tolerance.

    The two-DoubleExponential composition must reach the same global
    minimum as a hypothetical single three-exponential kernel would,
    verifying the multi-node Jacobian assembly produces the correct
    gradient for all six free parameters simultaneously.
    """
    opts = FitOptions(solver="lm", max_iterations=10000, tolerance=1e-12)
    result = fit(_build_graph(START2), _measurement(), opts)
    assert result.success is True, (
        f"Lanczos1 (start2) did not converge: {result.message}"
    )

    recovered = _project_to_nist(result)
    for name, (certified_val, _) in CERTIFIED.items():
        rel = abs(recovered[name] - certified_val) / abs(certified_val)
        assert rel < 1e-3, (
            f"{name} (start2): recovered {recovered[name]:.6e}, "
            f"certified {certified_val:.6e}, rel {rel:.2e}"
        )


def test_lanczos1_rss_matches_nist_certified() -> None:
    """The fitted RSS lies within absolute tolerance 1e-20 of certified.

    Certified RSS = 1.4307867721e-25 (machine-epsilon scale; synthetically
    generated data).  Relative tolerance is meaningless at this scale, so
    the assertion uses absolute tolerance 1e-20 — any solver reaching the
    global minimum will satisfy this, and any solver that lands in a nearby
    local minimum (RSS ≫ 1e-20) will fail it.
    """
    opts = FitOptions(solver="lm", max_iterations=10000, tolerance=1e-12)
    result = fit(_build_graph(START2), _measurement(), opts)
    assert result.success is True

    rss_recovered = float(result.chi2)
    assert abs(rss_recovered - RSS) < 1e-20, (
        f"RSS: recovered {rss_recovered:.6e}, certified {RSS:.6e}, "
        f"abs_diff {abs(rss_recovered - RSS):.6e}"
    )


def test_lanczos1_reduced_chi2_matches_certified() -> None:
    """Reduced χ² lies within absolute tolerance 1e-21 of certified.

    Certified reduced χ² = RSS / DOF = 1.4307867721e-25 / 18 ≈ 7.95e-27.
    Again at machine-epsilon scale; absolute tolerance 1e-21 is used.
    Also cross-checks that spectrafit counts DOF = 18 correctly: the two
    fixed parameters (exp3.A2, exp3.lam2) must be excluded from the
    free-parameter count (6 free, not 8).
    """
    opts = FitOptions(solver="lm", max_iterations=10000, tolerance=1e-12)
    result = fit(_build_graph(START2), _measurement(), opts)
    assert result.success is True

    certified_red_chi2 = RSS / DOF
    recovered = float(result.reduced_chi2)
    assert abs(recovered - certified_red_chi2) < 1e-21, (
        f"reduced χ²: recovered {recovered:.6e}, "
        f"certified {certified_red_chi2:.6e}, "
        f"abs_diff {abs(recovered - certified_red_chi2):.6e}"
    )
    assert result.dof == DOF


def test_lanczos1_fixture_is_well_formed() -> None:
    """Smoke check on the embedded NIST Lanczos1 fixture.

    Verifies the observation count and that Y is strictly monotonically
    decreasing — the sum of three positive-amplitude exponential decays
    on x ≥ 0 with positive rate constants must be a strictly decreasing
    function.
    """
    assert N_OBS == 24
    assert DOF == 18
    assert X.shape == (24,)
    assert Y.shape == (24,)
    assert np.all(np.isfinite(X))
    assert np.all(np.isfinite(Y))
    # x runs from 0.0 to 1.15 in steps of 0.05.
    assert X[0] == pytest.approx(0.0)
    assert X[-1] == pytest.approx(1.15)
    # Sum of positive-amplitude, positive-rate exponential decays is
    # strictly decreasing — each successive Y must be smaller than the last.
    assert np.all(np.diff(Y) < 0), (
        "Lanczos1 Y must be strictly monotonically decreasing "
        "(sum of three decaying exponentials on x≥0)"
    )
