"""Model registry — the extensible catalogue of fittable shapes.

Each shape is registered **once** as a :class:`PeakModel` record that bundles
everything the engine needs: the numpy formula (data generation + scoring), the
lmfit shape callable (oracle), the spectrafit ``ModelType`` name (subject), the
canonical parameter names, and whether the jax oracle supports it. Adding a model
is a one-record registration — backends never hardcode per-model maps.

Conventions (``MODELS.md``): ``amplitude`` is the peak value at ``center`` (not
area), ``sigma`` is the standard-deviation width, and the pseudo-Voigt mixing
weight is always ``fraction``.

This module holds **behaviour** (formulas), so the registry records are Pydantic
models with `Callable` fields rather than plain dataclasses — keeping the whole
engine pydantic-first while still carrying code.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from typing import Any

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, model_validator
from scipy.special import erfcx  # scaled erfc, exp(x²)·erfc(x) — overflow-free EMG tail
from scipy.special import wofz  # Faddeeva function for the true Voigt profile

from spectrafit_core.models import ModelType

Array = NDArray[np.float64]
_erfc = np.vectorize(math.erfc)  # numpy has no erfc; math.erfc is stdlib
_erf = np.vectorize(math.erf)  # numpy has no erf; math.erf is stdlib
_SQRT2 = math.sqrt(2.0)

# --------------------------------------------------------------------------- #
# Wheel-eval helper — PARITY-ONLY (DECISIONS.md 2026-06-10 fairness revert)
#
# The numpy formulas below are the canonical, timing-fair oracle
# implementations: lmfit and scipy-ls introspect and call ``evaluate`` inside
# their *timed* fit loops, so these bodies must never pay wheel/JSON overhead
# (CLAUDE.md: "per-point array serialization never pollutes the comparison").
# The Rust kernels registered in
# ``crates/spectrafit-models/src/lib.rs::model_from_str`` are mathematically
# identical; that parity is enforced by
# ``tests/unit/oracles/test_wheel_eval.py`` via :func:`_wheel_eval` and
# :func:`wheel_parity_pairs` — NOT by routing the hot path through the wheel.
# --------------------------------------------------------------------------- #
# ``_CORE_WHEEL`` is intentionally ``Any``-typed because it must be assignable
# either to the imported ``spectrafit_core._core`` extension module (happy
# path) or to ``None`` (wheel unavailable). Using a single ``Any``-typed
# declaration with an explicit cast avoids the conflicting-declarations
# diagnostic that ``ty`` raises when the import-narrowed and ``None`` arms
# would otherwise produce two incompatible declared types.
_CORE_WHEEL: Any = None
_WHEEL_AVAILABLE = False
try:
    from spectrafit_core import _core as _core_extension

    _CORE_WHEEL = _core_extension
    _WHEEL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by the fallback test
    pass


def _wheel_eval(model_type: str, x: Array, params: dict[str, float]) -> Array:
    """Evaluate a model kernel via the Rust wheel.

    Constructs a single-node FitGraph JSON for ``model_type``, calls
    ``_core.evaluate(graph_json, params_json, data_json)``, and returns the
    resulting numpy array. ``model_type`` must be one of the keys accepted by
    ``spectrafit_models::model_from_str``; ``params`` keys must be the bare
    parameter names (without the node prefix).

    Raises :class:`RuntimeError` when the wheel is unavailable. This helper is
    a **parity instrument only** — the parity tests skip when the wheel is
    absent; production ``evaluate`` bodies are pure numpy and never call it.
    """
    if not _WHEEL_AVAILABLE or _CORE_WHEEL is None:
        raise RuntimeError(
            "spectrafit_core wheel unavailable — run `maturin develop` to build"
        )
    node_id = "k"  # short fixed node id keeps the param prefix predictable
    nodes = [
        {
            "id": node_id,
            "model_type": model_type,
            "parameters": {
                name: {
                    "value": float(v),
                    "min": None,
                    "max": None,
                    "vary": True,
                    "expr": None,
                    "scale": None,
                }
                for name, v in params.items()
            },
        }
    ]
    graph_json = json.dumps({"schema_version": "0.1", "nodes": nodes, "expr_edges": []})
    params_json = json.dumps({f"{node_id}.{k}": float(v) for k, v in params.items()})
    x_arr = np.asarray(x, dtype=np.float64)
    data_json = json.dumps(
        {
            "schema_version": "0.1",
            "x": [[float(v)] for v in x_arr.tolist()],
            "y": [0.0] * x_arr.size,
            "sigma": None,
            "label": None,
        }
    )
    result = json.loads(_CORE_WHEEL.evaluate(graph_json, params_json, data_json))
    return np.asarray(result, dtype=np.float64)


# --------------------------------------------------------------------------- #
# Peak formulas (numpy) — canonical spectrafit conventions
# --------------------------------------------------------------------------- #


def gaussian(x: Array, amplitude: float, center: float, sigma: float) -> Array:
    """Gaussian peak: ``amplitude`` at ``center``, std-dev ``sigma``."""
    return amplitude * np.exp(-0.5 * ((x - center) / sigma) ** 2)


def lorentzian(x: Array, amplitude: float, center: float, sigma: float) -> Array:
    """Lorentzian peak normalized to ``amplitude`` at ``center`` (HWHM ``sigma``)."""
    return amplitude / (1.0 + ((x - center) / sigma) ** 2)


def pseudo_voigt(
    x: Array, amplitude: float, center: float, sigma: float, fraction: float
) -> Array:
    """Pseudo-Voigt: ``fraction``·Lorentzian + (1−``fraction``)·Gaussian (peak ``amplitude``).

    Formulas are inlined (not calls to :func:`lorentzian` / :func:`gaussian`)
    so this hot-path body has no coupling to sibling function bodies.
    """
    mix = float(np.clip(fraction, 0.0, 1.0))
    z = (x - center) / sigma
    lorentz = amplitude / (1.0 + z**2)
    gauss = amplitude * np.exp(-0.5 * z**2)
    return mix * lorentz + (1.0 - mix) * gauss


def fano(x: Array, amplitude: float, center: float, gamma: float, q: float) -> Array:
    """Fano resonance: ``A·(q+ε)²/(1+ε²)``, ε=(x−center)/gamma."""
    eps = (x - center) / gamma
    return amplitude * (q + eps) ** 2 / (1.0 + eps**2)


def constant(x: Array, c: float) -> Array:
    """Constant background ``c``."""
    return np.full_like(x, c)


def linear(x: Array, slope: float, intercept: float) -> Array:
    """Linear background ``slope·x + intercept``."""
    return slope * x + intercept


def quadratic(x: Array, amplitude: float, center: float, offset: float) -> Array:
    """Quadratic bowl ``A·(x−center)² + offset``."""
    return amplitude * (x - center) ** 2 + offset


def arctan_step(x: Array, amplitude: float, center: float, sigma: float) -> Array:
    """Arctan edge: ``A·(½ + (1/π)·arctan((x−center)/sigma))`` (rising)."""
    return amplitude * (0.5 + np.arctan((x - center) / sigma) / np.pi)


def tanh_step(x: Array, amplitude: float, center: float, sigma: float) -> Array:
    """Tanh edge: ``(A/2)·(1 + tanh((x−center)/sigma))`` (rising)."""
    return 0.5 * amplitude * (1.0 + np.tanh((x - center) / sigma))


def erfc_step(x: Array, amplitude: float, center: float, sigma: float) -> Array:
    """Erfc edge: ``(A/2)·erfc((x−center)/(sigma·√2))`` (falling)."""
    return 0.5 * amplitude * _erfc((x - center) / (sigma * math.sqrt(2.0)))


def double_exponential(
    x: Array, A1: float, lam1: float, A2: float, lam2: float
) -> Array:  # noqa: N803
    """Bi-exponential decay ``A1·exp(−lam1·x) + A2·exp(−lam2·x)``."""
    return A1 * np.exp(-lam1 * x) + A2 * np.exp(-lam2 * x)


# --------------------------------------------------------------------------- #
# Asymmetric / true-Voigt lineshapes — formulas IDENTICAL to the Rust kernels
# (crates/spectrafit-models/src/{voigt_true,skewed_gaussian,emg,doniach}.rs) so
# numpy↔Rust kernel parity holds. See DECISIONS.md / the deep-research report.
# --------------------------------------------------------------------------- #
def true_voigt(
    x: Array, amplitude: float, center: float, sigma: float, gamma: float
) -> Array:
    """True Voigt (Gaussian ⊗ Lorentzian) via the Faddeeva fn, peak height ``amplitude``.

    ``A·Re[w(z)]/Re[w(z₀)]`` with ``z=((x−center)+iγ)/(σ√2)``, ``z₀=iγ/(σ√2)``.

    NOTE: the Rust kernel uses the Hui–Armstrong–Wray Faddeeva approximation
    (~1e-6 accuracy) while the numpy fallback uses ``scipy.special.wofz``, so
    wheel-vs-numpy parity here is ~1e-4 — see ``test_kernel_parity.py``.
    """
    inv = 1.0 / (sigma * _SQRT2)
    z = ((x - center) + 1j * abs(gamma)) * inv
    z0 = 1j * abs(gamma) * inv
    return amplitude * wofz(z).real / wofz(z0).real


def skewed_gaussian(
    x: Array, amplitude: float, center: float, sigma: float, gamma: float
) -> Array:
    """Skewed Gaussian ``A·exp(−½((x−c)/σ)²)·(1 + erf(γ(x−c)/(σ√2)))`` (γ = skew)."""
    dx = x - center
    g = np.exp(-0.5 * (dx / sigma) ** 2)
    return amplitude * g * (1.0 + _erf(gamma * dx / (sigma * _SQRT2)))


def exp_gaussian(
    x: Array, amplitude: float, center: float, sigma: float, gamma: float
) -> Array:
    """Exponentially-modified Gaussian (asymmetric tail); non-finite → 0 (Rust parity).

    Numerically stable, overflow-free, and exact — **no clamp**. The naive form
    ``exp(arg_exp)·erfc(z)`` overflows to ``inf·0 → NaN`` once ``arg_exp > 709``
    (e.g. ``gamma*sigma > 37``). Using the algebraic identity
    ``arg_exp − z² = −(x−center)²/(2σ²)`` we split on the sign of ``z``:

    * ``z ≥ 0``: ``A·(γ/2)·exp(−(x−center)²/(2σ²))·erfcx(z)`` — both factors are
      bounded (``erfcx(z) ∈ (0,1]``, Gaussian ``≤ 1``), so no overflow.
    * ``z < 0``: ``A·(γ/2)·exp(arg_exp)·erfc(z)`` — here ``arg_exp < 0`` so ``exp``
      is safe, and ``erfc(z) ∈ (1,2)``.

    The branches are continuous at ``z = 0``. ``scipy.special.erfcx`` is
    machine-precision; the Rust kernel uses the identical split with a Cody
    ``erfcx`` port, so numpy↔Rust parity holds to ~1e-9 even in the extreme tail.
    """
    arg_exp = gamma * (center - x) + 0.5 * (gamma * sigma) ** 2
    z = (center + gamma * sigma * sigma - x) / (_SQRT2 * sigma)
    gauss = np.exp(-((x - center) ** 2) / (2.0 * sigma * sigma))
    pref = amplitude * 0.5 * gamma
    with np.errstate(over="ignore", invalid="ignore"):
        v = np.where(
            z >= 0.0,
            pref * gauss * erfcx(z),
            pref * np.exp(np.where(z >= 0.0, 0.0, arg_exp)) * _erfc(z),
        )
    return np.where(np.isfinite(v), v, 0.0)


def doniach_sunjic(
    x: Array, amplitude: float, center: float, sigma: float, gamma: float
) -> Array:
    """Doniach–Šunjić ``A·cos[πγ/2+(1−γ)atan(u)]/(1+u²)^((1−γ)/2)``, u=(x−c)/σ (γ = asym)."""
    u = (x - center) / sigma
    num = np.cos(0.5 * math.pi * gamma + (1.0 - gamma) * np.arctan(u))
    den = (1.0 + u * u) ** ((1.0 - gamma) / 2.0)
    return amplitude * num / den


def log_normal(x: Array, amplitude: float, center: float, sigma: float) -> Array:
    """Log-normal peak ``A·exp(−(ln(x/center))²/(2σ²))`` for ``x>0`` (else 0).

    Numerically identical to the Rust ``log_normal`` kernel (the parity oracle):
    ``amplitude`` is the peak height at ``x=center>0``, ``sigma`` the log-space width.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        val = amplitude * np.exp(-((np.log(x / center)) ** 2) / (2.0 * sigma**2))
    return np.where(x > 0.0, val, 0.0)


def pearson7(
    x: Array, amplitude: float, center: float, sigma: float, m: float
) -> Array:
    """Pearson VII ``A/[1+((x−c)/σ)²·(2^{1/m}−1)]^m``; σ = HWHM, m→1 Lorentzian, m→∞ Gaussian.

    Numerically identical to the Rust ``pearson7`` kernel (the parity oracle).
    """
    z = (x - center) / sigma
    return amplitude / (1.0 + z * z * (2.0 ** (1.0 / m) - 1.0)) ** m


def split_gaussian(
    x: Array, amplitude: float, center: float, sigma_l: float, sigma_r: float
) -> Array:
    """Split (asymmetric) Gaussian — width ``sigma_l`` for x<center, ``sigma_r`` for x≥center.

    Covers catalog #6 (asymmetric split-σ Gaussian) and #10 (bi-Gaussian) — the same
    shape. Numerically identical to the Rust ``split_gaussian`` kernel.
    """
    return np.where(
        x < center,
        amplitude * np.exp(-0.5 * ((x - center) / sigma_l) ** 2),
        amplitude * np.exp(-0.5 * ((x - center) / sigma_r) ** 2),
    )


def moffat(
    x: Array, amplitude: float, center: float, sigma: float, beta: float
) -> Array:
    """Moffat ``A/(((x−c)/σ)²+1)^β``; parity oracle for the Rust ``moffat`` kernel."""
    return amplitude / (((x - center) / sigma) ** 2 + 1.0) ** beta


def students_t(
    x: Array, amplitude: float, center: float, sigma: float, nu: float
) -> Array:
    """Student's-t ``A/(1+((x−c)/σ)²/ν)^((ν+1)/2)``; oracle for the Rust ``students_t`` kernel."""
    return amplitude / (1.0 + ((x - center) / sigma) ** 2 / nu) ** ((nu + 1.0) / 2.0)


def split_pearson7(
    x: Array,
    amplitude: float,
    center: float,
    sigma_l: float,
    sigma_r: float,
    m_l: float,
    m_r: float,
) -> Array:
    """Split Pearson VII (split width+exponent each side); oracle for the Rust kernel."""
    left = (
        amplitude
        / (1.0 + ((x - center) / sigma_l) ** 2 * (2.0 ** (1.0 / m_l) - 1.0)) ** m_l
    )
    right = (
        amplitude
        / (1.0 + ((x - center) / sigma_r) ** 2 * (2.0 ** (1.0 / m_r) - 1.0)) ** m_r
    )
    return np.where(x < center, left, right)


def breit_wigner(
    x: Array, amplitude: float, center: float, sigma: float, q: float
) -> Array:
    """Breit-Wigner-Fano ``A·(q·g+(x−c))²/(g²+(x−c)²)``, g=σ/2; oracle for the Rust kernel."""
    g = sigma / 2.0
    return amplitude * (q * g + (x - center)) ** 2 / (g * g + (x - center) ** 2)


def asym_ir(x: Array, amplitude: float, center: float, sigma: float, k: float) -> Array:
    """Asymmetric IR band ``A·G·sigmoid``; sigmoid exponent clamped to match the Rust kernel."""
    g = amplitude * np.exp(-((x - center) ** 2) / (2.0 * sigma**2))
    arg = np.clip(-k * (x - center), None, 50.0)
    return g / (1.0 + np.exp(arg))


def harmonic_ir(x: Array, amplitude: float, center: float, sigma: float) -> Array:
    """Harmonic-oscillator IR ``A/((c²−x²)²+(σ·x)²)``; oracle for the Rust ``harmonic_ir`` kernel."""
    return amplitude / ((center**2 - x**2) ** 2 + (sigma * x) ** 2)


def tauc(x: Array, amplitude: float, e_gap: float, exponent: float) -> Array:
    """Tauc band-gap edge ``A·(x−e_gap)^p`` for ``x>e_gap`` (else 0); oracle for the Rust kernel.

    Heaviside cut-off at the gap keeps the fractional power real; numerically identical
    to the Rust ``tauc`` kernel (``np.where(x>e_gap, A·(x−e_gap)^p, 0)``). Param order
    (``amplitude, e_gap, exponent``) is identical on both sides — verified against
    ``crates/spectrafit-models/src/tauc.rs::param_names`` during the C2 migration.
    """
    excess = x - e_gap
    return np.where(
        excess > 0.0,
        amplitude * np.where(excess > 0.0, excess, 1.0) ** exponent,
        0.0,
    )


def cauchy_dispersion(x: Array, a: float, b: float, c: float) -> Array:
    """Cauchy dispersion ``n(x)=a+b/x²+c/x⁴`` for ``x>0`` (else 0); oracle for the Rust kernel."""
    with np.errstate(divide="ignore", invalid="ignore"):
        val = a + b / x**2 + c / x**4
    return np.where(x > 0.0, val, 0.0)


def kww(x: Array, amplitude: float, tau: float, beta: float) -> Array:
    """KWW stretched exponential ``A·exp(−(x/τ)^β)`` for ``x≥0`` (else 0); oracle for the Rust kernel.

    The base ``x/τ`` is masked to a safe ``1.0`` where ``x<0`` so the fractional power
    never produces a NaN before ``np.where`` selects the ``0`` branch.
    """
    safe = np.where(x >= 0.0, x / tau, 1.0)
    return np.where(x >= 0.0, amplitude * np.exp(-(safe**beta)), 0.0)


def saturating_exponential(x: Array, amplitude: float, rate: float) -> Array:
    """Saturating exponential ``amplitude · (1 − exp(−rate · x))`` (BoxBOD model).

    Rises monotonically from 0 toward *amplitude* with characteristic rate *rate*.
    Numerically identical to the Rust kernel ``SaturatingExponential``.
    """
    return amplitude * (1.0 - np.exp(-rate * x))


def power_saturation(x: Array, amplitude: float, rate: float) -> Array:
    """Power-law saturation ``amplitude · (1 − (1 + rate·x/2)^(−2))`` (Misra1b model).

    Rises monotonically from 0 toward *amplitude* with characteristic rate *rate*.
    Numerically identical to the Rust kernel ``PowerSaturation``.
    """
    return amplitude * (1.0 - (1.0 + rate * x / 2.0) ** (-2.0))


def power_law_offset(x: Array, amplitude: float, offset: float, shape: float) -> Array:
    """Power-law with offset ``amplitude · (offset + x)^(−1/shape)`` (Bennett5 model).

    Numerically identical to the Rust kernel ``PowerLawOffset``.  The caller must
    ensure ``offset + x > 0`` for all data points; negative or zero arguments yield
    ``nan`` (matching the Rust domain guard).
    """
    return amplitude * (offset + x) ** (-1.0 / shape)


def mgh09_rational(
    x: Array,
    amplitude: float,
    num_lin: float,
    den_lin: float,
    den_const: float,
) -> Array:
    """Kowalik–Osborne rational function (NIST StRD MGH09 model).

    ``amplitude · (x² + num_lin·x) / (x² + den_lin·x + den_const)``

    Numerically identical to the Rust kernel ``Mgh09Rational``.  The denominator
    must be non-zero; at the MGH09 certified parameters the discriminant
    ``den_lin² − 4·den_const < 0``, ensuring D > 0 for all x.

    Param mapping to NIST b-parameters:
        amplitude = b1, num_lin = b2, den_lin = b3, den_const = b4
    """
    n = x**2 + num_lin * x
    d = x**2 + den_lin * x + den_const
    return amplitude * n / d


# --------------------------------------------------------------------------- #
# Registry record
# --------------------------------------------------------------------------- #
class PeakModel(BaseModel):
    """One registered fittable shape: formula + per-backend adapters + metadata."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True, extra="forbid")

    key: str
    """Registry key, e.g. ``"gaussian"`` (also the catalog/case ``model`` field)."""
    spectrafit_type: str
    """Name of the spectrafit ``ModelType`` enum member, e.g. ``"GAUSSIAN"``."""
    param_names: tuple[str, ...]
    """Canonical per-peak parameter names in order."""
    evaluate: Callable[..., Array]
    """``evaluate(x, **params) -> y`` numpy formula for one peak."""
    formula_latex: str = ""
    """LaTeX formula string for this model shape (compact, uses MODELS.md param names).
    Empty string for shapes without a simple closed-form (landscapes, etc.)."""
    jax_supported: bool = False
    """Whether the jax oracle implements this shape."""
    extra_defaults: dict[str, float] = {}
    """Defaults for non-amplitude/center/sigma params (e.g. ``fraction``)."""

    @model_validator(mode="after")
    def _spectrafit_type_is_known_member(self) -> "PeakModel":
        """Bind ``spectrafit_type`` to a real ``ModelType`` member at registration.

        ``spectrafit_type`` carries the enum *member name* (e.g. ``"GAUSSIAN"``,
        ``"DONIACH"``), resolved at fit time via ``getattr(ModelType, …)``. Pinning
        it to ``ModelType.__members__`` here turns a typo or a future member rename
        into a registration-time ``ValidationError`` instead of a fit-time
        ``AttributeError``.
        """
        if self.spectrafit_type not in ModelType.__members__:
            msg = (
                f"PeakModel(key={self.key!r}): spectrafit_type "
                f"{self.spectrafit_type!r} is not a ModelType member name "
                f"(expected one of {sorted(ModelType.__members__)})"
            )
            raise ValueError(msg)
        return self

    def one(self, x: Array, params: dict[str, float]) -> Array:
        """Evaluate a single peak from a param dict."""
        return self.evaluate(x, **{k: params[k] for k in self.param_names})

    def sum(self, x: Array, peaks: list[dict[str, float]]) -> Array:
        """Sum this model over a list of peak-parameter dicts (zeros if empty)."""
        out = np.zeros_like(x)
        for peak in peaks:
            out = out + self.one(x, peak)
        return out


MODEL_REGISTRY: dict[str, PeakModel] = {}


def register_model(model: PeakModel) -> PeakModel:
    """Register *model* under its key (idempotent overwrite) and return it."""
    MODEL_REGISTRY[model.key] = model
    return model


def get_model(key: str) -> PeakModel:
    """Look up a registered model by key."""
    try:
        return MODEL_REGISTRY[key]
    except KeyError:  # pragma: no cover - guarded by CaseSpec validation
        raise KeyError(
            f"unknown model {key!r}; registered: {sorted(MODEL_REGISTRY)}"
        ) from None


_PSEUDO_VOIGT = PeakModel(
    key="pseudo_voigt",
    spectrafit_type="PSEUDO_VOIGT",
    param_names=("amplitude", "center", "sigma", "fraction"),
    evaluate=pseudo_voigt,
    jax_supported=True,
    extra_defaults={"fraction": 0.5},
    formula_latex=(
        r"A\!\left[\mathrm{fraction}\cdot\frac{1}{1+\!\left(\frac{x-c}{\sigma}\right)^{\!2}}"
        r"+(1-\mathrm{fraction})\cdot e^{-\frac{(x-c)^2}{2\sigma^2}}\right]"
    ),
)

# The built-in model catalogue as pure data; `voigt` is a frozen copy of
# pseudo-Voigt (same formula/params) so the two can never silently diverge.
_BUILTIN_MODELS: tuple[PeakModel, ...] = (
    PeakModel(
        key="gaussian",
        spectrafit_type="GAUSSIAN",
        param_names=("amplitude", "center", "sigma"),
        evaluate=gaussian,
        jax_supported=True,
        formula_latex=r"A \cdot \exp\!\left(-\dfrac{(x-c)^2}{2\sigma^2}\right)",
    ),
    PeakModel(
        key="lorentzian",
        spectrafit_type="LORENTZIAN",
        param_names=("amplitude", "center", "sigma"),
        evaluate=lorentzian,
        jax_supported=True,
        formula_latex=r"\dfrac{A}{1 + \left(\dfrac{x-c}{\sigma}\right)^{\!2}}",
    ),
    _PSEUDO_VOIGT,
    _PSEUDO_VOIGT.model_copy(update={"key": "voigt", "spectrafit_type": "VOIGT"}),
    PeakModel(
        key="fano",
        spectrafit_type="FANO",
        param_names=("amplitude", "center", "gamma", "q"),
        evaluate=fano,
        formula_latex=r"A \cdot \dfrac{(q + \varepsilon)^2}{1 + \varepsilon^2},\quad \varepsilon=\dfrac{x-c}{\gamma}",
    ),
    PeakModel(
        key="constant",
        spectrafit_type="CONSTANT",
        param_names=("c",),
        evaluate=constant,
        formula_latex=r"c",
    ),
    PeakModel(
        key="linear",
        spectrafit_type="LINEAR",
        param_names=("slope", "intercept"),
        evaluate=linear,
        formula_latex=r"\mathrm{slope} \cdot x + \mathrm{intercept}",
    ),
    PeakModel(
        key="quadratic",
        spectrafit_type="QUADRATIC",
        param_names=("amplitude", "center", "offset"),
        evaluate=quadratic,
        formula_latex=r"A \cdot (x - c)^2 + \mathrm{offset}",
    ),
    PeakModel(
        key="arctan_step",
        spectrafit_type="ARCTAN_STEP",
        param_names=("amplitude", "center", "sigma"),
        evaluate=arctan_step,
        formula_latex=r"A \cdot \left(\tfrac{1}{2} + \dfrac{1}{\pi}\arctan\!\left(\dfrac{x-c}{\sigma}\right)\right)",
    ),
    PeakModel(
        key="tanh_step",
        spectrafit_type="TANH_STEP",
        param_names=("amplitude", "center", "sigma"),
        evaluate=tanh_step,
        formula_latex=r"A \cdot \left(\tfrac{1}{2} + \dfrac{1}{2}\tanh\!\left(\dfrac{x-c}{\sigma}\right)\right)",
    ),
    PeakModel(
        key="erfc_step",
        spectrafit_type="ERFC_STEP",
        param_names=("amplitude", "center", "sigma"),
        evaluate=erfc_step,
        formula_latex=r"A \cdot \dfrac{1}{2}\,\mathrm{erfc}\!\left(\dfrac{x-c}{\sigma\sqrt{2}}\right)",
    ),
    PeakModel(
        key="double_exponential",
        spectrafit_type="DOUBLE_EXPONENTIAL",
        param_names=("A1", "lam1", "A2", "lam2"),
        evaluate=double_exponential,
        formula_latex=r"A_1\,e^{-\lambda_1 x} + A_2\,e^{-\lambda_2 x}",
    ),
    PeakModel(
        key="true_voigt",
        spectrafit_type="TRUE_VOIGT",
        param_names=("amplitude", "center", "sigma", "gamma"),
        evaluate=true_voigt,
        formula_latex=(
            r"A \cdot \mathrm{Re}\!\left[W\!\left(\dfrac{x-c+i\gamma}{\sigma\sqrt{2}}\right)\right]"
            r"\,/\,\mathrm{Re}\!\left[W\!\left(\dfrac{i\gamma}{\sigma\sqrt{2}}\right)\right]"
        ),
    ),
    PeakModel(
        key="skewed_gaussian",
        spectrafit_type="SKEWED_GAUSSIAN",
        param_names=("amplitude", "center", "sigma", "gamma"),
        evaluate=skewed_gaussian,
        formula_latex=(
            r"A \cdot \exp\!\left(-\dfrac{(x-c)^2}{2\sigma^2}\right)"
            r"\cdot \left(1 + \mathrm{erf}\!\left(\dfrac{\gamma(x-c)}{\sigma\sqrt{2}}\right)\right)"
        ),
    ),
    PeakModel(
        key="exp_gaussian",
        spectrafit_type="EXP_GAUSSIAN",
        param_names=("amplitude", "center", "sigma", "gamma"),
        evaluate=exp_gaussian,
        formula_latex=(
            r"A \cdot \dfrac{\gamma}{2}\exp\!\left(\dfrac{\gamma}{2}(2c-2x+\gamma\sigma^2)\right)"
            r"\cdot\mathrm{erfc}\!\left(\dfrac{c-x+\gamma\sigma^2}{\sigma\sqrt{2}}\right)"
        ),
    ),
    PeakModel(
        key="doniach_sunjic",
        spectrafit_type="DONIACH",
        param_names=("amplitude", "center", "sigma", "gamma"),
        evaluate=doniach_sunjic,
        formula_latex=(
            r"A \cdot \dfrac{\cos\!\left(\tfrac{\pi\gamma}{2}+(1-\gamma)\arctan\!\left(\tfrac{x-c}{\sigma}\right)\right)}"
            r"{\left(1+\left(\tfrac{x-c}{\sigma}\right)^{\!2}\right)^{(1-\gamma)/2}}"
        ),
    ),
    PeakModel(
        key="log_normal",
        spectrafit_type="LOG_NORMAL",
        param_names=("amplitude", "center", "sigma"),
        evaluate=log_normal,
        jax_supported=False,
        formula_latex=(
            r"A \cdot \exp\!\left(-\dfrac{(\ln x - c)^2}{2\sigma^2}\right),\quad x>0"
        ),
    ),
    PeakModel(
        key="pearson7",
        spectrafit_type="PEARSON7",
        param_names=("amplitude", "center", "sigma", "m"),
        evaluate=pearson7,
        jax_supported=False,
        formula_latex=r"A \cdot \left(1 + \left(\dfrac{x-c}{\sigma}\right)^{\!2}\left(2^{1/m}-1\right)\right)^{\!-m}",
    ),
    PeakModel(
        key="split_gaussian",
        spectrafit_type="SPLIT_GAUSSIAN",
        param_names=("amplitude", "center", "sigma_l", "sigma_r"),
        evaluate=split_gaussian,
        jax_supported=False,
        formula_latex=(
            r"A \cdot \exp\!\left(-\dfrac{(x-c)^2}{2\sigma_{\mathrm{L/R}}^2}\right),"
            r"\quad \sigma_\mathrm{L}\text{ for }x\le c,\;\sigma_\mathrm{R}\text{ for }x>c"
        ),
    ),
    PeakModel(
        key="moffat",
        spectrafit_type="MOFFAT",
        param_names=("amplitude", "center", "sigma", "beta"),
        evaluate=moffat,
        jax_supported=False,
        formula_latex=r"A \cdot \left(1 + \left(\dfrac{x-c}{\sigma}\right)^{\!2}\right)^{\!-\beta}",
    ),
    PeakModel(
        key="students_t",
        spectrafit_type="STUDENTS_T",
        param_names=("amplitude", "center", "sigma", "nu"),
        evaluate=students_t,
        jax_supported=False,
        formula_latex=r"A \cdot \left(1 + \dfrac{(x-c)^2}{\nu\,\sigma^2}\right)^{\!-(\nu+1)/2}",
    ),
    PeakModel(
        key="split_pearson7",
        spectrafit_type="SPLIT_PEARSON7",
        param_names=("amplitude", "center", "sigma_l", "sigma_r", "m_l", "m_r"),
        evaluate=split_pearson7,
        jax_supported=False,
        formula_latex=(
            r"A \cdot \left(1+\left(\dfrac{x-c}{\sigma_{\mathrm{L/R}}}\right)^{\!2}\right)^{\!-m_{\mathrm{L/R}}},"
            r"\quad \text{L/R by side}"
        ),
    ),
    PeakModel(
        key="breit_wigner",
        spectrafit_type="BREIT_WIGNER",
        param_names=("amplitude", "center", "sigma", "q"),
        evaluate=breit_wigner,
        jax_supported=False,
        formula_latex=(
            r"A \cdot \dfrac{(q\sigma/2 + x - c)^2}{(x-c)^2 + (\sigma/2)^2}"
        ),
    ),
    PeakModel(
        key="asym_ir",
        spectrafit_type="ASYM_IR",
        param_names=("amplitude", "center", "sigma", "k"),
        evaluate=asym_ir,
        jax_supported=False,
        formula_latex=(
            r"\dfrac{A \cdot \exp\!\left(-\dfrac{(x-c)^2}{2\sigma^2}\right)}"
            r"{1+\exp\!\left(-k(x-c)\right)}"
        ),
    ),
    PeakModel(
        key="harmonic_ir",
        spectrafit_type="HARMONIC_IR",
        param_names=("amplitude", "center", "sigma"),
        evaluate=harmonic_ir,
        jax_supported=False,
        formula_latex=r"\dfrac{A}{(c^2-x^2)^2+(\sigma x)^2}",
    ),
    PeakModel(
        key="tauc",
        spectrafit_type="TAUC",
        param_names=("amplitude", "e_gap", "exponent"),
        evaluate=tauc,
        jax_supported=False,
        formula_latex=r"A \cdot (x - E_\mathrm{gap})^{\mathrm{exponent}},\quad x>E_\mathrm{gap}",
    ),
    PeakModel(
        key="cauchy_dispersion",
        spectrafit_type="CAUCHY_DISPERSION",
        param_names=("a", "b", "c"),
        evaluate=cauchy_dispersion,
        jax_supported=False,
        formula_latex=r"a + \dfrac{b}{x^2} + \dfrac{c}{x^4}",
    ),
    PeakModel(
        key="kww",
        spectrafit_type="KWW",
        param_names=("amplitude", "tau", "beta"),
        evaluate=kww,
        jax_supported=False,
        formula_latex=r"A \cdot \exp\!\left(-\left(\dfrac{x}{\tau}\right)^{\!\beta}\right),\quad x\ge 0",
    ),
    PeakModel(
        key="saturating_exponential",
        spectrafit_type="SATURATING_EXPONENTIAL",
        param_names=("amplitude", "rate"),
        evaluate=saturating_exponential,
        jax_supported=False,
        formula_latex=r"A \cdot \left(1 - e^{-k\,x}\right)",
    ),
    PeakModel(
        key="power_saturation",
        spectrafit_type="POWER_SATURATION",
        param_names=("amplitude", "rate"),
        evaluate=power_saturation,
        jax_supported=False,
        formula_latex=r"A \cdot \left(1 - \left(1 + \dfrac{k\,x}{2}\right)^{\!-2}\right)",
    ),
    PeakModel(
        key="power_law_offset",
        spectrafit_type="POWER_LAW_OFFSET",
        param_names=("amplitude", "offset", "shape"),
        evaluate=power_law_offset,
        jax_supported=False,
        formula_latex=r"A \cdot (b + x)^{-1/s}",
    ),
    PeakModel(
        key="mgh09_rational",
        spectrafit_type="MGH09_RATIONAL",
        param_names=("amplitude", "num_lin", "den_lin", "den_const"),
        evaluate=mgh09_rational,
        jax_supported=False,
        formula_latex=r"A \cdot \dfrac{x^2 + b_2\,x}{x^2 + b_3\,x + b_4}",
    ),
)


def _register_builtin_models() -> None:
    """Populate :data:`MODEL_REGISTRY` from the built-in catalogue (idempotent)."""
    for model in _BUILTIN_MODELS:
        register_model(model)


_register_builtin_models()


# Registry keys whose Rust wheel kernel must stay numerically identical to the
# numpy ``evaluate`` body (the 29 MIGRATE-classified kernels of the C2 study).
_WHEEL_PARITY_KEYS: tuple[str, ...] = (
    "gaussian",
    "lorentzian",
    "pseudo_voigt",
    "voigt",
    "fano",
    "constant",
    "linear",
    "quadratic",
    "arctan_step",
    "tanh_step",
    "erfc_step",
    "double_exponential",
    "true_voigt",
    "skewed_gaussian",
    "exp_gaussian",
    "doniach_sunjic",
    "log_normal",
    "pearson7",
    "split_gaussian",
    "moffat",
    "students_t",
    "split_pearson7",
    "breit_wigner",
    "asym_ir",
    "harmonic_ir",
    "tauc",
    "cauchy_dispersion",
    "kww",
    "saturating_exponential",
    "power_saturation",
    "power_law_offset",
    "mgh09_rational",
)


def wheel_parity_pairs() -> list[tuple[str, "PeakModel"]]:
    """(wheel_key, model) pairs for the 29 MIGRATE-classified kernels.

    The numpy ``evaluate`` bodies ARE the timing-fair oracle implementations
    (lmfit / scipy-ls introspect and call them inside their timed fit loops —
    they must never pay wheel/JSON overhead). Parity with the Rust kernels is
    enforced by tests/unit/oracles/test_wheel_eval.py via ``_wheel_eval``,
    NOT by routing the hot path through the wheel. See DECISIONS.md
    [2026-06-10] benchmark-fairness revert.

    ``voigt`` is a frozen copy of ``pseudo_voigt`` on the Python side, so it
    maps to the ``pseudo_voigt`` wheel key here (the dedicated ``voigt`` Rust
    kernel is cross-checked separately in the parity test).
    """
    return [
        ("pseudo_voigt" if key == "voigt" else key, MODEL_REGISTRY[key])
        for key in _WHEEL_PARITY_KEYS
    ]


# --------------------------------------------------------------------------- #
# Optimization landscapes — moved to oracles.opt_func (separation of concerns).
# Re-exported here for backward compatibility; all consumers using
# ``models.LANDSCAPE_REGISTRY``, ``models.get_landscape``, or
# ``models.landscape`` continue to work unchanged.
# --------------------------------------------------------------------------- #
from oracles.opt_func import (  # noqa: F401, E402
    LANDSCAPE_REGISTRY,
    get_landscape,
    landscape,
)
