"""Tests for the ``_wheel_eval`` parity helper.

After the benchmark-fairness revert (DECISIONS.md 2026-06-10) the numpy
``evaluate`` bodies in :mod:`oracles.models` ARE the oracle implementations —
lmfit / scipy-ls call them inside their timed fit loops, so they never route
through the wheel. Rust↔numpy kernel parity is enforced HERE instead, via
:func:`oracles.models._wheel_eval` and :func:`oracles.models.wheel_parity_pairs`.
These tests pin three properties:

1. The helper agrees with the inline numpy formula for ``gaussian``.
2. The helper raises ``RuntimeError`` when the wheel is monkey-patched
   to "unavailable" — proving the graceful-degradation contract.
3. Every (wheel_key, model) pair from ``wheel_parity_pairs()`` agrees between
   the Rust wheel kernel and the numpy ``evaluate`` body, at the same
   per-model bounds as ``tests/parity/test_kernel_parity.py`` — machine
   epsilon for everything except ``true_voigt`` (Hui–Armstrong–Wray vs
   scipy.special.wofz, ~1e-4).
"""

from __future__ import annotations

import numpy as np
import pytest

from oracles import models as oracle_models
from oracles.models import PeakModel, _wheel_eval, wheel_parity_pairs

# Shared probe grid (mirrors tests/parity/test_kernel_parity.py). Param values
# below pick sigma/gamma strictly > 0 so that width-dominated kernels
# (gaussian-family, lorentzian, true_voigt, pseudo_voigt) stay smooth. For
# ``harmonic_ir`` the singularity is at ``sigma → 0`` (NOT at ``x = center``);
# the resonance row ``|x| = center`` is finite as long as ``sigma > 0`` because
# the kernel's damping term keeps the denominator bounded away from zero.
# ``sigma = 1.3`` below leaves a comfortable non-zero denominator at resonance.
_X = np.linspace(-4.0, 8.0, 49)

_PARAM_VALUES: dict[str, float] = {
    "amplitude": 2.5,
    "center": 1.5,
    "sigma": 1.3,
    "gamma": 1.1,
    "fraction": 0.4,
    "q": 1.7,
    "c": 0.8,
    "slope": 0.6,
    "intercept": -0.4,
    "offset": 5.0,  # power_law_offset needs offset + x > 0 on _X=[-4,8]; quadratic: any value ok
    "A1": 1.4,
    "lam1": 0.25,
    "A2": 0.9,
    "lam2": 0.07,
    "m": 2.0,
    "sigma_l": 1.1,
    "sigma_r": 1.4,
    "beta": 2.0,
    "nu": 3.0,
    "m_l": 2.0,
    "m_r": 3.0,
    "k": 0.8,
    "e_gap": 0.5,
    "exponent": 2.0,
    "a": 1.5,
    "b": 0.4,
    "tau": 2.0,
    # NIST saturating/regression models — values mirror tests/parity/test_kernel_parity.py
    # so the positive-domain constraints hold on _X = [-4, 8] (negative-base powers → NaN
    # otherwise): power_saturation needs 1 + rate·x/2 > 0; power_law_offset needs offset + x > 0.
    "rate": 0.4,
    "shape": 0.93,
    "num_lin": 0.19,
    "den_lin": 0.12,
    "den_const": 0.14,
}

_PARITY_PAIRS: list[tuple[str, PeakModel]] = wheel_parity_pairs()


def _params_for(model: PeakModel) -> dict[str, float]:
    """Reasonable param dict in canonical (registry) order for *model*."""
    return {name: _PARAM_VALUES[name] for name in model.param_names}


# --------------------------------------------------------------------------- #
# 1. Helper unit-test — gaussian wheel call ≡ inline numpy formula
# --------------------------------------------------------------------------- #
def test_wheel_eval_gaussian_matches_numpy() -> None:
    """``_wheel_eval('gaussian', …)`` must equal the inline numpy formula."""
    pytest.importorskip("spectrafit_core")
    amplitude, center, sigma = 2.5, 1.5, 1.3
    got = _wheel_eval(
        "gaussian",
        _X,
        {"amplitude": amplitude, "center": center, "sigma": sigma},
    )
    expected = amplitude * np.exp(-0.5 * ((_X - center) / sigma) ** 2)
    np.testing.assert_allclose(got, expected, rtol=1e-10, atol=1e-12)


# --------------------------------------------------------------------------- #
# 2. Unavailability contract — monkeypatch the import-availability flag
# --------------------------------------------------------------------------- #
def test_wheel_eval_raises_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``_WHEEL_AVAILABLE`` is False, ``_wheel_eval`` raises RuntimeError."""
    monkeypatch.setattr(oracle_models, "_WHEEL_AVAILABLE", False)
    monkeypatch.setattr(oracle_models, "_CORE_WHEEL", None)
    with pytest.raises(RuntimeError, match="spectrafit_core wheel unavailable"):
        oracle_models._wheel_eval(
            "gaussian",
            _X,
            {"amplitude": 1.0, "center": 0.0, "sigma": 1.0},
        )


# --------------------------------------------------------------------------- #
# 3. Per-model wheel-vs-numpy parity — THE load-bearing gate.
#
# ``model.one`` is pure numpy after the fairness revert, so this compares the
# Rust wheel kernel against the numpy oracle directly — no monkeypatching.
# It subsumes the old ``test_wheel_eval_round_trip_per_model`` (deleted): that
# test compared two wheel-routed call paths against each other, which became
# meaningless once the two paths genuinely differ (wheel vs numpy).
# --------------------------------------------------------------------------- #
# Per-model tolerance for wheel-vs-numpy parity. Most kernels agree to
# machine eps; ``true_voigt`` is the one structural outlier — the Rust
# kernel uses the Hui–Armstrong–Wray rational approximation of the Faddeeva
# function while the numpy oracle uses ``scipy.special.wofz``, so parity is
# bounded at ~1e-4 (matched by ``tests/parity/test_kernel_parity.py``).
_PER_MODEL_TOLS: dict[str, tuple[float, float]] = {
    "true_voigt": (2e-4, 1e-6),
}
_DEFAULT_TOL: tuple[float, float] = (1e-9, 1e-12)


@pytest.mark.parametrize(
    ("wheel_key", "model"),
    _PARITY_PAIRS,
    ids=[model.key for _, model in _PARITY_PAIRS],
)
def test_wheel_matches_numpy_per_model(wheel_key: str, model: PeakModel) -> None:
    """Each parity model's Rust wheel output must match its numpy oracle.

    This is what keeps the timing-fair numpy bodies honest: any formula drift
    between ``crates/spectrafit-models`` and ``oracles.models`` fails here
    instead of surfacing as a |Δr²| gate regression. Tolerances mirror
    ``tests/parity/test_kernel_parity.py`` (the upstream parity gate).
    """
    pytest.importorskip("spectrafit_core")
    params = _params_for(model)

    wheel_y = _wheel_eval(wheel_key, _X, params)
    numpy_y = model.one(_X, params)

    rtol, atol = _PER_MODEL_TOLS.get(model.key, _DEFAULT_TOL)
    np.testing.assert_allclose(
        wheel_y,
        numpy_y,
        rtol=rtol,
        atol=atol,
        err_msg=f"wheel-vs-numpy drift on {model.key} exceeds rtol={rtol} atol={atol}",
    )


# --------------------------------------------------------------------------- #
# 4. voigt ↔ pseudo_voigt Rust kernel cross-check.
# --------------------------------------------------------------------------- #
def test_voigt_rust_kernel_matches_pseudo_voigt() -> None:
    """The dedicated ``voigt`` Rust kernel must equal ``pseudo_voigt``.

    The Python registry treats ``voigt`` as a frozen ``model_copy`` of
    ``pseudo_voigt`` (so ``wheel_parity_pairs`` remaps it to the
    ``pseudo_voigt`` wheel key), but ``voigt`` is a registered Rust kernel in
    its own right (``crates/spectrafit-models/src/lib.rs::model_from_str``).
    Exercise it directly so a divergent ``voigt.rs`` formula trips this test
    instead of staying silently green.
    """
    pytest.importorskip("spectrafit_core")
    params = {
        "amplitude": _PARAM_VALUES["amplitude"],
        "center": _PARAM_VALUES["center"],
        "sigma": _PARAM_VALUES["sigma"],
        "fraction": _PARAM_VALUES["fraction"],
    }
    wheel_voigt = _wheel_eval("voigt", _X, params)
    wheel_pv = _wheel_eval("pseudo_voigt", _X, params)
    np.testing.assert_allclose(
        wheel_voigt,
        wheel_pv,
        rtol=1e-12,
        atol=1e-14,
        err_msg="voigt and pseudo_voigt Rust kernels disagree — formula drift",
    )
