//! The generic Δ-radius trust-region control loop.
//!
//! Unlike Levenberg–Marquardt (which controls step size through the damping `λ`
//! and lives in `spectrafit-levenberg-marquardt`), the dogleg and Newton-CG
//! methods are genuine trust-region methods: they maintain an explicit radius
//! `Δ`, solve the subproblem within it, and grow/shrink `Δ` from the gain ratio
//! `ρ = actual/predicted`. This module owns that shared loop; each method only
//! supplies a [`SubproblemStep`]. The classic accept/update rule is Nocedal &
//! Wright, *Numerical Optimization*, Algorithm 4.1.
//!
//! Stopping criteria (`ftol`/`xtol`/`gtol`) match the LM driver and
//! `scipy.optimize.least_squares` so methods are comparable. Bounds reflection
//! and tied-parameter application live in the problem's
//! [`set_params`](TrustRegionProblem::set_params); the driver only proposes
//! steps and reads back the applied parameters.

use faer::Mat;

use crate::problem::TrustRegionProblem;
use crate::report::{Report, Termination};
use crate::step::{Subproblem, SubproblemStep};

/// Tuning for a single Δ-radius trust-region solve.
#[derive(Debug, Clone, Copy)]
pub struct TrustRegionConfig {
    /// Relative cost-decrease tolerance.
    pub ftol: f64,
    /// Relative step-size tolerance.
    pub xtol: f64,
    /// Gradient infinity-norm tolerance.
    pub gtol: f64,
    /// Maximum residual evaluations.
    pub max_nfev: usize,
    /// Initial trust radius `Δ` (scaled units); `≤ 0` ⇒ a problem-derived default.
    pub delta0: f64,
    /// Hard upper bound on `Δ`.
    pub max_delta: f64,
    /// Acceptance threshold: accept the step when `ρ > eta`.
    pub eta: f64,
}

impl Default for TrustRegionConfig {
    fn default() -> Self {
        Self {
            ftol: 1e-8,
            xtol: 1e-8,
            gtol: 1e-8,
            max_nfev: 10_000,
            delta0: 0.0, // derive from the first scaled gradient
            max_delta: 1e3,
            eta: 1e-4,
        }
    }
}

/// Minimise `½‖r(p)‖²` over the free parameters of `problem` with an explicit
/// Δ-radius trust region, delegating the per-iteration subproblem to `step`.
///
/// On return the problem holds the best parameters found. Deterministic: no RNG,
/// no clock — identical inputs give identical iterates.
pub fn minimize_tr<P: TrustRegionProblem, S: SubproblemStep>(
    problem: &mut P,
    step: &S,
    cfg: &TrustRegionConfig,
) -> Report {
    // Serial faer for the skinny per-iteration matrices (see the LM driver note).
    faer::set_global_parallelism(faer::Par::Seq);
    let m = problem.n_residuals();
    let p = problem.n_params();

    // Moré column scaling `D_j = max over iterations of ‖J_:,j‖`, floored at 1.
    let mut diag = vec![1.0_f64; p];
    let mut diag_initialized = false;

    let mut r = Mat::<f64>::zeros(m, 1);
    let mut r_trial = Mat::<f64>::zeros(m, 1);
    let mut j = Mat::<f64>::zeros(m, p);

    let mut n_residual_evals = 0usize;
    let mut n_jacobian_evals = 0usize;
    let mut n_iter = 0usize;

    // Per-iteration convergence trajectory (observability only); see the LM driver
    // for the recording contract (once per accepted point + the terminal point,
    // de-duplicated).
    let mut cost_history: Vec<f64> = Vec::new();
    let mut gradient_norm_history: Vec<f64> = Vec::new();
    // This driver does not yet record the per-iteration θ trajectory; only the
    // faer LM driver does. Left empty (honest) rather than partially populated.
    let params_history: Vec<Vec<f64>> = Vec::new();

    macro_rules! report {
        ($term:expr, $cost:expr, $gnorm:expr) => {{
            let final_cost: f64 = $cost;
            let final_gnorm: f64 = $gnorm;
            if cost_history.last() != Some(&final_cost) {
                cost_history.push(final_cost);
                gradient_norm_history.push(final_gnorm);
            }
            return Report {
                termination: $term,
                n_iter,
                n_residual_evals,
                n_jacobian_evals,
                cost: final_cost,
                gradient_norm: final_gnorm,
                cost_history,
                gradient_norm_history,
                params_history,
            };
        }};
    }

    if problem.residuals_into(r.as_mut()).is_err() {
        report!(Termination::NumericalError, f64::INFINITY, 0.0);
    }
    n_residual_evals += 1;
    let mut cost = 0.5 * r.as_ref().squared_norm_l2();
    if !cost.is_finite() {
        report!(Termination::NumericalError, cost, 0.0);
    }
    if cost == 0.0 {
        report!(Termination::ResidualsZero, cost, 0.0);
    }

    let mut delta = cfg.delta0; // 0 ⇒ initialise from the first scaled gradient
    let mut delta_init = cfg.delta0 > 0.0;

    loop {
        if problem.jacobian_into(j.as_mut()).is_err() {
            report!(Termination::NumericalError, cost, 0.0);
        }
        n_jacobian_evals += 1;

        // Monotone Moré column scaling.
        for (jc, d) in diag.iter_mut().enumerate() {
            let cn = j.as_ref().col(jc).norm_l2();
            let cn = if cn > 0.0 { cn } else { 1.0 };
            *d = if diag_initialized { (*d).max(cn) } else { cn };
        }
        diag_initialized = true;

        // Gradient g = Jᵀr and first-order optimality test. For bounded
        // problems use the Coleman–Li-scaled measure ‖v·g‖_∞ (v from
        // `trust_scaling`, → 0 at an active bound) — the raw ‖g‖_∞ never
        // fires at a legitimate constrained optimum and the loop would stall
        // to a NoImprovement "failure" (G25; same fix as the LM driver).
        // Unbounded problems (trust_scaling = None) keep the raw norm.
        // NOTE: v is box-width-normalized (not scipy TRF's unnormalized
        // distance), so the gate is laxer by ~1/range for a wide-box
        // parameter — same caveat as the LM driver; tracked as G28.
        let g = j.as_ref().transpose() * r.as_ref();
        let gnorm = g.as_ref().norm_max();
        // Record the accepted point's trajectory (index 0 = initial point).
        cost_history.push(cost);
        gradient_norm_history.push(gnorm);
        let g_vec: Vec<f64> = (0..p).map(|i| g[(i, 0)]).collect();
        let opt_norm = match problem.trust_scaling(&g_vec) {
            Some(v) => g_vec
                .iter()
                .zip(v.iter())
                .map(|(gi, vi)| (gi * vi).abs())
                .fold(0.0_f64, f64::max),
            None => gnorm,
        };
        if opt_norm <= cfg.gtol {
            report!(Termination::Gtol, cost, gnorm);
        }

        // Scaled subproblem: J̃ = J/D, g̃ = g/D. The trust region is the
        // Euclidean ball ‖δ̃‖ ≤ Δ; the step is mapped back via δ = δ̃/D.
        let j_scaled = Mat::from_fn(m, p, |i, c| j[(i, c)] / diag[c]);
        let g_scaled = Mat::from_fn(p, 1, |i, _| g[(i, 0)] / diag[i]);
        let sub = Subproblem::new(j_scaled.as_ref(), g_scaled.as_ref());

        // Initialise Δ from the scaled gradient magnitude on the first iteration.
        if !delta_init {
            let gs = g_scaled.as_ref().squared_norm_l2().sqrt();
            delta = if gs > 0.0 { gs } else { 1.0 };
            delta_init = true;
        }

        let p_cur = problem.params();
        loop {
            let res = step.solve(&sub, delta);
            let s_tilde = res.step;
            let pred = res.predicted_reduction;
            if !(pred.is_finite() && pred > 0.0) {
                // Degenerate subproblem (e.g. ‖g‖≈0 model): shrink and retry.
                delta *= 0.25;
                if delta <= f64::MIN_POSITIVE * 4.0 {
                    report!(Termination::NoImprovement, cost, gnorm);
                }
                continue;
            }

            // Unscale the step: δ = δ̃ / D.
            let delta_step = Mat::from_fn(p, 1, |i, _| s_tilde[(i, 0)] / diag[i]);
            let p_trial: Vec<f64> = (0..p).map(|i| p_cur[i] + delta_step[(i, 0)]).collect();
            problem.set_params(&p_trial);
            if problem.residuals_into(r_trial.as_mut()).is_err() {
                report!(Termination::NumericalError, cost, gnorm);
            }
            n_residual_evals += 1;
            let cost_trial = 0.5 * r_trial.as_ref().squared_norm_l2();
            let actual = cost - cost_trial;
            // Gain ratio against the APPLIED step when the problem's
            // projection clipped the proposal — judging against the raw
            // step's `pred` lets the clipped direction's phantom reduction
            // collapse ρ and reject legitimate free-direction refinements
            // (G25, second mechanism; same fix as the LM driver). Interior
            // steps keep the subproblem's `pred` unchanged.
            let p_applied = problem.params();
            let clipped = p_applied.iter().zip(p_trial.iter()).any(|(a, t)| a != t);
            let pred_eff = if clipped {
                let delta_a = Mat::from_fn(p, 1, |i, _| p_applied[i] - p_cur[i]);
                let jda = j.as_ref() * delta_a.as_ref();
                let gda: f64 = (0..p).map(|i| g[(i, 0)] * delta_a[(i, 0)]).sum();
                -gda - 0.5 * jda.as_ref().squared_norm_l2()
            } else {
                pred
            };
            let rho = if pred_eff.is_finite() && pred_eff > 0.0 {
                actual / pred_eff
            } else {
                0.0
            };

            // Δ update (NW Alg 4.1): shrink on a poor ratio, grow on a very good
            // boundary step, otherwise leave Δ unchanged.
            if rho < 0.25 {
                delta *= 0.25;
            } else if rho > 0.75 && res.hit_boundary {
                delta = (2.0 * delta).min(cfg.max_delta);
            }

            if rho > cfg.eta {
                // Accept. Step/param norms use the applied (post-reflection)
                // params (`p_applied`, read above for the gain ratio).
                let mut step_norm2 = 0.0;
                let mut param_norm2 = 0.0;
                for i in 0..p {
                    let d = p_applied[i] - p_cur[i];
                    step_norm2 += d * d;
                    param_norm2 += p_applied[i] * p_applied[i];
                }
                let step_norm = step_norm2.sqrt();
                let param_norm = param_norm2.sqrt();

                std::mem::swap(&mut r, &mut r_trial);
                cost = cost_trial;
                n_iter += 1;

                if cost == 0.0 {
                    report!(Termination::ResidualsZero, cost, gnorm);
                }
                if actual <= cfg.ftol * cost.max(f64::MIN_POSITIVE) {
                    report!(Termination::Ftol, cost, gnorm);
                }
                if step_norm <= cfg.xtol * (cfg.xtol + param_norm) {
                    report!(Termination::Xtol, cost, gnorm);
                }
                break; // re-evaluate the Jacobian at the accepted point
            } else {
                // Reject: restore params; Δ has already shrunk, retry the
                // subproblem at the same point with a tighter radius.
                problem.set_params(&p_cur);
                if delta <= f64::MIN_POSITIVE * 4.0 {
                    report!(Termination::NoImprovement, cost, gnorm);
                }
            }

            if n_residual_evals >= cfg.max_nfev {
                report!(Termination::MaxEval, cost, gnorm);
            }
        }

        if n_residual_evals >= cfg.max_nfev {
            let final_gnorm = (j.as_ref().transpose() * r.as_ref()).norm_max();
            report!(Termination::MaxEval, cost, final_gnorm);
        }
    }
}
