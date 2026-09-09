//! The problem contract for the Newton-CG solver.
//!
//! Re-exports the framework [`TrustRegionProblem`] so a model/graph crate can
//! implement the Newton-CG solver's problem contract through a single
//! `spectrafit-newton-cg` dependency (matching the per-method-crate layout
//! `driver` / `step` / `problem` / `tests`).
//!
//! # `apply_jacobian` / `apply_jacobian_transpose` are reserved
//!
//! This crate's driver does **not** use the trait's matrix-free operators.
//! Newton-CG here runs its truncated-CG subproblem against the dense *scaled*
//! Jacobian via `Subproblem::hvec`, so the operators are never called on the
//! solve path and their default implementations are exercised only by the
//! framework's contract test. They are reserved for a future matrix-free
//! implementor; overriding them today changes nothing about how this solver
//! runs.

pub use spectrafit_trust_region::TrustRegionProblem;
