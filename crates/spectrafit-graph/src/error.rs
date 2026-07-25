//! Graph compilation and execution errors.
//!
//! NOTE (Plan A scaffold): [`GraphError`] is defined as the typed error
//! shape we INTEND to use at API boundaries. Today, public functions
//! still return `Result<_, CoreError>` — the conversion is a Plan A2
//! follow-up. New code that needs structured graph error reporting
//! should construct GraphError variants now; legacy `CoreError::Eval(String)`
//! call sites are migrated incrementally.
//!
//! ## Invariant vs. boundary-crossing sites
//!
//! Not every `unwrap()` in this crate is a bug.  Two categories exist:
//!
//! - **Boundary-crossing**: an `unwrap()` that can be triggered by external
//!   input (malformed schema, unknown model key, missing parameter, etc.).
//!   These are converted to `Result<_, GraphError>` variants here.
//! - **Invariant**: an `unwrap()` that is protected by a prior structural
//!   guarantee (e.g. "we just inserted this key, so `.get()` must return
//!   `Some`").  These are kept but annotated with an `// INVARIANT:` comment
//!   explaining the guarantee that rules out the failure branch.

use spectrafit_types::CoreError;
use thiserror::Error;

/// Errors produced by the graph compiler and executor.
#[derive(Debug, Error)]
pub enum GraphError {
    /// A node referenced by ID was not found in the compiled graph.
    ///
    /// Triggered when user-supplied `params_flat` references a node that does
    /// not exist in the graph.
    #[error("unknown node id: '{0}'")]
    UnknownNode(String),

    /// A cycle was detected in the `expr_edge` dependency graph.
    ///
    /// Triggered during compilation when two or more `expr_edges` form a
    /// circular dependency (e.g. `a → b → a`).
    #[error("cycle detected in expr_edge dependency graph at target '{0}'")]
    Cycle(String),

    /// An expression string failed to lex or parse.
    ///
    /// Triggered when an `expr_edge.expression` contains syntax that the
    /// restricted grammar does not support (unknown character, unbalanced
    /// parentheses, trailing tokens, etc.).
    #[error("malformed expression: {0}")]
    MalformedExpression(String),

    /// Two or more `expr_edges` point to the same target parameter.
    ///
    /// Each parameter may be the target of at most one `expr_edge`.
    #[error("duplicate expr_edge target: '{0}'")]
    DuplicateExprTarget(String),

    /// A required model parameter is missing from the node's `parameters` map.
    ///
    /// Triggered at compile time when the spec omits a parameter required by
    /// the model kernel.
    #[error("node '{node}' is missing required parameter '{param}'")]
    MissingParameter {
        /// Node identifier.
        node: String,
        /// Required parameter name that was absent.
        param: String,
    },

    /// Two nodes in the graph share the same `id`.
    ///
    /// Node IDs key the free-column layout and the per-node component map;
    /// a duplicate ID would silently corrupt both.
    #[error("duplicate node id '{0}': node ids must be unique within a graph")]
    DuplicateNodeId(String),

    /// The `model_type` string was not recognised by the model registry.
    #[error("unknown model type: '{0}'")]
    UnknownModelType(String),

    /// An expression evaluation failed (e.g. division by zero, missing key).
    #[error("expression evaluation failed: {0}")]
    EvalFailure(String),

    /// The `x` buffer length is not a multiple of the graph's `n_dims`.
    #[error("x buffer length {x_len} is not a multiple of n_dims {n_dims}")]
    XBufferStrideMismatch {
        /// Length of the supplied `x` slice.
        x_len: usize,
        /// Expected stride (number of coordinate components per point).
        n_dims: usize,
    },

    /// The graph mixes nodes with different coordinate dimensionalities.
    ///
    /// All nodes in a graph must share the same `n_dims`.
    #[error(
        "dimensionality mismatch: node '{first}' has n_dims={first_nd} \
         but node '{second}' has n_dims={second_nd}"
    )]
    DimensionalityMismatch {
        /// First (reference) node id.
        first: String,
        /// `n_dims` of the first node.
        first_nd: usize,
        /// Second (conflicting) node id.
        second: String,
        /// `n_dims` of the second node.
        second_nd: usize,
    },

    /// A `params_flat` entry that is required for evaluation is missing.
    ///
    /// Triggered when the caller's `params_flat` map does not contain a key
    /// for a parameter that the model requires.
    #[error("missing parameter key '{0}' in params_flat")]
    MissingParamKey(String),

    /// Division by zero occurred while evaluating a tied expression.
    #[error("expr division by zero")]
    DivisionByZero,

    /// An expression's input was empty (no tokens after lex).
    #[error("empty expression")]
    EmptyExpression,

    /// A `dataset_index` on a node points past the recorded `dataset_offsets`.
    ///
    /// Triggered when a node carries `dataset_index = Some(i)` but the solver
    /// has filled `dataset_offsets` for fewer than `i + 1` datasets — indexing
    /// would otherwise overrun `dataset_offsets`.
    #[error(
        "node '{node}' has dataset_index {dataset_index} but only {n_datasets} \
         dataset(s) are recorded (valid indices 0..{n_datasets})"
    )]
    DatasetIndexOutOfRange {
        /// Node identifier.
        node: String,
        /// Out-of-range index value.
        dataset_index: usize,
        /// Number of recorded datasets (valid indices are `0..n_datasets`).
        n_datasets: usize,
    },

    /// A residual/observation/sigma buffer length disagreed with the point count.
    #[error("residual, observation, sigma lengths must match the number of points")]
    OutputBufferShape,

    /// A reusable output buffer's length did not match the predicted point count.
    #[error("output buffer length {actual} does not match number of points {expected}")]
    OutputBufferLength {
        /// Length of the supplied buffer.
        actual: usize,
        /// Required length (= number of points).
        expected: usize,
    },
}

/// Map [`GraphError`] to the workspace-wide [`CoreError`].
///
/// `GraphError` is the structured shape the graph crate produces internally;
/// `CoreError::Eval(String)` is the legacy stringly-typed boundary the rest of
/// the workspace consumes. This conversion lets callers use `?` to flatten a
/// graph-layer failure into the boundary error type without losing the
/// `Display` message.
impl From<GraphError> for CoreError {
    fn from(value: GraphError) -> Self {
        CoreError::Eval(value.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn graph_error_converts_into_core_error_eval() {
        let g = GraphError::UnknownModelType("nonsuch".to_string());
        let c: CoreError = g.into();
        match c {
            CoreError::Eval(msg) => {
                assert!(msg.contains("unknown model type"));
                assert!(msg.contains("nonsuch"));
            }
            other => panic!("expected CoreError::Eval, got {other:?}"),
        }
    }

    #[test]
    fn graph_error_division_by_zero_renders() {
        let g = GraphError::DivisionByZero;
        assert_eq!(format!("{g}"), "expr division by zero");
    }

    #[test]
    fn graph_error_dataset_index_renders() {
        let g = GraphError::DatasetIndexOutOfRange {
            node: "bg".to_string(),
            dataset_index: 5,
            n_datasets: 2,
        };
        let s = format!("{g}");
        assert!(s.contains("'bg'"));
        assert!(s.contains("dataset_index 5"));
        assert!(s.contains("only 2 dataset"));
    }
}
