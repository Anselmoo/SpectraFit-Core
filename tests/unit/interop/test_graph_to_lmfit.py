"""Graph JSON executed by lmfit: ``reproducibility/interop/graph_to_lmfit.py`` (#93).

The translator reads a ``FitGraph`` JSON file and builds the same model in lmfit. These
tests pin the acceptance of package 08, fixed before the translator was written (see
``reproducibility/interop/README.md``, "Acceptance measures"):

* round trip per kernel with an lmfit counterpart: at the same parameters the translated
  lmfit model equals ``spectrafit_core.evaluate`` to $10^{-10}$ relative in the max norm;
* kernels without a counterpart, edges outside the expression grammar and graph features
  lmfit cannot carry raise with their name; nothing is dropped;
* the translator never imports the Python graph objects.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
from oracles.models import MODEL_REGISTRY
from spectrafit_core import (
    ExprEdge,
    FitGraph,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    evaluate,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
TRANSLATOR = REPO_ROOT / "reproducibility" / "interop" / "graph_to_lmfit.py"
REL_TOL = 1e-10


def _load_translator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("graph_to_lmfit", TRANSLATOR)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["graph_to_lmfit"] = module
    spec.loader.exec_module(module)
    return module


g2l = _load_translator()

# One point per kernel inside its documented parameter domain.
POINTS: dict[str, dict[str, float]] = {
    "constant": {"c": 2.5},
    "linear": {"slope": 0.7, "intercept": -1.3},
    "quadratic": {"amplitude": 0.3, "center": 2.0, "offset": -1.0},
    "gaussian": {"amplitude": 3.0, "center": 4.0, "sigma": 1.3},
    "lorentzian": {"amplitude": 3.0, "center": 4.0, "sigma": 1.3},
    "voigt": {"amplitude": 3.0, "center": 4.0, "sigma": 1.3, "fraction": 0.35},
    "pseudo_voigt": {"amplitude": 3.0, "center": 4.0, "sigma": 1.3, "fraction": 0.35},
    "arctan_step": {"amplitude": 2.0, "center": 4.0, "sigma": 0.8},
    "tanh_step": {"amplitude": 2.0, "center": 4.0, "sigma": 0.8},
    "erfc_step": {"amplitude": 2.0, "center": 4.0, "sigma": 0.8},
    "fano": {"amplitude": 1.5, "center": 4.0, "gamma": 0.9, "q": 1.7},
    "breit_wigner": {"amplitude": 1.5, "center": 4.0, "sigma": 0.9, "q": 1.7},
    "double_exponential": {"A1": 3.0, "lam1": 0.4, "A2": 1.2, "lam2": 0.05},
    "saturating_exponential": {"amplitude": 4.0, "rate": 0.3},
    "skewed_gaussian": {"amplitude": 3.0, "center": 4.0, "sigma": 1.3, "gamma": 2.0},
    "exp_gaussian": {"amplitude": 3.0, "center": 4.0, "sigma": 1.0, "gamma": 0.8},
    "doniach_sunjic": {"amplitude": 3.0, "center": 4.0, "sigma": 0.9, "gamma": 0.2},
    "pearson7": {"amplitude": 3.0, "center": 4.0, "sigma": 1.1, "m": 1.8},
    "moffat": {"amplitude": 3.0, "center": 4.0, "sigma": 1.1, "beta": 1.6},
    "cauchy_dispersion": {"a": 1.5, "b": 0.01, "c": 0.0002},
}
# ``cauchy_dispersion`` is documented for wavelengths ``x > 0`` only.
GRIDS = {"cauchy_dispersion": np.linspace(0.3, 2.0, 341)}
DEFAULT_GRID = np.linspace(-5.0, 15.0, 401)


def _alternative(point: dict[str, float]) -> dict[str, float]:
    """A second point per kernel, still inside every documented domain."""
    return {k: 1.37 * v + 0.11 for k, v in point.items()}


def _write(graph: FitGraph | dict, tmp_path: Path, name: str = "graph.json") -> Path:
    path = tmp_path / name
    text = graph.model_dump_json() if isinstance(graph, FitGraph) else json.dumps(graph)
    path.write_text(text)
    return path


def _sfc_values(translation, values: dict[str, float]) -> dict[str, float]:
    """Map lmfit parameter values back to ``node.param`` keys."""
    return {key: values[name] for key, name in translation.names.items()}


def _gap(f_lmfit: np.ndarray, f_sfc: np.ndarray) -> float:
    return float(np.max(np.abs(f_lmfit - f_sfc)) / np.max(np.abs(f_sfc)))


# ---------------------------------------------------------------- coverage lists


def test_kernel_lists_cover_every_model_type_once() -> None:
    mapped, unmapped = set(g2l.KERNELS), set(g2l.UNMAPPED)
    assert not mapped & unmapped
    assert mapped | unmapped == {m.value for m in ModelType}
    assert mapped == set(POINTS)


def test_kernel_parameter_names_match_the_oracle_registry() -> None:
    by_type = {ModelType[m.spectrafit_type].value: m for m in MODEL_REGISTRY.values()}
    checked = 0
    for name, kernel in g2l.KERNELS.items():
        if name in by_type:
            assert tuple(kernel.params) == tuple(by_type[name].param_names), name
            checked += 1
    assert checked >= 15


def test_translator_does_not_import_spectrafit_core() -> None:
    tree = ast.parse(TRANSLATOR.read_text())
    imported = set()
    for node in ast.walk(tree):
        match node:
            case ast.Import(names=names):
                imported |= {a.name.split(".")[0] for a in names}
            case ast.ImportFrom(module=module) if module:
                imported.add(module.split(".")[0])
    assert "spectrafit_core" not in imported
    assert "oracles" not in imported


# ---------------------------------------------------------------- round trip (acceptance 2)


@pytest.mark.parametrize("variant", ["point", "alternative"])
@pytest.mark.parametrize("kernel", sorted(POINTS))
def test_round_trip_per_kernel(kernel: str, variant: str, tmp_path: Path) -> None:
    point = POINTS[kernel] if variant == "point" else _alternative(POINTS[kernel])
    node = ModelNodeSpec(
        id="n0",
        model_type=ModelType(kernel),
        parameters={k: Parameter(value=v) for k, v in point.items()},
    )
    graph = FitGraph(nodes=[node])
    translation = g2l.translate_file(_write(graph, tmp_path))
    x = GRIDS.get(kernel, DEFAULT_GRID)
    f_lmfit = translation.model.eval(translation.params, x=x)
    f_sfc = np.asarray(
        evaluate(
            graph,
            {f"n0.{k}": v for k, v in point.items()},
            MeasurementData(x=x.tolist(), y=x.tolist()),
        ),
    )
    assert np.all(np.isfinite(f_sfc))
    assert _gap(f_lmfit, f_sfc) <= REL_TOL, f"{kernel}: {_gap(f_lmfit, f_sfc):.3g}"


def _composite() -> FitGraph:
    def node(nid: str, kernel: str, **values: float | Parameter) -> ModelNodeSpec:
        params = {
            k: v if isinstance(v, Parameter) else Parameter(value=v) for k, v in values.items()
        }
        return ModelNodeSpec(id=nid, model_type=ModelType(kernel), parameters=params)

    return FitGraph(
        nodes=[
            node("bg", "constant", c=0.4),
            node("s3", "arctan_step", amplitude=2.0, center=4.0, sigma=0.7),
            node("s2", "arctan_step", amplitude=1.0, center=9.0, sigma=0.7),
            node("g1", "gaussian", amplitude=3.0, center=4.2, sigma=0.9),
            node(
                "g2",
                "lorentzian",
                amplitude=1.0,
                center=9.5,
                sigma=Parameter(value=1.0, expr="-(g1.sigma) * -2 / (1 + g1 . amplitude)"),
            ),
        ],
        expr_edges=[
            ExprEdge(target_node="s2", target_param="amplitude", expression="s3.amplitude / 2"),
            ExprEdge(target_node="s2", target_param="sigma", expression="s3.sigma"),
            ExprEdge(target_node="s3", target_param="center", expression="g1.center"),
            ExprEdge(
                target_node="s2",
                target_param="center",
                expression="g1.center + 5 - 0.5 * (g1.sigma + 1e-1)",
            ),
            ExprEdge(target_node="g2", target_param="amplitude", expression="s2.amplitude * 3"),
        ],
    )


def _reference_ties(graph: FitGraph, values: dict[str, float]) -> dict[str, float]:
    """Evaluate every tie with Python's own arithmetic, independent of the translator."""
    ties = {f"{e.target_node}.{e.target_param}": e.expression for e in graph.expr_edges}
    for n in graph.nodes:
        ties |= {f"{n.id}.{k}": p.expr for k, p in n.parameters.items() if p.expr}
    out = dict(values)
    for _ in ties:  # enough passes for any dependency chain
        nodes: dict[str, SimpleNamespace] = {}
        for key, value in out.items():
            nid, pname = key.split(".", 1)
            setattr(nodes.setdefault(nid, SimpleNamespace()), pname, value)
        for target, expression in ties.items():
            # The expressions are the literals of ``_composite`` above, evaluated with no
            # builtins: a reference that does not go through the translator's parser.
            out[target] = eval(expression.replace(" . ", "."), {"__builtins__": {}}, nodes)
    return out


def test_round_trip_composite_with_edges_and_parameter_expr(tmp_path: Path) -> None:
    graph = _composite()
    translation = g2l.translate_file(_write(graph, tmp_path))
    values = _sfc_values(translation, translation.params.valuesdict())
    reference = _reference_ties(graph, values)
    for key, want in reference.items():
        assert values[key] == pytest.approx(want, rel=1e-15, abs=0.0), key
    x = DEFAULT_GRID
    f_lmfit = translation.model.eval(translation.params, x=x)
    f_sfc = np.asarray(evaluate(graph, values, MeasurementData(x=x.tolist(), y=x.tolist())))
    assert _gap(f_lmfit, f_sfc) <= REL_TOL
    tied = {"s2.amplitude", "s2.sigma", "s3.center", "s2.center", "g2.amplitude", "g2.sigma"}
    for key in tied:
        par = translation.params[translation.names[key]]
        assert par.expr is not None, key
        assert par.min == -np.inf, key
        assert par.max == np.inf, key


def test_source_is_the_code_that_runs(tmp_path: Path) -> None:
    translation = g2l.translate_file(_write(_composite(), tmp_path))
    assert translation.source.count(".set(expr=") == 6
    model, params = g2l.execute_source(translation.source)
    x = DEFAULT_GRID
    np.testing.assert_array_equal(
        model.eval(params, x=x),
        translation.model.eval(translation.params, x=x),
    )


def test_fixed_and_bounded_parameters_carry_over(tmp_path: Path) -> None:
    node = ModelNodeSpec(
        id="g",
        model_type=ModelType.GAUSSIAN,
        parameters={
            "amplitude": Parameter(value=2.0, min=0.0),
            "center": Parameter(value=1.0, min=-3.0, max=3.0),
            "sigma": Parameter(value=0.5, vary=False),
        },
    )
    translation = g2l.translate_file(_write(FitGraph(nodes=[node]), tmp_path))
    p = translation.params
    assert (p["g__amplitude"].min, p["g__amplitude"].max) == (0.0, np.inf)
    assert (p["g__center"].min, p["g__center"].max) == (-3.0, 3.0)
    assert p["g__sigma"].vary is False
    assert p["g__amplitude"].vary is True


def test_scale_and_tied_bounds_are_recorded_in_notes(tmp_path: Path) -> None:
    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="a",
                model_type=ModelType.CONSTANT,
                parameters={"c": Parameter(value=1.0, scale=10.0)},
            ),
            ModelNodeSpec(
                id="b",
                model_type=ModelType.CONSTANT,
                parameters={"c": Parameter(value=0.5, min=0.0, max=1.0)},
            ),
        ],
        expr_edges=[ExprEdge(target_node="b", target_param="c", expression="a.c / 2")],
    )
    notes = " ".join(g2l.translate_file(_write(graph, tmp_path)).notes)
    assert "a.c" in notes
    assert "scale" in notes
    assert "b.c" in notes
    assert "bounds" in notes


# ---------------------------------------------------------------- refusals (acceptance 1)


@pytest.mark.parametrize("kernel", sorted(g2l.UNMAPPED))
def test_kernel_without_counterpart_raises_with_its_name(kernel: str, tmp_path: Path) -> None:
    node = ModelNodeSpec(
        id="peak7",
        model_type=ModelType(kernel),
        parameters={"amplitude": Parameter(value=1.0)},
    )
    with pytest.raises(g2l.TranslationError) as info:
        g2l.translate_file(_write(FitGraph(nodes=[node]), tmp_path))
    assert kernel in str(info.value)
    assert "peak7" in str(info.value)


BAD_EXPRESSIONS = [
    "exp(g1.sigma)",
    "g1.sigma ** 2",
    "g1.sigma ^ 2",
    "g1",
    "g1.sigma *",
    "(g1.sigma",
    "g1.sigma)",
    ".5 * g1.sigma",
    "g1.width",
    "g1.sigma, 2",
]


def _two_gaussians(edge: ExprEdge | None = None, expr: str | None = None) -> FitGraph:
    g1 = ModelNodeSpec(
        id="g1",
        model_type=ModelType.GAUSSIAN,
        parameters={k: Parameter(value=1.0) for k in ("amplitude", "center", "sigma")},
    )
    g2 = ModelNodeSpec(
        id="g2",
        model_type=ModelType.GAUSSIAN,
        parameters={
            "amplitude": Parameter(value=1.0, expr=expr),
            "center": Parameter(value=2.0),
            "sigma": Parameter(value=1.0),
        },
    )
    return FitGraph(nodes=[g1, g2], expr_edges=[edge] if edge else [])


@pytest.mark.parametrize("expression", BAD_EXPRESSIONS)
def test_edge_outside_the_grammar_raises_with_its_name(expression: str, tmp_path: Path) -> None:
    edge = ExprEdge(target_node="g2", target_param="amplitude", expression=expression)
    with pytest.raises(g2l.TranslationError) as info:
        g2l.translate_file(_write(_two_gaussians(edge=edge), tmp_path))
    assert "g2.amplitude" in str(info.value)
    assert expression in str(info.value)


@pytest.mark.parametrize("expression", BAD_EXPRESSIONS[:3])
def test_parameter_expr_outside_the_grammar_raises(expression: str, tmp_path: Path) -> None:
    with pytest.raises(g2l.TranslationError) as info:
        g2l.translate_file(_write(_two_gaussians(expr=expression), tmp_path))
    assert "g2.amplitude" in str(info.value)


def test_duplicate_tie_raises(tmp_path: Path) -> None:
    edge = ExprEdge(target_node="g2", target_param="amplitude", expression="g1.amplitude")
    with pytest.raises(g2l.TranslationError, match=r"g2\.amplitude"):
        g2l.translate_file(_write(_two_gaussians(edge=edge, expr="g1.sigma"), tmp_path))


def _gaussian_json(**node_extra: object) -> dict:
    node = ModelNodeSpec(
        id="g1",
        model_type=ModelType.GAUSSIAN,
        parameters={k: Parameter(value=1.0) for k in ("amplitude", "center", "sigma")},
    )
    data = json.loads(FitGraph(nodes=[node]).model_dump_json())
    data["nodes"][0].update(node_extra)
    return data


@pytest.mark.parametrize(
    ("mutate", "needle"),
    [
        (lambda d: d.update(schema_version="0.2"), "schema_version"),
        (lambda d: d.update(colour="red"), "colour"),
        (lambda d: d["nodes"][0].update(dataset_index=1), "g1"),
        (lambda d: d["nodes"][0].update(id="peak-1"), "peak-1"),
        (lambda d: d["nodes"][0].update(weight=2), "weight"),
        (lambda d: d["nodes"][0]["parameters"]["sigma"].update(stderr=0.1), "stderr"),
        (lambda d: d["nodes"][0]["parameters"].update(width={"value": 1.0}), "g1.width"),
        (lambda d: d["nodes"][0]["parameters"].pop("sigma"), "g1.sigma"),
        (lambda d: d["nodes"][0].update(model_type="sinc"), "sinc"),
        (lambda d: d.update(nodes=[]), "no nodes"),
    ],
)
def test_graph_features_lmfit_cannot_carry_raise(mutate, needle: str, tmp_path: Path) -> None:
    data = _gaussian_json()
    mutate(data)
    with pytest.raises(g2l.TranslationError) as info:
        g2l.translate_file(_write(data, tmp_path))
    assert needle in str(info.value)


def test_null_bounds_read_as_unbounded(tmp_path: Path) -> None:
    data = _gaussian_json()
    data["nodes"][0]["parameters"]["sigma"].update(min=None, max=None)
    p = g2l.translate_file(_write(data, tmp_path)).params["g1__sigma"]
    assert (p.min, p.max) == (-np.inf, np.inf)
