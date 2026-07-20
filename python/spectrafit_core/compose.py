"""``compose()`` DSL — pure-Python sugar for building :class:`FitGraph`.

The :class:`FitGraph` Pydantic contract is unchanged. This module adds two layers
on top of it:

* **Factory functions** per canonical :class:`ModelType` member
  (:func:`gaussian`, :func:`lorentzian`, :func:`voigt`, …) that take the model's
  parameters as keyword arguments and return a ready-to-use
  :class:`ModelNodeSpec`. Bounds and other :class:`Parameter` fields propagate
  via the ``<param>_<field>=`` convention (e.g. ``amplitude_min=0.0``).

  For the ``amplitude / center / sigma`` family — the dominant spectral
  convention — three single-letter shorthands are also accepted:

  =========  ============
  Shorthand  Canonical
  =========  ============
  ``a``      ``amplitude``
  ``c``      ``center``
  ``s``      ``sigma``
  =========  ============

  Bound kwargs follow the same shorthand: ``a_min=`` ⇔ ``amplitude_min=``. The
  shorthand is only accepted on models that actually have those canonical
  params; on e.g. :func:`constant` (whose only parameter is ``c``), ``c=...``
  is itself the canonical kwarg and is **not** treated as a shorthand for
  ``center``.

* :func:`compose` + :class:`ComposeBuilder` — a chainable helper that gathers
  a list of nodes and optional :class:`ExprEdge` constraints, then builds a
  :class:`FitGraph`.  The builder is also iterable, so existing
  ``FitGraph(nodes=[…])`` call-sites work unchanged when fed
  ``compose([…])`` directly.

The output is **byte-identical** to a hand-rolled :class:`FitGraph`:
``compose(...).build().model_dump_json() == handrolled.model_dump_json()``.
This is asserted in ``tests/test_compose_dsl.py`` for every
:class:`ModelType` member.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from .graph import ExprEdge, FitGraph
from .models import ModelNodeSpec, ModelType
from .parameters import Parameter

# Every factory kwarg value feeds exactly one ``Parameter`` field: ``value`` /
# ``min`` / ``max`` / ``scale`` take ``float`` (``min``/``max`` also accept
# ``str``/``None`` via their before-validators), ``vary`` takes ``bool``, and
# ``expr`` takes ``str | None``.  This union is the envelope of all of those;
# ``int`` is included because the numeric fields accept plain int literals
# (``gaussian("g", center=0)``) — pydantic coerces int→float. Validation to
# the exact per-field type happens in ``Parameter``.
type ParamKwarg = float | int | bool | str | None

__all__ = [
    "ComposeBuilder",
    "arctan_step",
    "asym_ir",
    "breit_wigner",
    "cauchy_dispersion",
    "compose",
    "constant",
    "doniach_sunjic",
    "double_exponential",
    "erfc_step",
    "exp_gaussian",
    "fano",
    "gaussian",
    "gaussian2d",
    "harmonic_ir",
    "kww",
    "linear",
    "log_normal",
    "lorentzian",
    "mgh09_rational",
    "moffat",
    "pearson7",
    "power_law_offset",
    "power_saturation",
    "pseudo_voigt",
    "quadratic",
    "saturating_exponential",
    "skewed_gaussian",
    "split_gaussian",
    "split_pearson7",
    "students_t",
    "tanh_step",
    "tauc",
    "true_voigt",
    "voigt",
]


# --------------------------------------------------------------------------- #
# Canonical parameter table
# --------------------------------------------------------------------------- #
# Single source of truth for the canonical parameter names of every
# ModelType.  Keep in lock-step with crates/spectrafit-models/src/*.rs and
# python/extras/bench/models.py (the parity oracle); the
# test_compose_param_names_match_bench_registry test pins this.

CANONICAL_PARAMS: Final[dict[ModelType, tuple[str, ...]]] = {
    ModelType.GAUSSIAN: ("amplitude", "center", "sigma"),
    ModelType.GAUSSIAN2D: (
        "amplitude",
        "center_x",
        "center_y",
        "sigma_x",
        "sigma_y",
    ),
    ModelType.LORENTZIAN: ("amplitude", "center", "sigma"),
    ModelType.VOIGT: ("amplitude", "center", "sigma", "fraction"),
    ModelType.CONSTANT: ("c",),
    ModelType.LINEAR: ("slope", "intercept"),
    ModelType.QUADRATIC: ("amplitude", "center", "offset"),
    ModelType.ARCTAN_STEP: ("amplitude", "center", "sigma"),
    ModelType.TANH_STEP: ("amplitude", "center", "sigma"),
    ModelType.ERFC_STEP: ("amplitude", "center", "sigma"),
    ModelType.PSEUDO_VOIGT: ("amplitude", "center", "sigma", "fraction"),
    ModelType.FANO: ("amplitude", "center", "gamma", "q"),
    ModelType.DOUBLE_EXPONENTIAL: ("A1", "lam1", "A2", "lam2"),
    ModelType.TRUE_VOIGT: ("amplitude", "center", "sigma", "gamma"),
    ModelType.SKEWED_GAUSSIAN: ("amplitude", "center", "sigma", "gamma"),
    ModelType.EXP_GAUSSIAN: ("amplitude", "center", "sigma", "gamma"),
    ModelType.DONIACH: ("amplitude", "center", "sigma", "gamma"),
    ModelType.LOG_NORMAL: ("amplitude", "center", "sigma"),
    ModelType.PEARSON7: ("amplitude", "center", "sigma", "m"),
    ModelType.SPLIT_GAUSSIAN: ("amplitude", "center", "sigma_l", "sigma_r"),
    ModelType.MOFFAT: ("amplitude", "center", "sigma", "beta"),
    ModelType.STUDENTS_T: ("amplitude", "center", "sigma", "nu"),
    ModelType.SPLIT_PEARSON7: (
        "amplitude",
        "center",
        "sigma_l",
        "sigma_r",
        "m_l",
        "m_r",
    ),
    ModelType.BREIT_WIGNER: ("amplitude", "center", "sigma", "q"),
    ModelType.ASYM_IR: ("amplitude", "center", "sigma", "k"),
    ModelType.HARMONIC_IR: ("amplitude", "center", "sigma"),
    ModelType.TAUC: ("amplitude", "e_gap", "exponent"),
    ModelType.CAUCHY_DISPERSION: ("a", "b", "c"),
    ModelType.KWW: ("amplitude", "tau", "beta"),
    ModelType.SATURATING_EXPONENTIAL: ("amplitude", "rate"),
    ModelType.POWER_SATURATION: ("amplitude", "rate"),
    ModelType.POWER_LAW_OFFSET: ("amplitude", "offset", "shape"),
    ModelType.MGH09_RATIONAL: ("amplitude", "num_lin", "den_lin", "den_const"),
}


# Shorthand: only ever maps these three letters to these three canonical names.
# Restricted on purpose — on a model like `constant` (`c` is canonical) the
# user-facing `c=...` is itself canonical, not a shorthand for `center`.
_SHORTHAND: Final[dict[str, str]] = {
    "a": "amplitude",
    "c": "center",
    "s": "sigma",
}

# Allowed Parameter field suffixes on a kwarg like ``amplitude_min=0.0``.
_PARAM_FIELD_SUFFIXES: Final[tuple[str, ...]] = ("min", "max", "vary", "expr", "scale")


# --------------------------------------------------------------------------- #
# Core builder used by every factory
# --------------------------------------------------------------------------- #
def _build_node(
    *,
    model_type: ModelType,
    node_id: str,
    user_kwargs: dict[str, ParamKwarg],
    dataset_index: int | None = None,
) -> ModelNodeSpec:
    """Translate user kwargs into a :class:`ModelNodeSpec`.

    Args:
        model_type: The canonical :class:`ModelType` member for this node.
        node_id: Unique identifier for the node inside its graph.
        user_kwargs: All keyword arguments passed to the factory.  Each is
            either a canonical parameter name (or its accepted shorthand) giving
            an initial *value*, or a ``<param>_<field>`` form (e.g.
            ``"amplitude_min"``) populating the matching :class:`Parameter`
            field.  Shorthand suffix kwargs (``a_min``) are translated the same
            way as their leading-name counterparts.
        dataset_index: Forwarded to :class:`ModelNodeSpec.dataset_index`.

    Returns:
        A validated :class:`ModelNodeSpec`.

    Raises:
        TypeError: If a required parameter has no value, or if any kwarg does
            not map to a canonical parameter / accepted suffix.
    """
    canonical = CANONICAL_PARAMS[model_type]
    shorthand = {sh: full for sh, full in _SHORTHAND.items() if full in canonical}

    # Buckets per canonical param: {name -> {"value"|"min"|"max"|...: kwarg}}
    buckets: dict[str, dict[str, ParamKwarg]] = {name: {} for name in canonical}

    for key, value in user_kwargs.items():
        target_name, field = _resolve_kwarg(key, canonical, shorthand)
        # ``_resolve_kwarg`` only returns names already in ``canonical``, so
        # ``target_name`` is always a valid bucket key here.
        if field in buckets[target_name]:
            raise TypeError(
                f"{model_type.value}: duplicate value for "
                f"{target_name!r} (field {field!r}) via {key!r}"
            )
        buckets[target_name][field] = value

    parameters: dict[str, Parameter] = {}
    for name in canonical:
        fields = buckets[name]
        if "value" not in fields:
            raise TypeError(f"{model_type.value}: missing required parameter {name!r}")
        # ``model_validate`` (not ``Parameter(**fields)``): which Parameter
        # field each ParamKwarg lands in is only known at runtime, so the
        # mapping is validated as a whole — same pydantic validation pipeline,
        # same ValidationErrors, and no per-field static-assignability claim.
        parameters[name] = Parameter.model_validate(fields)

    return ModelNodeSpec(
        id=node_id,
        model_type=model_type,
        parameters=parameters,
        dataset_index=dataset_index,
    )


def _resolve_kwarg(
    key: str,
    canonical: tuple[str, ...],
    shorthand: dict[str, str],
) -> tuple[str, str]:
    """Map a user kwarg to ``(canonical_param_name, parameter_field)``.

    Returns ``(param, "value")`` for a leading-name kwarg and ``(param, field)``
    where ``field`` is one of ``min``, ``max``, ``vary``, ``expr``, ``scale``
    when the kwarg ends in ``_<field>``.

    Raises:
        TypeError: If the kwarg cannot be matched to any canonical name or
            shorthand, with or without a suffix.
    """
    # 1) Exact canonical name — value
    if key in canonical:
        return key, "value"
    # 2) Shorthand a/c/s — value
    if key in shorthand:
        return shorthand[key], "value"
    # 3) Suffix form: <name>_<field>
    for suffix in _PARAM_FIELD_SUFFIXES:
        tail = f"_{suffix}"
        if key.endswith(tail):
            head = key[: -len(tail)]
            if head in canonical:
                return head, suffix
            if head in shorthand:
                return shorthand[head], suffix
    raise TypeError(
        f"unexpected keyword {key!r}; expected one of {canonical} "
        f"(or {tuple(shorthand)}) optionally suffixed with "
        f"{_PARAM_FIELD_SUFFIXES}"
    )


# --------------------------------------------------------------------------- #
# Public factories — one per ModelType member
# --------------------------------------------------------------------------- #
def gaussian(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a Gaussian peak node ``A·exp(−½((x−c)/σ)²)``.

    Required params: ``amplitude`` (or ``a``), ``center`` (or ``c``),
    ``sigma`` (or ``s``).  Bound suffixes (``a_min=``, ``sigma_max=``, …)
    propagate to the underlying :class:`Parameter`.
    """
    return _build_node(
        model_type=ModelType.GAUSSIAN,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def gaussian2d(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a 2-D Gaussian node.

    Required params: ``amplitude``, ``center_x``, ``center_y``, ``sigma_x``,
    ``sigma_y``.
    """
    return _build_node(
        model_type=ModelType.GAUSSIAN2D,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def lorentzian(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a Lorentzian peak node ``A / (1 + ((x−c)/σ)²)``."""
    return _build_node(
        model_type=ModelType.LORENTZIAN,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def voigt(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a Voigt (pseudo-Voigt alias) node.

    Required params: ``amplitude``, ``center``, ``sigma``, ``fraction``.
    """
    return _build_node(
        model_type=ModelType.VOIGT,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def constant(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a constant background node.

    Required param: ``c`` (the constant value).  Note ``c`` here is the
    canonical param name, *not* a shorthand for ``center``.
    """
    return _build_node(
        model_type=ModelType.CONSTANT,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def linear(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a linear background node ``slope·x + intercept``."""
    return _build_node(
        model_type=ModelType.LINEAR,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def quadratic(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a quadratic bowl node ``A·(x−c)² + offset``."""
    return _build_node(
        model_type=ModelType.QUADRATIC,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def arctan_step(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build an arctan edge node ``A·(½ + (1/π)·arctan((x−c)/σ))``."""
    return _build_node(
        model_type=ModelType.ARCTAN_STEP,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def tanh_step(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a tanh edge node ``(A/2)·(1 + tanh((x−c)/σ))``."""
    return _build_node(
        model_type=ModelType.TANH_STEP,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def erfc_step(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build an erfc edge node ``(A/2)·erfc((x−c)/(σ·√2))``."""
    return _build_node(
        model_type=ModelType.ERFC_STEP,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def pseudo_voigt(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a pseudo-Voigt node ``η·L + (1−η)·G`` with ``η = fraction``."""
    return _build_node(
        model_type=ModelType.PSEUDO_VOIGT,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def fano(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a Fano resonance node ``A·(q+ε)²/(1+ε²)``, ε=(x−c)/γ."""
    return _build_node(
        model_type=ModelType.FANO,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def double_exponential(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a bi-exponential decay node ``A1·exp(−λ1·x) + A2·exp(−λ2·x)``."""
    return _build_node(
        model_type=ModelType.DOUBLE_EXPONENTIAL,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def true_voigt(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a true Voigt (Faddeeva) node with Gaussian σ and Lorentzian γ."""
    return _build_node(
        model_type=ModelType.TRUE_VOIGT,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def skewed_gaussian(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a skewed Gaussian node (γ = skew)."""
    return _build_node(
        model_type=ModelType.SKEWED_GAUSSIAN,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def exp_gaussian(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build an exponentially-modified Gaussian (EMG) node."""
    return _build_node(
        model_type=ModelType.EXP_GAUSSIAN,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def doniach_sunjic(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a Doniach–Šunjić node (γ = asymmetry)."""
    return _build_node(
        model_type=ModelType.DONIACH,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def log_normal(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a log-normal peak node ``A·exp(−(ln(x/c))²/(2σ²))``."""
    return _build_node(
        model_type=ModelType.LOG_NORMAL,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def pearson7(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a Pearson VII node (shape exponent ``m``)."""
    return _build_node(
        model_type=ModelType.PEARSON7,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def split_gaussian(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a split-σ asymmetric Gaussian node (``sigma_l``, ``sigma_r``)."""
    return _build_node(
        model_type=ModelType.SPLIT_GAUSSIAN,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def moffat(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a Moffat node ``A/(((x−c)/σ)²+1)^β``."""
    return _build_node(
        model_type=ModelType.MOFFAT,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def students_t(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a Student's-t node (degrees-of-freedom ``nu``)."""
    return _build_node(
        model_type=ModelType.STUDENTS_T,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def split_pearson7(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a split Pearson VII node (split width + exponent each side)."""
    return _build_node(
        model_type=ModelType.SPLIT_PEARSON7,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def breit_wigner(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a Breit-Wigner-Fano node."""
    return _build_node(
        model_type=ModelType.BREIT_WIGNER,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def asym_ir(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build an asymmetric IR band node (sigmoid asymmetry ``k``)."""
    return _build_node(
        model_type=ModelType.ASYM_IR,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def harmonic_ir(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a harmonic-oscillator IR band node."""
    return _build_node(
        model_type=ModelType.HARMONIC_IR,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def tauc(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a Tauc band-gap edge node (``e_gap``, ``exponent``)."""
    return _build_node(
        model_type=ModelType.TAUC,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def cauchy_dispersion(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a Cauchy dispersion node ``a + b/x² + c/x⁴``.

    Note ``a``, ``b``, ``c`` here are the **canonical** Cauchy coefficients,
    not the ``a``/``c`` shorthand (the shorthand only applies to models that
    carry ``amplitude``/``center``/``sigma``).
    """
    return _build_node(
        model_type=ModelType.CAUCHY_DISPERSION,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def kww(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a KWW stretched-exponential node ``A·exp(−(x/τ)^β)``."""
    return _build_node(
        model_type=ModelType.KWW,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def saturating_exponential(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a saturating-exponential node ``amplitude·(1 − exp(−rate·x))`` (BoxBOD)."""
    return _build_node(
        model_type=ModelType.SATURATING_EXPONENTIAL,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def power_saturation(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a power-saturation node ``amplitude·(1 − (1 + rate·x/2)^(−2))`` (Misra1b)."""
    return _build_node(
        model_type=ModelType.POWER_SATURATION,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def power_law_offset(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build a power-law-with-offset node (``amplitude``, ``offset``, ``shape``)."""
    return _build_node(
        model_type=ModelType.POWER_LAW_OFFSET,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


def mgh09_rational(
    id: str, *, dataset_index: int | None = None, **params: ParamKwarg
) -> ModelNodeSpec:
    """Build an MGH09 rational node (``amplitude``, ``num_lin``, ``den_lin``, ``den_const``)."""
    return _build_node(
        model_type=ModelType.MGH09_RATIONAL,
        node_id=id,
        user_kwargs=params,
        dataset_index=dataset_index,
    )


# --------------------------------------------------------------------------- #
# Compose builder
# --------------------------------------------------------------------------- #
class ComposeBuilder(BaseModel):
    """Chainable accumulator that turns a list of nodes + ties into a graph.

    Iterating over a :class:`ComposeBuilder` yields its nodes, so the builder
    can be passed directly into ``FitGraph(nodes=...)`` for backward
    compatibility.  Call :meth:`build` to get a fully validated
    :class:`FitGraph`, including any :class:`ExprEdge` constraints added via
    :meth:`bind`.

    Attributes:
        nodes: The model nodes collected by :func:`compose`.
        expr_edges: Parameter-constraint edges added via :meth:`bind`.
        schema_version: IR schema version forwarded to :class:`FitGraph`.
    """

    nodes: list[ModelNodeSpec]
    expr_edges: list[ExprEdge] = []
    schema_version: str = "0.1"

    model_config = ConfigDict(extra="forbid")

    def bind(self, expression: str, to: str) -> "ComposeBuilder":
        """Add an :class:`ExprEdge` tying ``to`` to ``expression``.

        Args:
            expression: A formula referencing other nodes' parameters as
                ``"node_id.param"``.
            to: The target ``"node_id.param"`` whose value is constrained.
                Both positional and keyword forms are accepted, so
                ``bind("g0.sigma", "g1.sigma")`` and
                ``bind("g0.sigma", to="g1.sigma")`` are equivalent.

        Returns:
            ``self``, so calls can be chained.

        Raises:
            ValueError: If ``to`` is not in ``"node_id.param"`` form.
        """
        if "." not in to:
            raise ValueError(f"bind(to=...) must be 'node_id.param', got {to!r}")
        target_node, target_param = to.split(".", 1)
        if not target_node or not target_param:
            raise ValueError(f"bind(to=...) must be 'node_id.param', got {to!r}")
        self.expr_edges.append(
            ExprEdge(
                target_node=target_node,
                target_param=target_param,
                expression=expression,
            )
        )
        return self

    def build(self) -> FitGraph:
        """Materialise an immutable :class:`FitGraph` from the accumulator."""
        return FitGraph(
            schema_version=self.schema_version,
            nodes=list(self.nodes),
            expr_edges=list(self.expr_edges),
        )

    # Intentional LSP break: pydantic's BaseModel.__iter__ yields (name, value)
    # field pairs; this class's public iteration protocol is "yield the nodes"
    # so FitGraph(nodes=compose([…])) works. ty is the repo's authoritative
    # checker, so one ty suppression is kept; the mypy one is dropped (mypy is
    # not a CI gate here).
    def __iter__(self) -> Iterator[ModelNodeSpec]:  # ty: ignore[invalid-method-override]
        """Yield the collected nodes so ``FitGraph(nodes=compose([…]))`` works.

        Overriding the Pydantic-default ``__iter__`` (which yields field
        ``(name, value)`` pairs) with a node iterator is intentional — this is
        the public iteration protocol callers rely on.  Use
        ``self.model_dump()`` if you need the underlying field view.
        """
        return iter(self.nodes)


def compose(nodes: Sequence[ModelNodeSpec]) -> ComposeBuilder:
    """Start a :class:`ComposeBuilder` from a sequence of model nodes.

    Args:
        nodes: Nodes built via the factory functions above (or any other
            :class:`ModelNodeSpec` instances).

    Returns:
        A fresh :class:`ComposeBuilder` ready for :meth:`ComposeBuilder.bind`
        / :meth:`ComposeBuilder.build`.
    """
    return ComposeBuilder(nodes=list(nodes))
