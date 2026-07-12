//! The problem contract for the Newton-CG solver.
//!
//! Re-exports the framework [`TrustRegionProblem`] so a model/graph crate can
//! implement the Newton-CG solver's problem contract through a single
//! `spectrafit-newton-cg` dependency (matching the per-method-crate layout
//! `driver` / `step` / `problem` / `tests`). Implementors that want true
//! matrix-free scaling override the trait's `apply_jacobian` / `apply_jacobian_transpose`.

pub use spectrafit_trust_region::TrustRegionProblem;
