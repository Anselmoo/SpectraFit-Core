"""Real per-iteration convergence history from the faer solver drivers.

Phase 3 of the benchmark rebuild added additive observability to the core: the LM
and trust-region drivers record the cost / gradient-norm trajectory. These tests
pin that it is real (monotone, terminal cost matches), length-consistent, and that
solvers without a native trace (lm-legacy oracle) report an empty history.
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


def _gaussian_case() -> tuple[FitGraph, MeasurementData]:
    x = np.linspace(-5.0, 5.0, 120)
    rng = np.random.default_rng(0)
    y = 3.0 * np.exp(-0.5 * ((x - 0.4) / 0.8) ** 2) + rng.normal(0, 0.02, x.size)
    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="p",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0),
                    "center": Parameter(value=0.0),
                    "sigma": Parameter(value=1.0, min=0.0),
                },
            )
        ]
    )
    return graph, MeasurementData(x=x.tolist(), y=y.tolist())


@pytest.mark.parametrize("solver", ["lm", "trf", "dogleg", "newton-cg"])
def test_faer_drivers_record_real_history(solver: str) -> None:
    """faer LM / trust-region drivers emit a monotone, terminal-consistent trace."""
    graph, data = _gaussian_case()
    result = fit(graph, data, FitOptions(solver=solver, max_iterations=200))

    cost = result.cost_history
    grad = result.gradient_norm_history
    assert len(cost) >= 2, "expected at least the initial + one accepted point"
    assert len(cost) == len(grad), "cost and gradient histories must align"
    # Monotone non-increasing (LM/TR only accept cost-reducing steps).
    assert all(cost[i] >= cost[i + 1] - 1e-9 for i in range(len(cost) - 1))
    # The trace ends at the reported terminal cost (½‖r‖² == chi2/2 here).
    assert cost[-1] == pytest.approx(result.chi2 / 2.0, rel=1e-6, abs=1e-9)
    assert all(np.isfinite(c) for c in cost)
    assert all(np.isfinite(gnorm) for gnorm in grad)


def test_lm_legacy_oracle_has_empty_history() -> None:
    """The lm-legacy oracle exposes no native trace → empty history (not faked)."""
    graph, data = _gaussian_case()
    result = fit(graph, data, FitOptions(solver="lm-legacy"))
    assert result.cost_history == []
    assert result.gradient_norm_history == []
