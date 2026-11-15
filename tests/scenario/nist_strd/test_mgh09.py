"""NIST StRD MGH09 — Kowalik–Osborne rational-function FitGraph V&V (W8 breadth, new family).

MGH09 is a 4-parameter, 11-observation nonlinear regression problem from the
NIST Statistical Reference Datasets (StRD) collection.  NIST classifies it as
**"Higher"** difficulty (Kowalik and Osborne, 1968).

    y = b1·(x² + b2·x) / (x² + b3·x + b4)

This maps 1-to-1 to spectrafit's ``MGH09_RATIONAL`` kernel
(params ``amplitude`` = b1, ``num_lin`` = b2, ``den_lin`` = b3, ``den_const`` = b4),
so no re-parameterization is required.

**"Higher" difficulty by design** — the problem is start-sensitive and the
parameter space is poorly conditioned near the solution.  Both NIST starts are
provided; Start1 = (25, 39, 41.5, 39) is very far from the certified values
≈ (0.19, 0.19, 0.12, 0.14) and unlikely to converge for a gradient-based LM
solver.  Start2 = (0.25, 0.39, 0.415, 0.39) is closer and is the primary test.
Both convergence tests are marked ``xfail(strict=False)``.

**Convergence tracking.** A start test passes (XPASS) when the fit stopped on
a convergence test, i.e. the termination reason ``result.message`` is one of
``_CONVERGENCE_TERMINATIONS`` (the keys of the gtol, ftol, xtol and
zero-residual tests of the ``solver="lm"`` path), and recovered the certified
values. It does not read ``result.success``: since #93 that flag also requires
a Gauss-Newton stationary end point and admits a ``no_improvement_possible``
stop, so it is no convergence signal. ``tests/meta/test_nist_convergence_tracking.py``
fails if the tracking reads it again.

Source: https://www.itl.nist.gov/div898/strd/nls/data/mgh09.shtml
"""

from __future__ import annotations

import numpy as np
import pytest
from oracles.nist_strd.mgh09 import (
    CERTIFIED,
    DOF,
    N_OBS,
    RSS,
    START1,
    START2,
    X,
    Y,
)
from spectrafit_core import (
    FitGraph,
    FitOptions,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LM_OPTS = FitOptions(solver="lm", max_iterations=10000, tolerance=1e-12)
_CONVERGENCE_TERMINATIONS: frozenset[str] = frozenset(
    {"converged_ftol", "converged_gtol", "converged_xtol", "residuals_zero"},
)


def _build_mgh09_graph(start: dict[str, float]) -> FitGraph:
    """Single MGH09_RATIONAL node matching NIST MGH09 model.

    Mapping: amplitude = b1, num_lin = b2, den_lin = b3, den_const = b4.

    No bounds are needed for amplitude or num_lin (certified values are ≈ 0.19).
    den_lin and den_const are positive at the certified solution; no positivity
    constraint is applied because the LM search needs freedom to cross zero
    during the trajectory from Start2.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="mgh09",
                model_type=ModelType.MGH09_RATIONAL,
                parameters={
                    "amplitude": Parameter(value=start["b1"]),
                    "num_lin": Parameter(value=start["b2"]),
                    "den_lin": Parameter(value=start["b3"]),
                    "den_const": Parameter(value=start["b4"]),
                },
            ),
        ],
    )


def _measurement() -> MeasurementData:
    return MeasurementData(x=X.tolist(), y=Y.tolist())


# ---------------------------------------------------------------------------
# Smoke / fixture tests (always pass)
# ---------------------------------------------------------------------------


def test_mgh09_fixture_is_well_formed() -> None:
    """Smoke check on the embedded NIST MGH09 fixture."""
    assert N_OBS == 11
    assert DOF == 7
    assert X.shape == (11,)
    assert Y.shape == (11,)
    assert np.all(np.isfinite(X))
    assert np.all(np.isfinite(Y))
    # x values run from small (0.0625) to large (4.0); should be strictly increasing
    # when sorted (NIST file is y-then-x; we've stored (x, y) pairs already).
    assert np.all(np.diff(X) < 0), "x values must be strictly decreasing (large to small)"
    # All y values are positive.
    assert np.all(Y > 0), "MGH09 y values are all positive"


def test_mgh09_rss_cross_check() -> None:
    """RSS / DOF = residual std dev² matches published value to 10 sig figs.

    Certified RSS = 3.0750560385e-04, DOF = 7.
    sqrt(RSS/DOF) = 6.6279236552e-03  (certified residual std dev 6.6279236551e-03).
    """
    import math

    residual_std = math.sqrt(RSS / DOF)
    assert abs(residual_std - 6.6279236551e-03) / 6.6279236551e-03 < 1e-8, (
        f"RSS cross-check failed: sqrt(RSS/DOF)={residual_std:.10e}"
    )


def test_mgh09_numpy_oracle_at_certified() -> None:
    """The numpy oracle at certified params produces the correct RSS.

    This is a kernel-correctness check independent of the solver.
    """
    b1, _ = CERTIFIED["b1"]
    b2, _ = CERTIFIED["b2"]
    b3, _ = CERTIFIED["b3"]
    b4, _ = CERTIFIED["b4"]

    n = X**2 + b2 * X
    d = X**2 + b3 * X + b4
    y_model = b1 * n / d
    residuals = Y - y_model
    rss_recovered = float(np.sum(residuals**2))

    rel = abs(rss_recovered - RSS) / RSS
    assert rel < 1e-3, (
        f"Numpy oracle at certified params: RSS={rss_recovered:.10e}, "
        f"certified={RSS:.10e}, rel={rel:.2e}"
    )


# ---------------------------------------------------------------------------
# Convergence tests (xfail — MGH09 is "Higher" difficulty)
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=False,
    reason=(
        "NIST MGH09 is classified 'Higher' difficulty (Kowalik and Osborne, 1968). "
        "Start2 (b1=0.25, b2=0.39, b3=0.415, b4=0.39) is the closer starting guess "
        "but the rational function's poorly-conditioned parameter space may prevent "
        "convergence to the certified minimum from a plain gradient-based LM path. "
        "XPASS (convergence within 5e-2 relative on all params) is welcome; "
        "XFAIL confirms the NIST 'Higher' difficulty classification."
    ),
)
def test_mgh09_recovers_nist_certified_parameters_start2() -> None:
    r"""From NIST start2 the LM fit stops on a convergence test at the certified values.

    Start 2 is $(b_1, b_2, b_3, b_4) = (0.25, 0.39, 0.415, 0.39)$, the closer of
    the two published starting guesses (Start 1 scaled down by 100). The test
    passes when the termination reason is one of ``_CONVERGENCE_TERMINATIONS``
    and $b_1, \ldots, b_4$ each agree with their certified values to a relative
    error below $5 \times 10^{-2}$.

    The tolerance is looser than the default $10^{-3}$ because $b_2$ has a large
    certified standard deviation ($\sigma_{b_2} = 1.9633 \times 10^{-1}
    \approx 1.02\,b_2$), a flat basin in the $b_2$ direction where sub-percent
    recovery is not expected.
    """
    result = fit(_build_mgh09_graph(START2), _measurement(), _LM_OPTS)
    assert result.message in _CONVERGENCE_TERMINATIONS, (
        f"MGH09 (start2) stopped without a convergence test: {result.message}"
    )

    b1_rec = result.params["mgh09.amplitude"].value
    b2_rec = result.params["mgh09.num_lin"].value
    b3_rec = result.params["mgh09.den_lin"].value
    b4_rec = result.params["mgh09.den_const"].value

    b1_cert, _ = CERTIFIED["b1"]
    b2_cert, _ = CERTIFIED["b2"]
    b3_cert, _ = CERTIFIED["b3"]
    b4_cert, _ = CERTIFIED["b4"]

    tol = 5e-2
    rel_b1 = abs(b1_rec - b1_cert) / abs(b1_cert)
    rel_b2 = abs(b2_rec - b2_cert) / abs(b2_cert)
    rel_b3 = abs(b3_rec - b3_cert) / abs(b3_cert)
    rel_b4 = abs(b4_rec - b4_cert) / abs(b4_cert)

    assert rel_b1 < tol, (
        f"b1 (start2): recovered {b1_rec:.6e}, certified {b1_cert:.6e}, rel {rel_b1:.2e}"
    )
    assert rel_b2 < tol, (
        f"b2/num_lin (start2): recovered {b2_rec:.6e}, certified {b2_cert:.6e}, rel {rel_b2:.2e}"
    )
    assert rel_b3 < tol, (
        f"b3/den_lin (start2): recovered {b3_rec:.6e}, certified {b3_cert:.6e}, rel {rel_b3:.2e}"
    )
    assert rel_b4 < tol, (
        f"b4/den_const (start2): recovered {b4_rec:.6e}, certified {b4_cert:.6e}, rel {rel_b4:.2e}"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "NIST MGH09 start1 (b1=25, b2=39, b3=41.5, b4=39) is far from the "
        "certified minimum ≈ (0.19, 0.19, 0.12, 0.14) and is expected to fail "
        "or land on a different local minimum for LM solvers. "
        "XFAIL confirms the NIST 'Higher' difficulty classification; "
        "XPASS (convergence within 5e-2) is a bonus."
    ),
)
def test_mgh09_recovers_nist_certified_parameters_start1() -> None:
    r"""From NIST start1 the LM fit stops on a convergence test at the certified values.

    Start 1 is $(b_1, b_2, b_3, b_4) = (25, 39, 41.5, 39)$, far from the
    certified values and documented as extremely difficult for gradient-based
    solvers. The test passes when the termination reason is one of
    ``_CONVERGENCE_TERMINATIONS`` and $b_1, \ldots, b_4$ each agree with their
    certified values to a relative error below $5 \times 10^{-2}$.
    """
    result = fit(_build_mgh09_graph(START1), _measurement(), _LM_OPTS)
    assert result.message in _CONVERGENCE_TERMINATIONS, (
        f"MGH09 (start1) stopped without a convergence test: {result.message}"
    )

    b1_rec = result.params["mgh09.amplitude"].value
    b2_rec = result.params["mgh09.num_lin"].value
    b3_rec = result.params["mgh09.den_lin"].value
    b4_rec = result.params["mgh09.den_const"].value

    b1_cert, _ = CERTIFIED["b1"]
    b2_cert, _ = CERTIFIED["b2"]
    b3_cert, _ = CERTIFIED["b3"]
    b4_cert, _ = CERTIFIED["b4"]

    tol = 5e-2
    rel_b1 = abs(b1_rec - b1_cert) / abs(b1_cert)
    rel_b2 = abs(b2_rec - b2_cert) / abs(b2_cert)
    rel_b3 = abs(b3_rec - b3_cert) / abs(b3_cert)
    rel_b4 = abs(b4_rec - b4_cert) / abs(b4_cert)

    assert rel_b1 < tol, (
        f"b1 (start1): recovered {b1_rec:.6e}, certified {b1_cert:.6e}, rel {rel_b1:.2e}"
    )
    assert rel_b2 < tol, (
        f"b2/num_lin (start1): recovered {b2_rec:.6e}, certified {b2_cert:.6e}, rel {rel_b2:.2e}"
    )
    assert rel_b3 < tol, (
        f"b3/den_lin (start1): recovered {b3_rec:.6e}, certified {b3_cert:.6e}, rel {rel_b3:.2e}"
    )
    assert rel_b4 < tol, (
        f"b4/den_const (start1): recovered {b4_rec:.6e}, certified {b4_cert:.6e}, rel {rel_b4:.2e}"
    )
