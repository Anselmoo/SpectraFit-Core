"""NIST StRD Misra1a — saturating-exponential FitGraph V&V (W8 breadth, 4th dataset).

Misra1a is a 2-parameter, 14-observation nonlinear regression problem from the
NIST Statistical Reference Datasets (StRD) collection.  NIST classifies it as
**"Lower"** difficulty — both starting points should converge for well-implemented
LM solvers.

    y = b1·(1 − exp(−b2·x))

This maps 1-to-1 to spectrafit's ``SATURATING_EXPONENTIAL`` kernel
(params ``amplitude`` = b1, ``rate`` = b2), so no re-parameterization is
required.  The single-node graph exercises:

* The saturating-exponential kernel formula (exact correctness vs NIST truth).
* The covariance-from-Jacobian path (certified σ check for a 2-param model).
* The trust-region LM convergence from "Lower" difficulty starts.
* DOF accounting: 14 − 2 = 12 (larger dataset than BoxBOD, verified here).

Source: https://www.itl.nist.gov/div898/strd/nls/data/misra1a.shtml
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
from oracles.nist_strd.misra1a import (
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


def _build_misra1a_graph(start: dict[str, float]) -> FitGraph:
    """Single SATURATING_EXPONENTIAL node matching NIST Misra1a model.

    Mapping: amplitude = b1, rate = b2.  Both parameters constrained to
    min=0 because the Misra1a model is physically meaningful only for
    positive amplitude and rate.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="m1a",
                model_type=ModelType.SATURATING_EXPONENTIAL,
                parameters={
                    "amplitude": Parameter(value=start["b1"], min=0.0),
                    "rate": Parameter(value=start["b2"], min=0.0),
                },
            )
        ]
    )


def _measurement() -> MeasurementData:
    return MeasurementData(x=X.tolist(), y=Y.tolist())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_misra1a_fixture_is_well_formed() -> None:
    """Smoke check on the embedded NIST Misra1a fixture."""
    assert N_OBS == 14
    assert DOF == 12
    assert X.shape == (14,)
    assert Y.shape == (14,)
    assert np.all(np.isfinite(X))
    assert np.all(np.isfinite(Y))
    # x values (pressure) are strictly increasing.
    assert np.all(np.diff(X) > 0)
    # y values (volume) are strictly increasing toward saturation.
    assert np.all(np.diff(Y) > 0)


@pytest.mark.parametrize("start_name,start", [("start2", START2), ("start1", START1)])
def test_misra1a_recovers_nist_certified_parameters(
    start_name: str, start: dict[str, float]
) -> None:
    """From NIST starting values, spectrafit recovers certified b1 and b2 within 1e-3 relative.

    NIST classifies Misra1a as "Lower" difficulty; both Start 1 and Start 2
    should converge.  The ``SATURATING_EXPONENTIAL`` node maps amplitude↔b1
    and rate↔b2 directly.
    """
    result = fit(_build_misra1a_graph(start), _measurement(), _LM_OPTS)
    assert result.success is True, (
        f"Misra1a ({start_name}) did not converge: {result.message}"
    )

    b1_recovered = result.params["m1a.amplitude"].value
    b2_recovered = result.params["m1a.rate"].value

    b1_cert, _ = CERTIFIED["b1"]
    b2_cert, _ = CERTIFIED["b2"]

    rel_b1 = abs(b1_recovered - b1_cert) / abs(b1_cert)
    rel_b2 = abs(b2_recovered - b2_cert) / abs(b2_cert)

    assert rel_b1 < 1e-3, (
        f"b1 ({start_name}): recovered {b1_recovered:.6e}, "
        f"certified {b1_cert:.6e}, rel {rel_b1:.2e}"
    )
    assert rel_b2 < 1e-3, (
        f"b2 ({start_name}): recovered {b2_recovered:.6e}, "
        f"certified {b2_cert:.6e}, rel {rel_b2:.2e}"
    )


def test_misra1a_rss_matches_nist_certified() -> None:
    """The fitted residual sum of squares matches NIST's certified RSS within 1e-4 relative.

    Certified RSS = 1.2455138894e-01 (10 significant figures).
    """
    result = fit(_build_misra1a_graph(START2), _measurement(), _LM_OPTS)
    assert result.success is True

    rss_recovered = float(result.chi2)
    rel = abs(rss_recovered - RSS) / RSS
    assert rel < 1e-4, (
        f"RSS: recovered {rss_recovered:.10e}, certified {RSS:.10e}, rel {rel:.2e}"
    )


def test_misra1a_reduced_chi2_and_dof() -> None:
    """Reduced χ² matches certified RSS/DOF within 1e-4 relative; DOF == 12.

    Cross-checks the DOF count: spectrafit must count 14 − 2 = 12 (both
    parameters are free; no fixed parameters).
    """
    result = fit(_build_misra1a_graph(START2), _measurement(), _LM_OPTS)
    assert result.success is True

    assert result.dof == DOF, (
        f"DOF mismatch: spectrafit reports {result.dof}, expected {DOF}"
    )

    certified_red_chi2 = RSS / DOF
    recovered = float(result.reduced_chi2)
    rel = abs(recovered - certified_red_chi2) / certified_red_chi2
    assert rel < 1e-4, (
        f"reduced χ²: recovered {recovered:.10e}, "
        f"certified {certified_red_chi2:.10e}, rel {rel:.2e}"
    )


def test_misra1a_certified_stderr_matches_nist() -> None:
    """Per-parameter stderrs match NIST certified 1σ within 5e-2 relative.

    spectrafit computes cov = (JᵀJ)⁻¹·(chi2/DOF) after convergence, so the
    per-parameter stderr should agree with NIST's certified standard deviations.

    Tolerance: 5e-2 relative (≈ 5%).  The wider envelope accounts for the
    covariance inversion in IEEE-754 double precision vs NIST extended precision.
    """
    result = fit(_build_misra1a_graph(START2), _measurement(), _LM_OPTS)
    assert result.success is True

    amp_pr = result.params["m1a.amplitude"]
    rate_pr = result.params["m1a.rate"]

    assert amp_pr.stderr is not None, "amplitude stderr must not be None after convergence"
    assert rate_pr.stderr is not None, "rate stderr must not be None after convergence"

    _, b1_sigma_cert = CERTIFIED["b1"]
    _, b2_sigma_cert = CERTIFIED["b2"]

    sigma_b1_recovered = float(amp_pr.stderr)
    sigma_b2_recovered = float(rate_pr.stderr)

    rel_b1 = abs(sigma_b1_recovered - b1_sigma_cert) / b1_sigma_cert
    rel_b2 = abs(sigma_b2_recovered - b2_sigma_cert) / b2_sigma_cert

    assert rel_b1 < 5e-2, (
        f"b1 stderr: recovered {sigma_b1_recovered:.6e}, "
        f"certified {b1_sigma_cert:.6e}, rel {rel_b1:.4f}"
    )
    assert rel_b2 < 5e-2, (
        f"b2 stderr: recovered {sigma_b2_recovered:.6e}, "
        f"certified {b2_sigma_cert:.6e}, rel {rel_b2:.4f}"
    )
