---
icon: lucide/git-fork
description: How models compile to a directed-acyclic-graph IR — ModelNodeSpec nodes, ExprEdge ties, and sum aggregation, evaluated entirely in Rust.
tags:
  - Models
  - Rust
  - Python
---

# Model Composition — DAG IR

Models are defined as a directed acyclic graph (DAG) — spectrafit-core's
model intermediate representation (IR) — at the Python level, serialised
to JSON, and evaluated entirely in Rust.

## Nodes

Each node is a [`ModelNodeSpec`][spectrafit_core.ModelNodeSpec]: a typed model
instance with a unique `id`, one [`ModelType`][spectrafit_core.ModelType]
kernel (Gaussian, Lorentzian, Voigt, …), and its `parameters` keyed by name.
An optional `dataset_index` scopes the node to one dataset in a multi-dataset
("global analysis") fit — `None` (the default) makes it a global node
contributing to every dataset's points; `i` restricts it to dataset `i`'s
residuals and Jacobian columns.

## Edges

Edges encode parameter constraints (ties) across nodes, and **are evaluated in
Rust** — `expr_edges` are parsed into an `Expr`/`TiedPlan` abstract syntax
tree (AST) in `spectrafit-graph::expr` at compile time, then re-applied every
solver iteration by `LmProblem::set_free_and_tied`
(`crates/spectrafit-solver/src/lm_problem.rs`, shared by both the
nalgebra-LM and faer trust-region front-ends) so each tied target is
recomputed from its expression before the model is evaluated:

Each edge is an [`ExprEdge`][spectrafit_core.ExprEdge]: a `target_node` /
`target_param` pair naming the parameter to constrain, plus an `expression`
string that references other nodes' parameters in `node_id.param` form
(e.g. `"0.5 * peak1.amplitude"`).

## Aggregation

Node outputs are **summed** at each x point. This is fixed behaviour, not a
selectable default: `crates/spectrafit-graph/src/executor.rs` accumulates
`sum += node.model.eval(...)` on every evaluation path, and neither
`FitGraphSpec` nor the compiled `FitGraph` carries an aggregation
discriminator. There is no product/max/custom mode to choose.

## Why not operator overloading (lmfit-style)?

lmfit's `model1 + model2` creates a binary tree evaluated recursively at
Python speed, allocating N temporary NumPy arrays per iteration. Our DAG is
compiled once to a Rust struct; evaluation is a single O(N_nodes * N_x) loop
with no Python round-trips.

## See also

- **Related examples**: [`shared_params.md`](../tutorials/gallery/shared_params.md)
  (an expression edge tying one node's parameter to another's),
  [`multi_dataset.md`](../tutorials/gallery/multi_dataset.md) (several datasets
  composed into one graph),
  [`3d_fitting.md`](../tutorials/gallery/3d_fitting.md) (composition at scale).
- **Related explanation**: [Parameter Model](parameter-model.md) (what the
  parameters the nodes declare can be bound to).
- **Glossary**: [Glossary](../glossary.md) — definitions for this page's
  project-specific terms (`DAG IR`, `ExprEdge`, `ModelNodeSpec`, `trust-region`, `LM`).
