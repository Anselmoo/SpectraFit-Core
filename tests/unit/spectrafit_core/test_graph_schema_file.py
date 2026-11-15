"""The shipped graph JSON Schema matches ``FitGraph.model_json_schema()`` (#93).

``python/spectrafit_core/graph.schema.json`` is written by
``scripts/export_graph_schema.py``. A change to ``FitGraph``, ``ModelNodeSpec``,
``Parameter``, ``ExprEdge`` or ``ModelType`` that is not followed by
``uv run python scripts/export_graph_schema.py`` fails here.
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
from types import ModuleType

import jsonschema
import pytest
from jsonschema.protocols import Validator
from spectrafit_core import FitGraph, ModelNodeSpec, ModelType, Parameter

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "export_graph_schema.py"
SCHEMA = REPO_ROOT / "python" / "spectrafit_core" / "graph.schema.json"
EELS_GRAPH = REPO_ROOT / "reproducibility" / "interop" / "fe_l23_constrained.graph.json"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_export_graph_schema", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema_file_is_current() -> None:
    script = _load_script()
    assert script.SCHEMA_PATH == SCHEMA
    assert SCHEMA.read_text(encoding="utf-8") == script.render(), (
        "graph.schema.json is stale: run `uv run python scripts/export_graph_schema.py`"
    )


def test_schema_file_is_strict_json_of_the_fit_graph() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"), parse_constant=_reject)
    assert schema["title"] == "FitGraph"
    assert {"ModelNodeSpec", "Parameter", "ExprEdge", "ModelType"} <= set(schema["$defs"])
    assert (
        schema["properties"]["schema_version"]["default"]
        == FitGraph.model_fields["schema_version"].default
    )


def test_check_mode_reports_a_stale_file(tmp_path: Path) -> None:
    script = _load_script()
    stale = tmp_path / "graph.schema.json"
    stale.write_text("{}\n", encoding="utf-8")
    assert script.main(["--check", "--path", str(stale)]) == 1
    assert script.main(["--path", str(stale)]) == 0
    assert script.main(["--check", "--path", str(stale)]) == 0


def _reject(token: str) -> float:
    msg = f"non-standard JSON constant {token} in graph.schema.json"
    raise ValueError(msg)


def _validator() -> Validator:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def _unbounded_graph() -> FitGraph:
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g1",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0, min=0.0),
                    "center": Parameter(value=0.0),
                    "sigma": Parameter(value=1.0, max=5.0),
                },
            ),
        ],
    )


def test_shipped_eels_graph_validates_against_the_schema() -> None:
    graph = json.loads(EELS_GRAPH.read_text(encoding="utf-8"))
    _validator().validate(graph)


@pytest.mark.parametrize("bound", ["min", "max"])
def test_bound_schema_is_number_or_null_with_default_and_description(bound: str) -> None:
    prop = json.loads(SCHEMA.read_text(encoding="utf-8"))["$defs"]["Parameter"]["properties"][bound]
    assert prop["anyOf"] == [{"type": "number"}, {"type": "null"}]
    assert "default" in prop
    assert prop["default"] is None
    assert prop["description"]


@pytest.mark.parametrize("bound", ["min", "max"])
def test_non_numeric_bound_is_rejected(bound: str) -> None:
    graph = json.loads(_unbounded_graph().model_dump_json())
    graph["nodes"][0]["parameters"]["center"][bound] = "unbounded"
    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(graph)


def test_unbounded_graph_round_trips_through_the_schema() -> None:
    original = _unbounded_graph()
    wire = original.model_dump_json()
    _validator().validate(json.loads(wire))
    restored = FitGraph.model_validate_json(wire)
    params = restored.nodes[0].parameters
    assert params["center"].min == -math.inf
    assert params["center"].max == math.inf
    assert params["amplitude"].max == math.inf
    assert params["sigma"].min == -math.inf
    assert restored == original
