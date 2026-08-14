r"""Registry-driven numpy $\leftrightarrow$ jax kernel parity, on randomised parameters.

WHY THIS EXISTS. Every registered shape now has two implementations of one
formula: the canonical numpy ``PeakModel.evaluate`` (which lmfit and scipy-ls
call inside their *timed* fit loops) and the jax twin
``PeakModel.jax_evaluate`` in :mod:`oracles.jax_kernels` (which optimistix
differentiates and JITs). If those two silently diverge, every jax benchmark
number in the report becomes a measurement of a formula mismatch rather than of
a solver — and it would look perfectly healthy while doing so. This test is the
mechanical guard against that.

The complementary test ``tests/parity/test_kernel_parity.py`` checks the same
pairing at ONE hand-picked parameter set per shape (alongside numpy$\leftrightarrow$Rust).
This one instead sweeps several *random* draws per shape across each shape's
admissible envelope, so a divergence that only shows up in a corner of parameter
space — the branch masking in ``exp_gaussian`` / ``tauc`` / ``log_normal``, the
regime split in :func:`oracles.jax_kernels._erfcx`, the width-split ``where`` in
``split_gaussian`` — cannot hide behind a single lucky point.

Coverage is parametrised over :data:`oracles.models.MODEL_REGISTRY` itself, so a
newly registered shape is covered the moment it carries a ``jax_evaluate``; there
is no hand-maintained shape list here that could fall behind the registry.
"""

from __future__ import annotations

import numpy as np
import pytest
from oracles.models import MODEL_REGISTRY, SHAPE_BOUNDS, get_model

# --------------------------------------------------------------------------- #
# Tolerance
# --------------------------------------------------------------------------- #
# Measured, not guessed. Across all 32 shapes x 8 seeded draws the worst observed
# scale-relative deviation max|jax - numpy| / max|numpy| is 1.0e-14, on true_voigt
# (jax and scipy carry different Faddeeva implementations). The next worst is
# 1.5e-15 (split_pearson7) and every remaining shape sits at or below ~1e-15 --
# a handful of ULP of pure float64 re-association, with 9 shapes bit-identical.
# 1e-12 leaves ~100x headroom over the worst case for platform/XLA-version jitter
# while staying orders of magnitude tighter than any physically meaningful
# disagreement between two spellings of the same formula.
#
# DO NOT loosen this to make a failure pass. A kernel that cannot meet 1e-12 is
# not "close enough" — it is a different formula, and the honest fix is to fix
# the kernel or to leave that shape unported (drop its ``jax_evaluate``).
_PARITY_TOL = 1e-12

_N_DRAWS = 8
_N_POINTS = 97
_SEED = 20260813

# --------------------------------------------------------------------------- #
# Sampling envelopes
# --------------------------------------------------------------------------- #
_DEFAULT_X_RANGE = (-4.0, 8.0)

_X_RANGE: dict[str, tuple[float, float]] = {
    # Mirrors ``cases._LINESHAPE_X_RANGE``: these shapes are only defined (or only
    # non-trivial) on a positive / gap-bounded abscissa, and the catalogue
    # generates them there too.
    "log_normal": (0.2, 8.0),
    "tauc": (0.2, 8.0),
    "cauchy_dispersion": (0.3, 6.0),
    "kww": (0.0, 10.0),
    "saturating_exponential": (0.0, 8.0),
    "power_saturation": (0.0, 8.0),
    "power_law_offset": (0.0, 8.0),
    "mgh09_rational": (0.1, 8.0),
    # harmonic_ir's denominator (c^2 - x^2)^2 + (sigma*x)^2 collapses toward zero
    # as x and center both approach 0; a positive grid keeps it a real resonance.
    "harmonic_ir": (0.5, 6.0),
}

_PARAM_RANGE: dict[str, tuple[float, float]] = {
    "amplitude": (0.5, 5.0),
    "center": (-1.0, 3.0),
    "sigma": (0.4, 2.5),
    "sigma_l": (0.4, 2.5),
    "sigma_r": (0.4, 2.5),
    "gamma": (0.3, 2.0),
    "fraction": (0.0, 1.0),
    "c": (-2.0, 2.0),
    "slope": (-2.0, 2.0),
    "intercept": (-3.0, 3.0),
    "offset": (2.0, 8.0),
    "shape": (0.3, 3.0),
    "A1": (0.5, 4.0),
    "lam1": (0.05, 1.0),
    "A2": (0.3, 3.0),
    "lam2": (0.02, 0.6),
    "e_gap": (0.5, 3.0),
    "exponent": (0.5, 3.0),
    "a": (0.5, 3.0),
    "b": (0.1, 2.0),
    "tau": (0.5, 5.0),
    "rate": (0.05, 1.5),
    "num_lin": (0.05, 0.5),
    "den_lin": (0.05, 0.5),
    "den_const": (0.05, 0.5),
    # The long-tail shape parameters take their envelope straight from the
    # registry's own SHAPE_BOUNDS table -- the same finite box the lmfit and
    # scipy-ls oracles search in -- rather than a second hand-tuned copy.
    **SHAPE_BOUNDS,
}

_PARAM_RANGE_OVERRIDES: dict[str, dict[str, tuple[float, float]]] = {
    # `center` is the log-space location and must be strictly positive.
    "log_normal": {"center": (0.5, 3.0)},
    # Keep the resonance inside the grid and away from x = 0.
    "harmonic_ir": {"center": (1.0, 4.0)},
    # Doniach-Sunjic `gamma` is the asymmetry index, physical only in (0, 1);
    # it is NOT the Lorentzian width the shared `gamma` default describes.
    "doniach_sunjic": {"gamma": (0.02, 0.6)},
    # KWW `beta` is a stretch exponent in (0, 1]-ish, not moffat's SHAPE_BOUNDS
    # power; beyond ~3 the profile is a step and the comparison is vacuous.
    "kww": {"beta": (0.2, 3.0)},
    # power_law_offset needs offset + x > 0 across its (0, 8] grid.
    "power_law_offset": {"offset": (0.5, 5.0)},
}


def _range_for(key: str, name: str) -> tuple[float, float]:
    """Sampling envelope for parameter *name* of shape *key*."""
    override = _PARAM_RANGE_OVERRIDES.get(key, {}).get(name)
    if override is not None:
        return override
    try:
        return _PARAM_RANGE[name]
    except KeyError:  # pragma: no cover - a new param name needs an envelope
        msg = f"no sampling envelope registered for parameter {name!r} (shape {key!r})"
        raise AssertionError(msg) from None


def _grid(key: str) -> np.ndarray:
    """Probe abscissa for shape *key*."""
    lo, hi = _X_RANGE.get(key, _DEFAULT_X_RANGE)
    return np.linspace(lo, hi, _N_POINTS)


def _draws(key: str) -> list[dict[str, float]]:
    """``_N_DRAWS`` deterministic parameter dicts in canonical registry order.

    Seeded per shape off a fixed base so a failure is reproducible verbatim and
    the suite never flakes on a fresh random draw.
    """
    rng = np.random.default_rng([_SEED, *(ord(ch) for ch in key)])
    names = get_model(key).param_names
    return [
        {name: float(rng.uniform(*_range_for(key, name))) for name in names}
        for _ in range(_N_DRAWS)
    ]


_JAX_KEYS = sorted(k for k, m in MODEL_REGISTRY.items() if m.jax_supported)


@pytest.fixture(scope="module")
def _jax_x64() -> None:
    """Enable float64 once per module -- jax defaults to float32, which would fail."""
    jax = pytest.importorskip("jax")
    jax.config.update("jax_enable_x64", True)  # noqa: FBT003 - jax's own signature


@pytest.mark.usefixtures("_jax_x64")
@pytest.mark.parametrize("key", _JAX_KEYS)
def test_jax_kernel_matches_numpy_on_random_params(key: str) -> None:
    """``jax_evaluate`` must equal ``evaluate`` on every seeded draw for *key*."""
    pytest.importorskip("jax")
    import jax.numpy as jnp

    model = get_model(key)
    assert model.jax_evaluate is not None  # guarded by the _JAX_KEYS filter
    x = _grid(key)
    jx = jnp.asarray(x)

    for i, params in enumerate(_draws(key)):
        expected = np.asarray(model.one(x, params), dtype=float)
        assert np.isfinite(expected).all(), (
            f"{key} draw {i}: the numpy reference itself is non-finite at "
            f"{params} -- the sampling envelope, not the jax kernel, is wrong"
        )
        got = np.asarray(
            model.jax_evaluate(jx, **{n: params[n] for n in model.param_names}),
            dtype=float,
        )
        scale = float(np.max(np.abs(expected)))
        # Scale-relative: several shapes cross zero (linear, doniach_sunjic,
        # breit_wigner), where a pointwise rtol is meaningless.
        deviation = float(np.max(np.abs(got - expected))) / max(scale, 1.0)
        assert deviation <= _PARITY_TOL, (
            f"{key} draw {i}: jax/numpy deviation {deviation:.3e} exceeds "
            f"{_PARITY_TOL:.0e} at {params}"
        )


@pytest.mark.usefixtures("_jax_x64")
def test_jax_emg_matches_numpy_in_the_overflow_tail() -> None:
    r"""The ``erfcx`` regime split must hold where the naive EMG form overflows.

    ``jax.scipy.special`` has no ``erfcx``, so :func:`oracles.jax_kernels._erfcx`
    reconstructs it. At $\gamma = 38$ the exponent $\mathrm{arg\_exp}$ reaches
    $\approx 800$, so the naive $\exp(\mathrm{arg\_exp})\cdot\mathrm{erfc}(z)$
    would be $\infty \cdot 0 =$ NaN in both runtimes; the random-draw sweep above
    never reaches this regime. The numpy side is itself pinned against a 50-digit
    mpmath reference in ``tests/parity/test_kernel_parity.py``, so agreeing with
    it here is agreement with ground truth.
    """
    pytest.importorskip("jax")
    import jax.numpy as jnp

    model = get_model("exp_gaussian")
    params = {"amplitude": 1.0, "center": 0.0, "sigma": 1.0, "gamma": 38.0}
    x = np.linspace(-2.0, 3.0, 51)

    expected = np.asarray(model.one(x, params), dtype=float)
    assert model.jax_evaluate is not None
    got = np.asarray(model.jax_evaluate(jnp.asarray(x), **params), dtype=float)

    assert np.isfinite(got).all(), "jax EMG produced a non-finite value in the tail"
    np.testing.assert_allclose(got, expected, rtol=1e-12, atol=0.0)


@pytest.mark.usefixtures("_jax_x64")
@pytest.mark.parametrize("key", _JAX_KEYS)
def test_jax_kernel_is_differentiable(key: str) -> None:
    """Every kernel must yield a finite gradient -- optimistix's LM needs one.

    A kernel can match numpy pointwise and still be useless to the jax backend if
    a masked ``where`` branch leaks a NaN into reverse-mode AD (the classic jax
    trap this module's double-``where`` masking exists to avoid). Value parity
    alone would not catch it.
    """
    jax = pytest.importorskip("jax")
    import jax.numpy as jnp

    model = get_model(key)
    assert model.jax_evaluate is not None
    x = jnp.asarray(_grid(key))

    def loss(p: object) -> object:
        kwargs = {n: p[i] for i, n in enumerate(model.param_names)}
        return jnp.sum(model.jax_evaluate(x, **kwargs) ** 2)  # type: ignore[misc]

    for i, params in enumerate(_draws(key)):
        flat = jnp.asarray([params[n] for n in model.param_names], dtype=jnp.float64)
        grad = np.asarray(jax.grad(loss)(flat), dtype=float)
        assert np.isfinite(grad).all(), f"{key} draw {i}: non-finite gradient {grad} at {params}"
