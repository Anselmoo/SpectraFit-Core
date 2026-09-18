//! Steihaug–Toint truncated conjugate-gradient subproblem solver.
//!
//! Approximately minimises the scaled quadratic model `g̃ᵀδ̃ + ½ δ̃ᵀHδ̃` (with
//! `H = J̃ᵀJ̃`) inside the trust region `‖δ̃‖ ≤ Δ` using conjugate gradients, and
//! truncates early on two events (Nocedal & Wright, *Numerical Optimization*,
//! Algorithm 7.2):
//!
//! * **negative curvature** (`dᵀHd ≤ 0`) — follow the search direction to the
//!   trust-region boundary;
//! * **trust-region exit** (`‖z + αd‖ ≥ Δ`) — stop at the boundary.
//!
//! Otherwise CG runs until the model gradient is small (a forcing-sequence
//! tolerance giving superlinear convergence). The Gauss–Newton Hessian is **never
//! formed**: every iteration uses one matrix-free product `H·v = J̃ᵀ(J̃·v)` from
//! the [`Subproblem`], so the cost scales with the *residual* count, not `p²` —
//! the lever for large nD fits.

use faer::Mat;
use spectrafit_trust_region::{StepResult, Subproblem, SubproblemStep};

/// Matrix-free Newton-CG (Steihaug–Toint) trust-region subproblem solver (stateless).
pub struct SteihaugStep;

#[inline]
fn dot(a: &Mat<f64>, b: &Mat<f64>) -> f64 {
    (a.as_ref().transpose() * b.as_ref())[(0, 0)]
}

#[inline]
fn norm(v: &Mat<f64>) -> f64 {
    v.as_ref().squared_norm_l2().sqrt()
}

/// Largest `τ ≥ 0` with `‖z + τ·d‖ = Δ` (positive root; `z` is interior so it exists).
fn boundary_tau(z: &Mat<f64>, d: &Mat<f64>, radius: f64) -> f64 {
    let a = dot(d, d);
    if a <= 0.0 {
        return 0.0;
    }
    let b = 2.0 * dot(z, d);
    let c = dot(z, z) - radius * radius;
    let disc = (b * b - 4.0 * a * c).max(0.0);
    ((-b + disc.sqrt()) / (2.0 * a)).max(0.0)
}

impl SubproblemStep for SteihaugStep {
    fn solve(&self, sub: &Subproblem<'_>, radius: f64) -> StepResult {
        let p = sub.n_params();
        let g = sub.gradient(); // g̃

        let finish = |step: Mat<f64>, hit_boundary: bool| {
            let predicted_reduction = sub.predicted_reduction(step.as_ref());
            StepResult {
                step,
                predicted_reduction,
                hit_boundary,
            }
        };

        // CG on H δ = −g̃, starting from z₀ = 0 ⇒ residual r₀ = g̃, direction d₀ = −g̃.
        let mut z = Mat::<f64>::zeros(p, 1);
        let mut r = Mat::from_fn(p, 1, |i, _| g[(i, 0)]);
        let r0_norm = norm(&r);
        if r0_norm == 0.0 {
            return finish(z, false); // already stationary
        }
        // Forcing-sequence tolerance ‖r‖ ≤ ‖r₀‖·min(0.5, √‖r₀‖) (superlinear).
        let tol = r0_norm * 0.5_f64.min(r0_norm.sqrt());
        let mut d = Mat::from_fn(p, 1, |i, _| -r[(i, 0)]);
        let mut rr = dot(&r, &r);

        let max_iter = 2 * p + 10;
        for _ in 0..max_iter {
            let hd = sub.hvec(d.as_ref());
            let dhd = dot(&d, &hd);
            if dhd <= 0.0 {
                // Negative curvature: ride d to the boundary.
                let tau = boundary_tau(&z, &d, radius);
                let step = Mat::from_fn(p, 1, |i, _| z[(i, 0)] + tau * d[(i, 0)]);
                return finish(step, true);
            }
            let alpha = rr / dhd;
            let z_next = Mat::from_fn(p, 1, |i, _| z[(i, 0)] + alpha * d[(i, 0)]);
            if norm(&z_next) >= radius {
                // Exited the trust region: stop at the boundary along d.
                let tau = boundary_tau(&z, &d, radius);
                let step = Mat::from_fn(p, 1, |i, _| z[(i, 0)] + tau * d[(i, 0)]);
                return finish(step, true);
            }
            z = z_next;
            let r_next = Mat::from_fn(p, 1, |i, _| r[(i, 0)] + alpha * hd[(i, 0)]);
            if norm(&r_next) <= tol {
                return finish(z, false); // interior CG convergence
            }
            let rr_next = dot(&r_next, &r_next);
            let beta = rr_next / rr;
            d = Mat::from_fn(p, 1, |i, _| -r_next[(i, 0)] + beta * d[(i, 0)]);
            r = r_next;
            rr = rr_next;
        }
        finish(z, false) // budget exhausted — return the best interior iterate
    }
}
