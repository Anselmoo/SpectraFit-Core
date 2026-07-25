//! `spectrafit-levenberg-marquardt` — the Levenberg–Marquardt family of solvers.
//!
//! This crate is one *method* on the graph-agnostic
//! [`spectrafit-trust-region`](spectrafit_trust_region) framework: it owns the
//! classic LM outer loop (Nielsen `λ/ν` damping, gain-ratio acceptance, Moré
//! column scaling) and the regime-adaptive damped Gauss–Newton step
//! (normal-equations + Cholesky, or thin-SVD secular), and layers two opt-in
//! variants on the same loop:
//!
//! * **TRF** — Coleman–Li bound scaling folded into the damping
//!   ([`StrategyConfig::bound_scaling`]).
//! * **geodesic** — Transtrum/Sethna second-order acceleration
//!   ([`StrategyConfig::geodesic`]).
//!
//! The shared problem contract ([`TrustRegionProblem`]) and outcome types
//! ([`Report`], [`Termination`]) live in the framework crate and are re-exported
//! here, so a consumer needs only a `spectrafit-levenberg-marquardt` dependency
//! for the full LM API surface.

mod driver;
mod problem;
mod step;

pub use driver::{minimize, StrategyConfig};
pub use problem::TrustRegionProblem;
pub use step::{factorize, select_regime, StepError, StepFactor, StepKind, StepOutput};

// Re-export the framework outcome types so downstream consumers depend only on
// this crate for the full LM API surface.
pub use spectrafit_trust_region::{Report, Termination};

#[cfg(test)]
mod tests;
