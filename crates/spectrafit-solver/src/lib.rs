//! spectrafit-solver — fitting engine with LM, TRF, IRLS, DE, and VarPro solvers.
#![warn(missing_docs)]
//!
//! Public API:
//!   - [`fit`] — dispatch to the appropriate solver based on `FitOptionsSpec.solver`
//!   - [`SolverError`] — solver-layer error type (boundary-crossing failures)

pub mod dispatch;
pub mod error;
pub mod global;
pub mod irls;
pub mod postfit;
pub mod problem;

pub use dispatch::fit;
pub use error::SolverError;
