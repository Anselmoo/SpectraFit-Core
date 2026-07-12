"""End-to-end per-iteration θ trajectory across the PyO3 boundary.

Invariant V (V1/V2/V3): the faer LM driver records the free-parameter vector θ
at every accepted point (Rust `Report.params_history`), it is threaded through
`FitResultSpec` and crosses the PyO3 boundary into `FitResult.params_history`,
and the trajectory genuinely approaches the known synthetic truth. This is the
real metric the dashboard's convergence panel will render — replacing the
χ²-floor proxy.
"""

from __future__ import annotations

import numpy as np

from spectrafit_core import (
    FitGraph,
    FitOptions,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)

# Known synthetic truth for the Gaussian.
_TRUTH = {"amplitude": 3.0, "center": 0.0, "sigma": 0.8}


def _clean_gaussian() -> MeasurementData:
    rng = np.random.default_rng(7)
    x = np.linspace(-3.0, 3.0, 120)
    y = (
        _TRUTH["amplitude"]
        * np.exp(-0.5 * (x / _TRUTH["sigma"]) ** 2)
        + rng.normal(0.0, 0.01, x.size)
    )
    return MeasurementData(x=x.tolist(), y=y.tolist())


def _gaussian_graph() -> FitGraph:
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0, min=0.0),
                    "center": Parameter(value=0.0),
                    "sigma": Parameter(value=1.0, min=1e-6),
                },
            )
        ]
    )


def test_lm_fit_exposes_theta_trajectory_across_pyo3() -> None:
    result = fit(_gaussian_graph(), _clean_gaussian(), FitOptions(solver="lm"))
    assert result.success

    hist = result.params_history
    # V2: the field crosses the boundary populated (not the empty default).
    assert hist, "LM fit must expose a non-empty params_history across PyO3"
    # Lock-step with the cost trajectory (same recording site in the driver).
    assert len(hist) == len(result.cost_history)
    # Each θ has the free-parameter dimension (amplitude, center, sigma).
    assert all(len(theta) == 3 for theta in hist)


def test_theta_trajectory_ends_at_the_fitted_solution() -> None:
    result = fit(_gaussian_graph(), _clean_gaussian(), FitOptions(solver="lm"))
    order = result.covariance_param_order
    assert order is not None, "need the free-param order to interpret θ entries"

    last = result.params_history[-1]
    # The final recorded θ is the fitted solution, addressed by name via order.
    # Exact equality holds because no Parameter.scale is set (all scales == 1.0),
    # so the driver's working θ equals the physical parameter value.
    for value, name in zip(last, order):
        assert value == result.parameters[name].value


def test_theta_trajectory_approaches_known_truth() -> None:
    """V3: the scale-normalized distance dₖ = ‖(θₖ − θ_true)/s‖₂ shrinks to ~0."""
    result = fit(_gaussian_graph(), _clean_gaussian(), FitOptions(solver="lm"))
    order = result.covariance_param_order
    assert order is not None
    # Map free-param names to the synthetic truth (strip the "g." node prefix).
    truth = [_TRUTH[name.split(".", 1)[-1]] for name in order]

    def dist(theta: list[float]) -> float:
        return float(
            np.sqrt(
                sum(
                    ((tk - tt) / max(abs(tt), 1.0)) ** 2
                    for tk, tt in zip(theta, truth)
                )
            )
        )

    d_first = dist(result.params_history[0])
    d_last = dist(result.params_history[-1])
    assert d_last < d_first, f"θ did not approach truth: {d_first} -> {d_last}"
    assert d_last < 0.05, f"final θ-distance to truth too large: {d_last}"
