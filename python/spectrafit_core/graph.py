"""Fit-graph contracts: model topology, expression edges, and global fits."""

from __future__ import annotations

import json
import re
from importlib import import_module
from collections.abc import Mapping
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .data import MeasurementData, MeasurementInput, dump_measurement_json
from .models import ModelNodeSpec
from .result import FitResult

_NODE_REF_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.[A-Za-z_][A-Za-z0-9_]*\b")


def _to_jsonable(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        # `value.tolist()` overload is incomplete in the numpy typeshed for
        # arrays of object dtype; safe because the isinstance narrows value.
        return [
            _to_jsonable(item)
            for item in value.tolist()  # ty: ignore[no-matching-overload]
        ]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


def _dump_params_json(params: Mapping[str, object]) -> str:
    return json.dumps(_to_jsonable(params))


class ExprEdge(BaseModel):
    """A directed expression edge that constrains one parameter to a formula.

    Args:
        target_node: ID of the node whose parameter is constrained.
        target_param: Name of the parameter to constrain.
        expression: Formula referencing other node params as ``node_id.param``.

    Note:
        Expression edges are validated for cycles and unknown nodes at
        construction time.  The engine parses them into a dependency-ordered,
        cycle-checked plan (a DAG) and evaluates them per solver iteration, so
        ``fit()`` applies the tie during fitting — they are not rejected.

    """

    target_node: str
    target_param: str
    expression: str

    model_config = ConfigDict(extra="forbid")


class FitGraph(BaseModel):
    """A directed acyclic graph specifying the model topology for a fit.

    Args:
        schema_version: IR schema version string (default ``"0.1"``).
        nodes: Ordered list of model nodes (each with a unique ``id``).
        expr_edges: Optional parameter-constraint edges.  Must form a DAG.

    Note:
        The Rust engine parses ``expr_edges`` into a dependency-ordered,
        cycle-checked plan (``CompiledGraph.tied_plan``) and the LM/TRF solver
        loop applies that plan per iteration, so calling ``fit()`` with
        non-empty ``expr_edges`` evaluates the tied parameters during the fit.
        Per-parameter ``Parameter.expr`` is an equivalent constraint surface:
        both ``expr_edges`` and ``Parameter.expr`` are validated for cycles and
        unknown nodes at construction time and evaluated identically at fit-time.

    """

    schema_version: str = "0.1"
    nodes: list[ModelNodeSpec]
    expr_edges: list[ExprEdge] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate_graph(self) -> "FitGraph":
        node_ids = [node.id for node in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("node ids must be unique")

        known = set(node_ids)
        adjacency = {node_id: set() for node_id in known}
        for edge in self.expr_edges:
            if edge.target_node not in known:
                raise ValueError(f"unknown target node: {edge.target_node}")
            for source_node in _NODE_REF_RE.findall(edge.expression):
                if source_node not in known:
                    raise ValueError(
                        f"unknown source node in expression: {source_node}"
                    )
                adjacency[source_node].add(edge.target_node)

        # Also validate per-parameter ``Parameter.expr`` constraints so both
        # constraint surfaces (``expr_edges`` and ``Parameter.expr``) are
        # checked identically at construction time — not deferred to fit()-time.
        for node in self.nodes:
            for param in node.parameters.values():
                if param.expr is None:
                    continue
                for source_node in _NODE_REF_RE.findall(param.expr):
                    if source_node not in known:
                        raise ValueError(
                            f"unknown source node in expression: {source_node}"
                        )
                    adjacency[source_node].add(node.id)

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visited:
                return
            if node_id in visiting:
                raise ValueError("FitGraph must be acyclic")
            visiting.add(node_id)
            for child in adjacency[node_id]:
                visit(child)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in node_ids:
            visit(node_id)
        return self

    def compile(self) -> "FitGraph":
        """Return this graph unchanged (validation happens at construction)."""
        return self

    def eval(self, params: Mapping[str, object], data: MeasurementInput) -> np.ndarray:
        """Evaluate the summed model over ``data`` at the given parameters."""
        core = import_module("spectrafit_core._core")
        result_json = core.evaluate(
            self.model_dump_json(),
            _dump_params_json(params),
            dump_measurement_json(data),
        )
        return np.asarray(json.loads(result_json), dtype=float)

    def eval_components(
        self, params: Mapping[str, object], data: MeasurementInput
    ) -> dict[str, np.ndarray]:
        """Evaluate each node separately, returning per-node model arrays."""
        core = import_module("spectrafit_core._core")
        result_json = core.evaluate_components(
            self.model_dump_json(),
            _dump_params_json(params),
            dump_measurement_json(data),
        )
        payload = json.loads(result_json)
        return {
            node_id: np.asarray(values, dtype=float)
            for node_id, values in payload.items()
        }


class GlobalFitGraph(BaseModel):
    """Multi-dataset graph with globally shared and locally free parameters.

    Use this when you have multiple datasets that share the same peak positions
    and widths (globally shared) but have independent amplitudes or other
    per-dataset parameters (locally free).  A typical use case is time-resolved
    spectroscopy: N spectra at different time points, all sharing peak centers
    and widths, with amplitudes that evolve over time.

    Args:
        global_nodes: Nodes whose parameters are shared across **all** datasets.
            Each node appears once in the assembled ``FitGraph``.
        local_nodes: Nodes whose parameters are **replicated per dataset**.
            Each local node ``id`` gains a slice-index suffix
            ``"{id}_s{i}"`` (0-based) in the assembled graph.
        n_slices: Number of dataset slices to replicate local nodes for.
        schema_version: IR schema version string (default ``"0.1"``).

    Example:
        >>> g = GlobalFitGraph(
        ...     global_nodes=[ModelNodeSpec(id="peak", model_type="gaussian",
        ...                                 parameters={...})],
        ...     local_nodes=[ModelNodeSpec(id="bg", model_type="constant",
        ...                               parameters={...})],
        ...     n_slices=10,
        ... )
        >>> flat = g.to_fit_graph()  # returns a standard FitGraph

    """

    schema_version: str = "0.1"
    global_nodes: list[ModelNodeSpec]
    local_nodes: list[ModelNodeSpec]
    n_slices: int = Field(ge=1)
    shared_local_params: list[str] | dict[str, list[str]] = Field(default_factory=list)
    """Local-node parameter names **shared (tied) across slices** — per-*parameter*
    global analysis (the lmfit ``fit_multi_datasets`` pattern, e.g. ``["sigma"]``
    to share peak width while amplitude/center stay per-dataset).

    Two forms:

    * a flat ``list[str]`` — applied to **every** local node that has the named
      params (e.g. ``["sigma"]``); or
    * a ``{local_node_id: [param_names]}`` mapping — **per-node** control (e.g.
      ``{"peak": ["sigma"], "bg": []}``), so different local nodes can share
      different parameters.

    Implemented by tying each slice ``i≥1`` replica's parameter to slice 0's via
    an ``expr_edge``, so the shared value is optimised jointly over all datasets.
    Names absent on a node, or non-varying, are ignored. Use ``global_nodes`` to
    share *every* parameter of a node."""

    model_config = ConfigDict(extra="forbid")

    def to_fit_graph(self) -> FitGraph:
        """Assemble a flat ``FitGraph`` by replicating local nodes per slice.

        Returns:
            A ``FitGraph`` with global nodes followed by ``n_slices`` copies of
            each local node.  Local node ids are suffixed ``"_s{i}"`` (e.g.
            ``"bg_s0"``, ``"bg_s1"`` …), each ``dataset_index``-scoped to its
            slice.  Any :attr:`shared_local_params` are tied across slices via
            ``expr_edges`` (slice ``i≥1`` follows slice 0), giving
            per-*parameter* global analysis.

        """
        import copy

        nodes: list[ModelNodeSpec] = list(self.global_nodes)
        for i in range(self.n_slices):
            for local in self.local_nodes:
                replica = copy.deepcopy(local)
                replica = replica.model_copy(
                    update={"id": f"{local.id}_s{i}", "dataset_index": i}
                )
                nodes.append(replica)

        # Per-parameter sharing: tie each shared local param across slices so it
        # is optimised jointly (slice i≥1 references slice 0's value). Accept a
        # flat list (all local nodes) or a {node_id: [params]} per-node mapping.
        shared = self.shared_local_params
        edges: list[ExprEdge] = []
        for local in self.local_nodes:
            names = shared if isinstance(shared, list) else shared.get(local.id, [])
            for pname in names:
                ps = local.parameters.get(pname)
                if ps is None or not getattr(ps, "vary", True):
                    continue
                for i in range(1, self.n_slices):
                    edges.append(
                        ExprEdge(
                            target_node=f"{local.id}_s{i}",
                            target_param=pname,
                            expression=f"{local.id}_s0.{pname}",
                        )
                    )
        return FitGraph(
            schema_version=self.schema_version, nodes=nodes, expr_edges=edges
        )

    def fit(
        self,
        datasets: list[MeasurementData],
        options: object | None = None,
    ) -> FitResult:
        """Fit all datasets in a single simultaneous (joint) solve.

        The lmfit ``fit_multi_datasets`` pattern.
        Builds one flattened :class:`FitGraph` via :meth:`to_fit_graph` (global
        nodes + per-dataset local replicas scoped through ``dataset_index``) and
        minimises every shared and local parameter together over the
        concatenated residual. Shared parameters live on the global nodes; each
        dataset's local parameters live on its ``"{id}_s{i}"`` replica and only
        affect that dataset's points.

        Args:
            datasets: One ``MeasurementData`` per slice. Must have
                ``len(datasets) == n_slices``.
            options: ``FitOptions`` (or ``None`` for defaults).

        Returns:
            A single ``FitResult``: global params keyed by ``"{node_id}.{param}"``,
            per-dataset local params by ``"{node_id}_s{i}.{param}"``, and
            per-dataset diagnostics in ``dataset_slices``.

        Raises:
            ValueError: If ``len(datasets) != n_slices``.

        Note:
            For the legacy two-stage sequential approximation (fit globals on the
            stack, freeze, then fit each slice's locals), use
            :meth:`fit_all_slices`.

        """
        from .fit import fit as _fit
        from .options import FitOptions

        if len(datasets) != self.n_slices:
            raise ValueError(
                f"GlobalFitGraph.fit expects {self.n_slices} datasets, "
                f"got {len(datasets)}"
            )
        opts = FitOptions.model_validate(options or FitOptions())
        return _fit(self.to_fit_graph(), datasets, opts)

    def fit_all_slices(
        self,
        datasets: list[MeasurementData],
        options: object | None = None,
    ) -> list[FitResult]:
        """Fit each slice and return all per-slice results.

        Two-stage strategy:

        1. Jointly fit ``global_nodes`` against all stacked data.
        2. Per-slice: fix global params, fit ``local_nodes`` on slice data.

        Args:
            datasets: One ``MeasurementData`` per slice.
            options: ``FitOptions`` (or ``None`` for defaults).

        Returns:
            List of ``FitResult``, one per slice, in dataset order.

        Raises:
            ValueError: If ``len(datasets) != n_slices``.

        """
        import copy

        from .fit import fit as _fit
        from .options import FitOptions
        from .parameters import Parameter

        if len(datasets) != self.n_slices:
            raise ValueError(
                f"GlobalFitGraph.fit expects {self.n_slices} datasets, "
                f"got {len(datasets)}"
            )

        opts = FitOptions.model_validate(options or FitOptions())

        # ── Stage 1: Joint fit of global nodes against all stacked data ─────
        if self.global_nodes:
            global_graph = FitGraph(
                schema_version=self.schema_version,
                nodes=list(self.global_nodes),
            )
            global_result = _fit(global_graph, datasets, opts)
            # Extract fitted global param values
            global_fixed: dict[str, dict[str, float]] = {}
            for node in self.global_nodes:
                global_fixed[node.id] = {}
                for pname in node.parameters:
                    key = f"{node.id}.{pname}"
                    if key in global_result.parameters:
                        global_fixed[node.id][pname] = global_result.parameters[
                            key
                        ].value
        else:
            global_fixed = {}

        # ── Stage 2: Per-slice refinement with local nodes only ───────────
        slice_results: list[Any] = []
        for i, ds in enumerate(datasets):
            # Build per-slice graph: global nodes (fixed) + local nodes (free)
            slice_nodes: list[ModelNodeSpec] = []

            # Global nodes: fix all params at Stage 1 values
            for node in self.global_nodes:
                fixed_node = copy.deepcopy(node)
                fixed_params = global_fixed.get(node.id, {})
                new_params = {}
                for pname, param in node.parameters.items():
                    new_val = fixed_params.get(pname, param.value)
                    new_params[pname] = Parameter(value=new_val, vary=False)
                fixed_node = fixed_node.model_copy(update={"parameters": new_params})
                slice_nodes.append(fixed_node)

            # Local nodes: replicate for this slice
            for local in self.local_nodes:
                replica = copy.deepcopy(local)
                replica = replica.model_copy(update={"id": f"{local.id}_s{i}"})
                slice_nodes.append(replica)

            slice_graph = FitGraph(
                schema_version=self.schema_version,
                nodes=slice_nodes,
            )
            slice_result = _fit(slice_graph, [ds], opts)
            slice_results.append(slice_result)

        return slice_results
