//! Powell's dogleg subproblem solver.
//!
//! Given the scaled subproblem (`J̃`, `g̃`, radius `Δ`), the dogleg method picks a
//! step on the piecewise-linear path Cauchy → Gauss–Newton:
//!
//! 1. If the Gauss–Newton step `δ_GN = −(J̃ᵀJ̃)⁻¹ g̃` lies inside the trust region
//!    (`‖δ_GN‖ ≤ Δ`), take it — full Newton convergence near the optimum.
//! 2. Otherwise compute the Cauchy point `δ_C = −(‖g̃‖²/‖J̃g̃‖²) g̃` (the
//!    unconstrained steepest-descent minimiser). If it is already outside `Δ`,
//!    take the steepest-descent direction clipped to the boundary.
//! 3. Otherwise interpolate along `δ_C → δ_GN` to the point where `‖δ‖ = Δ`.
//!
//! A rank-deficient `J̃ᵀJ̃` (no Gauss–Newton step) degrades gracefully to the
//! Cauchy / steepest-descent step.

use faer::prelude::*;
use faer::{Mat, Side};
use spectrafit_trust_region::{StepResult, Subproblem, SubproblemStep};

/// Powell's dogleg trust-region subproblem solver (stateless).
pub struct DoglegStep;

#[inline]
fn norm2(v: &Mat<f64>) -> f64 {
    v.as_ref().squared_norm_l2()
}

#[inline]
fn dot(a: &Mat<f64>, b: &Mat<f64>) -> f64 {
    (a.as_ref().transpose() * b.as_ref())[(0, 0)]
}

impl SubproblemStep for DoglegStep {
    fn solve(&self, sub: &Subproblem<'_>, radius: f64) -> StepResult {
        let p = sub.n_params();
        let g = sub.gradient(); // g̃ (p×1)
        let jt = sub.jacobian(); // J̃ (m×p)

        let finish = |step: Mat<f64>, hit_boundary: bool| {
            let predicted_reduction = sub.predicted_reduction(step.as_ref());
            StepResult {
                step,
                predicted_reduction,
                hit_boundary,
            }
        };

        // Gauss–Newton step: (J̃ᵀJ̃) δ = −g̃ (None if not positive-definite).
        let h = jt.transpose() * jt;
        let neg_g = Mat::from_fn(p, 1, |i, _| -g[(i, 0)]);
        let gn = h
            .as_ref()
            .llt(Side::Lower)
            .ok()
            .map(|llt| llt.solve(neg_g.as_ref()));

        // 1. GN inside the trust region ⇒ take it.
        if let Some(gn) = &gn {
            if norm2(gn).sqrt() <= radius {
                return finish(gn.clone(), false);
            }
        }

        // Cauchy point along −g̃.
        let g_norm2 = g.squared_norm_l2();
        let g_norm = g_norm2.sqrt();
        if g_norm == 0.0 {
            return finish(Mat::zeros(p, 1), false); // stationary: no descent direction
        }
        let jg = sub.jvec(g); // J̃ g̃
        let jg_norm2 = jg.as_ref().squared_norm_l2();

        // Steepest-descent direction clipped to the boundary (used when the
        // curvature along −g̃ is ~0 or the Cauchy point is already outside Δ).
        let boundary_sd = || Mat::from_fn(p, 1, |i, _| -(radius / g_norm) * g[(i, 0)]);

        if jg_norm2 <= 0.0 {
            return finish(boundary_sd(), true);
        }

        let t_star = g_norm2 / jg_norm2;
        let cauchy = Mat::from_fn(p, 1, |i, _| -t_star * g[(i, 0)]);
        if norm2(&cauchy).sqrt() >= radius {
            return finish(boundary_sd(), true);
        }

        // 3. Dogleg interpolation Cauchy → GN to the boundary ‖δ‖ = Δ.
        let Some(gn) = gn else {
            // Rank-deficient: no GN leg — accept the interior Cauchy step.
            return finish(cauchy, false);
        };
        let d = Mat::from_fn(p, 1, |i, _| gn[(i, 0)] - cauchy[(i, 0)]);
        let a = norm2(&d);
        if a <= 0.0 {
            return finish(cauchy, false); // GN ≈ Cauchy
        }
        // Solve a·τ² + b·τ + c = 0 for τ ∈ [0,1], c = ‖cauchy‖² − Δ² < 0.
        let b = 2.0 * dot(&cauchy, &d);
        let c = norm2(&cauchy) - radius * radius;
        let disc = (b * b - 4.0 * a * c).max(0.0);
        let tau = ((-b + disc.sqrt()) / (2.0 * a)).clamp(0.0, 1.0);
        let step = Mat::from_fn(p, 1, |i, _| cauchy[(i, 0)] + tau * d[(i, 0)]);
        finish(step, true)
    }
}
