//! `spectrafit-trust-region` — a faer-native, graph-agnostic trust-region framework.
//!
//! This crate owns the *shared contract and vocabulary* of nonlinear
//! least-squares fitting so that every solver method in the workspace
//! (`spectrafit-levenberg-marquardt`, and the planned dogleg / Newton-CG
//! crates) builds on one tested foundation, pure-Rust SIMD via
//! [`faer`](https://docs.rs/faer) with no BLAS/C dependency.
//!
//! # Design
//!
//! * [`TrustRegionProblem`] is the only coupling point: an implementor supplies
//!   weighted residuals and a weighted Jacobian written into caller-owned `faer`
//!   buffers (plus matrix-free `J·v` / `Jᵀ·u` operators for Krylov methods), and
//!   applies any parameter-space projection (bounds reflection, expression-tied
//!   parameters) in [`TrustRegionProblem::set_params`].
//! * [`Report`] / [`Termination`] are the generic outcome types every method
//!   reports, so consumers speak one vocabulary regardless of which method ran.
//!
//! Each concrete *method* (its outer control loop and step computation) lives in
//! its own crate on top of this framework — e.g. the LM / TRF / geodesic loop is
//! in `spectrafit-levenberg-marquardt`. The framework depends only on
//! `spectrafit-types` (for [`CoreError`]) and `faer`, so it sits as a leaf next
//! to `spectrafit-types` in the workspace DAG.
//!
//! [`CoreError`]: spectrafit_types::CoreError

mod driver;
mod problem;
mod report;
mod step;

pub use driver::{minimize_tr, TrustRegionConfig};
pub use problem::TrustRegionProblem;
pub use report::{Report, Termination};
pub use step::{StepResult, Subproblem, SubproblemStep};

#[cfg(test)]
mod tests;
