//! Self-contained convergence tests on synthetic problems — no graph, no models.

use approx::assert_relative_eq;
use faer::MatMut;
use spectrafit_types::CoreError;

use crate::{minimize, select_regime, StepKind, StrategyConfig, TrustRegionProblem};

/// Linear residual `r(x) = A·x − b`, constant Jacobian `J = A`.
///
/// `½‖r‖²` is a convex quadratic, so the minimiser is the normal-equations
/// solution and any correct LM step reaches it in one accepted iteration.
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

/// Rosenbrock as least squares: `r₁ = 10(x₂ − x₁²)`, `r₂ = 1 − x₁`.
/// Global minimum at `(1, 1)` with cost `0`.
struct RosenbrockProblem {
    x: [f64; 2],
}

impl TrustRegionProblem for RosenbrockProblem {
    fn n_residuals(&self) -> usize {
        2
    }
    fn n_params(&self) -> usize {
        2
    }
    fn params(&self) -> Vec<f64> {
        self.x.to_vec()
    }
    fn set_params(&mut self, p: &[f64]) {
        self.x = [p[0], p[1]];
    }
    fn residuals_into(&mut self, mut r: MatMut<'_, f64>) -> Result<(), CoreError> {
        r[(0, 0)] = 10.0 * (self.x[1] - self.x[0] * self.x[0]);
        r[(1, 0)] = 1.0 - self.x[0];
        Ok(())
    }
    fn jacobian_into(&mut self, mut jac: MatMut<'_, f64>) -> Result<(), CoreError> {
        // ∂r₁/∂x = [−20·x₁, 10]; ∂r₂/∂x = [−1, 0]
        jac[(0, 0)] = -20.0 * self.x[0];
        jac[(0, 1)] = 10.0;
        jac[(1, 0)] = -1.0;
        jac[(1, 1)] = 0.0;
        Ok(())
    }
}

/// Sloppy two-exponential `m(t) = e^{-k₁t} + e^{-k₂t}` (free `k₁,k₂`). With
/// nearby rates the Jacobian columns are near-collinear (`JᵀJ` ill-conditioned),
/// the canonical "sloppy" surface where geodesic acceleration pays off.
struct TwoExpProblem {
    t: Vec<f64>,
    y: Vec<f64>,
    k: [f64; 2],
}

impl TwoExpProblem {
    fn new(k_true: [f64; 2], k_init: [f64; 2]) -> Self {
        let t: Vec<f64> = (0..25).map(|i| 0.1 + 0.12 * i as f64).collect();
        let y: Vec<f64> = t
            .iter()
            .map(|&ti| (-k_true[0] * ti).exp() + (-k_true[1] * ti).exp())
            .collect();
        Self { t, y, k: k_init }
    }
}

impl TrustRegionProblem for TwoExpProblem {
    fn n_residuals(&self) -> usize {
        self.t.len()
    }
    fn n_params(&self) -> usize {
        2
    }
    fn params(&self) -> Vec<f64> {
        self.k.to_vec()
    }
    fn set_params(&mut self, p: &[f64]) {
        self.k = [p[0], p[1]];
    }
    fn residuals_into(&mut self, mut r: MatMut<'_, f64>) -> Result<(), CoreError> {
        for (i, &ti) in self.t.iter().enumerate() {
            let m = (-self.k[0] * ti).exp() + (-self.k[1] * ti).exp();
            r[(i, 0)] = m - self.y[i];
        }
        Ok(())
    }
    fn jacobian_into(&mut self, mut jac: MatMut<'_, f64>) -> Result<(), CoreError> {
        for (i, &ti) in self.t.iter().enumerate() {
            jac[(i, 0)] = -ti * (-self.k[0] * ti).exp();
            jac[(i, 1)] = -ti * (-self.k[1] * ti).exp();
        }
        Ok(())
    }
}

fn cfg(kind: StepKind) -> StrategyConfig {
    StrategyConfig {
        kind,
        ..Default::default()
    }
}

#[test]
fn linear_problem_recovers_least_squares_solution_normal_eq() {
    // Overdetermined: 3 eqs, 2 unknowns. True x = [2, -1]; exactly consistent.
    let a = vec![vec![1.0, 0.0], vec![0.0, 1.0], vec![1.0, 1.0]];
    let true_x = [2.0, -1.0];
    let b: Vec<f64> = a
        .iter()
        .map(|row| row[0] * true_x[0] + row[1] * true_x[1])
        .collect();
    let mut prob = LinearProblem {
        a,
        b,
        x: vec![0.0, 0.0],
    };
    let report = minimize(&mut prob, &cfg(StepKind::NormalEqLlt));
    assert!(report.termination.was_successful(), "{:?}", report);
    assert_relative_eq!(prob.x[0], 2.0, epsilon = 1e-8);
    assert_relative_eq!(prob.x[1], -1.0, epsilon = 1e-8);
    assert!(report.cost < 1e-16, "cost = {}", report.cost);
}

#[test]
fn linear_problem_recovers_least_squares_solution_svd() {
    let a = vec![vec![1.0, 0.0], vec![0.0, 1.0], vec![1.0, 1.0]];
    let true_x = [2.0, -1.0];
    let b: Vec<f64> = a
        .iter()
        .map(|row| row[0] * true_x[0] + row[1] * true_x[1])
        .collect();
    let mut prob = LinearProblem {
        a,
        b,
        x: vec![0.0, 0.0],
    };
    let report = minimize(&mut prob, &cfg(StepKind::SvdSecular));
    assert!(report.termination.was_successful(), "{:?}", report);
    assert_relative_eq!(prob.x[0], 2.0, epsilon = 1e-8);
    assert_relative_eq!(prob.x[1], -1.0, epsilon = 1e-8);
}

#[test]
fn both_step_kinds_agree_on_linear_solution() {
    let a = vec![
        vec![1.0, 2.0],
        vec![3.0, 1.0],
        vec![-1.0, 1.0],
        vec![2.0, -2.0],
    ];
    let b = vec![1.0, 2.0, 0.5, -0.3];
    let solve = |kind| {
        let mut prob = LinearProblem {
            a: a.clone(),
            b: b.clone(),
            x: vec![0.0, 0.0],
        };
        let _ = minimize(&mut prob, &cfg(kind));
        prob.x
    };
    let ne = solve(StepKind::NormalEqLlt);
    let svd = solve(StepKind::SvdSecular);
    assert_relative_eq!(ne[0], svd[0], epsilon = 1e-7);
    assert_relative_eq!(ne[1], svd[1], epsilon = 1e-7);
}

#[test]
fn rosenbrock_converges_to_minimum() {
    let mut prob = RosenbrockProblem { x: [-1.2, 1.0] };
    let report = minimize(&mut prob, &cfg(StepKind::NormalEqLlt));
    assert!(report.termination.was_successful(), "{:?}", report);
    assert_relative_eq!(prob.x[0], 1.0, epsilon = 1e-6);
    assert_relative_eq!(prob.x[1], 1.0, epsilon = 1e-6);
    assert!(report.cost < 1e-12, "cost = {}", report.cost);
}

#[test]
fn rosenbrock_converges_via_svd() {
    let mut prob = RosenbrockProblem { x: [-1.2, 1.0] };
    let report = minimize(&mut prob, &cfg(StepKind::SvdSecular));
    assert!(report.termination.was_successful(), "{:?}", report);
    assert_relative_eq!(prob.x[0], 1.0, epsilon = 1e-6);
    assert_relative_eq!(prob.x[1], 1.0, epsilon = 1e-6);
}

#[test]
fn geodesic_speeds_up_sloppy_two_exponential() {
    let k_true = [0.9_f64, 1.4_f64]; // nearby rates ⇒ sloppy
    let k_init = [0.4_f64, 2.4_f64];

    // Plain LM baseline.
    let mut p_lm = TwoExpProblem::new(k_true, k_init);
    let rep_lm = minimize(&mut p_lm, &cfg(StepKind::NormalEqLlt));

    // Geodesic-accelerated.
    let mut p_geo = TwoExpProblem::new(k_true, k_init);
    let cfg_geo = StrategyConfig {
        geodesic: true,
        ..cfg(StepKind::NormalEqLlt)
    };
    let rep_geo = minimize(&mut p_geo, &cfg_geo);

    // Both converge to the same (rate-symmetric) optimum.
    assert!(rep_lm.termination.was_successful(), "lm: {:?}", rep_lm);
    assert!(rep_geo.termination.was_successful(), "geo: {:?}", rep_geo);
    assert!(rep_geo.cost < 1e-12, "geodesic cost {}", rep_geo.cost);
    // Recovered rates (allow the k₁↔k₂ symmetry).
    let mut got = p_geo.k;
    got.sort_by(|a, b| a.partial_cmp(b).unwrap());
    assert_relative_eq!(got[0], 0.9, max_relative = 1e-4);
    assert_relative_eq!(got[1], 1.4, max_relative = 1e-4);
    // On this sloppy surface geodesic should not need more accepted iterations
    // than plain LM (typically fewer).
    assert!(
        rep_geo.n_iter <= rep_lm.n_iter,
        "geodesic n_iter={} should be ≤ LM n_iter={}",
        rep_geo.n_iter,
        rep_lm.n_iter
    );
}

#[test]
fn regime_selector_picks_paths() {
    assert_eq!(select_regime(100_000, 3), StepKind::NormalEqLlt); // n ≫ p
    assert_eq!(select_regime(2_000, 150), StepKind::SvdSecular); // large p
    assert_eq!(select_regime(10, 8), StepKind::NormalEqLlt); // borderline → NE
}

#[test]
fn params_history_records_theta_trajectory_converging_to_truth() {
    // Invariant V (V3) raw material: the LM driver records the free-parameter
    // vector θ at every accepted point, lock-step with cost_history, and the
    // trajectory approaches the known truth (1, 1). This is what the
    // convergence-to-truth metric dₖ = ‖(θₖ − θ_true)/s‖₂ is computed from.
    let theta_true = [1.0_f64, 1.0];
    let mut prob = RosenbrockProblem { x: [-1.2, 1.0] };
    let report = minimize(&mut prob, &cfg(StepKind::NormalEqLlt));
    assert!(report.termination.was_successful(), "{:?}", report);

    // Lock-step length invariant with the cost trajectory.
    assert_eq!(
        report.params_history.len(),
        report.cost_history.len(),
        "params_history must be recorded once per cost_history entry"
    );
    // A multi-step descent on Rosenbrock records more than the initial point.
    assert!(
        report.params_history.len() >= 2,
        "expected a multi-point θ trajectory, got {}",
        report.params_history.len()
    );
    // Every recorded θ has the free-parameter dimension (n_params == 2).
    assert!(report.params_history.iter().all(|t| t.len() == 2));

    // Index 0 is the initial guess; the last is the recovered solution.
    let first = &report.params_history[0];
    assert_relative_eq!(first[0], -1.2, epsilon = 1e-12);
    assert_relative_eq!(first[1], 1.0, epsilon = 1e-12);
    let last = report.params_history.last().unwrap();
    assert_relative_eq!(last[0], 1.0, epsilon = 1e-6);
    assert_relative_eq!(last[1], 1.0, epsilon = 1e-6);

    // Scale-normalized distance to truth dₖ = ‖(θₖ − θ_true)/s‖₂, s = |θ_true|.max(1).
    let dist = |theta: &[f64]| -> f64 {
        theta
            .iter()
            .zip(theta_true.iter())
            .map(|(&tk, &tt)| ((tk - tt) / tt.abs().max(1.0)).powi(2))
            .sum::<f64>()
            .sqrt()
    };
    let d_first = dist(first);
    let d_last = dist(last);
    // Ends essentially at the truth, and far closer than it started (the
    // Stage-1 V&V acceptance criterion: dₖ → ≤ recovery tol).
    assert!(d_last < 1e-6, "final θ-distance to truth = {}", d_last);
    assert!(
        d_last < d_first,
        "trajectory did not approach truth: {} -> {}",
        d_first,
        d_last
    );
}

// ---------------------------------------------------------------------------
// G25 — bound-aware termination (scipy-TRF scaled first-order measure)
// ---------------------------------------------------------------------------

/// 1-D bounded problem: `r(x) = x − 2` with box `[0, 1]`.
///
/// The unconstrained optimum (x = 2) lies outside the box; the constrained
/// optimum is x = 1 with the bound active. `set_params` clamps into the box
/// (projection lives in the problem, as with `LmProblem`); `trust_scaling`
/// mirrors the Coleman–Li fraction-of-box-remaining semantics of
/// `spectrafit-solver::problem::LmProblem::trust_scaling`.
struct BoundedProblem {
    x: f64,
    lo: f64,
    hi: f64,
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
        self.x = p[0].clamp(self.lo, self.hi);
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
            self.hi - self.x
        } else if g > 0.0 {
            self.x - self.lo
        } else {
            (self.hi - self.x).min(self.x - self.lo)
        };
        let range = self.hi - self.lo;
        Some(vec![(dist / range).clamp(1e-9, 1.0)])
    }
}

/// A stall against an active bound with ~zero projected gradient is a
/// legitimate constrained optimum and must terminate as a SUCCESS (Gtol via
/// the Coleman–Li-scaled measure ‖v·g‖_∞, as scipy TRF does) — not as a
/// `NoImprovement` failure. This is the G25 repro shape (TI-003 nested
/// order-1: `fraction` pinned at 1.0).
#[test]
fn bound_pinned_optimum_terminates_as_success() {
    let mut prob = BoundedProblem {
        x: 0.5,
        lo: 0.0,
        hi: 1.0,
    };
    let cfg = StrategyConfig::default();
    let report = minimize(&mut prob, &cfg);
    assert!(
        report.termination.was_successful(),
        "bound-pinned optimum misclassified: {:?} (gnorm {})",
        report.termination,
        report.gradient_norm
    );
    assert_relative_eq!(prob.x, 1.0, epsilon = 1e-9);
}

/// Control: the same problem WITHOUT bounds must still converge to the
/// unconstrained optimum x = 2 — the scaled measure must not perturb the
/// unbounded path (trust_scaling = None ⇒ raw ‖g‖_∞, existing behavior).
#[test]
fn unbounded_control_still_reaches_unconstrained_optimum() {
    struct FreeProblem {
        x: f64,
    }
    impl TrustRegionProblem for FreeProblem {
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
            self.x = p[0];
        }
        fn residuals_into(&mut self, mut r: MatMut<'_, f64>) -> Result<(), CoreError> {
            r[(0, 0)] = self.x - 2.0;
            Ok(())
        }
        fn jacobian_into(&mut self, mut jac: MatMut<'_, f64>) -> Result<(), CoreError> {
            jac[(0, 0)] = 1.0;
            Ok(())
        }
    }
    let mut prob = FreeProblem { x: 0.5 };
    let report = minimize(&mut prob, &StrategyConfig::default());
    assert!(report.termination.was_successful());
    assert_relative_eq!(prob.x, 2.0, epsilon = 1e-6);
}

/// A bound-pinned point where the FREE direction still has a large gradient
/// must NOT be upgraded: 2-D problem, x₀ pinned at its bound but x₁ far from
/// its optimum at the moment x₀ pins. The solver must keep iterating on x₁
/// (not exit early via the scaled measure) and finish at the true constrained
/// optimum (1, 3).
#[test]
fn scaled_measure_does_not_mask_free_direction_gradient() {
    struct MixedProblem {
        x: [f64; 2],
    }
    impl TrustRegionProblem for MixedProblem {
        fn n_residuals(&self) -> usize {
            2
        }
        fn n_params(&self) -> usize {
            2
        }
        fn params(&self) -> Vec<f64> {
            self.x.to_vec()
        }
        fn set_params(&mut self, p: &[f64]) {
            // x0 boxed in [0, 1]; x1 free.
            self.x = [p[0].clamp(0.0, 1.0), p[1]];
        }
        fn residuals_into(&mut self, mut r: MatMut<'_, f64>) -> Result<(), CoreError> {
            r[(0, 0)] = self.x[0] - 2.0;
            r[(1, 0)] = self.x[1] - 3.0;
            Ok(())
        }
        fn jacobian_into(&mut self, mut jac: MatMut<'_, f64>) -> Result<(), CoreError> {
            jac[(0, 0)] = 1.0;
            jac[(0, 1)] = 0.0;
            jac[(1, 0)] = 0.0;
            jac[(1, 1)] = 1.0;
            Ok(())
        }
        fn trust_scaling(&self, grad: &[f64]) -> Option<Vec<f64>> {
            let g0 = grad[0];
            let dist = if g0 < 0.0 {
                1.0 - self.x[0]
            } else if g0 > 0.0 {
                self.x[0]
            } else {
                (1.0 - self.x[0]).min(self.x[0])
            };
            // x1 unbounded ⇒ v = 1 (mirrors LmProblem: infinite range ⇒ 1.0).
            Some(vec![dist.clamp(1e-9, 1.0), 1.0])
        }
    }
    let mut prob = MixedProblem { x: [0.5, -50.0] };
    let report = minimize(&mut prob, &StrategyConfig::default());
    assert!(
        report.termination.was_successful(),
        "constrained optimum misclassified: {:?}",
        report.termination
    );
    assert_relative_eq!(prob.x[0], 1.0, epsilon = 1e-9);
    assert_relative_eq!(prob.x[1], 3.0, epsilon = 1e-6);
}
