//! `spectrafit-newton-cg` — matrix-free Newton-CG (Steihaug–Toint) trust region.
//!
//! One *method* on the graph-agnostic
//! [`spectrafit-trust-region`](spectrafit_trust_region) framework: it supplies
//! the [`SteihaugStep`] subproblem solver — truncated conjugate gradients that
//! never form `JᵀJ`, using only matrix-free `H·v = J̃ᵀ(J̃·v)` products — and a
//! thin [`minimize`] entry point; the framework owns the Δ-radius control loop.
//!
//! This is the large-scale lever: the per-iteration cost scales with the number
//! of residuals, not `p²`, so it stays cheap when the parameter count is large
//! or `JᵀJ` is ill-conditioned (the regime where forming the normal equations
//! squares the condition number).

mod driver;
mod problem;
mod step;

pub use driver::minimize;
pub use problem::TrustRegionProblem;
pub use step::SteihaugStep;

// Re-export the framework config + outcome types so consumers depend only on
// this crate for the full Newton-CG API surface.
pub use spectrafit_trust_region::{Report, Termination, TrustRegionConfig};

#[cfg(test)]
mod tests;
