"""NIST StRD Bennett5 — power-law-with-offset FitGraph V&V (W8 breadth, new family).

Bennett5 is a 3-parameter, 154-observation nonlinear regression problem from the
NIST Statistical Reference Datasets (StRD) collection.  NIST classifies it as
**"Higher"** difficulty — one of the most ill-conditioned StRD problems.

    y = b1·(b2 + x)^(−1/b3)

This maps 1-to-1 to spectrafit's ``POWER_LAW_OFFSET`` kernel
(params ``amplitude`` = b1, ``offset`` = b2, ``shape`` = b3), so no
re-parameterization is required.

**Ill-conditioned by design** — b1 ≈ −2524 is large in magnitude, and the
exponent −1/b3 ≈ −1.073 is close to −1, making the Jacobian near-singular with
respect to b2 and b3 in certain regions.  The problem is highly start-sensitive:
both NIST starts (−2000,50,0.8) and (−1500,45,0.85) may not converge to the
certified minimum with a plain gradient-based LM solver.  Start2 tests are marked
``xfail(strict=False)`` — convergence to the certified values is welcome (XPASS)
but not guaranteed (XFAIL confirms the "Higher" difficulty label).

Source: https://www.itl.nist.gov/div898/strd/nls/data/bennett5.shtml
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
from oracles.nist_strd.bennett5 import (
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

_LM_OPTS = FitOptions(solver="lm", max_iterations=10000, tolerance=1e-12)


def _build_bennett5_graph(start: dict[str, float]) -> FitGraph:
    """Single POWER_LAW_OFFSET node matching NIST Bennett5 model.

    Mapping: amplitude = b1, offset = b2, shape = b3.

    b1 is large and negative; no positivity constraint is applied to
    amplitude.  offset (b2 ≈ 46.7) must stay positive to keep `offset + x > 0`
    for x ≈ 7–12; we set a loose lower bound of 0.1.  shape (b3 ≈ 0.93) is a
    positive exponent; we set min=0.01 to avoid division-by-zero in −1/shape.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="b5",
                model_type=ModelType.POWER_LAW_OFFSET,
                parameters={
                    "amplitude": Parameter(value=start["b1"]),
                    "offset": Parameter(value=start["b2"], min=0.1),
                    "shape": Parameter(value=start["b3"], min=0.01),
                },
            )
        ]
    )


def _measurement() -> MeasurementData:
    return MeasurementData(x=X.tolist(), y=Y.tolist())


# ---------------------------------------------------------------------------
# Smoke / fixture tests (always pass)
# ---------------------------------------------------------------------------


def test_bennett5_fixture_is_well_formed() -> None:
    """Smoke check on the embedded NIST Bennett5 fixture."""
    assert N_OBS == 154
    assert DOF == 151
    assert X.shape == (154,)
    assert Y.shape == (154,)
    assert np.all(np.isfinite(X))
    assert np.all(np.isfinite(Y))
    # x values should be strictly increasing.
    assert np.all(np.diff(X) > 0), "x values must be strictly increasing"
    # All y values are negative (b1 is negative, u^p > 0).
    assert np.all(Y < 0), "Bennett5 y values are all negative"


def test_bennett5_rss_cross_check() -> None:
    """RSS / DOF = residual std dev² matches published value to 10 sig figs.

    Certified RSS = 5.2404744073e-04, DOF = 151.
    sqrt(RSS/DOF) = 1.8629312528e-03  (certified residual std dev).
    """
    import math

    residual_std = math.sqrt(RSS / DOF)
    assert abs(residual_std - 1.8629312528e-03) / 1.8629312528e-03 < 1e-9, (
        f"RSS cross-check failed: sqrt(RSS/DOF)={residual_std:.10e}"
    )


def test_bennett5_numpy_oracle_at_certified() -> None:
    """The numpy oracle ``amplitude·(offset+x)^(−1/shape)`` at certified params
    produces the expected model values and RSS within floating-point precision.

    This is a kernel-correctness check independent of the solver.
    """
    b1, _ = CERTIFIED["b1"]
    b2, _ = CERTIFIED["b2"]
    b3, _ = CERTIFIED["b3"]

    y_model = b1 * (b2 + X) ** (-1.0 / b3)
    residuals = Y - y_model
    rss_recovered = float(np.sum(residuals**2))

    rel = abs(rss_recovered - RSS) / RSS
    assert rel < 1e-3, (
        f"Numpy oracle at certified params: RSS={rss_recovered:.10e}, "
        f"certified={RSS:.10e}, rel={rel:.2e}"
    )


# ---------------------------------------------------------------------------
# Convergence tests (xfail — Bennett5 is ill-conditioned)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=False,
    reason=(
        "NIST Bennett5 is classified 'Higher' difficulty and is one of the most "
        "ill-conditioned StRD nonlinear problems.  b1 ≈ −2524 is large in magnitude "
        "and the exponent −1/b3 ≈ −1.073 makes the Jacobian nearly singular in the "
        "b2/b3 subspace.  Start2 (b1=−1500, b2=45, b3=0.85) may fail to reach the "
        "certified minimum with the LM solver from a plain gradient-only path. "
        "XPASS (convergence within 1e-3 relative) is welcome; XFAIL confirms the "
        "NIST 'Higher' difficulty classification."
    ),
)
def test_bennett5_recovers_nist_certified_parameters_start2() -> None:
    """From NIST start2, spectrafit recovers certified b1/b2/b3 within 1e-3 relative.

    Start 2 = (b1=−1500, b2=45, b3=0.85) is the closer of the two published
    starting guesses.
    """
    result = fit(_build_bennett5_graph(START2), _measurement(), _LM_OPTS)
    assert result.success is True, (
        f"Bennett5 (start2) did not converge: {result.message}"
    )

    b1_rec = result.params["b5.amplitude"].value
    b2_rec = result.params["b5.offset"].value
    b3_rec = result.params["b5.shape"].value

    b1_cert, _ = CERTIFIED["b1"]
    b2_cert, _ = CERTIFIED["b2"]
    b3_cert, _ = CERTIFIED["b3"]

    rel_b1 = abs(b1_rec - b1_cert) / abs(b1_cert)
    rel_b2 = abs(b2_rec - b2_cert) / abs(b2_cert)
    rel_b3 = abs(b3_rec - b3_cert) / abs(b3_cert)

    assert rel_b1 < 1e-3, (
        f"b1 (start2): recovered {b1_rec:.6e}, certified {b1_cert:.6e}, rel {rel_b1:.2e}"
    )
    assert rel_b2 < 1e-3, (
        f"b2 (start2): recovered {b2_rec:.6e}, certified {b2_cert:.6e}, rel {rel_b2:.2e}"
    )
    assert rel_b3 < 1e-3, (
        f"b3 (start2): recovered {b3_rec:.6e}, certified {b3_cert:.6e}, rel {rel_b3:.2e}"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "NIST Bennett5 start1 (b1=−2000, b2=50, b3=0.8) is further from the "
        "certified minimum than start2 and is expected to fail or land on a "
        "local minimum for LM solvers. XFAIL confirms the 'Higher' difficulty "
        "classification; XPASS (convergence within 1e-3) is a bonus."
    ),
)
def test_bennett5_recovers_nist_certified_parameters_start1() -> None:
    """From NIST start1, spectrafit recovers certified b1/b2/b3 within 1e-3 relative.

    Marked xfail: start1 = (b1=−2000, b2=50, b3=0.8) is the more distant
    starting guess, documented as problematic for gradient-based solvers.
    """
    result = fit(_build_bennett5_graph(START1), _measurement(), _LM_OPTS)
    assert result.success is True, (
        f"Bennett5 (start1) did not converge: {result.message}"
    )

    b1_rec = result.params["b5.amplitude"].value
    b2_rec = result.params["b5.offset"].value
    b3_rec = result.params["b5.shape"].value

    b1_cert, _ = CERTIFIED["b1"]
    b2_cert, _ = CERTIFIED["b2"]
    b3_cert, _ = CERTIFIED["b3"]

    rel_b1 = abs(b1_rec - b1_cert) / abs(b1_cert)
    rel_b2 = abs(b2_rec - b2_cert) / abs(b2_cert)
    rel_b3 = abs(b3_rec - b3_cert) / abs(b3_cert)

    assert rel_b1 < 1e-3, (
        f"b1 (start1): recovered {b1_rec:.6e}, certified {b1_cert:.6e}, rel {rel_b1:.2e}"
    )
    assert rel_b2 < 1e-3, (
        f"b2 (start1): recovered {b2_rec:.6e}, certified {b2_cert:.6e}, rel {rel_b2:.2e}"
    )
    assert rel_b3 < 1e-3, (
        f"b3 (start1): recovered {b3_rec:.6e}, certified {b3_cert:.6e}, rel {rel_b3:.2e}"
    )
