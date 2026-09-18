r"""All solver arms must reach the same optimum on a well-conditioned problem.

There is no oracle for "the right parameters" on real spectral data. But a
problem with a **unique minimum** admits a surrogate: every solver that
claims convergence must agree with every other solver, to within its own
numerical noise floor. A disagreement in the sixth significant figure is a
real finding about one arm's step rule or termination test — it is not
measurement noise, because there is no measurement here, only a closed-form
Gaussian and eight different roads to the same $\hat\theta$.

``crates/spectrafit-solver/src/dispatch.rs`` (``Solver::parse``, ~line 105)
accepts ten solver strings, authoritatively:

=====================  =============================  ============================================
Canonical string       Aliases                         Family
=====================  =============================  ============================================
``"lm"``                —                               faer Levenberg-Marquardt (default)
``"lm-legacy"``         —                               nalgebra LM parity oracle
``"trf"``               —                               Coleman-Li bound-scaled LM (faer core)
``"geodesic"``          ``"lm-geodesic"``               Transtrum geodesic-accelerated LM (faer core)
``"dogleg"``            —                               Powell's dogleg trust region
``"newton-cg"``         ``"newton_cg"``, ``"newtoncg"``, Matrix-free Newton-CG (Steihaug-Toint)
                        ``"steihaug"``
``"global"``            —                               Differential Evolution + LM refinement
``"varpro"``            —                               Variable Projection
``"auto"``              —                               Structure-based routing (varpro or trf)
``"irls"``              ``"irls:<weight>"`` suffix       Iteratively re-weighted least squares
=====================  =============================  ============================================

Two arms are **deliberately excluded** from the strict, same-$\hat\theta$
comparison:

* ``"global"`` runs differential evolution before its LM refinement step.
  It is stochastic by construction, so it need not land on the identical
  optimum every run — only near it.
* ``"irls"`` re-weights the residuals at every outer iteration (Huber by
  default). On a clean, noise-free Gaussian this is *solving a different
  objective* from ordinary least squares — the re-weighting can shift the
  optimum away from the unweighted minimum even when both converge cleanly.
  It is not being unfair to ``"irls"`` to loosen its tolerance; comparing it
  to plain LM at ``rtol=1e-6`` would be comparing two different problems.

Both get their own test (:func:`test_stochastic_and_reweighting_arms_land_near_truth`)
that asserts convergence and proximity to the analytic truth, at a looser
tolerance, instead of bit-for-bit agreement with the ``"lm"`` reference.
"""

from __future__ import annotations

import numpy as np
import pytest
from numpy.testing import assert_allclose
from spectrafit_core import (
    FitGraph,
    FitOptions,
    FitResult,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)

# The eight arms compared strictly against the "lm" reference. "global" and
# "irls" are excluded — see the module docstring — and get their own,
# looser test below.
_STRICT_ARMS: list[str] = [
    "lm",
    "lm-legacy",
    "trf",
    "geodesic",
    "dogleg",
    "newton-cg",
    "varpro",
    "auto",
]

# Per-arm relative-tolerance overrides, keyed by arm name. Default is 1e-6
# (agreement to six significant figures). Populate only when an arm has a
# *measured* disagreement with the "lm" reference that is a genuine property
# of its step rule or termination test — never to blanket-silence a finding.
# Each override cites the measured relative difference and the parameter it
# was observed on.
_ARM_RTOL: dict[str, float] = {}

_TRUTH: dict[str, float] = {"amplitude": 3.0, "center": 1.5, "sigma": 0.8}


def _well_conditioned_xy() -> tuple[np.ndarray, np.ndarray]:
    """A single clean Gaussian: unique minimum, low $\\kappa(J)$, no noise."""
    x = np.linspace(-4.0, 7.0, 240)
    y = _TRUTH["amplitude"] * np.exp(
        -((x - _TRUTH["center"]) ** 2) / (2 * _TRUTH["sigma"] ** 2),
    )
    return x, y


@pytest.fixture
def well_conditioned_case() -> tuple[np.ndarray, np.ndarray, dict[str, float]]:
    """A well-conditioned single-Gaussian case other parity tasks may reuse.

    Returns:
        ``(x, y, truth)`` — a noise-free Gaussian with a unique minimum, and
        the ground-truth parameters used to generate it.
    """
    x, y = _well_conditioned_xy()
    return x, y, dict(_TRUTH)


def _gaussian_graph() -> FitGraph:
    """A single Gaussian node, seeded away from the truth so every arm must actually search."""
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g0",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0, min=0.0),
                    "center": Parameter(value=0.0),
                    "sigma": Parameter(value=1.0, min=1e-6),
                },
            ),
        ],
    )


def _fit(x: np.ndarray, y: np.ndarray, solver: str) -> FitResult:
    """Run ``fit`` against the clean single-Gaussian graph with the given solver string."""
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    graph = _gaussian_graph()
    options = FitOptions(solver=solver, max_iterations=500)
    return fit(graph, data, options)


@pytest.mark.parametrize("arm", _STRICT_ARMS)
def test_every_arm_reaches_the_same_optimum(
    arm: str,
    well_conditioned_case: tuple[np.ndarray, np.ndarray, dict[str, float]],
) -> None:
    """Each strict solver arm recovers the same $\\hat\\theta$ as the ``"lm"`` reference.

    Args:
        arm: The solver string under test, one of :data:`_STRICT_ARMS`.
        well_conditioned_case: The ``(x, y, truth)`` fixture.
    """
    x, y, _truth = well_conditioned_case
    reference = _fit(x, y, "lm")
    assert reference.success, "the lm reference itself failed to converge"

    result = _fit(x, y, arm)
    assert result.success, f"{arm} did not converge on a well-conditioned single Gaussian"

    rtol = _ARM_RTOL.get(arm, 1e-6)
    for name, ref_param in reference.parameters.items():
        assert_allclose(
            result.parameters[name].value,
            ref_param.value,
            rtol=rtol,
            err_msg=f"{arm} disagrees with lm on {name} (rtol={rtol})",
        )


@pytest.mark.parametrize("arm", ["global", "irls"])
def test_stochastic_and_reweighting_arms_land_near_truth(
    arm: str,
    well_conditioned_case: tuple[np.ndarray, np.ndarray, dict[str, float]],
) -> None:
    """``"global"`` and ``"irls"`` need only converge near the analytic truth, not agree with lm.

    ``"global"`` is stochastic (differential evolution); ``"irls"`` solves a
    re-weighted objective. Neither is required to reproduce the ``"lm"``
    optimum to machine-level agreement — see the module docstring — but both
    must still land close to the truth on a problem this clean.

    Args:
        arm: ``"global"`` or ``"irls"``.
        well_conditioned_case: The ``(x, y, truth)`` fixture.
    """
    x, y, truth = well_conditioned_case
    result = _fit(x, y, arm)
    assert result.success, f"{arm} did not converge on a well-conditioned single Gaussian"

    for name, truth_value in truth.items():
        key = f"g0.{name}"
        assert_allclose(
            result.parameters[key].value,
            truth_value,
            rtol=5e-2,
            err_msg=f"{arm} landed far from the analytic truth on {name}",
        )
