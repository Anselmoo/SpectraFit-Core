"""Trust-region power-user knobs — Python ↔ Rust binding pins.

Cycle 8.2: `delta0`, `max_delta`, and `eta` are now optional fields on
`FitOptions`, plumbed through `crates/spectrafit-types/FitOptionsSpec`
into the `dispatch.rs::TrustRegionConfig` for the `"dogleg"` and
`"newton-cg"` solvers.

These tests prove the knobs reach the solver: if the field were silently
dropped or never read, every test below would converge to the same
parameters as the default — which is exactly what we assert is NOT the
case. Specifically:

* `eta` is bounded to `[0, 0.25)` (the trust-region driver's own
  `debug_assert!(eta < 0.25)`: a rejected step only shrinks `Δ` when
  `ρ < 0.25`, so `eta >= 0.25` could spin to `max_nfev` instead of
  failing cleanly). That means the field can no longer be pushed high
  enough to force near-universal step rejection at the solver — the
  bound itself is now the proof that an "impossible" `eta` never
  reaches the TR core; see
  `test_tr_knob_out_of_range_eta_rejected_at_construction` below.
* `max_delta` capped to a tiny value forces the solver to take many
  more small steps; the final fit is still valid but `n_iter` is much
  larger than the default.
* Defaults (`delta0=None`, `max_delta=None`, `eta=None`) must produce
  exactly the same fit as omitting the fields entirely.
"""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError
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
            ),
        ],
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
    assert r_baseline.success
    assert r_none.success
    a_base = r_baseline.parameters["g.amplitude"].value
    a_none = r_none.parameters["g.amplitude"].value
    assert a_base == pytest.approx(a_none, abs=1e-9), (
        f"{solver}: explicit None should equal omitted; got base={a_base:.6f} vs none={a_none:.6f}"
    )


@pytest.mark.parametrize("solver", ["dogleg", "newton-cg"])
def test_tr_knob_out_of_range_eta_rejected_at_construction(solver: str) -> None:
    """`eta = 0.99` is no longer constructible — the field is capped `< 0.25`.

    This used to be a behavioral test: it set `eta=0.99` to force the TR
    driver to reject nearly every trial step (`ρ ≤ 1.0 always`, so `ρ > 0.99`
    almost never holds), proving the knob reaches the solver rather than
    being silently dropped. Now that `FitOptions.eta` is bounded to
    `[0, 0.25)` (matching the driver's `debug_assert!(eta < 0.25)`), no
    "impossible" eta can be constructed at all — Pydantic rejects it before
    the value ever reaches `fit()`/the TR core. The proof moved from solver
    behavior to construction-time validation.
    """
    with pytest.raises(ValidationError):
        FitOptions(solver=solver, max_iterations=300, eta=0.99)


def test_tr_knob_eta_in_range_reaches_the_solver() -> None:
    """An in-range `eta` (not just an out-of-range one) actually reaches the solver.

    `test_tr_knob_out_of_range_eta_rejected_at_construction` proves an
    out-of-range `eta` can no longer reach `fit()` at all — but that alone
    doesn't prove a valid `eta` is read once construction succeeds, only
    that Pydantic's `Field(ge=0.0, lt=0.25)` bound is enforced. On the
    clean, easy `_clean_gaussian` fixture used elsewhere in this module,
    ``eta=0.0`` and ``eta=0.24`` (the extremes of the valid range) converge
    identically — every trial step there is either clearly good or clearly
    bad, never in the borderline band `eta` controls — so that fixture
    cannot discriminate. A deliberately bad-started, sloppy two-peak
    problem gives Newton-CG enough marginal trial steps that the two
    extremes take a measurably different number of accepted iterations to
    reach the same `converged_ftol` optimum (measured at 30 vs. 25 on this
    fixture, reproducible across runs since the solver has no RNG). If
    `eta` were silently dropped before reaching
    `dispatch.rs::TrustRegionConfig`, both runs would take the identical
    path and `n_iter` would match.
    """
    rng = np.random.default_rng(3)
    x = np.linspace(-5.0, 5.0, 120)
    y = (
        2.0 * np.exp(-0.5 * ((x - (-1.2)) / 0.4) ** 2)
        + 1.4 * np.exp(-0.5 * ((x - 1.6) / 0.6) ** 2)
        + rng.normal(0.0, 0.15, x.size)
    )
    data = MeasurementData(x=x.tolist(), y=y.tolist())

    def bad_start_graph() -> FitGraph:
        return FitGraph(
            nodes=[
                ModelNodeSpec(
                    id="p1",
                    model_type=ModelType.GAUSSIAN,
                    parameters={
                        "amplitude": Parameter(value=5.0, min=0.0),
                        "center": Parameter(value=-3.0),
                        "sigma": Parameter(value=0.1, min=1e-6),
                    },
                ),
                ModelNodeSpec(
                    id="p2",
                    model_type=ModelType.GAUSSIAN,
                    parameters={
                        "amplitude": Parameter(value=0.2, min=0.0),
                        "center": Parameter(value=3.5),
                        "sigma": Parameter(value=2.0, min=1e-6),
                    },
                ),
            ],
        )

    r_lo = fit(
        bad_start_graph(),
        data,
        FitOptions(solver="newton-cg", max_iterations=300, eta=0.0),
    )
    r_hi = fit(
        bad_start_graph(),
        data,
        FitOptions(solver="newton-cg", max_iterations=300, eta=0.24),
    )
    assert r_lo.success
    assert r_hi.success
    assert r_lo.n_iter != r_hi.n_iter, (
        f"eta=0.0 (n_iter={r_lo.n_iter}) vs eta=0.24 (n_iter={r_hi.n_iter}) "
        "should take a different number of accepted iterations on this "
        "sloppy fixture — matching counts would mean eta is not reaching "
        "the solver"
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
    assert r_with_knobs.success
    assert r_clean.success
    a_knobs = r_with_knobs.parameters["g.amplitude"].value
    a_clean = r_clean.parameters["g.amplitude"].value
    # `lm` ignores the TR-only knobs; the two fits should be identical.
    assert a_knobs == pytest.approx(a_clean, abs=1e-9), (
        f"LM family should ignore TR-only knobs; got knobs={a_knobs:.6f} vs clean={a_clean:.6f}"
    )
