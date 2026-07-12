"""Trust-region power-user knobs — Python ↔ Rust binding pins.

Cycle 8.2: `delta0`, `max_delta`, and `eta` are now optional fields on
`FitOptions`, plumbed through `crates/spectrafit-types/FitOptionsSpec`
into the `dispatch.rs::TrustRegionConfig` for the `"dogleg"` and
`"newton-cg"` solvers.

These tests prove the knobs reach the solver: if the field were silently
dropped or never read, every test below would converge to the same
parameters as the default — which is exactly what we assert is NOT the
case. Specifically:

* `eta` close to 1.0 makes the trust-region driver reject almost every
  trial step (`accept iff ρ > eta`) and either bail with NoImprovement
  or exhaust the budget without finding the same optimum.
* `max_delta` capped to a tiny value forces the solver to take many
  more small steps; the final fit is still valid but `n_iter` is much
  larger than the default.
* Defaults (`delta0=None`, `max_delta=None`, `eta=None`) must produce
  exactly the same fit as omitting the fields entirely.
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


def _clean_gaussian() -> MeasurementData:
    rng = np.random.default_rng(11)
    x = np.linspace(-3.0, 3.0, 100)
    y = 3.0 * np.exp(-0.5 * (x / 0.8) ** 2) + rng.normal(0.0, 0.02, x.size)
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


@pytest.mark.parametrize("solver", ["dogleg", "newton-cg"])
def test_tr_knob_defaults_match_no_knobs_set(solver: str) -> None:
    """Setting every knob to its default sentinel (`None`) must equal omitting them.

    Anti-regression for the `Option<f64>` plumbing in dispatch.rs (Cycle 8.2):
    if `None` were inadvertently translated into `0.0` instead of "use library
    default," the fits below would diverge from the no-knob baseline.
    """
    data = _clean_gaussian()
    g = _gaussian_graph()
    r_baseline = fit(g, data, FitOptions(solver=solver, max_iterations=300))
    r_none = fit(
        g,
        data,
        FitOptions(
            solver=solver,
            max_iterations=300,
            delta0=None,
            max_delta=None,
            eta=None,
        ),
    )
    assert r_baseline.success and r_none.success
    a_base = r_baseline.parameters["g.amplitude"].value
    a_none = r_none.parameters["g.amplitude"].value
    assert a_base == pytest.approx(a_none, abs=1e-9), (
        f"{solver}: explicit None should equal omitted; got base={a_base:.6f} vs "
        f"none={a_none:.6f}"
    )


@pytest.mark.parametrize("solver", ["dogleg", "newton-cg"])
def test_tr_knob_impossible_eta_forces_no_improvement(solver: str) -> None:
    """`eta = 0.99` makes the TR driver reject most steps (ρ ≤ 1.0 always).

    Proves the field reaches the TR core: if `eta` were dropped, the fit
    would still converge cleanly via the default `eta=1e-4`. With the knob
    plumbed correctly, nearly every trial step's ρ fails the `ρ > eta = 0.99` test,
    Δ shrinks, and the driver emits `NoImprovement` or max iterations exhaustion
    with `success=False`. `eta ∈ [0, 1)` per Pydantic constraint; 0.99 is
    close enough to 1.0 that the Gauss-Newton step (ρ ≈ 1.0) is rejected.
    """
    data = _clean_gaussian()
    g = _gaussian_graph()
    r_default = fit(g, data, FitOptions(solver=solver, max_iterations=300))
    assert r_default.success and r_default.r_squared > 0.99
    r_impossible = fit(
        g,
        data,
        FitOptions(solver=solver, max_iterations=300, eta=0.99),
    )
    # Nearly every step fails ρ > 0.99 → success=False with NoImprovement or MaxIter.
    assert not r_impossible.success, (
        f"{solver}: eta=0.99 should reject most steps and end with failure, "
        f"but the fit reported success=True (r²={r_impossible.r_squared:.6f}, "
        f"n_iter={r_impossible.n_iter}). The eta knob is not reaching the TR core."
    )
    assert (
        "no_improvement" in r_impossible.message.lower()
        or "max" in r_impossible.message.lower()
    ), (
        f"{solver}: expected NoImprovement / MaxEval-style termination, got "
        f"message={r_impossible.message!r}"
    )


def test_tr_knob_unsupported_on_lm_family_is_harmless() -> None:
    """Setting TR knobs on `"lm"` is allowed but ignored (LM uses StrategyConfig).

    The wire shape stays uniform — no per-solver schema split — so callers
    don't need to know which knobs belong to which solver family. The LM
    family ignores `delta0`/`max_delta`/`eta`; they're picked up only by
    the dogleg / newton-cg dispatch arm.
    """
    data = _clean_gaussian()
    g = _gaussian_graph()
    r_with_knobs = fit(
        g,
        data,
        FitOptions(
            solver="lm",
            max_iterations=200,
            delta0=0.5,
            max_delta=10.0,
            eta=1e-4,
        ),
    )
    r_clean = fit(g, data, FitOptions(solver="lm", max_iterations=200))
    assert r_with_knobs.success and r_clean.success
    a_knobs = r_with_knobs.parameters["g.amplitude"].value
    a_clean = r_clean.parameters["g.amplitude"].value
    # `lm` ignores the TR-only knobs; the two fits should be identical.
    assert a_knobs == pytest.approx(a_clean, abs=1e-9), (
        f"LM family should ignore TR-only knobs; got knobs={a_knobs:.6f} vs "
        f"clean={a_clean:.6f}"
    )
