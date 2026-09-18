r"""VarPro must find the same minimum as full LM on a separable problem.

There is no independent oracle for "the right shape parameters" on real
data. But Variable Projection (VarPro) admits a surrogate that full LM
supplies for free: VarPro eliminates the linear amplitude coefficients
analytically via projection and optimises only the nonlinear shape
parameters (``center``, ``sigma``), while full LM optimises every parameter
— linear and nonlinear — jointly. On a **separable** problem (linear in the
amplitudes, nonlinear in everything else) the two formulations describe the
identical objective, so their minima must coincide. A disagreement here is a
real defect in the projection or in the derivative used to drive it toward
that minimum, not solver noise.

A two-Gaussian sum is the smallest case that actually exercises the
projection machinery: each peak has one linear amplitude and two nonlinear
shape parameters (``center``, ``sigma``), and — unlike a single Gaussian —
the sum is not trivially reducible to a one-parameter-family search, so
VarPro's basis-column projection has real work to do. This complements
``tests/parity/test_solver_invariance.py``, which compares all eight strict
solver arms (including ``"varpro"``) on a *single*-Gaussian fixture; this
module is narrower (varpro vs. lm only) but deeper (a genuinely separable,
multi-peak fixture where the projection's Jacobian variant matters).

Jacobian variant (see the finding recorded in
``crates/spectrafit-varpro/src/lib.rs``): the underlying ``varpro`` crate
(v0.14.0, the dependency pinned in ``crates/spectrafit-varpro/Cargo.toml``)
implements the **Kaufman (1975) approximation** to the Golub-Pereyra
projected-residual Jacobian, not the full Golub-Pereyra (1973) formula —
confirmed by that crate's own module doc, `` ~/.cargo/registry/src/index.crates.io-*/varpro-0.14.0/src/lib.rs:99``:
"The VarPro algorithm implemented here follows (O'Leary2013), but uses the
Kaufman approximation to calculate the Jacobian." Kaufman's approximation
drops the second term of the full projected derivative
(the component involving the pseudoinverse's own derivative), which is
cheaper per iteration and, per Kaufman (1975) and the surrounding
literature, converges to the *same* minimum as full Golub-Pereyra on a
well-posed separable problem — it only changes the convergence path and the
recovered covariance, not the optimum itself. That is exactly the claim
this test checks empirically.
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

# Ground truth for a well-separated two-Gaussian sum: linear in both
# amplitudes, nonlinear in both centers and both sigmas. Peaks are separated
# by several widths so there is a single, unambiguous joint minimum — no
# permutation-symmetric local minima to trip either solver.
_TRUTH: dict[str, dict[str, float]] = {
    "p0": {"amplitude": 2.5, "center": -2.0, "sigma": 0.7},
    "p1": {"amplitude": 4.0, "center": 3.0, "sigma": 1.1},
}


def _separable_two_peak_case() -> tuple[np.ndarray, np.ndarray, dict[str, dict[str, float]]]:
    """A noise-free two-Gaussian sum: separable in the amplitudes, nonlinear in center/sigma.

    Returns:
        ``(x, y, truth)`` — the independent variable, the noise-free curve,
        and the per-node ground-truth parameters used to generate it.
    """
    x = np.linspace(-8.0, 10.0, 400)
    y = np.zeros_like(x)
    for params in _TRUTH.values():
        y += params["amplitude"] * np.exp(
            -((x - params["center"]) ** 2) / (2 * params["sigma"] ** 2),
        )
    return x, y, _TRUTH


def _two_gaussian_graph() -> FitGraph:
    """Two Gaussian nodes, seeded away from the truth so each solver actually searches.

    Nonlinear parameters (``center``, ``sigma``) are left unbounded on
    purpose: VarPro has no native bounds support and silently falls back to
    LM when a nonlinear parameter carries a finite bound (see the "Bounds"
    section of ``crates/spectrafit-varpro/src/lib.rs``). Bounding a
    nonlinear parameter here would make the varpro arm secretly run LM,
    which would make this test agree with itself trivially rather than
    exercising the actual projection path.
    """
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="p0",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0),
                    "center": Parameter(value=-1.0),
                    "sigma": Parameter(value=1.0),
                },
            ),
            ModelNodeSpec(
                id="p1",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0),
                    "center": Parameter(value=2.0),
                    "sigma": Parameter(value=1.0),
                },
            ),
        ],
    )


def _fit(x: np.ndarray, y: np.ndarray, solver: str) -> FitResult:
    """Run ``fit`` against the two-Gaussian graph with the given solver string."""
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    graph = _two_gaussian_graph()
    options = FitOptions(solver=solver, max_iterations=500)
    return fit(graph, data, options)


def test_varpro_and_lm_reach_the_same_optimum() -> None:
    r"""Same $\hat\theta$ and the same $\chi^2$ on a separable two-peak fit, within solver tolerance."""
    x, y, _truth = _separable_two_peak_case()

    lm = _fit(x, y, solver="lm")
    assert lm.success, "the lm reference itself failed to converge on the separable two-peak case"

    vp = _fit(x, y, solver="varpro")
    assert vp.success, "varpro did not converge on the separable two-peak case"

    # Both arms converge chi2 down to the double-precision noise floor on this
    # noise-free fit (measured: lm ~3.3e-19, varpro ~1.6e-23) — chi2 itself is
    # indistinguishable from zero at that scale, so a *relative* comparison
    # between two near-zero floats is not meaningful (rtol alone flagged a
    # "0.9999" relative difference between two values a human would call
    # equal). atol=1e-10 sits many orders above the observed floor but far
    # below the chi2 a genuinely different optimum would produce on this
    # amplitude-2.5-4.0, 400-point problem — it does not loosen the actual
    # signal, which is the per-parameter rtol=1e-6 check below (already
    # tight, and it passes on its own).
    assert_allclose(
        vp.chi2,
        lm.chi2,
        rtol=1e-6,
        atol=1e-10,
        err_msg="varpro and lm disagree on chi2 for a separable problem",
    )
    for name, ref_param in lm.parameters.items():
        assert_allclose(
            vp.parameters[name].value,
            ref_param.value,
            rtol=1e-6,
            err_msg=f"varpro disagrees with lm on {name}",
        )


@pytest.mark.parametrize("node_id", ["p0", "p1"])
def test_varpro_recovers_the_analytic_truth_per_node(node_id: str) -> None:
    """Beyond agreeing with lm, both must also land near the analytic truth (sanity check).

    This guards against the degenerate case where varpro and lm agree with
    each other but have both wandered to a shared wrong answer (e.g. a
    shared local minimum, or a graph mis-specification bug that affects both
    equally). Every-arm agreement is necessary but not sufficient; recovering
    the generating parameters is the independent check.
    """
    x, y, truth = _separable_two_peak_case()
    vp = _fit(x, y, solver="varpro")
    assert vp.success, "varpro did not converge on the separable two-peak case"

    for pname, truth_value in truth[node_id].items():
        key = f"{node_id}.{pname}"
        assert_allclose(
            vp.parameters[key].value,
            truth_value,
            rtol=1e-6,
            err_msg=f"varpro did not recover the analytic truth for {key}",
        )
