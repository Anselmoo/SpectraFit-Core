//! The Levenberg–Marquardt outer control loop (LM / TRF / geodesic).
//!
//! One loop drives every LM-family strategy; only the [`StepKind`] and the `λ`
//! update differ. The loop is classic Levenberg–Marquardt with a Nielsen `λ/ν`
//! schedule and a gain-ratio accept/reject test, with stopping criteria matched
//! to `scipy.optimize.least_squares` / `lmfit` defaults (`ftol`, `xtol`,
//! `gtol`). Bounds reflection and tied-parameter application live inside the
//! problem's [`set_params`](TrustRegionProblem::set_params); the driver only
//! proposes raw steps and reads back the applied parameters.

use faer::{Mat, MatRef};

use crate::step::{factorize, StepError, StepFactor, StepKind};
use spectrafit_trust_region::{Report, Termination, TrustRegionProblem};

/// Tuning for a single Levenberg–Marquardt solve (covers LM, TRF and geodesic).
#[derive(Debug, Clone, Copy)]
pub struct StrategyConfig {
    /// Linear-algebra path for the step (pick via [`crate::select_regime`]).
    pub kind: StepKind,
    /// Relative cost-decrease tolerance.
    pub ftol: f64,
    /// Relative step-size tolerance.
    pub xtol: f64,
    /// Gradient infinity-norm tolerance.
    pub gtol: f64,
    /// Maximum residual evaluations.
    pub max_nfev: usize,
    /// Initial Marquardt damping `λ`.
    pub initial_lambda: f64,
    /// Enable geodesic acceleration (Transtrum): augment the LM velocity step
    /// with a second-directional-derivative acceleration term. Faster on
    /// sloppy/degenerate surfaces (multi-peak) at ~1 extra residual eval/iter.
    pub geodesic: bool,
    /// Finite-difference step for the geodesic second directional derivative.
    pub geodesic_h: f64,
    /// Acceptance threshold for the acceleration: accept `δ + ½a` only when
    /// `‖Da‖ / ‖Dδ‖ ≤ α` (mild curvature).
    pub geodesic_alpha: f64,
    /// Enable Coleman–Li bound scaling (Trust-Region-Reflective): fold the
    /// problem's [`trust_scaling`](TrustRegionProblem::trust_scaling) into the
    /// per-iteration damping so steps shrink as parameters approach active bounds.
    pub bound_scaling: bool,
}

impl Default for StrategyConfig {
    fn default() -> Self {
        Self {
            kind: StepKind::NormalEqLlt,
            ftol: 1e-8,
            xtol: 1e-8,
            gtol: 1e-8,
            max_nfev: 10_000,
            initial_lambda: 1e-3,
            geodesic: false,
            geodesic_h: 0.1,
            geodesic_alpha: 0.75,
            bound_scaling: false,
        }
    }
}

#[inline]
fn col_dot(a: MatRef<'_, f64>, b: MatRef<'_, f64>) -> f64 {
    let n = a.nrows();
    let mut s = 0.0;
    for i in 0..n {
        s += a[(i, 0)] * b[(i, 0)];
    }
    s
}

/// `‖Dv‖` where `D = diag(diag)`.
#[inline]
fn scaled_norm(v: &Mat<f64>, diag: &[f64]) -> f64 {
    let mut s = 0.0;
    for (i, &d) in diag.iter().enumerate() {
        let x = d * v[(i, 0)];
        s += x * x;
    }
    s.sqrt()
}

/// Geodesic acceleration (Transtrum/Sethna): given the LM velocity `δ`, compute
/// the acceleration `a` from the second directional derivative of the residual
/// along `δ` and return the augmented step `δ + ½a` (or `δ` if the curvature is
/// too large), plus its predicted reduction `−gᵀs − ½‖Js‖²`.
///
/// Probes the residual at `p + h·δ` (one extra eval), then restores the problem
/// to `p_cur`. Falls back to the plain velocity on any numerical failure.
#[allow(clippy::too_many_arguments)]
fn geodesic_augment<P: TrustRegionProblem>(
    problem: &mut P,
    factor: &StepFactor,
    j: MatRef<'_, f64>,
    r: MatRef<'_, f64>,
    g: MatRef<'_, f64>,
    p_cur: &[f64],
    velocity: Mat<f64>,
    diag: &[f64],
    lambda: f64,
    h: f64,
    alpha: f64,
    n_residual_evals: &mut usize,
) -> (Mat<f64>, f64) {
    let p = velocity.nrows();
    let m = j.nrows();

    let pred_of = |step: &Mat<f64>| {
        let js = j * step.as_ref();
        -col_dot(g, step.as_ref()) - 0.5 * js.as_ref().squared_norm_l2()
    };

    let jv = j * velocity.as_ref(); // m×1

    // Probe r(p + h·δ); restore to p_cur afterwards.
    let p_probe: Vec<f64> = (0..p).map(|i| p_cur[i] + h * velocity[(i, 0)]).collect();
    problem.set_params(&p_probe);
    let mut r_plus = Mat::<f64>::zeros(m, 1);
    let probe_ok = problem.residuals_into(r_plus.as_mut()).is_ok();
    problem.set_params(p_cur);
    // The probe is a real residual evaluation whether it succeeded or not — count
    // it before any early return so the work budget is accounted accurately.
    *n_residual_evals += 1;
    if !probe_ok {
        let pr = pred_of(&velocity);
        return (velocity, pr);
    }

    // Second directional derivative: r_vv ≈ (2/h)·[ (r(p+hδ) − r)/h − Jδ ].
    let rvv = Mat::from_fn(m, 1, |i, _| {
        (2.0 / h) * (((r_plus[(i, 0)] - r[(i, 0)]) / h) - jv[(i, 0)])
    });
    let jt_rvv = j.transpose() * rvv.as_ref(); // p×1
    let rhs2 = Mat::from_fn(p, 1, |i, _| -jt_rvv[(i, 0)]);

    let accel = match factor.solve_rhs(diag, lambda, rhs2.as_ref()) {
        Ok(a) => a,
        Err(_) => {
            let pr = pred_of(&velocity);
            return (velocity, pr);
        }
    };

    // Accept the acceleration only under mild curvature: ‖Da‖/‖Dδ‖ ≤ α.
    let dv = scaled_norm(&velocity, diag);
    let da = scaled_norm(&accel, diag);
    let step = if dv > 0.0 && da / dv <= alpha {
        Mat::from_fn(p, 1, |i, _| velocity[(i, 0)] + 0.5 * accel[(i, 0)])
    } else {
        velocity
    };
    let pr = pred_of(&step);
    (step, pr)
}

/// Minimise `½‖r(p)‖²` over the free parameters of `problem` with Levenberg–Marquardt.
///
/// On return the problem holds the best parameters found. Deterministic: no RNG,
/// no clock — identical inputs give identical iterates.
pub fn minimize<P: TrustRegionProblem>(problem: &mut P, cfg: &StrategyConfig) -> Report {
    // Run faer's dense kernels serially. Our matrices are skinny (p ≲ 150), so
    // faer's default Rayon dispatch costs more in thread-pool wake-up (~30–50 µs
    // per matmul) than the arithmetic itself — measured ~4.7× slowdown on a
    // 50k×3 fit. Data-parallelism that *does* pay off lives one level down in the
    // graph executor (its own Rayon path over data points), not in these
    // per-iteration p×p factorizations. faer is solver-internal in this
    // workspace, so setting the global policy here is safe.
    faer::set_global_parallelism(faer::Par::Seq);
    let m = problem.n_residuals();
    let p = problem.n_params();

    // Moré column scaling `D`: `D_j = max over iterations of ‖J_:,j‖`, floored at
    // 1 for all-zero columns. Monotone (never shrinks) per MINPACK, so the trust
    // region is measured in scaled units that equalise the Jacobian columns —
    // this is what keeps the normal-equations regime well-behaved despite its κ²
    // sensitivity. Filled from the first Jacobian below.
    let mut diag = vec![1.0_f64; p];
    let mut diag_initialized = false;

    let mut r = Mat::<f64>::zeros(m, 1);
    let mut r_trial = Mat::<f64>::zeros(m, 1);
    let mut j = Mat::<f64>::zeros(m, p);

    let mut n_residual_evals = 0usize;
    let mut n_jacobian_evals = 0usize;
    let mut n_iter = 0usize;

    // Per-iteration convergence trajectory (observability only). Recorded once at
    // the top of each outer iteration (the accepted point's cost + gradient norm)
    // and, via the `report!` macro, the terminal point — de-duplicated so a
    // gtol/max-eval stop at the same point is not double-counted.
    let mut cost_history: Vec<f64> = Vec::new();
    let mut gradient_norm_history: Vec<f64> = Vec::new();
    // The free-parameter vector θ recorded alongside each cost_history entry
    // (same length). Raw material for the convergence-to-truth metric.
    let mut params_history: Vec<Vec<f64>> = Vec::new();

    macro_rules! report {
        ($term:expr, $cost:expr, $gnorm:expr) => {{
            let final_cost: f64 = $cost;
            let final_gnorm: f64 = $gnorm;
            if cost_history.last() != Some(&final_cost) {
                cost_history.push(final_cost);
                gradient_norm_history.push(final_gnorm);
                params_history.push(problem.params());
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

    // Initial residual.
    if problem.residuals_into(r.as_mut()).is_err() {
        report!(Termination::NumericalError, f64::INFINITY, 0.0);
    }
    n_residual_evals += 1;
    let mut cost = 0.5 * r.as_ref().squared_norm_l2();
    if !cost.is_finite() {
        // NaN/inf in the starting residual (e.g. log of a non-positive model
        // value) — bail immediately rather than spin to NoImprovement.
        report!(Termination::NumericalError, cost, 0.0);
    }
    if cost == 0.0 {
        report!(Termination::ResidualsZero, cost, 0.0);
    }

    let mut lambda = cfg.initial_lambda;
    let mut nu = 2.0_f64;

    loop {
        // Jacobian at the current point.
        if problem.jacobian_into(j.as_mut()).is_err() {
            report!(Termination::NumericalError, cost, 0.0);
        }
        n_jacobian_evals += 1;

        // Update the Moré column scaling from this Jacobian's column norms.
        // faer stores columns contiguously, so `col(j).norm_l2()` is a fast
        // SIMD reduction.
        for (jc, d) in diag.iter_mut().enumerate() {
            let cn = j.as_ref().col(jc).norm_l2();
            let cn = if cn > 0.0 { cn } else { 1.0 };
            *d = if diag_initialized { (*d).max(cn) } else { cn };
        }
        diag_initialized = true;

        // Gradient g = Jᵀr and first-order optimality test.
        let g = j.as_ref().transpose() * r.as_ref();
        let gnorm = g.as_ref().norm_max();
        // Record the accepted point's trajectory (index 0 = initial point).
        // `problem` holds the accepted parameters here (p_cur), so `params()`
        // is θ at this point — kept in lock-step length with cost_history.
        cost_history.push(cost);
        gradient_norm_history.push(gnorm);
        params_history.push(problem.params());
        // First-order optimality. For a bounded problem the raw ‖g‖_∞ is the
        // wrong measure at an active bound: the gradient component pointing
        // into the wall can stay large at a legitimate constrained optimum,
        // so the raw test never fires and the loop stalls to a NoImprovement
        // "failure" (G25; TI-003 `fraction` pinned at 1.0). Use a Coleman–Li-
        // style scaled measure ‖v·g‖_∞ instead — `v_i → 0` as parameter `i`
        // approaches the bound its descent direction points into — so an
        // active-bound gradient no longer blocks convergence. Unbounded
        // problems (`trust_scaling` = None) keep the raw norm, unchanged.
        // `gradient_norm`/history stay raw for observability.
        //
        // NOTE: `trust_scaling` returns v normalized by box width (v_i =
        // dist_i/range_i, in `spectrafit-solver::problem`), NOT scipy TRF's
        // unnormalized distance. So this gate is laxer than scipy's by ~1/range
        // for a wide-box parameter sitting mid-box facing a wall; the accuracy
        // gate (max |Δr²| vs the oracle) bounds the practical impact. Making
        // the optimality gate use the unnormalized distance is tracked as G28.
        let g_vec: Vec<f64> = (0..p).map(|i| g[(i, 0)]).collect();
        let trust_v = problem.trust_scaling(&g_vec);
        let opt_norm = match &trust_v {
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

        // Per-iteration step scaling: the monotone Moré `diag`, optionally folded
        // with Coleman–Li bound scaling (TRF) `D_i ← D_i / √v_i` so steps shrink
        // near active bounds. `diag` itself stays monotone for the next iteration.
        let step_diag: Vec<f64> = if cfg.bound_scaling {
            match trust_v {
                Some(v) => diag
                    .iter()
                    .zip(v.iter())
                    .map(|(&d, &vi)| d / vi.clamp(1e-12, 1.0).sqrt())
                    .collect(),
                None => diag.clone(),
            }
        } else {
            diag.clone()
        };

        // Factor the step operator ONCE for this outer iteration (the O(m·p²)
        // work: forming JᵀJ, or the thin SVD of J̃). `J` and `step_diag` are
        // fixed across the inner λ search — only λ changes — so every λ trial and
        // the geodesic acceleration solve reuse this factorization.
        let factor: StepFactor = match factorize(cfg.kind, j.as_ref(), &step_diag) {
            Ok(f) => f,
            Err(_) => report!(Termination::NumericalError, cost, gnorm),
        };

        // Inner λ search: shrink the trust region (raise λ) until a step is
        // accepted or the budget runs out. `p_cur` is invariant across trials —
        // params only change on accept (we break) or reject (we restore to
        // p_cur) — so capture it once instead of cloning it every trial.
        let p_cur = problem.params();
        let mut bumps = 0usize;
        loop {
            let step = match factor.solve(g.as_ref(), r.as_ref(), &step_diag, lambda) {
                Ok(s) => s,
                Err(StepError::NotPositiveDefinite) | Err(StepError::Factorization(_)) => {
                    lambda *= nu;
                    nu *= 2.0;
                    bumps += 1;
                    if !lambda.is_finite() || bumps > 200 {
                        report!(Termination::NoImprovement, cost, gnorm);
                    }
                    continue;
                }
            };
            let delta = step.delta;
            let pred = step.predicted_reduction;
            if !(pred.is_finite() && pred > 0.0) {
                lambda *= nu;
                nu *= 2.0;
                bumps += 1;
                if !lambda.is_finite() || bumps > 200 {
                    report!(Termination::NoImprovement, cost, gnorm);
                }
                continue;
            }

            // Optional geodesic acceleration: augment the velocity δ with the
            // second-directional-derivative term. Re-validate the predicted
            // reduction since the augmented step may not be a descent direction.
            let (delta, pred) = if cfg.geodesic {
                geodesic_augment(
                    problem,
                    &factor,
                    j.as_ref(),
                    r.as_ref(),
                    g.as_ref(),
                    &p_cur,
                    delta,
                    &step_diag,
                    lambda,
                    cfg.geodesic_h,
                    cfg.geodesic_alpha,
                    &mut n_residual_evals,
                )
            } else {
                (delta, pred)
            };
            if !(pred.is_finite() && pred > 0.0) {
                lambda *= nu;
                nu *= 2.0;
                bumps += 1;
                if !lambda.is_finite() || bumps > 200 {
                    report!(Termination::NoImprovement, cost, gnorm);
                }
                continue;
            }

            // Trial point: p_trial = p_applied + δ.
            let p_trial: Vec<f64> = (0..p).map(|i| p_cur[i] + delta[(i, 0)]).collect();
            problem.set_params(&p_trial);
            if problem.residuals_into(r_trial.as_mut()).is_err() {
                // Restore the last accepted point before bailing so `problem`
                // holds the accepted θ (not the NaN-producing trial) when
                // `report!` fires — keeps params_history lock-step with
                // cost_history regardless of the dedup, and makes the failed
                // result report the last good parameters.
                problem.set_params(&p_cur);
                report!(Termination::NumericalError, cost, gnorm);
            }
            n_residual_evals += 1;
            let cost_trial = 0.5 * r_trial.as_ref().squared_norm_l2();

            let actual = cost - cost_trial;
            // Gain ratio. When the problem's projection (bounds reflection /
            // clamping in `set_params`) clipped the proposed step, judging
            // `actual` against the RAW step's predicted reduction is wrong:
            // the phantom reduction from the clipped direction dominates
            // `pred`, ρ collapses, and legitimate refinements of the still-
            // free directions get rejected until λ inflates to NoImprovement
            // (G25, second mechanism). Recompute the model reduction for the
            // APPLIED step δₐ = p_applied − p_cur in that case. Interior
            // (unclipped) steps keep the factorization's `pred` unchanged.
            let p_applied = problem.params();
            let clipped = p_applied
                .iter()
                .zip(p_trial.iter())
                .any(|(a, t)| a != t);
            let pred_eff = if clipped {
                let delta_a = Mat::from_fn(p, 1, |i, _| p_applied[i] - p_cur[i]);
                let jda = j.as_ref() * delta_a.as_ref();
                -col_dot(g.as_ref(), delta_a.as_ref())
                    - 0.5 * jda.as_ref().squared_norm_l2()
            } else {
                pred
            };
            let rho = if pred_eff.is_finite() && pred_eff > 0.0 {
                actual / pred_eff
            } else {
                // Fully-clamped (δₐ = 0) or degenerate applied step: no
                // model reduction to judge against — treat as a rejection.
                0.0
            };

            if rho > 1e-4 {
                // Accept. Step norm uses the parameters the problem actually
                // applied (post-reflection), not the proposed δ.
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

                // Nielsen λ decrease on a successful step.
                lambda *= f64::max(1.0 / 3.0, 1.0 - (2.0 * rho - 1.0).powi(3));
                nu = 2.0;

                if cost == 0.0 {
                    report!(Termination::ResidualsZero, cost, gnorm);
                }
                if actual <= cfg.ftol * cost.max(f64::MIN_POSITIVE) {
                    report!(Termination::Ftol, cost, gnorm);
                }
                if step_norm <= cfg.xtol * (cfg.xtol + param_norm) {
                    report!(Termination::Xtol, cost, gnorm);
                }
                break; // re-evaluate the Jacobian at the new point
            } else {
                // Reject: restore parameters, shrink the trust region.
                problem.set_params(&p_cur);
                lambda *= nu;
                nu *= 2.0;
                bumps += 1;
                if !lambda.is_finite() || bumps > 200 {
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
