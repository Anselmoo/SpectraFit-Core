//! `spectrafit-dogleg` — Powell's dogleg trust-region method.
//!
//! One *method* on the graph-agnostic
//! [`spectrafit-trust-region`](spectrafit_trust_region) framework: it supplies
//! the [`DoglegStep`] subproblem solver (Gauss–Newton / Cauchy interpolation
//! within the trust radius) and a thin [`minimize`] entry point; the framework
//! owns the Δ-radius control loop, gain-ratio acceptance and Moré scaling.
//!
//! Dogleg is a robust, cheap workhorse on mildly nonlinear least-squares
//! problems: it is full Gauss–Newton near the optimum and steepest-descent-like
//! far from it, all via one `p×p` Cholesky per iteration.

mod driver;
mod problem;
mod step;

pub use driver::minimize;
pub use problem::TrustRegionProblem;
pub use step::DoglegStep;

// Re-export the framework config + outcome types so consumers depend only on
// this crate for the full dogleg API surface.
pub use spectrafit_trust_region::{Report, Termination, TrustRegionConfig};

#[cfg(test)]
mod tests;
