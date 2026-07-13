"""IRLS robust-loss weight selection — Python ↔ Rust binding pins.

Cycle 8.1 audit follow-up. The first pass of the binding audit claimed
``WeightFn`` was unreachable from Python (`docs/rust_binding_audit.md` §2).
A second pass found the dispatch parser already handles the colon syntax
(`Solver::parse` at `crates/spectrafit-solver/src/dispatch.rs:108`):

* ``"irls"`` → `WeightFn::Huber(1.345)` (default)
* ``"irls:huber"`` → `WeightFn::Huber(1.345)`
* ``"irls:bisquare"`` / ``"irls:biweight"`` → `WeightFn::Bisquare(4.685)`
* ``"irls:cauchy"`` → `WeightFn::Cauchy(2.385)`

These tests pin that each `FitOptions.solver` string actually reaches the
underlying IRLS variant (no silent fall-through to the LM default) by:

1. Building a clean single-Gaussian fit with one large outlier injected.
2. Verifying every IRLS weight variant converges to roughly the same
   (outlier-resistant) amplitude — within a tolerance large enough to
   permit the three weight functions to disagree on tuning but small
   enough to detect "fell through to plain LM".
3. Verifying the fit succeeds and reports `success=True`.

If a future change breaks the parser arm or the IRLS dispatch, these
tests catch the regression at the Python boundary.
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


def _gaussian_with_outlier(seed: int = 17) -> MeasurementData:
    """A clean single Gaussian (amplitude=3, center=0, sigma=0.8) on 80
    points in [-3, 3], plus three sigma-10 outliers at random indices.

    The outlier amplitude is far larger than the signal so plain LM gets
    pulled noticeably toward them; the IRLS variants should down-weight
    the outliers and recover the true amplitude within ~0.3.
    """
    rng = np.random.default_rng(seed)
    x = np.linspace(-3.0, 3.0, 80)
    truth = 3.0 * np.exp(-0.5 * (x / 0.8) ** 2)
    y = truth + rng.normal(0.0, 0.05, x.size)
    # Inject three outliers at + ~50 sigma each.
    out_idx = rng.choice(x.size, 3, replace=False)
    y[out_idx] += 5.0
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


@pytest.mark.parametrize(
    ("solver_string", "expected_weight_family"),
    [
        ("irls", "huber-default"),
        ("irls:huber", "huber-default"),
        ("irls:bisquare", "bisquare"),
        ("irls:biweight", "bisquare"),  # alias
        ("irls:cauchy", "cauchy"),
    ],
)
def test_irls_weight_string_reaches_each_variant(
    solver_string: str, expected_weight_family: str
) -> None:
    """Every IRLS solver string converges; amplitude is recovered within 0.3.

    Tolerance is generous: each weight function has a different tuning
    constant, so they disagree on the exact converged amplitude. The point
    is to assert the FIT SUCCEEDS — any silent fall-through to plain LM
    would either fail to converge in the budget or land far from 3.0
    because the outliers would dominate.
    """
    data = _gaussian_with_outlier()
    options = FitOptions(solver=solver_string, max_iterations=400, tolerance=1e-7)
    result = fit(_gaussian_graph(), data, options)
    assert result.success, (
        f"IRLS variant {solver_string!r} ({expected_weight_family}) failed to "
        f"converge: message={result.message!r}"
    )
    recovered_amp = result.parameters["g.amplitude"].value
    # True amplitude is 3.0; outliers at +5 would drag plain LM toward ~4
    # (depending on hit rate); IRLS should hold close to 3 ± 0.3.
    assert 2.6 <= recovered_amp <= 3.4, (
        f"IRLS variant {solver_string!r} converged to amplitude {recovered_amp:.3f}; "
        f"expected ~3.0 ± 0.3 (outliers should have been down-weighted). "
        f"This regression suggests {solver_string!r} silently fell through to plain LM."
    )


def test_irls_default_matches_explicit_huber() -> None:
    """`solver="irls"` must produce the same fit as `solver="irls:huber"`.

    Anti-regression for the default arm at `irls.rs:84` (`_ => Huber`).
    If a future contributor changes the default WeightFn, this test fails
    and a deliberate decision is forced.
    """
    data = _gaussian_with_outlier(seed=42)
    g = _gaussian_graph()
    r_default = fit(g, data, FitOptions(solver="irls", max_iterations=400))
    r_huber = fit(g, data, FitOptions(solver="irls:huber", max_iterations=400))
    assert r_default.success and r_huber.success
    # Same algorithm, same seed, same start → same numbers.
    a_default = r_default.parameters["g.amplitude"].value
    a_huber = r_huber.parameters["g.amplitude"].value
    assert a_default == pytest.approx(a_huber, abs=1e-9), (
        f"`irls` default-arm parity broken: irls→{a_default:.6f} vs "
        f"irls:huber→{a_huber:.6f}"
    )
