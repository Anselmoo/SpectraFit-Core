//! The problem contract for the LM solver.
//!
//! The [`TrustRegionProblem`] trait is owned by the framework crate
//! ([`spectrafit_trust_region`]); this module re-exports it so a model/graph
//! crate can implement the LM solver's problem contract through a single
//! `spectrafit-levenberg-marquardt` dependency, matching the per-method-crate
//! layout (`driver` / `step` / `problem` / `tests`).

pub use spectrafit_trust_region::TrustRegionProblem;
