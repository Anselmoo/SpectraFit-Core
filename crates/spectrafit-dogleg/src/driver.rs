//! The dogleg solver entry point.
//!
//! A thin wrapper that drives the framework's generic Δ-radius trust-region loop
//! ([`minimize_tr`]) with the [`DoglegStep`] subproblem solver. All trust-region
//! bookkeeping (Δ updates, gain-ratio acceptance, Moré scaling, termination)
//! lives in the framework; this crate contributes only the step.

use spectrafit_trust_region::{minimize_tr, Report, TrustRegionConfig, TrustRegionProblem};

use crate::step::DoglegStep;

/// Minimise `½‖r(p)‖²` over the free parameters of `problem` with Powell's
/// dogleg trust-region method. On return the problem holds the best parameters.
pub fn minimize<P: TrustRegionProblem>(problem: &mut P, cfg: &TrustRegionConfig) -> Report {
    minimize_tr(problem, &DoglegStep, cfg)
}
