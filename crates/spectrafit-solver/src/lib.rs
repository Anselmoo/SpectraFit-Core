//! spectrafit-solver — fitting engine with LM, TRF, IRLS, DE, and VarPro solvers.
#![warn(missing_docs)]
//!
//! Public API:
//!   - [`fit`] — dispatch to the appropriate solver based on `FitOptionsSpec.solver`
//!   - [`SolverError`] — solver-layer error type (boundary-crossing failures)

// Modules are private: the crate's entire public surface is the curated
// `pub use` list below (house rule 26). Previously these were `pub mod`, which
// let a consumer reach solver internals — `LmProblem`, the post-fit assembly,
// the DE/IRLS drivers — directly, bypassing this list. Nothing outside the
// crate ever did; `spectrafit_solver::fit` is the only external reference.
mod dispatch;
mod error;
mod global;
mod irls;
mod lm_problem;
mod postfit;

pub use dispatch::fit;
pub use error::SolverError;
