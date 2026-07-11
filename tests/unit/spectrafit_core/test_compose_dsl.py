"""Tests for the ``compose()`` DSL — pure-Python sugar over FitGraph.

Coverage:

* Every canonical :class:`ModelType` member round-trips byte-identically via
  the matching factory function and a hand-rolled :class:`ModelNodeSpec`.
* The ``a``/``c``/``s`` shorthand maps to ``amplitude``/``center``/``sigma``.
* Bound suffixes (``a_min=``, ``sigma_max=``, …) propagate to ``Parameter``.
* :meth:`ComposeBuilder.bind` produces the expected ``ExprEdge`` list.
* Backward compat: ``FitGraph(nodes=[gaussian(...)])`` and
  ``FitGraph(nodes=compose([...]))`` both work.
"""

from __future__ import annotations

import math
from typing import Final

import pytest

from spectrafit_core import (
    ComposeBuilder,
    ExprEdge,
    FitGraph,
    ModelNodeSpec,
    ModelType,
    Parameter,
    compose,
    gaussian,
    lorentzian,
    pseudo_voigt,
)

# Bring every per-model factory into local scope for the fixture table below.
from spectrafit_core.compose import (
    CANONICAL_PARAMS,
    arctan_step,
    asym_ir,
    breit_wigner,
    cauchy_dispersion,
    constant,
    doniach_sunjic,
    double_exponential,
    erfc_step,
    exp_gaussian,
    fano,
    gaussian2d,
    harmonic_ir,
    kww,
    linear,
    log_normal,
    mgh09_rational,
    moffat,
    pearson7,
    power_law_offset,
    power_saturation,
    quadratic,
    saturating_exponential,
    skewed_gaussian,
    split_gaussian,
    split_pearson7,
    students_t,
    tanh_step,
    tauc,
    true_voigt,
    voigt,
)

# --------------------------------------------------------------------------- #
# Per-ModelType fixture: factory function + safe initial parameter values.
# Every value sits within the default ``Parameter`` bounds (−∞ … +∞), so the
# Pydantic post-init bounds check passes.  ``e_gap`` / ``tau`` / ``center``
# values for log-normal etc. are kept positive where the formula requires it.
# --------------------------------------------------------------------------- #

_FACTORY_FIXTURES: Final[dict[ModelType, tuple[object, dict[str, float]]]] = {
    ModelType.GAUSSIAN: (
        gaussian,
        {"amplitude": 1.0, "center": 0.0, "sigma": 1.0},
    ),
    ModelType.GAUSSIAN2D: (
        gaussian2d,
        {
            "amplitude": 1.5,
            "center_x": 0.5,
            "center_y": -0.25,
            "sigma_x": 1.0,
            "sigma_y": 0.75,
        },
    ),
    ModelType.LORENTZIAN: (
        lorentzian,
        {"amplitude": 1.0, "center": 0.0, "sigma": 1.0},
    ),
    ModelType.VOIGT: (
        voigt,
        {"amplitude": 1.0, "center": 0.0, "sigma": 1.0, "fraction": 0.5},
    ),
    ModelType.CONSTANT: (constant, {"c": 0.25}),
    ModelType.LINEAR: (linear, {"slope": 0.1, "intercept": 0.5}),
    ModelType.QUADRATIC: (
        quadratic,
        {"amplitude": 1.0, "center": 0.0, "offset": 0.0},
    ),
    ModelType.ARCTAN_STEP: (
        arctan_step,
        {"amplitude": 1.0, "center": 0.0, "sigma": 0.5},
    ),
    ModelType.TANH_STEP: (
        tanh_step,
        {"amplitude": 1.0, "center": 0.0, "sigma": 0.5},
    ),
    ModelType.ERFC_STEP: (
        erfc_step,
        {"amplitude": 1.0, "center": 0.0, "sigma": 0.5},
    ),
    ModelType.PSEUDO_VOIGT: (
        pseudo_voigt,
        {"amplitude": 1.0, "center": 0.0, "sigma": 1.0, "fraction": 0.4},
    ),
    ModelType.FANO: (
        fano,
        {"amplitude": 1.0, "center": 0.0, "gamma": 1.0, "q": 2.0},
    ),
    ModelType.DOUBLE_EXPONENTIAL: (
        double_exponential,
        {"A1": 1.0, "lam1": 0.3, "A2": 0.5, "lam2": 0.1},
    ),
    ModelType.TRUE_VOIGT: (
        true_voigt,
        {"amplitude": 1.0, "center": 0.0, "sigma": 1.0, "gamma": 0.5},
    ),
    ModelType.SKEWED_GAUSSIAN: (
        skewed_gaussian,
        {"amplitude": 1.0, "center": 0.0, "sigma": 1.0, "gamma": 1.0},
    ),
    ModelType.EXP_GAUSSIAN: (
        exp_gaussian,
        {"amplitude": 1.0, "center": 0.0, "sigma": 1.0, "gamma": 0.5},
    ),
    ModelType.DONIACH: (
        doniach_sunjic,
        {"amplitude": 1.0, "center": 0.0, "sigma": 1.0, "gamma": 0.1},
    ),
    ModelType.LOG_NORMAL: (
        log_normal,
        {"amplitude": 1.0, "center": 1.0, "sigma": 0.3},
    ),
    ModelType.PEARSON7: (
        pearson7,
        {"amplitude": 1.0, "center": 0.0, "sigma": 1.0, "m": 2.0},
    ),
    ModelType.SPLIT_GAUSSIAN: (
        split_gaussian,
        {"amplitude": 1.0, "center": 0.0, "sigma_l": 1.0, "sigma_r": 0.5},
    ),
    ModelType.MOFFAT: (
        moffat,
        {"amplitude": 1.0, "center": 0.0, "sigma": 1.0, "beta": 2.5},
    ),
    ModelType.STUDENTS_T: (
        students_t,
        {"amplitude": 1.0, "center": 0.0, "sigma": 1.0, "nu": 4.0},
    ),
    ModelType.SPLIT_PEARSON7: (
        split_pearson7,
        {
            "amplitude": 1.0,
            "center": 0.0,
            "sigma_l": 1.0,
            "sigma_r": 0.5,
            "m_l": 2.0,
            "m_r": 1.5,
        },
    ),
    ModelType.BREIT_WIGNER: (
        breit_wigner,
        {"amplitude": 1.0, "center": 0.0, "sigma": 1.0, "q": 2.0},
    ),
    ModelType.ASYM_IR: (
        asym_ir,
        {"amplitude": 1.0, "center": 0.0, "sigma": 1.0, "k": 0.5},
    ),
    ModelType.HARMONIC_IR: (
        harmonic_ir,
        {"amplitude": 1.0, "center": 1.0, "sigma": 0.5},
    ),
    ModelType.TAUC: (
        tauc,
        {"amplitude": 1.0, "e_gap": 1.0, "exponent": 0.5},
    ),
    ModelType.CAUCHY_DISPERSION: (
        cauchy_dispersion,
        {"a": 1.0, "b": 0.1, "c": 0.01},
    ),
    ModelType.KWW: (
        kww,
        {"amplitude": 1.0, "tau": 2.0, "beta": 0.7},
    ),
    ModelType.SATURATING_EXPONENTIAL: (
        saturating_exponential,
        {"amplitude": 2.0, "rate": 0.5},
    ),
    ModelType.POWER_SATURATION: (
        power_saturation,
        {"amplitude": 2.0, "rate": 0.5},
    ),
    ModelType.POWER_LAW_OFFSET: (
        power_law_offset,
        {"amplitude": 1.0, "offset": 1.0, "shape": 0.5},
    ),
    ModelType.MGH09_RATIONAL: (
        mgh09_rational,
        {"amplitude": 0.2, "num_lin": 0.2, "den_lin": 0.1, "den_const": 0.05},
    ),
}


# Models intentionally OUTSIDE the fixed-shape compose DSL. ``gaussian_nd`` is
# parametric (its parameters are runtime-indexed `center_0..center_{D-1}` /
# `sigma_0..`), so it has no single canonical param tuple or fixed-arity factory
# — it is constructed via explicit indexed parameters (see test_fit_nd.py), not
# the fluent DSL. The exemption is named (not silent) so the invariant still
# fails loudly for any *other* model that lacks a fixture/param table.
_DSL_EXEMPT: Final[frozenset[ModelType]] = frozenset({ModelType.GAUSSIAN_ND})


def test_every_model_type_has_a_fixture() -> None:
    """Every fixed-shape ``ModelType`` member is exercised by the fixture table."""
    missing = set(ModelType) - set(_FACTORY_FIXTURES) - _DSL_EXEMPT
    assert not missing, f"missing fixtures for {sorted(m.value for m in missing)}"


def test_every_model_type_has_a_canonical_param_table() -> None:
    """``CANONICAL_PARAMS`` covers every fixed-shape ``ModelType`` member."""
    missing = set(ModelType) - set(CANONICAL_PARAMS) - _DSL_EXEMPT
    assert not missing, (
        f"compose.CANONICAL_PARAMS missing: {sorted(m.value for m in missing)}"
    )


@pytest.mark.parametrize(
    "model_type",
    list(_FACTORY_FIXTURES),
    ids=lambda mt: mt.value,
)
def test_factory_matches_handrolled_byte_identical(model_type: ModelType) -> None:
    """Factory output equals a hand-rolled :class:`FitGraph` byte-for-byte."""
    factory, params = _FACTORY_FIXTURES[model_type]
    node_id = f"n_{model_type.value}"

    via_factory = compose([factory(id=node_id, **params)]).build()

    handrolled = FitGraph(
        nodes=[
            ModelNodeSpec(
                id=node_id,
                model_type=model_type,
                parameters={
                    name: Parameter(value=value) for name, value in params.items()
                },
            )
        ]
    )

    assert via_factory.model_dump_json() == handrolled.model_dump_json()


@pytest.mark.parametrize(
    "model_type",
    list(_FACTORY_FIXTURES),
    ids=lambda mt: mt.value,
)
def test_factory_produces_canonical_param_keys(model_type: ModelType) -> None:
    """The factory writes the canonical parameter names into the node."""
    factory, params = _FACTORY_FIXTURES[model_type]
    node = factory(id="x", **params)
    assert tuple(node.parameters) == CANONICAL_PARAMS[model_type]


# --------------------------------------------------------------------------- #
# Shorthand: a/c/s → amplitude/center/sigma
# --------------------------------------------------------------------------- #
def test_shorthand_acs_maps_to_canonical_names() -> None:
    """``gaussian(a=, c=, s=)`` matches ``gaussian(amplitude=, center=, sigma=)``."""
    short = gaussian(id="g", a=2.0, c=-0.5, s=1.5)
    full = gaussian(id="g", amplitude=2.0, center=-0.5, sigma=1.5)
    assert short.model_dump_json() == full.model_dump_json()


def test_shorthand_a_for_amplitude_propagates_to_value() -> None:
    """The shorthand sets the canonical parameter's ``value`` field."""
    node = gaussian(id="g", a=3.25, c=0.0, s=1.0)
    assert node.parameters["amplitude"].value == pytest.approx(3.25)


def test_shorthand_not_available_when_amplitude_absent() -> None:
    """``constant``'s only param is ``c`` — *not* a shorthand for ``center``."""
    # ``c=...`` is canonical here; the result has parameters={'c': ...}.
    node = constant(id="bg", c=0.75)
    assert "c" in node.parameters
    assert "center" not in node.parameters
    assert node.parameters["c"].value == pytest.approx(0.75)


def test_shorthand_a_rejected_for_cauchy_dispersion() -> None:
    """Cauchy dispersion (``a``, ``b``, ``c``) does not use the amp/centre shorthand."""
    # ``a``/``c`` here are canonical Cauchy coefficients; ``s`` is invalid.
    with pytest.raises(TypeError, match="unexpected keyword 's'"):
        cauchy_dispersion(id="d", a=1.0, b=0.1, c=0.01, s=1.0)


# --------------------------------------------------------------------------- #
# Bound propagation
# --------------------------------------------------------------------------- #
def test_bounds_via_canonical_suffix_propagate_to_parameter() -> None:
    """``amplitude_min`` / ``amplitude_max`` reach ``Parameter(min=, max=)``."""
    node = gaussian(
        id="g",
        amplitude=1.0,
        center=0.0,
        sigma=1.0,
        amplitude_min=0.0,
        amplitude_max=10.0,
    )
    assert node.parameters["amplitude"].min == pytest.approx(0.0)
    assert node.parameters["amplitude"].max == pytest.approx(10.0)


def test_bounds_via_shorthand_suffix_propagate_to_parameter() -> None:
    """``a_min`` / ``a_max`` reach the underlying amplitude :class:`Parameter`."""
    node = gaussian(id="g", a=1.0, c=0.0, s=1.0, a_min=0.0, a_max=10.0)
    assert node.parameters["amplitude"].min == pytest.approx(0.0)
    assert node.parameters["amplitude"].max == pytest.approx(10.0)


def test_vary_and_expr_suffixes_propagate() -> None:
    """``<param>_vary`` / ``<param>_expr`` reach ``Parameter.vary`` / ``.expr``."""
    node = gaussian(
        id="g",
        a=1.0,
        c=0.0,
        s=1.0,
        center_vary=False,
        amplitude_expr="other.amplitude",
    )
    assert node.parameters["center"].vary is False
    # ``vary`` is preserved as supplied; the engine ignores it when ``expr`` is set.
    assert node.parameters["amplitude"].expr == "other.amplitude"
    # amplitude_vary was not supplied, so the default (True) is preserved.
    assert node.parameters["amplitude"].vary is True


def test_canonical_and_shorthand_collision_is_rejected() -> None:
    """Passing both ``amplitude=`` and ``a=`` raises a clear error."""
    with pytest.raises(TypeError, match="duplicate value"):
        gaussian(id="g", a=1.0, amplitude=2.0, c=0.0, s=1.0)


def test_missing_required_param_raises() -> None:
    """A factory call missing a canonical param raises with the param name."""
    with pytest.raises(TypeError, match="missing required parameter 'sigma'"):
        gaussian(id="g", a=1.0, c=0.0)


def test_unknown_kwarg_raises() -> None:
    """An unknown keyword is rejected before any FitGraph is built."""
    with pytest.raises(TypeError, match="unexpected keyword"):
        gaussian(id="g", a=1.0, c=0.0, s=1.0, totally_made_up=3.14)


def test_default_bounds_are_infinite() -> None:
    """Unspecified bounds remain ``±inf`` (the :class:`Parameter` default)."""
    node = gaussian(id="g", a=1.0, c=0.0, s=1.0)
    p = node.parameters["amplitude"]
    assert math.isinf(p.min) and p.min < 0
    assert math.isinf(p.max) and p.max > 0


# --------------------------------------------------------------------------- #
# Compose builder & bind()
# --------------------------------------------------------------------------- #
def test_compose_returns_builder() -> None:
    """``compose()`` returns a :class:`ComposeBuilder`."""
    builder = compose([gaussian(id="g", a=1.0, c=0.0, s=1.0)])
    assert isinstance(builder, ComposeBuilder)


def test_compose_builder_iter_yields_nodes() -> None:
    """``ComposeBuilder`` is iterable over its model nodes."""
    nodes = [
        gaussian(id="g", a=1.0, c=0.0, s=1.0),
        lorentzian(id="l", a=0.5, c=2.0, s=0.3),
    ]
    builder = compose(nodes)
    assert list(builder) == nodes


def test_fitgraph_accepts_builder_directly_via_iter() -> None:
    """``FitGraph(nodes=compose([...]))`` works because the builder is iterable."""
    nodes = [gaussian(id="g", a=1.0, c=0.0, s=1.0)]
    via_compose = FitGraph(nodes=compose(nodes))
    via_handrolled = FitGraph(nodes=nodes)
    assert via_compose.model_dump_json() == via_handrolled.model_dump_json()


def test_build_returns_validated_fitgraph() -> None:
    """``.build()`` returns a :class:`FitGraph` instance."""
    graph = compose([gaussian(id="g", a=1.0, c=0.0, s=1.0)]).build()
    assert isinstance(graph, FitGraph)
    assert [n.id for n in graph.nodes] == ["g"]
    assert graph.expr_edges == []


def test_bind_adds_one_expr_edge() -> None:
    """A single :meth:`bind` call appends a matching :class:`ExprEdge`."""
    graph = (
        compose(
            [
                gaussian(id="g0", a=1.0, c=0.0, s=1.0),
                gaussian(id="g1", a=1.0, c=2.0, s=1.0),
            ]
        )
        .bind("g0.sigma", to="g1.sigma")
        .build()
    )
    assert graph.expr_edges == [
        ExprEdge(target_node="g1", target_param="sigma", expression="g0.sigma")
    ]


def test_bind_accepts_positional_to() -> None:
    """``bind("expr", "node.param")`` works without a ``to=`` keyword."""
    graph = (
        compose(
            [
                gaussian(id="g0", a=1.0, c=0.0, s=1.0),
                gaussian(id="g1", a=1.0, c=2.0, s=1.0),
            ]
        )
        .bind("g0.sigma", "g1.sigma")
        .build()
    )
    assert graph.expr_edges == [
        ExprEdge(target_node="g1", target_param="sigma", expression="g0.sigma")
    ]


def test_bind_is_chainable_and_preserves_order() -> None:
    """Multiple :meth:`bind` calls compose into an ordered list."""
    graph = (
        compose(
            [
                gaussian(id="g0", a=1.0, c=0.0, s=1.0),
                gaussian(id="g1", a=1.0, c=2.0, s=1.0),
                gaussian(id="g2", a=1.0, c=4.0, s=1.0),
            ]
        )
        .bind("g0.sigma", to="g1.sigma")
        .bind("g0.sigma", to="g2.sigma")
        .build()
    )
    assert [
        (e.target_node, e.target_param, e.expression) for e in graph.expr_edges
    ] == [
        ("g1", "sigma", "g0.sigma"),
        ("g2", "sigma", "g0.sigma"),
    ]


def test_bind_rejects_malformed_target() -> None:
    """``bind(to=…)`` requires a ``"node_id.param"`` target."""
    builder = compose([gaussian(id="g", a=1.0, c=0.0, s=1.0)])
    with pytest.raises(ValueError, match="'node_id.param'"):
        builder.bind("g.sigma", to="g_only")


def test_build_validates_unknown_target_node() -> None:
    """``FitGraph`` validation rejects a bind that references a missing node."""
    builder = compose([gaussian(id="g", a=1.0, c=0.0, s=1.0)]).bind(
        "g.sigma", to="ghost.sigma"
    )
    with pytest.raises(Exception, match="unknown target node"):
        builder.build()


# --------------------------------------------------------------------------- #
# Backward compatibility
# --------------------------------------------------------------------------- #
def test_factory_node_drops_into_legacy_fitgraph_ctor() -> None:
    """``FitGraph(nodes=[gaussian(...)])`` works without any builder."""
    graph = FitGraph(nodes=[gaussian(id="g0", a=1.0, c=0.0, s=1.0)])
    assert isinstance(graph, FitGraph)
    assert graph.nodes[0].model_type is ModelType.GAUSSIAN


def test_multi_node_compose_matches_handrolled() -> None:
    """A 2-node Gaussian + Lorentzian composition round-trips byte-identically."""
    via_compose = compose(
        [
            gaussian(id="g0", a=1.0, c=0.0, s=1.0),
            lorentzian(id="l0", a=0.5, c=2.0, s=0.3),
        ]
    ).build()
    via_handrolled = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g0",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0),
                    "center": Parameter(value=0.0),
                    "sigma": Parameter(value=1.0),
                },
            ),
            ModelNodeSpec(
                id="l0",
                model_type=ModelType.LORENTZIAN,
                parameters={
                    "amplitude": Parameter(value=0.5),
                    "center": Parameter(value=2.0),
                    "sigma": Parameter(value=0.3),
                },
            ),
        ]
    )
    assert via_compose.model_dump_json() == via_handrolled.model_dump_json()


def test_dataset_index_is_forwarded() -> None:
    """``dataset_index=`` reaches :class:`ModelNodeSpec.dataset_index`."""
    node = pseudo_voigt(id="p", a=1.0, c=0.0, s=1.0, fraction=0.5, dataset_index=3)
    assert node.dataset_index == 3


# --------------------------------------------------------------------------- #
# Canonical-param table is in lock-step with the bench-registry oracle
# (skipped when the optional benchmark extra is not installed).
# --------------------------------------------------------------------------- #
def test_compose_param_names_match_bench_registry() -> None:
    """Cross-check ``CANONICAL_PARAMS`` against ``oracles.models.MODEL_REGISTRY``.

    The bench registry is the parity oracle for Rust kernel shapes.  When the
    optional ``benchmark`` extra is installed, the canonical parameter names
    must agree (``gaussian2d`` is registry-absent and skipped).
    """
    pytest.importorskip("lmfit")  # benchmark extra; skip on slim installs
    try:
        from oracles.models import MODEL_REGISTRY  # noqa: PLC0415
    except ImportError:
        pytest.skip("benchmark extra not on PYTHONPATH")

    for model_type, expected in CANONICAL_PARAMS.items():
        if model_type is ModelType.GAUSSIAN2D:
            continue  # 2-D model is not in the 1-D bench registry
        peak = MODEL_REGISTRY[model_type.value]
        assert peak.param_names == expected, (
            f"{model_type.value}: compose says {expected}, "
            f"bench registry says {peak.param_names}"
        )
