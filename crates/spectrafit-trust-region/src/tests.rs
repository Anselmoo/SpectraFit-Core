//! Framework-level tests: the problem contract (matrix-free operators) and the
//! shared Δ-radius driver loop on synthetic problems — no graph, no models.
//! Method-specific convergence tests live in the method crates (e.g.
//! `spectrafit-levenberg-marquardt`); here the subproblem solvers are minimal
//! reference implementations (Cauchy point, exact Gauss–Newton) chosen so the
//! driver's termination and radius-update behaviour is what's under test.

use std::cell::RefCell;

use approx::assert_relative_eq;
use faer::{Mat, MatMut};
use spectrafit_types::CoreError;

use crate::{
    minimize_tr, StepResult, Subproblem, SubproblemStep, Termination, TrustRegionConfig,
    TrustRegionProblem,
};

/// Linear residual `r(x) = A·x − b`, constant Jacobian `J = A`.
struct LinearProblem {
    a: Vec<Vec<f64>>, // m × p, row-major
    b: Vec<f64>,      // m
    x: Vec<f64>,      // current params, p
}

impl TrustRegionProblem for LinearProblem {
    fn n_residuals(&self) -> usize {
        self.a.len()
    }
    fn n_params(&self) -> usize {
        self.x.len()
    }
    fn params(&self) -> Vec<f64> {
        self.x.clone()
    }
    fn set_params(&mut self, p: &[f64]) {
        self.x.copy_from_slice(p);
    }
    fn residuals_into(&mut self, mut r: MatMut<'_, f64>) -> Result<(), CoreError> {
        for (i, row) in self.a.iter().enumerate() {
            let dot: f64 = row.iter().zip(&self.x).map(|(a, x)| a * x).sum();
            r[(i, 0)] = dot - self.b[i];
        }
        Ok(())
    }
    fn jacobian_into(&mut self, mut jac: MatMut<'_, f64>) -> Result<(), CoreError> {
        for (i, row) in self.a.iter().enumerate() {
            for (jx, &v) in row.iter().enumerate() {
                jac[(i, jx)] = v;
            }
        }
        Ok(())
    }
}

#[test]
fn matrix_free_operators_match_dense_jacobian() {
    // Constant Jacobian J = A (LinearProblem): the default apply_jacobian /
    // apply_jacobian_transpose must agree with explicit J·v and Jᵀ·u. This locks
    // the matrix-free contract that Krylov subproblem solvers (Steihaug) rely on.
    let a = vec![
        vec![1.0, 2.0, -1.0],
        vec![3.0, 1.0, 0.5],
        vec![-1.0, 1.0, 2.0],
        vec![2.0, -2.0, 1.0],
    ];
    let m = a.len();
    let p = a[0].len();
    let mut prob = LinearProblem {
        a: a.clone(),
        b: vec![0.0; m],
        x: vec![0.0; p],
    };

    // out = J·v
    let v = [0.7, -1.3, 0.25];
    let mut jv = vec![0.0; m];
    prob.apply_jacobian(&v, &mut jv).unwrap();
    for (i, row) in a.iter().enumerate() {
        let expected: f64 = row.iter().zip(&v).map(|(aij, vj)| aij * vj).sum();
        assert_relative_eq!(jv[i], expected, epsilon = 1e-12);
    }

    // out = Jᵀ·u
    let u = [0.4, -0.6, 1.1, 0.9];
    let mut jtu = vec![0.0; p];
    prob.apply_jacobian_transpose(&u, &mut jtu).unwrap();
    for (c, jtu_c) in jtu.iter().enumerate() {
        let expected: f64 = (0..m).map(|i| a[i][c] * u[i]).sum();
        assert_relative_eq!(*jtu_c, expected, epsilon = 1e-12);
    }
}

// ---------------------------------------------------------------------------
// Driver tests — minimize_tr termination paths and the NW Alg 4.1 Δ update.
// ---------------------------------------------------------------------------

/// Cauchy-point step: steepest descent to the model minimiser along `−g̃`,
/// clipped at the trust-region boundary. The weakest legitimate subproblem
/// solver — exercises the driver over many iterations.
struct CauchyStep;

impl SubproblemStep for CauchyStep {
    fn solve(&self, sub: &Subproblem<'_>, radius: f64) -> StepResult {
        let p = sub.n_params();
        let g = sub.gradient();
        let gnorm2 = g.squared_norm_l2();
        if gnorm2 == 0.0 {
            return StepResult {
                step: Mat::zeros(p, 1),
                predicted_reduction: 0.0,
                hit_boundary: false,
            };
        }
        let hg = sub.hvec(g);
        let ghg: f64 = (0..p).map(|i| g[(i, 0)] * hg[(i, 0)]).sum();
        let gnorm = gnorm2.sqrt();
        let tau_boundary = radius / gnorm;
        let tau_unconstrained = if ghg > 0.0 {
            gnorm2 / ghg
        } else {
            f64::INFINITY
        };
        let tau = tau_boundary.min(tau_unconstrained);
        let step = Mat::from_fn(p, 1, |i, _| -tau * g[(i, 0)]);
        let predicted_reduction = sub.predicted_reduction(step.as_ref());
        StepResult {
            step,
            predicted_reduction,
            hit_boundary: tau_boundary <= tau_unconstrained,
        }
    }
}

/// Exact Gauss–Newton step: solves `J̃ᵀJ̃·δ̃ = −g̃` by Gaussian elimination
/// (tests use p ≤ 3), clipped to the boundary. On a linear problem this jumps
/// to the least-squares optimum in a single accepted step.
struct GaussNewtonStep;

impl SubproblemStep for GaussNewtonStep {
    fn solve(&self, sub: &Subproblem<'_>, radius: f64) -> StepResult {
        let p = sub.n_params();
        let jac = sub.jacobian();
        let g = sub.gradient();
        // Dense normal-equations assembly is fine at test sizes.
        let mut h = vec![vec![0.0_f64; p + 1]; p]; // augmented [H | −g]
        for (r, row) in h.iter_mut().enumerate() {
            for c in 0..p {
                row[c] = (0..jac.nrows()).map(|i| jac[(i, r)] * jac[(i, c)]).sum();
            }
            row[p] = -g[(r, 0)];
        }
        // Gaussian elimination with partial pivoting.
        for col in 0..p {
            let pivot = (col..p)
                .max_by(|&x, &y| h[x][col].abs().total_cmp(&h[y][col].abs()))
                .unwrap_or(col);
            h.swap(col, pivot);
            let d = h[col][col];
            if d == 0.0 {
                return StepResult {
                    step: Mat::zeros(p, 1),
                    predicted_reduction: 0.0,
                    hit_boundary: false,
                };
            }
            let pivot_row = h[col].clone();
            for (r, row) in h.iter_mut().enumerate() {
                if r != col {
                    let f = row[col] / d;
                    for (cell, pv) in row.iter_mut().zip(&pivot_row).skip(col) {
                        *cell -= f * pv;
                    }
                }
            }
        }
        let mut step = Mat::from_fn(p, 1, |i, _| h[i][p] / h[i][i]);
        let norm = step.as_ref().squared_norm_l2().sqrt();
        let hit_boundary = norm > radius;
        if hit_boundary {
            let scale = radius / norm;
            step = Mat::from_fn(p, 1, |i, _| step[(i, 0)] * scale);
        }
        let predicted_reduction = sub.predicted_reduction(step.as_ref());
        StepResult {
            step,
            predicted_reduction,
            hit_boundary,
        }
    }
}

/// Degenerate solver: zero step, zero predicted reduction. The driver must
/// shrink Δ to the floor and stop with `NoImprovement` — never loop forever.
struct NullStep;

impl SubproblemStep for NullStep {
    fn solve(&self, sub: &Subproblem<'_>, _radius: f64) -> StepResult {
        StepResult {
            step: Mat::zeros(sub.n_params(), 1),
            predicted_reduction: 0.0,
            hit_boundary: false,
        }
    }
}

/// Wraps an inner solver, recording the radius the driver passes to each
/// `solve` call — the observable seam for the NW Alg 4.1 update rule.
struct RecordingStep<S: SubproblemStep> {
    inner: S,
    radii: RefCell<Vec<f64>>,
}

impl<S: SubproblemStep> SubproblemStep for RecordingStep<S> {
    fn solve(&self, sub: &Subproblem<'_>, radius: f64) -> StepResult {
        self.radii.borrow_mut().push(radius);
        self.inner.solve(sub, radius)
    }
}

/// Solver that wildly overestimates its predicted reduction: every step gets
/// ρ ≈ 0 and is rejected, so the driver must shrink Δ by 0.25 each retry.
struct OverconfidentStep;

impl SubproblemStep for OverconfidentStep {
    fn solve(&self, sub: &Subproblem<'_>, radius: f64) -> StepResult {
        let inner = CauchyStep.solve(sub, radius);
        StepResult {
            step: inner.step,
            predicted_reduction: 1e12,
            hit_boundary: inner.hit_boundary,
        }
    }
}

fn linear_problem(a: Vec<Vec<f64>>, b: Vec<f64>, x0: Vec<f64>) -> LinearProblem {
    LinearProblem { a, b, x: x0 }
}

fn tr_config() -> TrustRegionConfig {
    TrustRegionConfig::default()
}

/// A · x0 == b exactly ⇒ zero cost before any iteration.
#[test]
fn residuals_zero_at_start_short_circuits() {
    let a = vec![vec![1.0, 2.0], vec![3.0, 1.0]];
    let x0 = vec![1.0, -1.0];
    let b = vec![-1.0, 2.0]; // A·x0
    let mut prob = linear_problem(a, b, x0.clone());
    let report = minimize_tr(&mut prob, &CauchyStep, &tr_config());
    assert_eq!(report.termination, Termination::ResidualsZero);
    assert!(report.termination.was_successful());
    assert_eq!(report.n_iter, 0);
    assert_eq!(report.n_residual_evals, 1);
    assert_eq!(report.cost, 0.0);
    assert_eq!(prob.params(), x0, "params must be untouched");
}

/// x0 at the normal-equations optimum of an inconsistent system ⇒ g = Jᵀr = 0
/// with nonzero cost ⇒ first-order optimality (Gtol) before any step.
#[test]
fn gtol_at_start_when_gradient_vanishes() {
    // Aᵀb = 0 for b = (1, 1, −1), so x0 = 0 is the least-squares optimum.
    let a = vec![vec![1.0, 0.0], vec![0.0, 1.0], vec![1.0, 1.0]];
    let b = vec![1.0, 1.0, -1.0];
    let mut prob = linear_problem(a, b, vec![0.0, 0.0]);
    let report = minimize_tr(&mut prob, &CauchyStep, &tr_config());
    assert_eq!(report.termination, Termination::Gtol);
    assert!(report.termination.was_successful());
    assert_eq!(report.n_iter, 0);
    assert_relative_eq!(report.cost, 1.5, epsilon = 1e-12);
}

/// Consistent system, exact GN step, generous radius ⇒ one accepted step lands
/// exactly on the optimum and the driver reports zero residuals.
#[test]
fn gauss_newton_converges_in_one_step_on_consistent_system() {
    let a = vec![vec![1.0, 2.0], vec![3.0, 1.0], vec![-1.0, 1.5]];
    let x_true = [2.0, -0.5];
    let b: Vec<f64> = a
        .iter()
        .map(|row| row[0] * x_true[0] + row[1] * x_true[1])
        .collect();
    let mut prob = linear_problem(a, b, vec![0.0, 0.0]);
    let cfg = TrustRegionConfig {
        delta0: 1e6,
        max_delta: 1e6,
        ..tr_config()
    };
    let report = minimize_tr(&mut prob, &GaussNewtonStep, &cfg);
    // The exact-zero cost may land as ~1e-30 in floating point, in which case
    // the driver exits via Gtol on the next iteration instead of ResidualsZero
    // — both are correct convergence outcomes here.
    assert!(
        matches!(
            report.termination,
            Termination::ResidualsZero | Termination::Gtol
        ),
        "unexpected termination: {:?}",
        report.termination
    );
    assert_eq!(report.n_iter, 1);
    assert!(
        report.cost < 1e-18,
        "cost not driven to zero: {}",
        report.cost
    );
    let p = prob.params();
    assert_relative_eq!(p[0], x_true[0], epsilon = 1e-9);
    assert_relative_eq!(p[1], x_true[1], epsilon = 1e-9);
}

/// Inconsistent system ⇒ GN jumps to the normal-equations solution, then the
/// next outer iteration sees a vanishing gradient (Gtol). Pins both the final
/// parameters and the analytically-known optimal cost.
#[test]
fn gauss_newton_converges_to_normal_equations_solution() {
    let a = vec![vec![1.0, 0.0], vec![0.0, 1.0], vec![1.0, 1.0]];
    let b = vec![2.0, 1.0, 1.0];
    // AᵀA = [[2,1],[1,2]], Aᵀb = (3, 2) ⇒ x* = (4/3, 1/3), cost* = 2/3.
    let mut prob = linear_problem(a, b, vec![-3.0, 5.0]);
    let cfg = TrustRegionConfig {
        delta0: 1e6,
        max_delta: 1e6,
        ..tr_config()
    };
    let report = minimize_tr(&mut prob, &GaussNewtonStep, &cfg);
    assert!(
        report.termination.was_successful(),
        "unexpected termination: {:?}",
        report.termination
    );
    let p = prob.params();
    assert_relative_eq!(p[0], 4.0 / 3.0, epsilon = 1e-9);
    assert_relative_eq!(p[1], 1.0 / 3.0, epsilon = 1e-9);
    assert_relative_eq!(report.cost, 2.0 / 3.0, epsilon = 1e-9);
}

/// Problem whose residual evaluation fails ⇒ immediate NumericalError with an
/// infinite cost, no residual evals counted beyond the failed one.
#[test]
fn numerical_error_on_failing_residual_evaluation() {
    struct FailingProblem;
    impl TrustRegionProblem for FailingProblem {
        fn n_residuals(&self) -> usize {
            2
        }
        fn n_params(&self) -> usize {
            1
        }
        fn params(&self) -> Vec<f64> {
            vec![0.0]
        }
        fn set_params(&mut self, _p: &[f64]) {}
        fn residuals_into(&mut self, _r: MatMut<'_, f64>) -> Result<(), CoreError> {
            Err(CoreError::Eval("synthetic failure".into()))
        }
        fn jacobian_into(&mut self, _jac: MatMut<'_, f64>) -> Result<(), CoreError> {
            Ok(())
        }
    }
    let report = minimize_tr(&mut FailingProblem, &CauchyStep, &tr_config());
    assert_eq!(report.termination, Termination::NumericalError);
    assert!(!report.termination.was_successful());
    assert!(report.cost.is_infinite());
    assert_eq!(report.n_iter, 0);
}

/// NaN residuals ⇒ non-finite cost ⇒ NumericalError before iterating.
#[test]
fn numerical_error_on_nan_residuals() {
    struct NanProblem;
    impl TrustRegionProblem for NanProblem {
        fn n_residuals(&self) -> usize {
            2
        }
        fn n_params(&self) -> usize {
            1
        }
        fn params(&self) -> Vec<f64> {
            vec![0.0]
        }
        fn set_params(&mut self, _p: &[f64]) {}
        fn residuals_into(&mut self, mut r: MatMut<'_, f64>) -> Result<(), CoreError> {
            r[(0, 0)] = f64::NAN;
            r[(1, 0)] = 1.0;
            Ok(())
        }
        fn jacobian_into(&mut self, _jac: MatMut<'_, f64>) -> Result<(), CoreError> {
            Ok(())
        }
    }
    let report = minimize_tr(&mut NanProblem, &CauchyStep, &tr_config());
    assert_eq!(report.termination, Termination::NumericalError);
    assert_eq!(report.n_iter, 0);
}

/// Impossible tolerances + inconsistent system ⇒ the only exit is the
/// residual-evaluation budget. The driver must respect max_nfev.
#[test]
fn max_eval_budget_is_respected() {
    let a = vec![vec![1.0, 0.0], vec![0.0, 1.0], vec![1.0, 1.0]];
    let b = vec![2.0, 1.0, 1.0];
    let mut prob = linear_problem(a, b, vec![-3.0, 5.0]);
    let cfg = TrustRegionConfig {
        ftol: 0.0,
        xtol: 0.0,
        gtol: 0.0,
        max_nfev: 5,
        ..tr_config()
    };
    let report = minimize_tr(&mut prob, &CauchyStep, &cfg);
    assert_eq!(report.termination, Termination::MaxEval);
    assert!(!report.termination.was_successful());
    assert!(report.n_residual_evals >= 5);
    // One overshoot at most: the check sits after the trial evaluation.
    assert!(report.n_residual_evals <= 6);
}

/// A degenerate subproblem (zero step, zero predicted reduction) must shrink Δ
/// to the floor and stop with NoImprovement — never spin forever.
#[test]
fn no_improvement_on_degenerate_subproblem() {
    let a = vec![vec![1.0, 0.0], vec![0.0, 1.0], vec![1.0, 1.0]];
    let b = vec![2.0, 1.0, 1.0];
    let mut prob = linear_problem(a, b, vec![-3.0, 5.0]);
    let report = minimize_tr(&mut prob, &NullStep, &tr_config());
    assert_eq!(report.termination, Termination::NoImprovement);
    assert!(!report.termination.was_successful());
    assert_eq!(report.n_iter, 0);
}

/// Rejected steps (ρ ≈ 0) must shrink Δ by exactly 0.25 per retry — the
/// contraction half of Nocedal–Wright Algorithm 4.1, observed through the
/// radius the driver hands to each solve call.
#[test]
fn radius_shrinks_by_quarter_on_rejected_steps() {
    let a = vec![vec![1.0, 0.0], vec![0.0, 1.0], vec![1.0, 1.0]];
    let b = vec![2.0, 1.0, 1.0];
    let mut prob = linear_problem(a, b, vec![-3.0, 5.0]);
    let step = RecordingStep {
        inner: OverconfidentStep,
        radii: RefCell::new(Vec::new()),
    };
    let cfg = TrustRegionConfig {
        max_nfev: 4,
        ..tr_config()
    };
    let report = minimize_tr(&mut prob, &step, &cfg);
    assert_eq!(report.termination, Termination::MaxEval);
    let radii = step.radii.borrow();
    assert!(
        radii.len() >= 3,
        "expected several solve calls, got {radii:?}"
    );
    for w in radii.windows(2) {
        assert_relative_eq!(w[1], w[0] * 0.25, epsilon = 1e-15);
    }
}

/// Very good boundary steps (ρ ≈ 1 on a linear problem, where the quadratic
/// model is exact) must double Δ — the expansion half of NW Algorithm 4.1.
#[test]
fn radius_doubles_on_good_boundary_steps() {
    let a = vec![vec![1.0, 0.0], vec![0.0, 1.0], vec![1.0, 1.0]];
    let b = vec![2.0, 1.0, 1.0];
    let mut prob = linear_problem(a, b, vec![-3.0, 5.0]);
    let step = RecordingStep {
        inner: CauchyStep,
        radii: RefCell::new(Vec::new()),
    };
    // Tiny initial radius: the first Cauchy steps are boundary-clipped with
    // ρ = 1 (linear ⇒ model exact), so Δ must double call over call.
    let cfg = TrustRegionConfig {
        delta0: 1e-3,
        ..tr_config()
    };
    let report = minimize_tr(&mut prob, &step, &cfg);
    assert!(
        report.termination.was_successful(),
        "unexpected termination: {:?}",
        report.termination
    );
    let radii = step.radii.borrow();
    assert!(
        radii.len() >= 3,
        "expected several solve calls, got {radii:?}"
    );
    assert_relative_eq!(radii[0], 1e-3, epsilon = 1e-15);
    assert_relative_eq!(radii[1], 2e-3, epsilon = 1e-15);
    assert_relative_eq!(radii[2], 4e-3, epsilon = 1e-15);
}

/// Report bookkeeping: histories are parallel arrays ending at the terminal
/// cost, index 0 is the initial point, and params_history stays empty (this
/// driver documents that it does not record the θ trajectory).
#[test]
fn report_history_invariants_hold() {
    let a = vec![vec![1.0, 0.0], vec![0.0, 1.0], vec![1.0, 1.0]];
    let b = vec![2.0, 1.0, 1.0];
    let x0 = vec![-3.0, 5.0];
    // Initial cost ½‖A·x0 − b‖².
    let initial_cost: f64 = 0.5
        * a.iter()
            .zip(&b)
            .map(|(row, bi)| {
                let r = row[0] * x0[0] + row[1] * x0[1] - bi;
                r * r
            })
            .sum::<f64>();
    let mut prob = linear_problem(a, b, x0);
    let cfg = TrustRegionConfig {
        delta0: 1e6,
        max_delta: 1e6,
        ..tr_config()
    };
    let report = minimize_tr(&mut prob, &GaussNewtonStep, &cfg);
    assert_eq!(
        report.cost_history.len(),
        report.gradient_norm_history.len()
    );
    assert!(!report.cost_history.is_empty());
    assert_relative_eq!(report.cost_history[0], initial_cost, epsilon = 1e-9);
    assert_relative_eq!(
        *report.cost_history.last().unwrap(),
        report.cost,
        epsilon = 1e-12
    );
    assert!(report.params_history.is_empty());
    // Cost history is non-increasing: the driver only records accepted points.
    for w in report.cost_history.windows(2) {
        assert!(
            w[1] <= w[0] + 1e-12,
            "cost increased: {:?}",
            report.cost_history
        );
    }
}

/// G25 — a stall against an active bound with ~zero projected gradient is a
/// constrained optimum and must terminate as SUCCESS (Gtol via the
/// Coleman–Li-scaled measure), not a NoImprovement failure. Mirrors the LM
/// driver's test; the Δ-radius driver shares both fixes (scaled optimality
/// at the gtol gate, applied-step gain ratio on clipped proposals).
#[test]
fn bound_pinned_optimum_terminates_as_success() {
    struct BoundedProblem {
        x: f64,
    }
    impl TrustRegionProblem for BoundedProblem {
        fn n_residuals(&self) -> usize {
            1
        }
        fn n_params(&self) -> usize {
            1
        }
        fn params(&self) -> Vec<f64> {
            vec![self.x]
        }
        fn set_params(&mut self, p: &[f64]) {
            self.x = p[0].clamp(0.0, 1.0);
        }
        fn residuals_into(&mut self, mut r: MatMut<'_, f64>) -> Result<(), CoreError> {
            r[(0, 0)] = self.x - 2.0;
            Ok(())
        }
        fn jacobian_into(&mut self, mut jac: MatMut<'_, f64>) -> Result<(), CoreError> {
            jac[(0, 0)] = 1.0;
            Ok(())
        }
        fn trust_scaling(&self, grad: &[f64]) -> Option<Vec<f64>> {
            let g = grad[0];
            let dist = if g < 0.0 {
                1.0 - self.x
            } else if g > 0.0 {
                self.x
            } else {
                (1.0 - self.x).min(self.x)
            };
            Some(vec![dist.clamp(1e-9, 1.0)])
        }
    }
    let mut prob = BoundedProblem { x: 0.5 };
    let report = minimize_tr(&mut prob, &CauchyStep, &tr_config());
    assert!(
        report.termination.was_successful(),
        "bound-pinned optimum misclassified: {:?} (gnorm {})",
        report.termination,
        report.gradient_norm
    );
    assert_relative_eq!(prob.x, 1.0, epsilon = 1e-9);
}
