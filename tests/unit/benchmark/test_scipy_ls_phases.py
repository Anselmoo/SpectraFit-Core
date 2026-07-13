"""Phase-helper coverage for the refactored ``_scipy_ls.py`` adapter.

The Plan C2 refactor (2026-06-10) split the scipy-ls backend into four typed
phases that each own one concern:

1. ``_build_initial_guess`` — flat-vector + bounds + clamped x0 + init fit
2. ``_solve`` — method-aware ``least_squares`` invocation (``match``-dispatched)
3. ``_extract_uncertainty`` — κ(J) cap + SVD-pseudoinverse stderr
4. ``_extract_params`` / ``_upgrade_success`` — flat-vector → contract keys
   + r²-quality success upgrade for soft failures

These tests pin the seams between those phases, so a future refactor can't
silently change the method-dispatch table, drop the κ(J) cap, or break the
stderr identity. The whole-suite numeric parity stays covered by the
existing parity / integration tests; this file only pins behaviour the
refactor introduced as a named seam.
"""

from __future__ import annotations

import math
from typing import Any
from unittest.mock import patch

import numpy as np
import pytest

from oracles.backends import _scipy_ls
from oracles.backends._scipy_ls import (
    _KAPPA_CAP,
    _build_initial_guess,
    _extract_params,
    _extract_uncertainty,
    _kappa_of,
    _solve,
    _stderr_from_jac,
)
from oracles.cases import CaseSpec, GaussianSpec, materialize


def _easy_case():
    """A clean single-Gaussian case — every solver should converge in <10 nfev."""
    return materialize(
        CaseSpec(
            id="ph-easy",
            name="phases-easy",
            category="easy",
            difficulty=0.1,
            components=[GaussianSpec(amplitude=1.0, center=0.0, sigma=0.5)],
            x_min=-3.0,
            x_max=3.0,
            n_points=100,
            noise=0.01,
        )
    )


# --------------------------------------------------------------------------- #
# Test 1 — Method dispatch routes to least_squares with the right ``method=``
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("method", ["lm", "trf", "dogbox"])
def test_solve_dispatch_picks_the_right_method(method: str) -> None:
    """_solve(method=...) must call least_squares with that method string.

    Spy on `scipy.optimize.least_squares` and assert the kwarg the dispatch
    actually passed. ``lm`` cannot accept bounds (no ``bounds`` kwarg);
    ``trf``/``dogbox`` must pass bounds natively.
    """
    case = _easy_case()
    box = _build_initial_guess(case)

    # Capture the real least_squares BEFORE patching so the spy can delegate
    # without re-entering the patched name (which would recurse forever).
    from scipy.optimize import least_squares as real_least_squares

    seen: dict[str, Any] = {}

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen["method"] = kwargs.get("method")
        seen["bounds"] = kwargs.get("bounds")
        return real_least_squares(*args, **kwargs)

    with patch("scipy.optimize.least_squares", side_effect=spy):
        _solve(method, box, case)  # ty: ignore[invalid-argument-type]  # pytest.mark.parametrize yields str; narrows to _Method Literal at runtime

    assert seen["method"] == method
    if method == "lm":
        # MINPACK has no bounds knob; the soft-barrier residual handles it.
        assert seen["bounds"] is None
    else:
        lo, hi = seen["bounds"]
        np.testing.assert_array_equal(lo, box.lo)
        np.testing.assert_array_equal(hi, box.hi)


def test_solve_unknown_method_raises() -> None:
    """An unsupported method must raise ValueError, not silently pick a default.

    The ``_Method`` Literal pins this at the type level; the runtime check
    here guards against an erased dynamic call (e.g. a JSON-driven registry).
    """
    case = _easy_case()
    box = _build_initial_guess(case)
    with pytest.raises(ValueError, match="bogus"):
        _solve("bogus", box, case)  # ty: ignore[invalid-argument-type]  # deliberately invalid method string to test the ValueError guard


# --------------------------------------------------------------------------- #
# Test 2 — κ(J) cap clamps an Inf condition number to _KAPPA_CAP
# --------------------------------------------------------------------------- #
def test_kappa_cap_clamps_huge_condition_to_one_e16() -> None:
    """A Jacobian whose true κ > 1e16 must report exactly ``_KAPPA_CAP``.

    Constructed: a 4×3 J whose smallest singular value is 1e-20 and largest
    is ~1, so ``cond(J) ≈ 1e20``. The helper must clamp to 1e16, NOT pass
    Inf through to downstream aggregations (geomean, ratios, plots).
    """
    huge_cond = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1e-20],
            [1.0, 1.0, 0.0],
        ]
    )
    raw_cond = float(np.linalg.cond(huge_cond))
    assert raw_cond > _KAPPA_CAP, (
        f"sanity: raw κ={raw_cond:g} must exceed the cap {_KAPPA_CAP:g}"
    )

    kappa = _kappa_of(huge_cond)
    assert kappa == _KAPPA_CAP

    # And a tame matrix passes through unclamped.
    well = np.eye(4, 3)
    tame = _kappa_of(well)
    assert tame is not None
    assert tame < _KAPPA_CAP
    assert math.isfinite(tame)


def test_kappa_of_none_or_empty_returns_none() -> None:
    """No Jacobian + zero-size Jacobian both map to ``None`` (undefined κ)."""
    assert _kappa_of(None) is None
    assert _kappa_of(np.zeros((0, 0))) is None


# --------------------------------------------------------------------------- #
# Test 3 — stderr via SVD pseudo-inverse reproduces the textbook OLS formula
# --------------------------------------------------------------------------- #
def test_stderr_from_jac_matches_textbook_ols() -> None:
    """A simple 2-param linear J with known cost → known stderrs (~1e-10).

    For residuals ``r = Jθ - y`` with cost = 0.5 * ‖r‖², the OLS covariance
    is ``cov = inv(JᵀJ) · 2·cost/(m−n)``, and ``stderr[i] = sqrt(cov[i,i])``.
    We pick a J whose ``JᵀJ`` inverse is analytic, then check the helper
    returns the same diagonal.
    """
    # J = [[1, 0], [0, 1], [1, 1], [1, -1]] → JᵀJ = diag(3, 3) → inv = diag(1/3, 1/3)
    jac = np.array(
        [
            [1.0, 0.0],
            [0.0, 1.0],
            [1.0, 1.0],
            [1.0, -1.0],
        ]
    )
    # Pick cost so the multiplier is clean: 2*cost/(m-n) = 2*cost/(4-2) = cost.
    # cost = 6.0 → s² = 6.0 → var = (1/3) * 6 = 2.0 → stderr = sqrt(2)
    cost = 6.0
    names = ["p0_amplitude", "p0_center"]
    out = _stderr_from_jac(jac, names, cost)

    expected = math.sqrt(2.0)
    assert out["p0.amplitude"] == pytest.approx(expected, abs=1e-10)
    assert out["p0.center"] == pytest.approx(expected, abs=1e-10)


def test_stderr_from_jac_underdetermined_returns_all_none() -> None:
    """When m ≤ n (under-determined) every stderr collapses to ``None``.

    Better to report None than a bogus number derived from a degenerate cov.
    """
    jac = np.array([[1.0, 2.0, 3.0]])  # 1 row, 3 params → m ≤ n
    names = ["p0_amplitude", "p0_center", "p0_sigma"]
    out = _stderr_from_jac(jac, names, cost=1.0)
    assert out == {
        "p0.amplitude": None,
        "p0.center": None,
        "p0.sigma": None,
    }


# --------------------------------------------------------------------------- #
# Test 4 — _extract_params unpacks the flat scipy ``x`` into ``p{i}.<name>``
# --------------------------------------------------------------------------- #
def test_extract_params_maps_flat_to_dotted_contract_keys() -> None:
    """``p0_amplitude`` → ``p0.amplitude`` for every flat name (no fixed params)."""
    # Use the easy non-FX case so the free/fixed split is trivial (all free).
    case = _easy_case()
    box = _build_initial_guess(case)

    class FakeRaw:
        # x carries only the FREE params — for a non-FX case that is all params.
        x = box.free_x0.copy()

    out = _extract_params(FakeRaw(), box)
    # The output must contain all param names in dotted form.
    for flat_name in box.names:
        i_str, p_str = flat_name.split("_", 1)
        dotted = f"{i_str}.{p_str}"
        assert dotted in out, f"missing key {dotted!r} in extract_params output"
    # Values must match the clipped x0 (free_x0 == x0 for a no-fixed case).
    for flat_name, expected in zip(box.names, box.x0):
        i_str, p_str = flat_name.split("_", 1)
        assert out[f"{i_str}.{p_str}"] == pytest.approx(expected, abs=1e-12)


# --------------------------------------------------------------------------- #
# Extras — uncertainty wrapper + build_initial_guess clamping invariant
# --------------------------------------------------------------------------- #
def test_extract_uncertainty_returns_both_kappa_and_stderr_map() -> None:
    """The wrapper bundles (κ, stderr) so the orchestrator does one call.

    A well-conditioned Jacobian + a non-zero cost → a finite κ and a stderr
    dict with one entry per name.  Uses an easy non-FX case so all params are
    free (free_names == names).
    """
    # Build a minimal _ParamBox with 2 free params for a clean analytic test.
    from oracles.backends._scipy_ls import _ParamBox

    two_names = ["p0_amplitude", "p0_center"]
    two_box = _ParamBox(
        names=two_names,
        x0=np.array([1.0, 2.0]),
        lo=np.array([0.0, -10.0]),
        hi=np.array([np.inf, 10.0]),
        init_fit=np.zeros(4),
        free_names=two_names,
        free_x0=np.array([1.0, 2.0]),
        free_lo=np.array([0.0, -10.0]),
        free_hi=np.array([np.inf, 10.0]),
        free_indices=[0, 1],
        fixed_names=[],
        fixed_vals=np.empty(0),
        fixed_indices=[],
    )

    class FakeRaw:
        jac = np.array(
            [
                [1.0, 0.0],
                [0.0, 1.0],
                [1.0, 1.0],
                [1.0, -1.0],
            ]
        )
        cost = 6.0
        x = np.array([1.0, 2.0])

    kappa, stderr = _extract_uncertainty(FakeRaw(), two_box)
    assert kappa is not None and math.isfinite(kappa)
    assert set(stderr.keys()) == {"p0.amplitude", "p0.center"}
    assert stderr["p0.amplitude"] == pytest.approx(math.sqrt(2.0), abs=1e-10)


def test_build_initial_guess_clamps_x0_into_envelope() -> None:
    """An out-of-range sigma in the guess must be clipped before ``x0`` ships.

    Without clamping, the ``lm`` path's soft barrier dominates from iteration
    0, and trf/dogbox reject the start — both ruin the comparison. The clamp
    in ``_build_initial_guess`` is what keeps the three solvers comparable.
    """
    case = _easy_case()
    box = _build_initial_guess(case)
    # Every x0 entry must lie inside the bounds (the post-clip invariant).
    assert np.all(box.x0 >= box.lo - 1e-12)
    assert np.all(box.x0 <= box.hi + 1e-12)
    # And the init_fit was evaluated AT the clipped x0 (so the cost-history
    # seed downstream is honest).
    assert box.init_fit.shape == case.y.shape


def test_shape_bounds_table_pins_long_tail_values() -> None:
    """The _SHAPE_BOUNDS table values are load-bearing — pin them explicitly.

    A drift here means lmfit and scipy-ls disagree because their search boxes
    differ, NOT because the solvers differ. The values are the same as those
    in `_lmfit.py` (post-CX-033 NaN cascade fix).
    """
    assert _scipy_ls._SHAPE_BOUNDS == {
        "m": (1.05, 50.0),
        "m_l": (1.05, 50.0),
        "m_r": (1.05, 50.0),
        "beta": (0.1, 50.0),
        "nu": (0.5, 200.0),
        "q": (-100.0, 100.0),
        "k": (-50.0, 50.0),
    }


def test_shape_bounds_lmfit_scipy_parity() -> None:
    """S2: the two independent ``_SHAPE_BOUNDS`` copies must stay identical.

    ``_lmfit._SHAPE_BOUNDS`` and ``_scipy_ls._SHAPE_BOUNDS`` are two physical
    tables. They define the long-tail shape-param search box each oracle uses;
    if one drifts, a "disagreement" between lmfit and scipy-ls would reflect a
    bounds-table drift, not a solver difference. This pins them equal (same keys,
    same (lo, hi) tuples) so editing one forces editing the other. Non-vacuous:
    were either table changed, this equality would fail.
    """
    from oracles.backends import _lmfit

    assert _lmfit._SHAPE_BOUNDS == _scipy_ls._SHAPE_BOUNDS, (
        "lmfit and scipy-ls _SHAPE_BOUNDS drifted — keep the two tables identical "
        "(an edit to one must be mirrored in the other)."
    )
