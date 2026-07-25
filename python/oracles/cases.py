"""Declarative, pydantic-first benchmark catalog — typed component graphs.

A case is a **graph of components** (like spectrafit's ``FitGraph``): each component
is a *typed* spec (Gaussian, Lorentzian, Voigt, Fano, background, edge, decay) with
its own validated fields — no untyped param dicts. The components form a discriminated
union keyed by ``model``; ``.to_params()`` produces the name→value dict only at the
Rust-kernel boundary. This exercises the full model-kernel space, not just Gaussians.

Layers:
- typed :class:`Component` specs + :class:`CaseSpec` — serializable case *data*.
- :class:`CaseFamily` — declarative generators that expand into many concrete specs.
- :class:`BenchCase` — the materialized spec (numpy ``x``/``y`` + truth/guess
  components), built by :func:`materialize`.

Category counts: single source of truth in :data:`CATEGORY_COUNTS`.
"""

from __future__ import annotations

import random
import zlib
from collections.abc import Callable, Sequence
from typing import Annotated, Literal, cast

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from oracles import models
from oracles.contract import SolverMeta
from oracles.models import Array, get_model


class CategoryDef(BaseModel):
    """One validated record per suite category — the single source of category truth.

    Replaces the four parallel dicts (counts/labels/prefix/hue) keyed by the same
    strings: a missing key in one of those silently became a runtime ``KeyError`` in
    ``engine._CATEGORY_META``. The derived dicts below project this registry, so the
    public names stay backward-compatible while drift is structurally impossible.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    prefix: str
    hue: str
    count: int = Field(ge=0)


# Single source of truth: one CategoryDef per category. Adding the next category is a
# record here, not edits across four dicts. (The genuine 2-D example lives in the
# featured `MultiDim` payload, not a suite category — see engine._multidim.)
CATEGORY_REGISTRY: dict[str, CategoryDef] = {
    c.id: c
    for c in (
        # Counts are diversity-driven (one case per distinct model × condition), NOT
        # padded targets — they equal the generator grid lengths (asserted in tests).
        CategoryDef(id="easy", label="Easy", prefix="EZ", hue="var(--ok)", count=20),
        CategoryDef(
            id="complex", label="Complex", prefix="CX", hue="var(--accent)", count=35
        ),
        CategoryDef(
            id="reality", label="Reality-like", prefix="RL", hue="var(--warn)", count=16
        ),
        CategoryDef(
            id="optfn",
            label="Optimization fns",
            prefix="OF",
            hue="var(--c-guess)",
            count=20,
        ),
        # 1-D many-peak large-N stress family.
        CategoryDef(
            id="scaling",
            label="Large-N scaling",
            prefix="SC",
            hue="var(--c-jax)",
            count=8,
        ),
        # Ill-conditioned LM regimes: degenerate Jacobians, near-equal widths, heavy
        # noise, mixed-shape blends, decade-spanning amplitude ratios.
        CategoryDef(
            id="edge",
            label="Edge / ill-conditioned",
            prefix="ED",
            hue="var(--bad)",
            count=20,
        ),
        # Asymmetric / true-Voigt lineshapes: true Voigt (Faddeeva), skewed Gaussian,
        # EMG, Doniach–Šunjić; plus XPS doublets, XAS L-edge L3/L2, XANES K-edge.
        CategoryDef(
            id="lineshapes",
            label="Asymmetric lineshapes",
            prefix="LS",
            hue="var(--c-lmfit)",
            count=24,
        ),
        # Fixed/shrunk-parameter cases: realistic "I know the center, fit the rest"
        # scenario where some parameters are held fixed at truth.
        CategoryDef(
            id="fixed",
            label="Fixed-param",
            prefix="FX",
            hue="var(--c-spectrafit)",
            count=4,
        ),
        # Tied/shared-parameter cases: two peaks with shared σ, tied centers, or
        # shared fraction — expressed via expr_edges. spectrafit + lmfit only.
        CategoryDef(
            id="tied",
            label="Tied/shared-param",
            prefix="TI",
            hue="var(--c-jax)",
            count=4,
        ),
    )
}

# Backward-compatible projections — engine.py / synth.py import these names unchanged.
# Derive, never duplicate: a new CATEGORY_REGISTRY record propagates to all four.
CATEGORY_COUNTS: dict[str, int] = {cid: c.count for cid, c in CATEGORY_REGISTRY.items()}
CATEGORY_LABELS: dict[str, str] = {cid: c.label for cid, c in CATEGORY_REGISTRY.items()}
PREFIX: dict[str, str] = {cid: c.prefix for cid, c in CATEGORY_REGISTRY.items()}
CATEGORY_HUE: dict[str, str] = {cid: c.hue for cid, c in CATEGORY_REGISTRY.items()}

# Catalog presentation metadata — the single home for solver styling. engine.py and
# synth.py import this rather than redefining it (silent drift between two copies is
# worse than a shared import).
SOLVER_META = [
    SolverMeta(
        id="spectrafit",
        label="spectrafit",
        color="var(--c-spectrafit)",
        soft="var(--c-spectrafit-soft)",
    ),
    SolverMeta(
        id="lmfit", label="lmfit", color="var(--c-lmfit)", soft="var(--c-lmfit-soft)"
    ),
    SolverMeta(id="jax", label="jax", color="var(--c-jax)", soft="var(--c-jax-soft)"),
    # scipy.optimize.least_squares — three solver-meta entries from one driver
    # (see backends/_scipy_ls.py). `lm` is the MINPACK clone (sanity); `trf` and
    # `dogbox` are independent trust-region voices. Color tokens fall back to
    # the canonical 3 in the web theme until a follow-up adds scipy-ls-specific
    # OKLCH hues — labels still render correctly via SolverMeta.label.
    SolverMeta(
        id="scipy-ls-lm",
        label="scipy-ls-lm",
        color="var(--c-scipy-ls-lm, var(--c-lmfit))",
        soft="var(--c-scipy-ls-lm-soft, var(--c-lmfit-soft))",
    ),
    SolverMeta(
        id="scipy-ls-trf",
        label="scipy-ls-trf",
        color="var(--c-scipy-ls-trf, var(--c-lmfit))",
        soft="var(--c-scipy-ls-trf-soft, var(--c-lmfit-soft))",
    ),
    SolverMeta(
        id="scipy-ls-dogbox",
        label="scipy-ls-dogbox",
        color="var(--c-scipy-ls-dogbox, var(--c-lmfit))",
        soft="var(--c-scipy-ls-dogbox-soft, var(--c-lmfit-soft))",
    ),
]

# Shape-defining params scored for recovery (slope/intercept/offset/c/fraction/q/lam
# are fit but not part of the error metric).
RECOVERABLE_PARAMS = ("amplitude", "center", "sigma", "gamma")


# --------------------------------------------------------------------------- #
# Typed component specs (discriminated union on `model`)
# --------------------------------------------------------------------------- #
class _Component(BaseModel):
    """Base for a typed graph component; ``to_params`` is the kernel-boundary dict."""

    model_config = ConfigDict(extra="forbid")

    def to_params(self) -> dict[str, float]:
        """Name→value parameter dict for the model kernel (excludes the discriminator)."""
        return self.model_dump(exclude={"model"})


class GaussianSpec(_Component):
    """Gaussian peak."""

    model: Literal["gaussian"] = "gaussian"
    amplitude: float
    center: float
    sigma: float


class LorentzianSpec(_Component):
    """Lorentzian peak."""

    model: Literal["lorentzian"] = "lorentzian"
    amplitude: float
    center: float
    sigma: float


class PseudoVoigtSpec(_Component):
    """Pseudo-Voigt / Voigt peak (Voigt is the spectrafit alias, same formula)."""

    model: Literal["pseudo_voigt", "voigt"] = "pseudo_voigt"
    amplitude: float
    center: float
    sigma: float
    fraction: float


class FanoSpec(_Component):
    """Fano resonance."""

    model: Literal["fano"] = "fano"
    amplitude: float
    center: float
    gamma: float
    q: float


class ConstantSpec(_Component):
    """Constant background."""

    model: Literal["constant"] = "constant"
    c: float


class LinearSpec(_Component):
    """Linear background."""

    model: Literal["linear"] = "linear"
    slope: float
    intercept: float


class QuadraticSpec(_Component):
    """Quadratic background / bowl."""

    model: Literal["quadratic"] = "quadratic"
    amplitude: float
    center: float
    offset: float


class StepSpec(_Component):
    """Edge/step background (arctan / tanh / erfc)."""

    model: Literal["arctan_step", "tanh_step", "erfc_step"]
    amplitude: float
    center: float
    sigma: float


class DecaySpec(_Component):
    """Bi-exponential decay."""

    model: Literal["double_exponential"] = "double_exponential"
    A1: float
    lam1: float
    A2: float
    lam2: float


class AsymPeakSpec(_Component):
    """Asymmetric / true-Voigt peak — all four share ``(amplitude, center, sigma, gamma)``.

    ``true_voigt`` (Faddeeva), ``skewed_gaussian``, ``exp_gaussian`` (EMG), and
    ``doniach_sunjic`` (XPS) carry a single nonlinear shape param ``gamma`` (Lorentzian
    HWHM / skew / decay-rate / asymmetry respectively).
    """

    model: Literal["true_voigt", "skewed_gaussian", "exp_gaussian", "doniach_sunjic"]
    amplitude: float
    center: float
    sigma: float
    gamma: float


class LogNormalSpec(_Component):
    """Log-normal peak (positive-axis, chromatography/particle-size style)."""

    model: Literal["log_normal"] = "log_normal"
    amplitude: float
    center: float
    sigma: float


class Pearson7Spec(_Component):
    """Pearson VII peak (tunable tail weight ``m``: m→1 Lorentzian, m→∞ Gaussian)."""

    model: Literal["pearson7"] = "pearson7"
    amplitude: float
    center: float
    sigma: float
    m: float


class SplitGaussianSpec(_Component):
    """Split (asymmetric) Gaussian — a different width each side (a.k.a. bi-Gaussian)."""

    model: Literal["split_gaussian"] = "split_gaussian"
    amplitude: float
    center: float
    sigma_l: float
    sigma_r: float


class MoffatSpec(_Component):
    """Moffat peak (β tail weight)."""

    model: Literal["moffat"] = "moffat"
    amplitude: float
    center: float
    sigma: float
    beta: float


class StudentsTSpec(_Component):
    """Student's-t peak (ν degrees of freedom)."""

    model: Literal["students_t"] = "students_t"
    amplitude: float
    center: float
    sigma: float
    nu: float


class SplitPearson7Spec(_Component):
    """Split Pearson VII (split width + exponent each side)."""

    model: Literal["split_pearson7"] = "split_pearson7"
    amplitude: float
    center: float
    sigma_l: float
    sigma_r: float
    m_l: float
    m_r: float


class BreitWignerSpec(_Component):
    """Breit-Wigner-Fano resonance."""

    model: Literal["breit_wigner"] = "breit_wigner"
    amplitude: float
    center: float
    sigma: float
    q: float


class AsymIrSpec(_Component):
    """Asymmetric IR band (Gaussian × logistic sigmoid)."""

    model: Literal["asym_ir"] = "asym_ir"
    amplitude: float
    center: float
    sigma: float
    k: float


class HarmonicIrSpec(_Component):
    """Driven damped harmonic-oscillator IR absorption."""

    model: Literal["harmonic_ir"] = "harmonic_ir"
    amplitude: float
    center: float
    sigma: float


class TaucSpec(_Component):
    """Tauc optical band-gap edge (power-law absorption above ``e_gap``)."""

    model: Literal["tauc"] = "tauc"
    amplitude: float
    e_gap: float
    exponent: float


class CauchyDispersionSpec(_Component):
    """Cauchy refractive-index dispersion ``a + b/x² + c/x⁴`` (positive-x)."""

    model: Literal["cauchy_dispersion"] = "cauchy_dispersion"
    a: float
    b: float
    c: float


class KwwSpec(_Component):
    """Kohlrausch–Williams–Watts stretched exponential (positive-x relaxation)."""

    model: Literal["kww"] = "kww"
    amplitude: float
    tau: float
    beta: float


class SaturatingExponentialSpec(_Component):
    """Saturating exponential ``amplitude·(1−exp(−rate·x))`` (NIST BoxBOD, positive-x)."""

    model: Literal["saturating_exponential"] = "saturating_exponential"
    amplitude: float
    rate: float


class PowerSaturationSpec(_Component):
    """Power-law saturation ``amplitude·(1−(1+rate·x/2)^(−2))`` (NIST Misra1b, positive-x)."""

    model: Literal["power_saturation"] = "power_saturation"
    amplitude: float
    rate: float


class PowerLawOffsetSpec(_Component):
    """Power-law with offset ``amplitude·(offset+x)^(−1/shape)`` (Bennett5-like, positive-x).

    Requires ``offset + x > 0`` on the grid — kept safe by a positive x-range plus an
    ``offset`` comfortably larger than ``|x_min|`` (mirrors the parity-test guard).
    """

    model: Literal["power_law_offset"] = "power_law_offset"
    amplitude: float
    offset: float
    shape: float


class Mgh09RationalSpec(_Component):
    """Kowalik–Osborne rational function (NIST StRD MGH09, positive-x).

    ``amplitude·(x²+num_lin·x)/(x²+den_lin·x+den_const)``; the denominator stays
    positive when ``den_lin²−4·den_const < 0`` (mirrors the parity-test param values).
    """

    model: Literal["mgh09_rational"] = "mgh09_rational"
    amplitude: float
    num_lin: float
    den_lin: float
    den_const: float


Component = Annotated[
    GaussianSpec
    | LorentzianSpec
    | PseudoVoigtSpec
    | FanoSpec
    | ConstantSpec
    | LinearSpec
    | QuadraticSpec
    | StepSpec
    | DecaySpec
    | AsymPeakSpec
    | LogNormalSpec
    | Pearson7Spec
    | SplitGaussianSpec
    | MoffatSpec
    | StudentsTSpec
    | SplitPearson7Spec
    | BreitWignerSpec
    | AsymIrSpec
    | HarmonicIrSpec
    | TaucSpec
    | CauchyDispersionSpec
    | KwwSpec
    | SaturatingExponentialSpec
    | PowerSaturationSpec
    | PowerLawOffsetSpec
    | Mgh09RationalSpec,
    Field(discriminator="model"),
]


# --------------------------------------------------------------------------- #
# Declarative case data
# --------------------------------------------------------------------------- #
class CaseSpec(BaseModel):
    """A fully concrete, serializable benchmark-case declaration."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    category: str
    difficulty: float = Field(ge=0.0, le=1.0)
    components: list[Component]
    x_min: float
    x_max: float
    n_points: int
    noise: float
    guess_scale: float = 0.1
    solver_hint: str = "lm"
    recover: bool = True
    featured: bool = False
    landscape: str | None = None
    condition: str | None = None
    """Qualitative scenario tag (e.g. ``"gaussian/noisy"``). The anti-padding invariant
    is: no two cases in a category share ``(frozenset(model keys), condition)``."""
    fixed_params: dict[str, list[str]] = Field(default_factory=dict)
    """Per-node fixed parameter names: ``{"p0": ["center"]}`` means the center of
    node p0 is held fixed at its guess value during the fit.  Empty for all existing
    cases (backward-compatible default)."""
    expr_edges: list[dict[str, str]] = Field(default_factory=list)
    """Expression-constraint edges in serialised form:
    ``[{"target_node": "p1", "target_param": "sigma", "expression": "p0.sigma"}]``.
    Empty for all existing cases.  Used by the spectrafit and lmfit backends to
    express tied/shared parameters; backends that cannot express ties (jax, scipy-ls)
    gate on ``bool(spec.expr_edges)`` in ``is_supported``."""


class BenchCase(BaseModel):
    """A materialized case: spec + generated data + truth/guess components."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True, extra="forbid")

    spec: CaseSpec
    x: Array
    y: Array
    comp_true: list[Component]
    comp_guess: list[Component]

    @property
    def id(self) -> str:  # noqa: A003
        """Case id."""
        return self.spec.id

    @property
    def name(self) -> str:
        """Human-readable case name."""
        return self.spec.name

    @property
    def category(self) -> str:
        """Category id."""
        return self.spec.category

    @property
    def difficulty(self) -> float:
        """Difficulty in [0, 1]."""
        return self.spec.difficulty

    @property
    def solver_hint(self) -> str:
        """Solver key passed to spectrafit."""
        return self.spec.solver_hint

    @property
    def recover(self) -> bool:
        """Whether parameter recovery is meaningful for this case."""
        return self.spec.recover

    @property
    def featured(self) -> bool:
        """Whether this is the featured case."""
        return self.spec.featured

    @property
    def n_components(self) -> int:
        """Number of graph components."""
        return len(self.comp_true)

    @property
    def n_peaks(self) -> int:
        """Alias for component count (the featured case is all-Gaussian peaks)."""
        return len(self.comp_true)

    @property
    def true_params(self) -> dict[str, float]:
        """Truth parameters keyed by dotted ``p{i}.param`` (graph order)."""
        return {
            f"p{i}.{k}": v
            for i, c in enumerate(self.comp_true)
            for k, v in c.to_params().items()
        }


# --------------------------------------------------------------------------- #
# Typed component generators
# --------------------------------------------------------------------------- #
def _binned_centers(rng: random.Random, n: int, lo: float, hi: float) -> list[float]:
    """One jittered center per equal bin so peaks stay resolvable."""
    step = (hi - lo) / n
    return [
        round(lo + step * (i + 0.5) + rng.uniform(-0.25, 0.25) * step, 3)
        for i in range(n)
    ]


def _peak(rng: random.Random, model: str, center: float, sigma_cap: float) -> Component:
    """Build a typed peak component of *model* at *center*."""
    amp = round(rng.uniform(1.0, 6.0), 3)
    width = round(rng.uniform(0.4, max(0.45, sigma_cap)), 3)
    match model:
        case "gaussian":
            return GaussianSpec(amplitude=amp, center=center, sigma=width)
        case "lorentzian":
            return LorentzianSpec(amplitude=amp, center=center, sigma=width)
        case "pseudo_voigt" | "voigt":
            return PseudoVoigtSpec(
                model=cast(Literal["pseudo_voigt", "voigt"], model),
                amplitude=amp,
                center=center,
                sigma=width,
                fraction=round(rng.uniform(0.3, 0.7), 3),
            )
        case "fano":
            return FanoSpec(
                amplitude=amp,
                center=center,
                gamma=width,
                q=round(rng.uniform(0.6, 2.4), 3),
            )
        case "true_voigt" | "skewed_gaussian" | "exp_gaussian" | "doniach_sunjic":
            # Asymmetric / true-Voigt shapes carry a model-appropriate `gamma`.
            return _asym(rng, model, amp, center, width)
        case "pearson7":
            return Pearson7Spec(
                amplitude=amp,
                center=center,
                sigma=width,
                m=round(rng.uniform(1.2, 4.0), 3),
            )
        case _:  # pragma: no cover - generator passes known keys
            raise ValueError(f"not a peak model: {model!r}")


def _peaks(
    rng: random.Random, model: str, n: int, lo: float, hi: float
) -> list[Component]:
    step = (hi - lo) / n
    return [_peak(rng, model, c, 0.45 * step) for c in _binned_centers(rng, n, lo, hi)]


def _linear_bg(rng: random.Random) -> Component:
    return LinearSpec(
        slope=round(rng.uniform(-0.08, 0.08), 4),
        intercept=round(rng.uniform(0.0, 0.8), 3),
    )


def _constant_bg(rng: random.Random) -> Component:
    return ConstantSpec(c=round(rng.uniform(0.1, 0.8), 3))


def _quadratic_bg(rng: random.Random, center: float) -> Component:
    return QuadraticSpec(
        amplitude=round(rng.uniform(0.01, 0.06), 4),
        center=round(center, 3),
        offset=round(rng.uniform(0.0, 0.6), 3),
    )


def _edge(
    rng: random.Random,
    model: Literal["arctan_step", "tanh_step", "erfc_step"],
    center: float,
) -> Component:
    return StepSpec(
        model=model,
        amplitude=round(rng.uniform(2.0, 5.0), 3),
        center=round(center, 3),
        sigma=round(rng.uniform(0.5, 1.5), 3),
    )


def _decay(rng: random.Random) -> Component:
    return DecaySpec(
        A1=round(rng.uniform(2.0, 5.0), 3),
        lam1=round(rng.uniform(0.4, 1.0), 3),
        A2=round(rng.uniform(1.0, 3.0), 3),
        lam2=round(rng.uniform(0.05, 0.3), 3),
    )


# --------------------------------------------------------------------------- #
# Declarative family generator
# --------------------------------------------------------------------------- #
class CaseFamily(BaseModel):
    """Declarative generator: expands into ``count`` concrete :class:`CaseSpec`s."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    category: str
    count: int
    compose: Callable[[random.Random, int], tuple[list[Component], dict]]
    x_range: tuple[float, float] = (-6.0, 6.0)
    n_points: int = 160
    noise: float = 0.03
    difficulty: tuple[float, float] = (0.1, 0.4)
    guess_scale: float = 0.1
    solver_hint: str = "lm"
    name_template: str = "{k}"
    points_scale_per_block: bool = False

    def expand(self, rng: random.Random) -> list[CaseSpec]:
        """Deterministically expand into concrete case specs."""
        specs: list[CaseSpec] = []
        for k in range(self.count):
            components, meta = self.compose(rng, k)
            n_points = (
                self.n_points * (1 + k // 6)
                if self.points_scale_per_block
                else self.n_points
            )
            xr = meta.get("x_range", self.x_range)
            specs.append(
                CaseSpec(
                    id=f"{PREFIX[self.category]}-{k + 1:03d}",
                    name=self.name_template.format(k=k + 1, **meta),
                    category=self.category,
                    difficulty=round(rng.uniform(*self.difficulty), 3),
                    components=components,
                    x_min=xr[0],
                    x_max=xr[1],
                    n_points=n_points,
                    noise=meta.get("noise", self.noise),
                    guess_scale=self.guess_scale,
                    solver_hint=meta.get("solver_hint", self.solver_hint),
                    recover=meta.get("recover", True),
                    landscape=meta.get("landscape"),
                    condition=meta.get("condition"),
                    fixed_params=meta.get("fixed_params", {}),
                    expr_edges=meta.get("expr_edges", []),
                )
            )
        return specs


# --------------------------------------------------------------------------- #
# Category recipes
# --------------------------------------------------------------------------- #
_EASY_MODELS = ["gaussian", "lorentzian", "pseudo_voigt", "voigt"]
# "Complex" = genuinely hard shapes (asymmetric / true-Voigt / Fano), NOT the trivial
# single-Gaussian family — those belong in `easy`. Blends of these stress the solver.
_COMPLEX_MODELS = [
    "pseudo_voigt",
    "true_voigt",
    "skewed_gaussian",
    "exp_gaussian",
    "doniach_sunjic",
    "fano",
    "pearson7",
]
_REALITY_RECIPES = [
    "xps",
    "raman",
    "uvvis",
    "xas",
    "ir",
    "decay",
    "fano_xps",
    "lognorm",
]
# All registered optimization landscapes (derived — adding one to LANDSCAPE_REGISTRY
# grows optfn by exactly one unique case, no padding).
_LANDSCAPES = list(models.LANDSCAPE_REGISTRY)

# Diversity-driven generation: every case is a distinct (model-set × qualitative
# condition); `count` is DERIVED from these grids (see FAMILIES / CATEGORY_REGISTRY),
# so a category can never silently grow into N× repeats of the same shape. The
# `condition` tag is carried onto CaseSpec and the anti-padding test asserts uniqueness.

# EASY: one peak shape under a qualitative condition (tag, noise, σ-scale, amplitude).
_EASY_CONDITIONS: list[tuple[str, float, float, float]] = [
    ("clean", 0.01, 1.0, 5.0),
    ("noisy", 0.08, 1.0, 5.0),
    ("broad", 0.02, 1.8, 4.0),
    ("narrow", 0.02, 0.5, 6.0),
    ("faint", 0.04, 1.0, 1.5),
]
_EASY_GRID: list[tuple[str, tuple[str, float, float, float]]] = [
    (m, cond) for m in _EASY_MODELS for cond in _EASY_CONDITIONS
]
# COMPLEX: each (model × peak-count) blend exactly once.
_COMPLEX_GRID: list[tuple[str, int]] = [
    (m, n) for m in _COMPLEX_MODELS for n in (2, 3, 4, 5, 6)
]
# REALITY: each recipe under a low / high noise variant.
_REALITY_GRID: list[tuple[str, int]] = [
    (r, v) for r in _REALITY_RECIPES for v in (0, 1)
]
# SCALING: peak count × noise level (the repetition axis is explicit, not padding).
_SCALING_GRID: list[tuple[int, str]] = [
    (n, lvl) for n in (5, 8, 11, 14) for lvl in ("lo", "hi")
]


def _easy(rng: random.Random, k: int) -> tuple[list[Component], dict]:
    model, (tag, noise, swid, amp) = _EASY_GRID[k]
    center = round(rng.uniform(-1.0, 1.0), 3)
    peak = _typed_peak(
        model, amp, center, round(0.8 * swid, 3), fraction=rng.uniform(0.3, 0.7)
    )
    return [peak], {
        "name": f"single {model} · {tag}",
        "condition": f"{model}/{tag}",
        "noise": noise,
    }


def _complex(rng: random.Random, k: int) -> tuple[list[Component], dict]:
    model, n = _COMPLEX_GRID[k]
    return _peaks(rng, model, n, -6.5, 6.5), {
        "name": f"{n}-{model} blend",
        "condition": f"{model}/{n}p",
    }


def _reality_recipe(
    rng: random.Random, recipe: str, v: int
) -> tuple[list[Component], str, dict]:
    """One reality scenario → (components, name, extra-meta). ``v`` is a 0/1 variant."""
    match recipe:
        case "xps":
            return (
                [*_peaks(rng, "voigt", 2 + v, -4.0, 4.0), _linear_bg(rng)],
                "XPS core-level (voigt + linear bg)",
                {},
            )
        case "raman":
            return (
                [*_peaks(rng, "lorentzian", 3 + v, -5.0, 5.0), _constant_bg(rng)],
                "Raman fingerprint (lorentzians + bg)",
                {},
            )
        case "uvvis":
            bg = _quadratic_bg(rng, 0.0) if v else _linear_bg(rng)
            return (
                [*_peaks(rng, "gaussian", 2 + v, -4.0, 4.0), bg],
                "UV-Vis bands (gaussians + poly bg)",
                {},
            )
        case "xas":
            edge = _edge(
                rng, "arctan_step" if v else "erfc_step", rng.uniform(-1.0, 1.0)
            )
            return (
                [edge, *_peaks(rng, "gaussian", 2 + v, -3.5, 3.5)],
                "XAS edge (step + gaussians)",
                {},
            )
        case "ir":
            return (
                [*_peaks(rng, "pseudo_voigt", 3 + v, -5.0, 5.0), _linear_bg(rng)],
                "IR amide (pseudo-voigt + bg)",
                {},
            )
        case "decay":
            return (
                [_decay(rng)],
                "time-resolved decay (bi-exponential)",
                {"x_range": (0.0, 10.0)},
            )
        case "lognorm":
            n = 1 + v
            peaks = [
                LogNormalSpec(
                    amplitude=round(rng.uniform(3.0, 6.0), 3),
                    center=round(rng.uniform(2.5, 8.0), 3),
                    sigma=round(rng.uniform(0.2, 0.5), 3),
                )
                for _ in range(n)
            ]
            return (
                [*peaks, _constant_bg(rng)],
                "chromatography (log-normal peaks)",
                {"x_range": (0.2, 12.0)},
            )
        case _:  # fano_xps
            return (
                [*_peaks(rng, "fano", 1 + v, -3.0, 3.0), _linear_bg(rng)],
                "Fano resonance (fano + linear bg)",
                {},
            )


def _reality(rng: random.Random, k: int) -> tuple[list[Component], dict]:
    recipe, v = _REALITY_GRID[k]
    comps, name, extra = _reality_recipe(rng, recipe, v)
    return comps, {
        "name": f"{name} · {'lo' if v == 0 else 'hi'} noise",
        "condition": f"{recipe}/v{v}",
        "noise": 0.03 if v == 0 else 0.06,
        **extra,
    }


def _optfn(_rng: random.Random, k: int) -> tuple[list[Component], dict]:
    fn = _LANDSCAPES[k]  # one case per registered landscape — no cycling
    # Multimodal target fit by a 2-Gaussian surrogate from a far start.
    comps: list[Component] = [
        GaussianSpec(amplitude=4.0, center=0.0, sigma=1.0),
        GaussianSpec(amplitude=2.0, center=0.0, sigma=2.0),
    ]
    return comps, {
        "name": f"{fn} multimodal trap",
        "condition": fn,
        "landscape": fn,
        "solver_hint": "global",
        "recover": False,
        "noise": 0.0,
        "x_range": (-5.0, 5.0),
    }


def _scaling(rng: random.Random, k: int) -> tuple[list[Component], dict]:
    """1-D many-peak, large-N stress case (runtime/accuracy scaling), not 2-D."""
    n, lvl = _SCALING_GRID[k]
    return _peaks(rng, "gaussian", n, -9.0, 9.0), {
        "name": f"{n}-peak × large-N ({lvl} noise)",
        "condition": f"{n}p/{lvl}",
        "noise": 0.02 if lvl == "lo" else 0.06,
        "x_range": (-10.0, 10.0),
    }


# --------------------------------------------------------------------------- #
# Edge / ill-conditioned recipes
# --------------------------------------------------------------------------- #
# Hard regimes real LM solvers disagree on. Each recipe is *data*: a first-class
# difficulty axis (overlap fraction, width ratio, SNR, amplitude decades) drives the
# component geometry, so a new hard case is a tuned knob, not a new code path.
_EDGE_REGIMES = ["doublet", "near_widths", "high_noise", "mixed_blend", "amp_decades"]
_EDGE_PEAK_SHAPES = ["gaussian", "lorentzian", "pseudo_voigt", "voigt"]


def _typed_peak(
    model: str, amp: float, center: float, width: float, fraction: float = 0.5
) -> Component:
    """One typed peak from explicit geometry (no rng) — the edge knobs set everything."""
    match model:
        case "gaussian":
            return GaussianSpec(
                amplitude=round(amp, 3), center=round(center, 3), sigma=round(width, 3)
            )
        case "lorentzian":
            return LorentzianSpec(
                amplitude=round(amp, 3), center=round(center, 3), sigma=round(width, 3)
            )
        case "pseudo_voigt" | "voigt":
            return PseudoVoigtSpec(
                model=cast(Literal["pseudo_voigt", "voigt"], model),
                amplitude=round(amp, 3),
                center=round(center, 3),
                sigma=round(width, 3),
                fraction=round(fraction, 3),
            )
        case _:  # pragma: no cover - generator passes known keys
            raise ValueError(f"not an edge peak model: {model!r}")


def _edge_doublet(rng: random.Random, k: int) -> tuple[list[Component], dict]:
    """Overlapping doublet: two peaks within ~`overlap`·sigma → degenerate Jacobian."""
    shape = _EDGE_PEAK_SHAPES[k % len(_EDGE_PEAK_SHAPES)]
    sigma = round(rng.uniform(0.7, 1.1), 3)
    overlap = round(
        rng.uniform(0.35, 1.0), 3
    )  # separation in units of sigma (< ~1 ⇒ degenerate)
    half = overlap * sigma / 2.0
    a1 = round(rng.uniform(3.0, 6.0), 3)
    a2 = round(
        a1 * rng.uniform(0.6, 1.0), 3
    )  # comparable heights worsen the degeneracy
    comps = [
        _typed_peak(shape, a1, -half, sigma, fraction=rng.uniform(0.3, 0.7)),
        _typed_peak(shape, a2, +half, sigma, fraction=rng.uniform(0.3, 0.7)),
    ]
    return comps, {
        "name": f"overlapping {shape} doublet (Δ={overlap:.2f}σ)",
        "noise": round(rng.uniform(0.02, 0.05), 3),
        "x_range": (-5.0, 5.0),
    }


def _edge_near_widths(rng: random.Random, k: int) -> tuple[list[Component], dict]:
    """Near-degenerate widths: 3 well-separated peaks with almost-equal sigma."""
    shape = _EDGE_PEAK_SHAPES[k % len(_EDGE_PEAK_SHAPES)]
    base = round(rng.uniform(0.7, 1.0), 3)
    spread = round(
        rng.uniform(0.005, 0.04), 4
    )  # fractional width spread (tiny ⇒ ill-posed)
    centers = [-3.0, 0.0, 3.0]
    comps = [
        _typed_peak(
            shape,
            round(rng.uniform(3.0, 6.0), 3),
            c,
            base * (1.0 + spread * (j - 1)),
            fraction=rng.uniform(0.3, 0.7),
        )
        for j, c in enumerate(centers)
    ]
    return comps, {
        "name": f"near-equal-width {shape} triplet (±{spread:.1%})",
        "noise": round(rng.uniform(0.02, 0.05), 3),
        "x_range": (-6.0, 6.0),
    }


def _edge_high_noise(rng: random.Random, k: int) -> tuple[list[Component], dict]:
    """High noise: SNR-limited single/double peak (noise 0.2–0.5 vs suite max 0.06)."""
    shape = _EDGE_PEAK_SHAPES[k % len(_EDGE_PEAK_SHAPES)]
    n = 1 + (k % 2)
    noise = round(rng.uniform(0.2, 0.5), 3)
    centers = [0.0] if n == 1 else [-2.0, 2.0]
    comps = [
        _typed_peak(
            shape,
            round(rng.uniform(3.0, 6.0), 3),
            c,
            round(rng.uniform(0.6, 1.1), 3),
            fraction=rng.uniform(0.3, 0.7),
        )
        for c in centers
    ]
    return comps, {
        "name": f"high-noise {shape} (σ_n={noise:.2f})",
        "noise": noise,
        "x_range": (-5.0, 5.0),
    }


def _edge_mixed_blend(rng: random.Random, _k: int) -> tuple[list[Component], dict]:
    """Mixed-shape blend: gaussian + lorentzian + pseudo-voigt in ONE spectrum."""
    centers = [-2.5, 0.0, 2.5]
    comps = [
        _typed_peak(
            "gaussian",
            round(rng.uniform(3.0, 6.0), 3),
            centers[0],
            round(rng.uniform(0.6, 1.0), 3),
        ),
        _typed_peak(
            "lorentzian",
            round(rng.uniform(3.0, 6.0), 3),
            centers[1],
            round(rng.uniform(0.6, 1.0), 3),
        ),
        _typed_peak(
            "pseudo_voigt",
            round(rng.uniform(3.0, 6.0), 3),
            centers[2],
            round(rng.uniform(0.6, 1.0), 3),
            fraction=rng.uniform(0.3, 0.7),
        ),
    ]
    return comps, {
        "name": "mixed gaussian+lorentzian+voigt blend",
        "noise": round(rng.uniform(0.03, 0.06), 3),
        "x_range": (-5.0, 5.0),
    }


def _edge_amp_decades(rng: random.Random, k: int) -> tuple[list[Component], dict]:
    """Amplitude ratios spanning decades: a tall peak next to a ~1% peak."""
    shape = _EDGE_PEAK_SHAPES[k % len(_EDGE_PEAK_SHAPES)]
    tall = round(rng.uniform(5.0, 8.0), 3)
    decades = rng.choice([1.5, 2.0, 2.5])  # tiny peak is 10^-decades of the tall one
    tiny = round(tall * 10.0 ** (-decades), 4)
    sigma = round(rng.uniform(0.6, 1.0), 3)
    comps = [
        _typed_peak(shape, tall, -2.0, sigma, fraction=rng.uniform(0.3, 0.7)),
        _typed_peak(shape, tiny, 2.0, sigma, fraction=rng.uniform(0.3, 0.7)),
    ]
    return comps, {
        "name": f"{shape} amplitude {10.0**decades:.0f}:1 (tiny={tiny:g})",
        "noise": round(rng.uniform(0.01, 0.03), 3),
        "x_range": (-5.0, 5.0),
    }


# EDGE: 5 regimes × 4 peak shapes. With len 5 and 4 coprime, (k%5, k%4) over k=0..19
# enumerates all 20 (regime, shape) combos exactly once — so count=20 gives a unique
# grid, no cycling (mixed_blend ignores shape; its 4 slots vary only the noise draw).
_EDGE_GRID_LEN = len(_EDGE_REGIMES) * len(_EDGE_PEAK_SHAPES)


def _edge_case(rng: random.Random, k: int) -> tuple[list[Component], dict]:
    """Dispatch one ill-conditioned regime per case over the unique (regime×shape) grid."""
    regime = _EDGE_REGIMES[k % len(_EDGE_REGIMES)]
    shape = _EDGE_PEAK_SHAPES[k % len(_EDGE_PEAK_SHAPES)]
    match regime:
        case "doublet":
            comps, meta = _edge_doublet(rng, k)
        case "near_widths":
            comps, meta = _edge_near_widths(rng, k)
        case "high_noise":
            comps, meta = _edge_high_noise(rng, k)
        case "mixed_blend":
            comps, meta = _edge_mixed_blend(rng, k)
        case _:  # amp_decades
            comps, meta = _edge_amp_decades(rng, k)
    meta["condition"] = f"{regime}/{shape}"
    return comps, meta


# --------------------------------------------------------------------------- #
# Asymmetric / true-Voigt lineshapes (deep-research Tier 2 models)
# --------------------------------------------------------------------------- #
_ASYM = Literal["true_voigt", "skewed_gaussian", "exp_gaussian", "doniach_sunjic"]
# Explicit (recipe, variant) grid — each a distinct asymmetric-lineshape scenario,
# no round-robin padding. `variant` is the model for "single", the band count for
# "ir_voigt", else "".
_LINESHAPE_GRID: list[tuple[str, str]] = [
    ("single", "true_voigt"),
    ("single", "skewed_gaussian"),
    ("single", "exp_gaussian"),
    ("single", "doniach_sunjic"),
    ("xps_doublet", ""),
    ("l_edge", ""),
    ("k_edge", ""),
    ("ir_voigt", "2"),
    ("ir_voigt", "3"),
    ("mixed_asym", ""),
    ("split_gauss", ""),
    ("moffat", ""),
    ("students_t", ""),
    ("split_p7", ""),
    ("breit_wigner", ""),
    ("asym_ir", ""),
    ("harmonic_ir", ""),
    ("tauc", ""),
    ("cauchy_dispersion", ""),
    ("kww", ""),
    ("saturating_exponential", ""),
    ("power_saturation", ""),
    ("power_law_offset", ""),
    ("mgh09_rational", ""),
]
# Recipes whose kernels are only defined for x>0 (Cauchy dispersion, KWW) or whose
# physical edge lives at positive energies (Tauc band-gap) → a positive x-range. The
# NIST regression/saturation curves (BoxBOD, Misra1b, Bennett5, MGH09) likewise hit a
# negative-base fractional power / domain-guard NaN on a grid spanning negative x, so
# each gets a positive-x range (offset+x>0, 1+rate·x/2>0 stay satisfied).
_LINESHAPE_X_RANGE: dict[str, tuple[float, float]] = {
    "tauc": (0.2, 8.0),
    "cauchy_dispersion": (0.3, 6.0),
    "kww": (0.0, 10.0),
    "saturating_exponential": (0.0, 8.0),
    "power_saturation": (0.0, 8.0),
    "power_law_offset": (0.0, 8.0),
    "mgh09_rational": (0.1, 8.0),
}
# Per-model `gamma` ranges (Lorentzian HWHM / skew / EMG rate / DS asymmetry).
_GAMMA_RANGE: dict[str, tuple[float, float]] = {
    "true_voigt": (0.3, 1.0),
    "skewed_gaussian": (0.6, 2.0),
    "exp_gaussian": (0.4, 1.1),
    "doniach_sunjic": (0.05, 0.30),
}


def _asym(
    rng: random.Random, model: str, amp: float, center: float, sigma: float
) -> Component:
    """One asymmetric peak with a model-appropriate ``gamma`` draw."""
    lo, hi = _GAMMA_RANGE[model]
    return AsymPeakSpec(
        model=cast(_ASYM, model),
        amplitude=round(amp, 3),
        center=round(center, 3),
        sigma=round(sigma, 3),
        gamma=round(rng.uniform(lo, hi), 4),
    )


def _lineshapes(rng: random.Random, k: int) -> tuple[list[Component], dict]:
    """One asymmetric-lineshape scenario per case, indexed over the explicit grid."""
    recipe, variant = _LINESHAPE_GRID[k]
    comps, name = _lineshape_recipe(rng, recipe, variant)
    meta: dict = {
        "name": name,
        "condition": f"{recipe}/{variant}" if variant else recipe,
    }
    if recipe in _LINESHAPE_X_RANGE:  # positive-x kernels need a positive grid
        meta["x_range"] = _LINESHAPE_X_RANGE[recipe]
    return comps, meta


def _lineshape_recipe(
    rng: random.Random, recipe: str, variant: str
) -> tuple[list[Component], str]:
    """Dispatch to the registered lineshape recipe (Plan C C3 refactor).

    Each recipe is implemented in its own module under ``oracles/lineshapes/``
    and self-registers via ``@register_lineshape``. Adding a new shape is a
    single new file — nothing else changes here.
    """
    from oracles.lineshapes import LINESHAPE_RECIPE_REGISTRY

    fn = LINESHAPE_RECIPE_REGISTRY.get(recipe)
    if fn is None:
        raise ValueError(
            f"unknown lineshape recipe {recipe!r}; "
            f"registered: {sorted(LINESHAPE_RECIPE_REGISTRY)}"
        )
    return fn(rng, variant)


# --------------------------------------------------------------------------- #
# Fixed-param family generators (Track 3)
# --------------------------------------------------------------------------- #
# Four cases: each fixes the center of the first (and only) peak at truth so the
# solver must recover amplitude + sigma while the center is held constant.
# Models: gaussian, lorentzian, pseudo_voigt, gaussian (noisy).
_FIXED_GRID: list[tuple[str, str, float]] = [
    ("gaussian", "center-fixed/clean", 0.02),
    ("lorentzian", "center-fixed/clean", 0.02),
    ("pseudo_voigt", "center-fixed/clean", 0.02),
    ("gaussian", "center-fixed/noisy", 0.08),
]


def _fixed_case(rng: random.Random, k: int) -> tuple[list[Component], dict]:
    """Single-peak case with the center held fixed at its truth value."""
    model_key, condition, noise = _FIXED_GRID[k]
    amp = round(rng.uniform(1.0, 3.0), 3)
    center = round(rng.uniform(-1.5, 1.5), 3)
    sigma = round(rng.uniform(0.4, 1.2), 3)
    fraction = round(rng.uniform(0.3, 0.7), 3)
    peak = _typed_peak(model_key, amp, center, sigma, fraction=fraction)
    meta: dict = {
        "name": f"single {model_key} · {condition}",
        "condition": condition,
        "noise": noise,
        # Mark p0.center as fixed — backends must not vary it.
        "fixed_params": {"p0": ["center"]},
    }
    return [peak], meta


# --------------------------------------------------------------------------- #
# Tied/shared-param family generators (Track 3)
# --------------------------------------------------------------------------- #
# Four cases: two-peak fits with a parameter tied across peaks via expr_edges.
# Tie semantics: p1.sigma = p0.sigma (shared width), or similar.
# Backend support: spectrafit (FitGraph expr_edges) + lmfit (expr= param).
# Disclosed exclusions: jax, scipy-ls (cannot express parameter ties).
_TIED_GRID: list[tuple[str, str, str]] = [
    # (model for both peaks, tie description, condition tag)
    ("gaussian", "shared_sigma", "gaussian/shared-sigma"),
    ("lorentzian", "shared_sigma", "lorentzian/shared-sigma"),
    ("pseudo_voigt", "shared_fraction", "pseudo_voigt/shared-fraction"),
    ("gaussian", "center_offset", "gaussian/center-offset"),
]


def _tied_case(rng: random.Random, k: int) -> tuple[list[Component], dict]:
    """Two-peak case with one parameter tied between peaks via expr_edges."""
    model_key, tie_kind, condition = _TIED_GRID[k]

    amp0 = round(rng.uniform(1.5, 3.0), 3)
    amp1 = round(rng.uniform(0.8, 2.0), 3)
    center0 = round(rng.uniform(-2.0, -0.5), 3)
    center1 = round(rng.uniform(0.5, 2.0), 3)
    sigma = round(rng.uniform(0.4, 0.9), 3)
    fraction = round(rng.uniform(0.3, 0.7), 3)

    match tie_kind:
        case "shared_sigma":
            # Both peaks share the same sigma; p1 is tied to p0.
            p0 = _typed_peak(model_key, amp0, center0, sigma, fraction=fraction)
            p1 = _typed_peak(model_key, amp1, center1, sigma, fraction=fraction)
            edges: list[dict[str, str]] = [
                {
                    "target_node": "p1",
                    "target_param": "sigma",
                    "expression": "p0.sigma",
                }
            ]
            name = f"2×{model_key} shared σ"
        case "shared_fraction":
            # Two pseudo_voigt with the same fraction.
            p0 = _typed_peak("pseudo_voigt", amp0, center0, sigma, fraction=fraction)
            p1 = _typed_peak("pseudo_voigt", amp1, center1, sigma, fraction=fraction)
            edges = [
                {
                    "target_node": "p1",
                    "target_param": "fraction",
                    "expression": "p0.fraction",
                }
            ]
            name = "2×pseudo_voigt shared fraction"
        case _:  # center_offset: p1.center = p0.center + fixed_gap
            # p1.center is tied to p0.center; the offset is baked into the truth
            # (both centers vary but p1 always tracks p0 during the fit).
            # We achieve this by fixing a constant offset in the expression.
            gap = round(abs(center1 - center0), 3)
            p0 = _typed_peak(model_key, amp0, center0, sigma, fraction=fraction)
            p1 = _typed_peak(model_key, amp1, center0 + gap, sigma, fraction=fraction)
            edges = [
                {
                    "target_node": "p1",
                    "target_param": "center",
                    "expression": f"p0.center + {gap}",
                }
            ]
            name = f"2×{model_key} center offset {gap:.3f}"

    meta: dict = {
        "name": name,
        "condition": condition,
        "noise": 0.03,
        "expr_edges": edges,
    }
    return [p0, p1], meta


FAMILIES: list[CaseFamily] = [
    CaseFamily(
        category="easy",
        count=len(_EASY_GRID),
        compose=_easy,
        x_range=(-6.0, 6.0),
        n_points=120,
        noise=0.02,
        difficulty=(0.05, 0.3),
        guess_scale=0.08,
        name_template="{name} #{k}",
    ),
    CaseFamily(
        category="complex",
        count=len(_COMPLEX_GRID),
        compose=_complex,
        x_range=(-7.0, 7.0),
        n_points=200,
        noise=0.05,
        difficulty=(0.3, 0.7),
        guess_scale=0.14,
        name_template="{name} #{k}",
    ),
    CaseFamily(
        category="reality",
        count=len(_REALITY_GRID),
        compose=_reality,
        x_range=(-5.2, 5.2),
        n_points=180,
        noise=0.06,
        difficulty=(0.4, 0.8),
        guess_scale=0.12,
        name_template="{name} #{k}",
    ),
    CaseFamily(
        category="optfn",
        count=len(_LANDSCAPES),
        compose=_optfn,
        x_range=(-5.0, 5.0),
        n_points=160,
        noise=0.0,
        difficulty=(0.7, 1.0),
        guess_scale=0.0,
        solver_hint="global",
        name_template="{name} #{k}",
    ),
    CaseFamily(
        category="scaling",
        count=len(_SCALING_GRID),
        compose=_scaling,
        x_range=(-10.0, 10.0),
        n_points=600,
        noise=0.04,
        difficulty=(0.5, 0.9),
        guess_scale=0.1,
        points_scale_per_block=True,
        name_template="{name} #{k}",
    ),
    # Edge / ill-conditioned: degenerate Jacobians, near-equal widths, heavy noise,
    # mixed-shape blends, decade-spanning amplitudes. Dense grid + wider start so the
    # difficulty is the *landscape*, not under-sampling or a trivially-close guess.
    CaseFamily(
        category="edge",
        count=_EDGE_GRID_LEN,
        compose=_edge_case,
        x_range=(-5.0, 5.0),
        n_points=240,
        noise=0.04,
        difficulty=(0.7, 1.0),
        guess_scale=0.18,
        name_template="{name} #{k}",
    ),
    # Asymmetric / true-Voigt lineshapes: true Voigt (Faddeeva), skewed Gaussian, EMG,
    # Doniach–Šunjić; XPS spin-orbit doublets, XAS L-edge L3/L2, XANES K-edge.
    CaseFamily(
        category="lineshapes",
        count=len(_LINESHAPE_GRID),
        compose=_lineshapes,
        x_range=(-6.0, 6.0),
        n_points=200,
        noise=0.04,
        difficulty=(0.4, 0.8),
        guess_scale=0.1,
        name_template="{name} #{k}",
    ),
    # Fixed/shrunk-parameter cases (Track 3): realistic constrained fits where the
    # center is held fixed at truth and only amplitude + sigma are free.
    CaseFamily(
        category="fixed",
        count=len(_FIXED_GRID),
        compose=_fixed_case,
        x_range=(-5.0, 5.0),
        n_points=160,
        noise=0.03,
        difficulty=(0.1, 0.3),
        guess_scale=0.12,
        name_template="{name} #{k}",
    ),
    # Tied/shared-parameter cases (Track 3): two-peak fits with a parameter tied
    # across peaks via expr_edges. spectrafit + lmfit only; jax/scipy excluded.
    CaseFamily(
        category="tied",
        count=len(_TIED_GRID),
        compose=_tied_case,
        x_range=(-5.0, 5.0),
        n_points=160,
        noise=0.03,
        difficulty=(0.2, 0.5),
        guess_scale=0.10,
        name_template="{name} #{k}",
    ),
]


# --------------------------------------------------------------------------- #
# Materialization
# --------------------------------------------------------------------------- #
def _jitter(
    rng: random.Random,
    comps: Sequence[Component],
    scale: float,
    *,
    fixed_by_index: dict[int, list[str]] | None = None,
) -> list[Component]:
    """Perturb each component's params into an initial guess (typed, via model_copy).

    Parameters named in *fixed_by_index* are **not** perturbed — their guess value
    equals their truth value so the backend can hold them fixed during the fit.
    """
    out: list[Component] = []
    for i, c in enumerate(comps):
        fixed_names: list[str] = (fixed_by_index or {}).get(i, [])
        params = c.to_params()
        update: dict[str, float] = {}
        for k, v in params.items():
            if k in fixed_names:
                update[k] = v  # do not perturb — backend will hold this fixed
                continue
            match k:
                case "center":
                    sigma = params.get("sigma") or params.get("gamma") or 0.5
                    update[k] = v + rng.uniform(-scale, scale) * max(sigma, 0.5)
                case "fraction":
                    update[k] = float(
                        np.clip(v + rng.uniform(-scale, scale), 0.05, 0.95)
                    )
                case _:
                    update[k] = v * (1 + rng.uniform(-scale, scale))
        out.append(c.model_copy(update=update))
    return out


def curve(x: Array, comps: Sequence[Component]) -> Array:
    """Evaluate and sum a list of typed components over the grid *x*."""
    out = np.zeros_like(x)
    for c in comps:
        out = out + get_model(c.model).one(x, c.to_params())
    return out


def materialize(spec: CaseSpec) -> BenchCase:
    """Generate the data + truth/guess components for *spec* (deterministic by id)."""
    rng = random.Random(zlib.crc32(spec.id.encode()))
    x = np.linspace(spec.x_min, spec.x_max, spec.n_points)
    truth = spec.components

    if spec.landscape is not None:
        y = models.landscape(spec.landscape, x)
        y = y.max() - y
        y = y / max(float(y.max()), 1e-9) * 5.0
        guess = list(truth)  # recovery N/A; the challenge is the multimodal target
    else:
        noise = np.array([rng.gauss(0, spec.noise) for _ in range(spec.n_points)])
        y = curve(x, truth) + noise
        # Collect names that must not be jittered (fixed at truth for the fit).
        fixed_by_index: dict[int, list[str]] = {
            int(nid[1:]): pnames
            for nid, pnames in spec.fixed_params.items()
            if nid.startswith("p") and nid[1:].isdigit()
        }
        guess = _jitter(rng, truth, spec.guess_scale, fixed_by_index=fixed_by_index)

    return BenchCase(spec=spec, x=x, y=y, comp_true=list(truth), comp_guess=guess)


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #
def build_specs(seed: int = 20260603) -> list[CaseSpec]:
    """Expand all families into the concrete spec list (deterministic)."""
    rng = random.Random(seed)
    specs: list[CaseSpec] = []
    for fam in FAMILIES:
        specs.extend(fam.expand(rng))
    # Featured case: a reality tri-Gaussian (the detailed peak panels assume a/c/s).
    for i, s in enumerate(specs):
        if s.category == "reality" and s.id.endswith("-001"):
            specs[i] = s.model_copy(
                update={
                    "featured": True,
                    "components": [
                        GaussianSpec(amplitude=4.95, center=-2.5, sigma=0.6),
                        GaussianSpec(amplitude=4.95, center=0.0, sigma=1.0),
                        GaussianSpec(amplitude=1.65, center=2.4, sigma=0.8),
                    ],
                    "name": "tri-gaussian · reality-like + 6% noise",
                }
            )
            break
    return specs


def build_catalog(seed: int = 20260603) -> list[BenchCase]:
    """Build the full deterministic catalog (materialized)."""
    return [materialize(s) for s in build_specs(seed)]


def featured_case(catalog: Sequence[BenchCase]) -> BenchCase:
    """Return the designated featured case (the reality tri-Gaussian)."""
    for c in catalog:
        if c.featured:
            return c
    return catalog[0]
