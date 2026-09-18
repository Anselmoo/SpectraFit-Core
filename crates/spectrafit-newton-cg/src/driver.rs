//! The Newton-CG (Steihaug) solver entry point.
//!
//! A thin wrapper driving the framework's generic Δ-radius trust-region loop
//! ([`minimize_tr`]) with the matrix-free [`SteihaugStep`] subproblem solver.

use spectrafit_trust_region::{minimize_tr, Report, TrustRegionConfig, TrustRegionProblem};

use crate::step::SteihaugStep;

/// Minimise `½‖r(p)‖²` over the free parameters of `problem` with the matrix-free
/// Newton-CG (Steihaug–Toint) trust-region method. On return the problem holds
/// the best parameters.
pub fn minimize<P: TrustRegionProblem>(problem: &mut P, cfg: &TrustRegionConfig) -> Report {
    minimize_tr(problem, &SteihaugStep, cfg)
}
