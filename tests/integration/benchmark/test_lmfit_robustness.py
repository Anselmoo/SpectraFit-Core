"""Regression: lmfit must not abort with NaN on the long-tail shape models.

Before the `_SHAPE_BOUNDS` table in `oracles.backends._lmfit`, the LM solver
could drive `pearson7.m → 0⁺`, `moffat.beta → 0`, etc., where the model formula
overflows to `inf`/`NaN` and lmfit raises
``ValueError('The model function generated NaN values …')``. The CX-033 failures
in `uv run poe report_html` were exactly this: a 4-peak Pearson VII blend whose
Monte-Carlo and scaling sub-fits aborted on every re-noise.

Two anti-regression tests:

1. The 4-pearson7 blend (== CX-033's grid slot) fits cleanly with lmfit under
   several MC noise seeds.
2. Every long-tail shape suffix the bench generators emit has both a finite
   `min` and `max` after ``LmfitBackend.build``.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("lmfit")

from oracles.backends._lmfit import _SHAPE_BOUNDS, LmfitBackend
from oracles.cases import (
    CaseSpec,
    Component,
    MoffatSpec,
    Pearson7Spec,
    StudentsTSpec,
    materialize,
)


def _pearson7_blend(seed: int) -> CaseSpec:
    """Build a 4-peak Pearson VII spec equivalent to CX-033's grid slot."""
    rng = np.random.default_rng(seed)
    centers = [-3.0, -1.0, 1.0, 3.0]
    components: list[Component] = [
        Pearson7Spec(
            amplitude=float(rng.uniform(2.5, 5.5)),
            center=c + float(rng.uniform(-0.15, 0.15)),
            sigma=float(rng.uniform(0.6, 1.1)),
            m=float(rng.uniform(1.3, 3.5)),
        )
        for c in centers
    ]
    return CaseSpec(
        id=f"TST-P7-{seed:03d}",
        name="4-pearson7 anti-regression",
        category="complex",
        difficulty=0.6,
        components=components,
        x_min=-7.0,
        x_max=7.0,
        n_points=200,
        noise=0.05,
        guess_scale=0.14,
    )


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_lmfit_pearson7_blend_does_not_nan(seed: int) -> None:
    """A 4-pearson7 blend with bench-realistic params must not abort lmfit on NaN.

    Mirrors the CX-033 failure mode that surfaced under `report_html`.
    """
    case = materialize(_pearson7_blend(seed))
    backend = LmfitBackend()
    # `fit` runs `_warmup` + n_reps solves; any internal NaN raises through.
    outcome = backend.fit(case, n_reps=1)
    assert outcome.success
    assert math.isfinite(outcome.r2)
    # The shape param `m` must have stayed inside its bound box.
    for i in range(len(case.comp_true)):
        m_val = outcome.params[f"p{i}.m"]
        lo, hi = _SHAPE_BOUNDS["m"]
        assert lo <= m_val <= hi, f"p{i}.m={m_val} escaped bounds [{lo}, {hi}]"


def _moffat_case() -> CaseSpec:
    """A single Moffat peak, sigma/beta in the bench-realistic ranges."""
    return CaseSpec(
        id="TST-MOF-001",
        name="moffat anti-regression",
        category="lineshapes",
        difficulty=0.5,
        components=[MoffatSpec(amplitude=4.0, center=0.0, sigma=0.9, beta=2.0)],
        x_min=-5.0,
        x_max=5.0,
        n_points=160,
        noise=0.03,
        guess_scale=0.10,
    )


def _students_t_case() -> CaseSpec:
    """A single Student's-t peak, nu in the bench-realistic range."""
    return CaseSpec(
        id="TST-ST-001",
        name="students_t anti-regression",
        category="lineshapes",
        difficulty=0.5,
        components=[StudentsTSpec(amplitude=4.0, center=0.0, sigma=0.9, nu=3.0)],
        x_min=-5.0,
        x_max=5.0,
        n_points=160,
        noise=0.03,
        guess_scale=0.10,
    )


@pytest.mark.parametrize(
    "case_factory,suffixes",
    [
        (_moffat_case, ["beta"]),
        (_students_t_case, ["nu"]),
        (_pearson7_blend, ["m"]),
    ],
)
def test_long_tail_shape_params_have_bounded_box(
    case_factory, suffixes: list[str]
) -> None:
    """Every long-tail shape param suffix gets finite ``min`` and ``max`` in build()."""
    case = materialize(
        case_factory(0) if case_factory is _pearson7_blend else case_factory()
    )
    backend = LmfitBackend()
    _, params, _, _ = backend.build(case)
    for i in range(len(case.comp_guess)):
        for suffix in suffixes:
            key = f"p{i}_{suffix}"
            par = params[key]
            assert math.isfinite(par.min), f"{key}.min is non-finite"
            assert math.isfinite(par.max), f"{key}.max is non-finite"
            lo, hi = _SHAPE_BOUNDS[suffix]
            assert par.min == pytest.approx(lo)
            assert par.max == pytest.approx(hi)


def test_exp_gaussian_is_finite_on_extreme_gamma() -> None:
    """numpy ``exp_gaussian`` stays finite across a wide γ/σ sweep (no overflow leak)."""
    from oracles.models import exp_gaussian

    x = np.linspace(-10.0, 10.0, 200)
    for gamma in (0.01, 0.1, 0.5, 1.0, 2.5, 5.0):
        for sigma in (0.05, 0.2, 1.0, 2.5):
            y = exp_gaussian(x, amplitude=4.0, center=0.0, sigma=sigma, gamma=gamma)
            assert np.all(np.isfinite(y)), (
                f"non-finite exp_gaussian at γ={gamma}, σ={sigma}: {y[~np.isfinite(y)]}"
            )


def test_pearson7_is_finite_on_low_m() -> None:
    """numpy ``pearson7`` stays finite across the LM-search envelope on ``m``."""
    from oracles.models import pearson7

    x = np.linspace(-5.0, 5.0, 200)
    for m in (1.05, 1.2, 2.0, 4.0, 10.0, 50.0):
        y = pearson7(x, amplitude=4.0, center=0.0, sigma=0.9, m=m)
        assert np.all(np.isfinite(y)), f"non-finite pearson7 at m={m}"
        assert np.all(y >= -1e-9), f"unexpected negative pearson7 at m={m}"
