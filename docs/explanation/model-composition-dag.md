---
icon: lucide/git-fork
---

# Model Composition — DAG IR

Models are defined as a directed acyclic graph at the Python level, serialised
to JSON, and evaluated entirely in Rust.

## Nodes

Each node is a `ModelNodeSpec`: a typed model instance with named parameters.

```python
class ModelNodeSpec(BaseModel):
    id: str                               # unique within graph
    model_type: ModelType                 # Gaussian | Lorentzian | ...
    parameters: dict[str, Parameter]
    dataset_index: int | None = None      # None = global node; multi-dataset scoping
```

## Edges

Edges encode parameter constraints (ties) across nodes, and **are evaluated in
Rust** — `expr_edges` are parsed into an `Expr`/`TiedPlan` AST
(`spectrafit-graph::expr`) at compile time, then re-applied every solver
iteration by `spectrafit-solver::problem::set_free_and_tied` (shared by both
the nalgebra-LM and faer trust-region front-ends) so each tied target is
recomputed from its expression before the model is evaluated:

```python
class ExprEdge(BaseModel):
    target_node: str
    target_param: str
    expression: str    # e.g. "0.5 * peak1.amplitude"
```

## Aggregation

Default: **sum** of all node outputs at each x point.

## Why not operator overloading (lmfit-style)?

lmfit's `model1 + model2` creates a binary tree evaluated recursively at
Python speed, allocating N temporary NumPy arrays per iteration. Our DAG is
compiled once to a Rust struct; evaluation is a single O(N_nodes * N_x) loop
with no Python round-trips.
