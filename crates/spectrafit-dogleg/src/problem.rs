//! The problem contract for the dogleg solver.
//!
//! Re-exports the framework [`TrustRegionProblem`] so a model/graph crate can
//! implement the dogleg solver's problem contract through a single
//! `spectrafit-dogleg` dependency (matching the per-method-crate layout
//! `driver` / `step` / `problem` / `tests`).

pub use spectrafit_trust_region::TrustRegionProblem;
