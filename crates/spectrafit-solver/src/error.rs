//! Solver-level error type.
//!
//! NOTE (Plan A scaffold): [`SolverError`] is defined as the typed error
//! shape for boundary-crossing solver failures. The A4 audit found that
//! all severity-9 `expect()` / `unwrap()` sites in spectrafit-solver
//! were in test code; the single production site (`global.rs:257`) is an
//! INVARIANT-guarded call. SolverError variants are available for new
//! boundary-facing code; widespread conversion of existing `CoreError`
//! returns is a Plan A2 follow-up.

use spectrafit_types::CoreError;
use thiserror::Error;

/// Errors originating in the solver layer.
#[derive(Debug, Error)]
pub enum SolverError {
    /// A free-key or parameter lookup inside the dispatch path failed.
    ///
    /// Typically caused by malformed graph input (a `free_key` that does not
    /// match `"node_id.param_name"` format, or a node/parameter that the
    /// compiled graph promised but the spec does not contain).
    #[error("dispatch error: {0}")]
    Dispatch(String),

    /// The global optimiser (Differential Evolution) could not produce a
    /// finite-cost candidate, e.g. because all population members diverged.
    #[error("global optimisation failed: {0}")]
    GlobalFailure(String),

    /// The post-fit covariance matrix is ill-conditioned (Cholesky failed or
    /// the condition number κ was above the safe threshold).
    #[error("postfit covariance ill-conditioned: κ={kappa:e}")]
    IllConditioned {
        /// The condition number κ = σ_max / σ_min of JᵀJ at the solution.
        kappa: f64,
    },

    /// An IRLS weight-update iteration encountered a numerical failure.
    #[error("irls weight update failed: {0}")]
    IrlsFailure(String),

    /// The graph is not separable but VarPro was explicitly requested.
    #[error("solver='varpro' requested but graph is not separable")]
    VarproNotSeparable,

    /// VarPro cannot honour tied parameters (from `expr_edges` or `Parameter.expr`).
    #[error(
        "solver='varpro' does not support tied parameters (expr_edges or \
         Parameter.expr); use solver='lm', 'trf', or 'geodesic'"
    )]
    VarproExprEdgesUnsupported,

    /// VarPro cannot honour per-dataset (`dataset_index`) node scoping.
    #[error(
        "solver='varpro' does not support per-dataset (dataset_index) node \
         scoping for simultaneous multi-dataset fits; use solver='lm', \
         'trf', or 'geodesic'"
    )]
    VarproDatasetScopingUnsupported,

    /// A tied target had a malformed `"node.param"` key.
    #[error("malformed tied target '{0}'")]
    MalformedTiedTarget(String),

    /// A tied target referenced a node not present in the compiled graph.
    #[error("tied target node '{0}' not found")]
    TiedTargetNodeMissing(String),

    /// A tied target referenced a parameter not present on the named node.
    #[error("tied target param '{0}' not found")]
    TiedTargetParamMissing(String),
}

/// Map [`SolverError`] to the workspace-wide [`CoreError`].
///
/// Symmetric to `From<GraphError> for CoreError` in the graph crate: the
/// solver produces typed `SolverError` variants internally; the PyO3 boundary
/// layer (`spectrafit-core`) and the rest of the workspace consume
/// `CoreError`, so this conversion lets `?` flatten without losing the
/// `Display` message.
impl From<SolverError> for CoreError {
    fn from(value: SolverError) -> Self {
        match value {
            // The solver-specific failure modes map to the dedicated
            // `CoreError::Solver` variant so callers downstream can recognise
            // "the solver ran but did not produce a usable answer" as distinct
            // from a graph compilation problem.
            SolverError::GlobalFailure(_)
            | SolverError::IllConditioned { .. }
            | SolverError::IrlsFailure(_) => CoreError::Solver(value.to_string()),
            // Dispatch / setup-time failures (malformed graph input, VarPro
            // capability mismatches, etc.) are evaluation-domain errors.
            SolverError::Dispatch(_)
            | SolverError::VarproNotSeparable
            | SolverError::VarproExprEdgesUnsupported
            | SolverError::VarproDatasetScopingUnsupported
            | SolverError::MalformedTiedTarget(_)
            | SolverError::TiedTargetNodeMissing(_)
            | SolverError::TiedTargetParamMissing(_) => CoreError::Eval(value.to_string()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn varpro_not_separable_maps_to_eval() {
        let e: CoreError = SolverError::VarproNotSeparable.into();
        match e {
            CoreError::Eval(msg) => assert!(msg.contains("not separable")),
            other => panic!("expected CoreError::Eval, got {other:?}"),
        }
    }

    #[test]
    fn global_failure_maps_to_solver() {
        let e: CoreError = SolverError::GlobalFailure("nan".into()).into();
        match e {
            CoreError::Solver(msg) => assert!(msg.contains("nan")),
            other => panic!("expected CoreError::Solver, got {other:?}"),
        }
    }

    #[test]
    fn ill_conditioned_maps_to_solver() {
        let e: CoreError = SolverError::IllConditioned { kappa: 1e20 }.into();
        match e {
            CoreError::Solver(msg) => assert!(msg.contains("ill-conditioned")),
            other => panic!("expected CoreError::Solver, got {other:?}"),
        }
    }

    #[test]
    fn malformed_tied_target_maps_to_eval() {
        let e: CoreError = SolverError::MalformedTiedTarget("nodot".into()).into();
        match e {
            CoreError::Eval(msg) => assert!(msg.contains("malformed tied target")),
            other => panic!("expected CoreError::Eval, got {other:?}"),
        }
    }
}
