"""NIST StRD Misra1b — power-law saturation FitGraph V&V (W8 breadth, 5th dataset).

Misra1b is a 2-parameter, 14-observation nonlinear regression problem from the
NIST Statistical Reference Datasets (StRD) collection.  NIST classifies it as
**"Lower"** difficulty — both starting points should converge for well-implemented
LM solvers.

    y = b1·(1 − (1 + b2·x/2)^(−2))

This maps 1-to-1 to spectrafit's ``POWER_SATURATION`` kernel
(params ``amplitude`` = b1, ``rate`` = b2), so no re-parameterization is
required.  The single-node graph exercises:

* The power-law saturation kernel formula (exact correctness vs NIST truth).
* The analytic Jacobian of the PowerSaturation kernel vs certified σ.
* The trust-region LM convergence from "Lower" difficulty starts.
* DOF accounting: 14 − 2 = 12 (verified here).
* The 4th model family in the NIST StRD validation suite.

Note: Misra1a and Misra1b share the same dataset; they differ only in the
functional form of the saturation model.

Source: https://www.itl.nist.gov/div898/strd/nls/data/misra1b.shtml
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
from oracles.nist_strd.misra1b import (
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


def _build_misra1b_graph(start: dict[str, float]) -> FitGraph:
    """Single POWER_SATURATION node matching NIST Misra1b model.

    Mapping: amplitude = b1, rate = b2.  Both parameters constrained to
    min=0 because the Misra1b model is physically meaningful only for
    positive amplitude and rate.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="m1b",
                model_type=ModelType.POWER_SATURATION,
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


def test_misra1b_fixture_is_well_formed() -> None:
    """Smoke check on the embedded NIST Misra1b fixture."""
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
def test_misra1b_recovers_nist_certified_parameters(
    start_name: str, start: dict[str, float]
) -> None:
    """From NIST starting values, spectrafit recovers certified b1 and b2 within 1e-3 relative.

    NIST classifies Misra1b as "Lower" difficulty; both Start 1 and Start 2
    should converge.  The ``POWER_SATURATION`` node maps amplitude↔b1
    and rate↔b2 directly.
    """
    result = fit(_build_misra1b_graph(start), _measurement(), _LM_OPTS)
    assert result.success is True, (
        f"Misra1b ({start_name}) did not converge: {result.message}"
    )

    b1_recovered = result.params["m1b.amplitude"].value
    b2_recovered = result.params["m1b.rate"].value

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


def test_misra1b_rss_matches_nist_certified() -> None:
    """The fitted residual sum of squares matches NIST's certified RSS within 1e-4 relative.

    Certified RSS = 7.5464681533e-02 (10 significant figures).
    """
    result = fit(_build_misra1b_graph(START2), _measurement(), _LM_OPTS)
    assert result.success is True

    rss_recovered = float(result.chi2)
    rel = abs(rss_recovered - RSS) / RSS
    assert rel < 1e-4, (
        f"RSS: recovered {rss_recovered:.10e}, certified {RSS:.10e}, rel {rel:.2e}"
    )


def test_misra1b_reduced_chi2_and_dof() -> None:
    """Reduced χ² matches certified RSS/DOF within 1e-4 relative; DOF == 12.

    Cross-checks the DOF count: spectrafit must count 14 − 2 = 12 (both
    parameters are free; no fixed parameters).
    """
    result = fit(_build_misra1b_graph(START2), _measurement(), _LM_OPTS)
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


def test_misra1b_certified_stderr_matches_nist() -> None:
    """Per-parameter stderrs match NIST certified 1σ within 5e-2 relative.

    spectrafit computes cov = (JᵀJ)⁻¹·(chi2/DOF) after convergence, so the
    per-parameter stderr should agree with NIST's certified standard deviations.

    Tolerance: 5e-2 relative (≈ 5%).  The wider envelope accounts for the
    covariance inversion in IEEE-754 double precision vs NIST extended precision.
    """
    result = fit(_build_misra1b_graph(START2), _measurement(), _LM_OPTS)
    assert result.success is True

    amp_pr = result.params["m1b.amplitude"]
    rate_pr = result.params["m1b.rate"]

    assert amp_pr.stderr is not None, (
        "amplitude stderr must not be None after convergence"
    )
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
