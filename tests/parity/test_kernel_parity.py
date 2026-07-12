"""Kernel single-source-of-truth parity.

The numpy formulas in :mod:`oracles.models` are the canonical definition of
every benchmark shape. The jax oracle (:mod:`oracles.backends._jax`) and the
Rust subject (``spectrafit_core``) each re-implement those kernels in their own
runtime, so they must agree with numpy *to machine precision* on identical params —
otherwise a backend comparison is measuring a formula mismatch, not a solver.

Two parities, each parameterized over the live :data:`MODEL_REGISTRY` (no hardcoded
param-name lists — canonical order comes from ``get_model(key).param_names``):

* numpy ↔ jax  — every ``jax_supported`` shape, run in-workflow.
* numpy ↔ Rust — every registered shape, skipped unless the compiled
  ``spectrafit_core`` extension is importable (it is rebuilt in Phase 3).
"""

from __future__ import annotations

import numpy as np
import pytest

from oracles.models import MODEL_REGISTRY, get_model

# Shared probe grid + per-name reasonable values. Positive, well-separated, and
# away from any singularity (sigma/gamma > 0, center inside the grid).
_X = np.linspace(-4.0, 8.0, 97)

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
    "offset": 5.0,  # power_law_offset: offset + x > 0 for x in [-4, 8]; quadratic: any value ok
    "shape": 0.93,  # power_law_offset shape (exponent parameter b3 ≈ 0.93 in Bennett5)
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
    "rate": 0.4,  # power_saturation: 1 + rate·x/2 > 0 for x in [-4, 8] (avoids u=0 at rate=0.5, x=-4)
    "num_lin": 0.19,    # mgh09_rational: numerator linear coeff (b2 ≈ 0.1913)
    "den_lin": 0.12,    # mgh09_rational: denominator linear coeff (b3 ≈ 0.1231)
    "den_const": 0.14,  # mgh09_rational: denominator constant (b4 ≈ 0.1361); discriminant < 0 → D > 0 on grid
}


def _params_for(key: str) -> dict[str, float]:
    """Reasonable param dict in canonical (registry) order for *key*."""
    model = get_model(key)
    return {name: _PARAM_VALUES[name] for name in model.param_names}


_JAX_KEYS = sorted(k for k, m in MODEL_REGISTRY.items() if m.jax_supported)
_ALL_KEYS = sorted(MODEL_REGISTRY)


# --------------------------------------------------------------------------- #
# Part 1 — numpy ↔ jax (run in-workflow)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("key", _JAX_KEYS)
def test_jax_kernel_matches_numpy(key: str) -> None:
    """``_jax._model`` over a single-component layout equals ``get_model(key).one``."""
    optx = pytest.importorskip("optimistix")  # noqa: F841 - availability gate
    jax = pytest.importorskip("jax")
    jax.config.update("jax_enable_x64", True)
    import jax.numpy as jnp

    from oracles.backends._jax import _model

    params = _params_for(key)
    flat = [params[name] for name in get_model(key).param_names]
    layout = ((key, len(flat)),)

    got = np.asarray(
        _model(jnp.asarray(flat, dtype=jnp.float64), jnp.asarray(_X), layout),
        dtype=float,
    )
    expected = get_model(key).one(_X, params)
    np.testing.assert_allclose(got, expected, rtol=1e-9)


# --------------------------------------------------------------------------- #
# Part 2 — numpy ↔ Rust (Phase 3: requires the compiled extension)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("key", _ALL_KEYS)
def test_rust_kernel_matches_numpy(key: str) -> None:
    """A one-component ``spectrafit_core`` graph equals ``get_model(key).one``.

    Builds the graph the same way the spectrafit backend does (registry
    ``spectrafit_type`` → ``ModelType`` member, canonical param order) and evaluates
    it through the top-level ``evaluate`` helper at the same params.
    """
    pytest.importorskip("spectrafit_core")
    from spectrafit_core import (
        FitGraph,
        MeasurementData,
        ModelNodeSpec,
        ModelType,
        Parameter,
        evaluate,
    )

    model = get_model(key)
    params = _params_for(key)
    node_id = "p0"
    node = ModelNodeSpec(
        id=node_id,
        model_type=getattr(ModelType, model.spectrafit_type),
        parameters={n: Parameter(value=float(params[n])) for n in model.param_names},
    )
    graph = FitGraph(nodes=[node])
    data = MeasurementData(x=_X.tolist(), y=[0.0] * len(_X))
    flat = {f"{node_id}.{n}": float(params[n]) for n in model.param_names}

    got = np.asarray(evaluate(graph, flat, data), dtype=float)
    expected = model.one(_X, params)
    # true_voigt uses the Hui–Armstrong–Wray Faddeeva approximation in Rust (~1e-6)
    # vs scipy.special.wofz in numpy, so it parity-checks to ~1e-4, not machine eps.
    rtol, atol = (2e-4, 1e-6) if key == "true_voigt" else (1e-9, 1e-12)
    np.testing.assert_allclose(got, expected, rtol=rtol, atol=atol)


# --------------------------------------------------------------------------- #
# Part 3 — EMG extreme-tail stability (numerically-stable erfcx form)
# --------------------------------------------------------------------------- #
# At unphysical params (gamma*sigma > 37) the naive ``exp(arg_exp)*erfc`` form
# overflows (arg_exp > 709 → inf → inf*0 → NaN → 0). The numpy oracle previously
# clamped ``exp(min(arg_exp, 700))`` which underestimates in 700 < arg_exp < 709.78.
# Both were wrong by up to ~0.34. The stable erfcx regime split is overflow-free
# AND exact, so numpy, Rust, AND a 50-digit mpmath reference must all agree.

# EMG at amplitude=1, center=0, sigma=1, gamma=38 over x in [-2, 3] spans
# arg_exp ≈ 608 .. 798 (crossing the 700/709 overflow boundary). All z >= 0,
# so the erfcx branch is exercised. mpmath 50-digit reference (mp.dps=50):
#   value = A * 0.5 * gamma * exp(arg_exp) * erfc(z)
_EMG_TAIL_PARAMS = {"amplitude": 1.0, "center": 0.0, "sigma": 1.0, "gamma": 38.0}
_EMG_TAIL_X = np.linspace(-2.0, 3.0, 51)


def _emg_mpmath_reference(x_grid: np.ndarray, p: dict[str, float]) -> np.ndarray:
    """50-digit mpmath EMG: the unimpeachable ground truth (no clamp, no overflow)."""
    mp = pytest.importorskip("mpmath")
    mp.mp.dps = 50
    a = mp.mpf(p["amplitude"])
    c = mp.mpf(p["center"])
    sigma = mp.mpf(p["sigma"])
    gamma = mp.mpf(p["gamma"])
    out = []
    for xv in x_grid:
        x = mp.mpf(float(xv))
        arg_exp = gamma * (c - x) + mp.mpf("0.5") * (gamma * sigma) ** 2
        z = (c + gamma * sigma * sigma - x) / (mp.sqrt(2) * sigma)
        out.append(float(a * mp.mpf("0.5") * gamma * mp.e**arg_exp * mp.erfc(z)))
    return np.asarray(out, dtype=float)


def test_emg_extreme_tail_numpy_matches_mpmath() -> None:
    """The numpy oracle must match the 50-digit mpmath reference in the extreme tail.

    Ground-truth check: numpy was previously WRONG here (clamp underestimated),
    so numpy==Rust alone would not prove correctness — both must match mpmath.
    """
    from oracles.models import get_model

    p = _EMG_TAIL_PARAMS
    got = np.asarray(get_model("exp_gaussian").one(_EMG_TAIL_X, p), dtype=float)
    ref = _emg_mpmath_reference(_EMG_TAIL_X, p)
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-12)


def test_emg_extreme_tail_numpy_rust_parity() -> None:
    """numpy ↔ Rust EMG parity at gamma=38 (extreme tail, arg_exp ≈ 703).

    Replicates the single-component graph eval from ``test_rust_kernel_matches_numpy``.
    """
    pytest.importorskip("spectrafit_core")
    from oracles.models import get_model
    from spectrafit_core import (
        FitGraph,
        MeasurementData,
        ModelNodeSpec,
        ModelType,
        Parameter,
        evaluate,
    )

    model = get_model("exp_gaussian")
    p = _EMG_TAIL_PARAMS
    node_id = "p0"
    node = ModelNodeSpec(
        id=node_id,
        model_type=getattr(ModelType, model.spectrafit_type),
        parameters={n: Parameter(value=float(p[n])) for n in model.param_names},
    )
    graph = FitGraph(nodes=[node])
    data = MeasurementData(
        x=_EMG_TAIL_X.tolist(), y=[0.0] * len(_EMG_TAIL_X)
    )
    flat = {f"{node_id}.{n}": float(p[n]) for n in model.param_names}

    got = np.asarray(evaluate(graph, flat, data), dtype=float)
    expected = np.asarray(model.one(_EMG_TAIL_X, p), dtype=float)
    np.testing.assert_allclose(got, expected, rtol=1e-9, atol=1e-12)


# --------------------------------------------------------------------------- #
# Part 4 — pseudo_voigt out-of-range fraction parity (both sides clamp [0,1])
# --------------------------------------------------------------------------- #
def test_pseudo_voigt_out_of_range_fraction_parity() -> None:
    """numpy ↔ Rust pseudo_voigt parity when ``fraction`` is out of [0, 1].

    The numpy oracle clips ``fraction`` to [0, 1]; the Rust kernel must do the
    same (``fraction.clamp(0.0, 1.0)``) so an LM search that strays out of range
    does not measure a formula mismatch. fraction=1.3 → both behave as fraction=1.
    """
    pytest.importorskip("spectrafit_core")
    from oracles.models import get_model
    from spectrafit_core import (
        FitGraph,
        MeasurementData,
        ModelNodeSpec,
        ModelType,
        Parameter,
        evaluate,
    )

    model = get_model("pseudo_voigt")
    params = {"amplitude": 2.5, "center": 1.5, "sigma": 1.3, "fraction": 1.3}
    node_id = "p0"
    node = ModelNodeSpec(
        id=node_id,
        model_type=getattr(ModelType, model.spectrafit_type),
        parameters={n: Parameter(value=float(params[n])) for n in model.param_names},
    )
    graph = FitGraph(nodes=[node])
    data = MeasurementData(x=_X.tolist(), y=[0.0] * len(_X))
    flat = {f"{node_id}.{n}": float(params[n]) for n in model.param_names}

    got = np.asarray(evaluate(graph, flat, data), dtype=float)
    expected = np.asarray(model.one(_X, params), dtype=float)
    np.testing.assert_allclose(got, expected, rtol=1e-9, atol=1e-12)
