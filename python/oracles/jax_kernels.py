r"""JAX transcriptions of every numpy peak kernel in :mod:`oracles.models`.

WHY A SEPARATE MODULE. The numpy ``evaluate`` bodies in :mod:`oracles.models`
sit *inside the timed fit loop* of the lmfit and scipy-ls benchmark backends, so
they must never grow a jax branch, a dispatch, or an import cost (DECISIONS.md
[2026-06-10] benchmark-fairness revert). The jax oracle needs the same formulas
expressed in ``jax.numpy`` so ``jax.grad``/``jax.jit`` can flow through them.
Two implementations of one formula is a real divergence hazard, so every kernel
here is pinned against its numpy twin by ``tests/unit/test_jax_kernel_parity.py``,
which parametrises over the live registry (a new shape is covered the moment it
is registered).

WHY NOT UNDER ``oracles/backends/``. :mod:`oracles.models` registers these
callables, and ``oracles.backends.__init__`` imports ``_base``, which imports
``oracles.cases``, which imports :mod:`oracles.models` — placing this module in
that package would make the registry's own import cycle back through the
backends layer. This module is a leaf: it imports nothing from ``oracles``.

WHY THE IMPORTS ARE LAZY. ``jax`` is an optional extra. Every kernel body
imports ``jax.numpy`` locally, so ``import oracles.models`` (and therefore the
whole test suite and the ``lmfit``/``scipy`` benchmark path) keeps working in an
environment where jax is absent. The kernels are only *called* by the jax
backend, which already refuses to construct without jax installed.

Signatures mirror the numpy originals exactly — ``kernel(x, **param_names)`` in
canonical registry order — so :func:`oracles.backends._jax._kernel` can splat a
flat parameter segment by name with no per-shape knowledge.

Note:
    Branch-masking discipline. Wherever the numpy body relies on ``np.errstate``
    to let a NaN/inf appear in an unselected ``np.where`` branch, the jax
    transcription masks the *input* to that branch instead (the "double-where"
    trick). ``jnp.where`` selects the right value either way, but a NaN in the
    discarded branch poisons the reverse-mode gradient optimistix computes.
"""

from __future__ import annotations

import math
from typing import Any

_SQRT2 = math.sqrt(2.0)
_SQRT_PI = math.sqrt(math.pi)

# Crossover between the two erfcx regimes. Below it the direct
# $\exp(z^2)\,\mathrm{erfc}(z)$ form is accurate but degrades like $z^2\varepsilon$,
# and past $z\approx 27$ it fails outright ($\mathrm{erfc}$ underflows to zero while
# $\exp$ overflows, giving $\infty\cdot 0 =$ NaN). Above it the 8-term asymptotic
# series has converged: at $z=15$ its first dropped term is
# $\approx 3\times10^{-14}$ relative, and it only shrinks from there. Measured
# against ``scipy.special.erfcx`` over $z \in [0, 100]$, the combined function's
# worst relative error is $1.8\times10^{-15}$ — the crossover itself is not the
# worst point.
_ERFCX_ASYMPTOTIC_Z = 15.0

_ERFCX_HORNER_COEFFS = (13.0, 11.0, 9.0, 7.0, 5.0, 3.0, 1.0)
r"""Horner factors of $\sum_{k=0}^{7}(-1)^k(2k-1)!!\,t^k$ with $t = 1/(2z^2)$,
applied outermost-last: repeatedly folding ``series = 1 - odd*t*series`` over
the descending odd numbers reproduces the double-factorial coefficients
$1,1,3,15,105,945,10395,135135$ without spelling them out.
"""


def _erfcx(z: Any) -> Any:
    r"""Scaled complementary error function $\exp(z^2)\,\mathrm{erfc}(z)$, for $z \ge 0$.

    ``jax.scipy.special`` has no ``erfcx`` (unlike ``scipy.special``), and the
    naive $\exp(z^2)\cdot\mathrm{erfc}(z)$ overflows to $\infty\cdot 0 =$ NaN once
    $z \gtrsim 27$. This is the two-regime replacement the EMG kernel needs:

    * $z < 15$: the direct product, which is exact to $\approx z^2\varepsilon$.
    * $z \ge 15$: the asymptotic expansion
      $\mathrm{erfcx}(z) \sim \frac{1}{z\sqrt{\pi}}\sum_{k}(-1)^k\frac{(2k-1)!!}{(2z^2)^k}$,
      evaluated in Horner form through $k=7$.

    Both branches are computed on *masked* inputs so neither can produce a NaN
    that would poison the gradient of the branch that is discarded.

    Only the $z \ge 0$ half is needed (and only that half is accurate): for
    $z < 0$, $\mathrm{erfcx}$ grows like $\exp(z^2)$ and overflows anyway, which
    is exactly why :func:`exp_gaussian` uses the plain ``erfc`` form there.
    """
    import jax.numpy as jnp
    from jax.scipy.special import erfc as jerfc

    use_asymptotic = z >= _ERFCX_ASYMPTOTIC_Z
    z_direct = jnp.where(use_asymptotic, 1.0, z)
    direct = jnp.exp(z_direct * z_direct) * jerfc(z_direct)

    z_asym = jnp.where(use_asymptotic, z, _ERFCX_ASYMPTOTIC_Z)
    t = 1.0 / (2.0 * z_asym * z_asym)
    series = 1.0
    for odd in _ERFCX_HORNER_COEFFS:  # unrolled at trace time (7 terms)
        series = 1.0 - odd * t * series
    asymptotic = series / (z_asym * _SQRT_PI)
    return jnp.where(use_asymptotic, asymptotic, direct)


# --------------------------------------------------------------------------- #
# Peak / lineshape kernels — one per registered shape, numpy signature order
# --------------------------------------------------------------------------- #
def gaussian(x: Any, amplitude: Any, center: Any, sigma: Any) -> Any:
    """JAX twin of :func:`oracles.models.gaussian`."""
    import jax.numpy as jnp

    return amplitude * jnp.exp(-0.5 * ((x - center) / sigma) ** 2)


def lorentzian(x: Any, amplitude: Any, center: Any, sigma: Any) -> Any:
    """JAX twin of :func:`oracles.models.lorentzian`."""
    return amplitude / (1.0 + ((x - center) / sigma) ** 2)


def pseudo_voigt(x: Any, amplitude: Any, center: Any, sigma: Any, fraction: Any) -> Any:
    """JAX twin of :func:`oracles.models.pseudo_voigt` (``fraction`` clipped to [0, 1])."""
    import jax.numpy as jnp

    mix = jnp.clip(fraction, 0.0, 1.0)
    z = (x - center) / sigma
    lorentz = amplitude / (1.0 + z**2)
    gauss = amplitude * jnp.exp(-0.5 * z**2)
    return mix * lorentz + (1.0 - mix) * gauss


def fano(x: Any, amplitude: Any, center: Any, gamma: Any, q: Any) -> Any:
    """JAX twin of :func:`oracles.models.fano`."""
    eps = (x - center) / gamma
    return amplitude * (q + eps) ** 2 / (1.0 + eps**2)


def constant(x: Any, c: Any) -> Any:
    """JAX twin of :func:`oracles.models.constant`.

    ``jnp.zeros_like(x) + c`` rather than ``jnp.full_like(x, c)``: the latter
    would treat a traced ``c`` as a fill *value* and drop it from the autodiff
    graph, so the constant background would show a zero gradient.
    """
    import jax.numpy as jnp

    return jnp.zeros_like(x) + c


def linear(x: Any, slope: Any, intercept: Any) -> Any:
    """JAX twin of :func:`oracles.models.linear`."""
    return slope * x + intercept


def quadratic(x: Any, amplitude: Any, center: Any, offset: Any) -> Any:
    """JAX twin of :func:`oracles.models.quadratic`."""
    return amplitude * (x - center) ** 2 + offset


def arctan_step(x: Any, amplitude: Any, center: Any, sigma: Any) -> Any:
    """JAX twin of :func:`oracles.models.arctan_step`."""
    import jax.numpy as jnp

    return amplitude * (0.5 + jnp.arctan((x - center) / sigma) / math.pi)


def tanh_step(x: Any, amplitude: Any, center: Any, sigma: Any) -> Any:
    """JAX twin of :func:`oracles.models.tanh_step`."""
    import jax.numpy as jnp

    return 0.5 * amplitude * (1.0 + jnp.tanh((x - center) / sigma))


def erfc_step(x: Any, amplitude: Any, center: Any, sigma: Any) -> Any:
    """JAX twin of :func:`oracles.models.erfc_step`."""
    from jax.scipy.special import erfc as jerfc

    return 0.5 * amplitude * jerfc((x - center) / (sigma * _SQRT2))


def double_exponential(x: Any, A1: Any, lam1: Any, A2: Any, lam2: Any) -> Any:
    """JAX twin of :func:`oracles.models.double_exponential` (``A1``/``A2`` mirror it)."""
    import jax.numpy as jnp

    return A1 * jnp.exp(-lam1 * x) + A2 * jnp.exp(-lam2 * x)


def true_voigt(x: Any, amplitude: Any, center: Any, sigma: Any, gamma: Any) -> Any:
    r"""JAX twin of :func:`oracles.models.true_voigt`.

    ``jax.scipy.special.wofz`` is the same Faddeeva function ``scipy.special.wofz``
    provides (agreement to $\approx 10^{-15}$), and ``jax.grad`` flows through it,
    so the true Voigt needs no reformulation — only a complex-dtype ``x64``
    context, which :class:`~oracles.backends._jax.JaxBackend` enables at import.
    """
    import jax.numpy as jnp
    from jax.scipy.special import wofz as jwofz

    inv = 1.0 / (sigma * _SQRT2)
    z = ((x - center) + 1j * jnp.abs(gamma)) * inv
    z0 = 1j * jnp.abs(gamma) * inv
    return amplitude * jnp.real(jwofz(z)) / jnp.real(jwofz(z0))


def skewed_gaussian(x: Any, amplitude: Any, center: Any, sigma: Any, gamma: Any) -> Any:
    """JAX twin of :func:`oracles.models.skewed_gaussian`."""
    import jax.numpy as jnp
    from jax.scipy.special import erf as jerf

    dx = x - center
    g = jnp.exp(-0.5 * (dx / sigma) ** 2)
    return amplitude * g * (1.0 + jerf(gamma * dx / (sigma * _SQRT2)))


def exp_gaussian(x: Any, amplitude: Any, center: Any, sigma: Any, gamma: Any) -> Any:
    r"""JAX twin of :func:`oracles.models.exp_gaussian` (overflow-free EMG).

    Identical regime split to the numpy body — $z \ge 0$ uses the ``erfcx`` form,
    $z < 0$ uses $\exp(\mathrm{arg\_exp})\,\mathrm{erfc}(z)$ with ``arg_exp < 0`` —
    but ``jax.scipy.special`` has no ``erfcx``, so :func:`_erfcx` supplies it, and
    both branches take masked inputs (numpy instead suppresses the resulting
    warnings with ``np.errstate``).
    """
    import jax.numpy as jnp
    from jax.scipy.special import erfc as jerfc

    arg_exp = gamma * (center - x) + 0.5 * (gamma * sigma) ** 2
    z = (center + gamma * sigma * sigma - x) / (_SQRT2 * sigma)
    gauss = jnp.exp(-((x - center) ** 2) / (2.0 * sigma * sigma))
    pref = amplitude * 0.5 * gamma
    upper = z >= 0.0
    v = jnp.where(
        upper,
        pref * gauss * _erfcx(jnp.where(upper, z, 0.0)),
        pref * jnp.exp(jnp.where(upper, 0.0, arg_exp)) * jerfc(z),
    )
    return jnp.where(jnp.isfinite(v), v, 0.0)


def doniach_sunjic(x: Any, amplitude: Any, center: Any, sigma: Any, gamma: Any) -> Any:
    """JAX twin of :func:`oracles.models.doniach_sunjic`."""
    import jax.numpy as jnp

    u = (x - center) / sigma
    num = jnp.cos(0.5 * math.pi * gamma + (1.0 - gamma) * jnp.arctan(u))
    den = (1.0 + u * u) ** ((1.0 - gamma) / 2.0)
    return amplitude * num / den


def log_normal(x: Any, amplitude: Any, center: Any, sigma: Any) -> Any:
    """JAX twin of :func:`oracles.models.log_normal` (zero for ``x <= 0``)."""
    import jax.numpy as jnp

    positive = x > 0.0
    safe_x = jnp.where(positive, x, 1.0)
    val = amplitude * jnp.exp(-((jnp.log(safe_x / center)) ** 2) / (2.0 * sigma**2))
    return jnp.where(positive, val, 0.0)


def pearson7(x: Any, amplitude: Any, center: Any, sigma: Any, m: Any) -> Any:
    """JAX twin of :func:`oracles.models.pearson7`."""
    z = (x - center) / sigma
    return amplitude / (1.0 + z * z * (2.0 ** (1.0 / m) - 1.0)) ** m


def split_gaussian(x: Any, amplitude: Any, center: Any, sigma_l: Any, sigma_r: Any) -> Any:
    """JAX twin of :func:`oracles.models.split_gaussian`."""
    import jax.numpy as jnp

    return jnp.where(
        x < center,
        amplitude * jnp.exp(-0.5 * ((x - center) / sigma_l) ** 2),
        amplitude * jnp.exp(-0.5 * ((x - center) / sigma_r) ** 2),
    )


def moffat(x: Any, amplitude: Any, center: Any, sigma: Any, beta: Any) -> Any:
    """JAX twin of :func:`oracles.models.moffat`."""
    return amplitude / (((x - center) / sigma) ** 2 + 1.0) ** beta


def students_t(x: Any, amplitude: Any, center: Any, sigma: Any, nu: Any) -> Any:
    """JAX twin of :func:`oracles.models.students_t`."""
    return amplitude / (1.0 + ((x - center) / sigma) ** 2 / nu) ** ((nu + 1.0) / 2.0)


def split_pearson7(
    x: Any,
    amplitude: Any,
    center: Any,
    sigma_l: Any,
    sigma_r: Any,
    m_l: Any,
    m_r: Any,
) -> Any:
    """JAX twin of :func:`oracles.models.split_pearson7`."""
    import jax.numpy as jnp

    left = amplitude / (1.0 + ((x - center) / sigma_l) ** 2 * (2.0 ** (1.0 / m_l) - 1.0)) ** m_l
    right = amplitude / (1.0 + ((x - center) / sigma_r) ** 2 * (2.0 ** (1.0 / m_r) - 1.0)) ** m_r
    return jnp.where(x < center, left, right)


def breit_wigner(x: Any, amplitude: Any, center: Any, sigma: Any, q: Any) -> Any:
    """JAX twin of :func:`oracles.models.breit_wigner`."""
    g = sigma / 2.0
    return amplitude * (q * g + (x - center)) ** 2 / (g * g + (x - center) ** 2)


def asym_ir(x: Any, amplitude: Any, center: Any, sigma: Any, k: Any) -> Any:
    """JAX twin of :func:`oracles.models.asym_ir` (sigmoid exponent capped at 50)."""
    import jax.numpy as jnp

    g = amplitude * jnp.exp(-((x - center) ** 2) / (2.0 * sigma**2))
    arg = jnp.minimum(-k * (x - center), 50.0)
    return g / (1.0 + jnp.exp(arg))


def harmonic_ir(x: Any, amplitude: Any, center: Any, sigma: Any) -> Any:
    """JAX twin of :func:`oracles.models.harmonic_ir`."""
    return amplitude / ((center**2 - x**2) ** 2 + (sigma * x) ** 2)


def tauc(x: Any, amplitude: Any, e_gap: Any, exponent: Any) -> Any:
    """JAX twin of :func:`oracles.models.tauc` (zero below the gap)."""
    import jax.numpy as jnp

    excess = x - e_gap
    above = excess > 0.0
    safe = jnp.where(above, excess, 1.0)
    return jnp.where(above, amplitude * safe**exponent, 0.0)


def cauchy_dispersion(x: Any, a: Any, b: Any, c: Any) -> Any:
    """JAX twin of :func:`oracles.models.cauchy_dispersion` (zero for ``x <= 0``)."""
    import jax.numpy as jnp

    positive = x > 0.0
    safe_x = jnp.where(positive, x, 1.0)
    val = a + b / safe_x**2 + c / safe_x**4
    return jnp.where(positive, val, 0.0)


def kww(x: Any, amplitude: Any, tau: Any, beta: Any) -> Any:
    r"""JAX twin of :func:`oracles.models.kww` (zero for ``x < 0``).

    Three-way rather than the numpy body's two-way mask. ``x = 0`` is a real grid
    point for this shape (the catalogue generates KWW on $[0, 10]$) and there the
    stretched power $(x/\tau)^\beta$ is exactly $0^\beta$: the value is fine
    ($\to 0$, so the kernel returns ``amplitude``), but its derivative
    $\beta\,b^{\beta-1}$ diverges, and reverse-mode AD multiplies that $\infty$
    by the $\partial b/\partial\tau = -x/\tau^2 = 0$ it sees at $x = 0$, yielding
    a NaN $\partial/\partial\tau$ that would poison every KWW solve. The function
    is constant in $\tau$ at $x = 0$, so the honest gradient is zero; splitting
    ``x == 0`` out of the power gives exactly that, with the identical value.
    """
    import jax.numpy as jnp

    positive = x > 0.0
    safe = jnp.where(positive, x / tau, 1.0)
    decayed = amplitude * jnp.exp(-(safe**beta))
    return jnp.where(x >= 0.0, jnp.where(positive, decayed, amplitude), 0.0)


def saturating_exponential(x: Any, amplitude: Any, rate: Any) -> Any:
    """JAX twin of :func:`oracles.models.saturating_exponential`."""
    import jax.numpy as jnp

    return amplitude * (1.0 - jnp.exp(-rate * x))


def power_saturation(x: Any, amplitude: Any, rate: Any) -> Any:
    """JAX twin of :func:`oracles.models.power_saturation`."""
    return amplitude * (1.0 - (1.0 + rate * x / 2.0) ** (-2.0))


def power_law_offset(x: Any, amplitude: Any, offset: Any, shape: Any) -> Any:
    """JAX twin of :func:`oracles.models.power_law_offset`."""
    return amplitude * (offset + x) ** (-1.0 / shape)


def mgh09_rational(
    x: Any,
    amplitude: Any,
    num_lin: Any,
    den_lin: Any,
    den_const: Any,
) -> Any:
    """JAX twin of :func:`oracles.models.mgh09_rational`."""
    n = x**2 + num_lin * x
    d = x**2 + den_lin * x + den_const
    return amplitude * n / d


def rational_cubic(
    x: Any,
    a0: float,
    a1: float,
    a2: float,
    a3: float,
    b1: float,
    b2: float,
    b3: float,
) -> Any:
    """JAX twin of :func:`oracles.models.rational_cubic`."""
    n = a0 + a1 * x + a2 * x**2 + a3 * x**3
    d = 1.0 + b1 * x + b2 * x**2 + b3 * x**3
    return n / d


def generalised_logistic(
    x: Any,
    amplitude: Any,
    shift: Any,
    rate: Any,
    shape: Any,
) -> Any:
    """JAX twin of :func:`oracles.models.generalised_logistic`."""
    import jax.numpy as jnp

    return amplitude / (1.0 + jnp.exp(shift - rate * x)) ** (1.0 / shape)


def exp_over_linear(x: Any, rate: Any, lin_const: Any, lin_slope: Any) -> Any:
    """JAX twin of :func:`oracles.models.exp_over_linear`."""
    import jax.numpy as jnp

    return jnp.exp(-rate * x) / (lin_const + lin_slope * x)
