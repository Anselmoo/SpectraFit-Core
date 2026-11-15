//! Self-contained convergence tests on synthetic problems — no graph, no models.

use approx::assert_relative_eq;
use faer::MatMut;
use spectrafit_types::CoreError;

use crate::{minimize, select_regime, StepKind, StrategyConfig, Termination, TrustRegionProblem};

/// Linear residual `r(x) = A·x − b`, constant Jacobian `J = A`.
///
/// `½‖r‖²` is a convex quadratic, so the minimiser is the normal-equations
/// solution and any correct LM step reaches it in one accepted iteration.
struct LinearProblem {
    a: Vec<Vec<f64>>, // m × p, row-major
    b: Vec<f64>,      // m
    x: Vec<f64>,      // current params, p
    /// Parameter vector at every `jacobian_into` call, in call order. Lets a
    /// test name the point the driver's reported `gradient_norm` is supposed
    /// to refer to (the most recent Jacobian evaluation) without guessing.
    jac_points: Vec<Vec<f64>>,
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
        self.jac_points.push(self.x.clone());
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

/// Pin faer's global parallelism to sequential dispatch. `minimize`'s
/// "deterministic" guarantee (see its doc comment) holds only under a fixed
/// parallelism policy — `spectrafit-solver::fit` sets this for the whole
/// fit, but these framework-level tests call the driver directly, so a test
/// that compares iterates (a history vector or a final parameter value)
/// exactly must set it itself rather than depend on faer's default.
fn seq() {
    faer::set_global_parallelism(faer::Par::Seq);
}

#[test]
fn linear_problem_recovers_least_squares_solution_normal_eq() {
    seq();
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
        jac_points: Vec::new(),
    };
    let report = minimize(&mut prob, &cfg(StepKind::NormalEqLlt));
    assert!(report.termination.was_successful(), "{:?}", report);
    assert_relative_eq!(prob.x[0], 2.0, epsilon = 1e-8);
    assert_relative_eq!(prob.x[1], -1.0, epsilon = 1e-8);
    assert!(report.cost < 1e-16, "cost = {}", report.cost);
}

#[test]
fn linear_problem_recovers_least_squares_solution_svd() {
    seq();
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
        jac_points: Vec::new(),
    };
    let report = minimize(&mut prob, &cfg(StepKind::SvdSecular));
    assert!(report.termination.was_successful(), "{:?}", report);
    assert_relative_eq!(prob.x[0], 2.0, epsilon = 1e-8);
    assert_relative_eq!(prob.x[1], -1.0, epsilon = 1e-8);
}

#[test]
fn both_step_kinds_agree_on_linear_solution() {
    seq();
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
            jac_points: Vec::new(),
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
    seq();
    let mut prob = RosenbrockProblem { x: [-1.2, 1.0] };
    let report = minimize(&mut prob, &cfg(StepKind::NormalEqLlt));
    assert!(report.termination.was_successful(), "{:?}", report);
    assert_relative_eq!(prob.x[0], 1.0, epsilon = 1e-6);
    assert_relative_eq!(prob.x[1], 1.0, epsilon = 1e-6);
    assert!(report.cost < 1e-12, "cost = {}", report.cost);
}

#[test]
fn rosenbrock_converges_via_svd() {
    seq();
    let mut prob = RosenbrockProblem { x: [-1.2, 1.0] };
    let report = minimize(&mut prob, &cfg(StepKind::SvdSecular));
    assert!(report.termination.was_successful(), "{:?}", report);
    assert_relative_eq!(prob.x[0], 1.0, epsilon = 1e-6);
    assert_relative_eq!(prob.x[1], 1.0, epsilon = 1e-6);
}

#[test]
fn geodesic_speeds_up_sloppy_two_exponential() {
    seq();
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
    seq();
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
// Bound-aware termination (scipy-TRF scaled first-order measure)
// ---------------------------------------------------------------------------

/// 1-D bounded problem: `r(x) = x − 2` with box `[0, 1]`.
///
/// The unconstrained optimum (x = 2) lies outside the box; the constrained
/// optimum is x = 1 with the bound active. `set_params` clamps into the box
/// (projection lives in the problem, as with `LmProblem`); `trust_scaling`
/// mirrors the Coleman–Li fraction-of-box-remaining semantics of
/// `spectrafit-solver::lm_problem::LmProblem::trust_scaling`.
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
/// `NoImprovement` failure. This is the repro shape for TI-003 (nested
/// order-1: `fraction` pinned at 1.0).
#[test]
fn bound_pinned_optimum_terminates_as_success() {
    seq();
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
    seq();
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
    seq();
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

/// `‖Aᵀ(A·x − b)‖∞` — the gradient infinity-norm of `½‖A·x − b‖²` at `x`,
/// computed independently of the driver so a test can pin which *point* the
/// driver's reported `gradient_norm` was taken at.
fn grad_inf_norm(a: &[Vec<f64>], b: &[f64], x: &[f64]) -> f64 {
    let r: Vec<f64> = a
        .iter()
        .zip(b)
        .map(|(row, bi)| row.iter().zip(x).map(|(aij, xj)| aij * xj).sum::<f64>() - bi)
        .collect();
    (0..x.len())
        .map(|c| {
            a.iter()
                .zip(&r)
                .map(|(row, ri)| row[c] * ri)
                .sum::<f64>()
                .abs()
        })
        .fold(0.0_f64, f64::max)
}

/// `Report.gradient_norm` means `‖Jᵀr‖∞` at the most recent point where the
/// Jacobian was evaluated (the start of the final outer iteration) — NOT a
/// mixed product of the stale Jacobian with the post-step residual. The
/// `MaxEval` exit that fires straight after an accepted step used to
/// recompute `(Jᵀ r_new).norm_max()` with the OLD `J`, which is neither the
/// gradient at the old point nor at the new one.
#[test]
fn max_eval_gradient_norm_is_taken_at_the_last_jacobian_point() {
    seq();
    let a = vec![vec![1.0, 0.0], vec![0.0, 1.0], vec![1.0, 1.0]];
    let b = vec![2.0, 1.0, 1.0];
    let mut prob = LinearProblem {
        a: a.clone(),
        b: b.clone(),
        x: vec![-3.0, 5.0],
        jac_points: Vec::new(),
    };
    let config = StrategyConfig {
        ftol: 0.0,
        xtol: 0.0,
        gtol: 0.0,
        max_nfev: 2,
        ..cfg(StepKind::NormalEqLlt)
    };
    let report = minimize(&mut prob, &config);
    assert_eq!(report.termination, Termination::MaxEval, "{report:?}");

    let x_jac = prob
        .jac_points
        .last()
        .expect("a Jacobian was evaluated")
        .clone();
    let x_final = prob.params();
    assert_ne!(
        x_jac, x_final,
        "this test only bites when the budget runs out AFTER an accepted step"
    );

    assert_relative_eq!(
        report.gradient_norm,
        grad_inf_norm(&a, &b, &x_jac),
        epsilon = 1e-12
    );
    assert_relative_eq!(
        report.gradient_norm,
        *report.gradient_norm_history.last().unwrap(),
        epsilon = 1e-12
    );
}

// ---------------------------------------------------------------------------
// Golden trajectories: interior problems, recorded bit for bit (#93)
// ---------------------------------------------------------------------------
//
// These fingerprints were recorded from the driver BEFORE the active-set
// projected step existed. Every case is an interior problem: either no bounds,
// or a box (exposed through `bounds()` and, for TRF, Coleman–Li
// `trust_scaling`) that no proposed or accepted iterate ever comes near. On
// such problems the active-set step must be inert, so every proposed parameter
// vector (accepted AND rejected trials), the accepted trajectory, the final
// parameters, the cost and the counters must stay bit-identical.

/// Wraps a problem, records the f64 bits of every vector passed to
/// `set_params` (every trial point the driver proposes, plus restores), and
/// optionally exposes a box through `bounds()` with `LmProblem`'s Coleman–Li
/// `trust_scaling` semantics.
struct Recorder {
    inner: Box<dyn TrustRegionProblem>,
    set_log: Vec<Vec<f64>>,
    bounds: Option<Vec<(f64, f64)>>,
}

impl Recorder {
    fn new(inner: Box<dyn TrustRegionProblem>, bounds: Option<Vec<(f64, f64)>>) -> Self {
        Self {
            inner,
            set_log: Vec::new(),
            bounds,
        }
    }
}

/// Coleman–Li `v_i`, copied from `spectrafit-solver::lm_problem::LmProblem::
/// trust_scaling` (fraction of the box left in the descent direction; 1 for a
/// one-sided bound).
fn lm_style_trust_scaling(x: &[f64], bounds: &[(f64, f64)], grad: &[f64]) -> Vec<f64> {
    (0..x.len())
        .map(|i| {
            let (lo, hi) = bounds[i];
            let g = grad.get(i).copied().unwrap_or(0.0);
            let up = if hi.is_finite() {
                hi - x[i]
            } else {
                f64::INFINITY
            };
            let down = if lo.is_finite() {
                x[i] - lo
            } else {
                f64::INFINITY
            };
            let dist = if g < 0.0 {
                up
            } else if g > 0.0 {
                down
            } else {
                up.min(down)
            };
            let range = if lo.is_finite() && hi.is_finite() {
                hi - lo
            } else {
                f64::INFINITY
            };
            if range.is_finite() && range > 0.0 {
                (dist / range).clamp(1e-9, 1.0)
            } else {
                1.0
            }
        })
        .collect()
}

impl TrustRegionProblem for Recorder {
    fn n_residuals(&self) -> usize {
        self.inner.n_residuals()
    }
    fn n_params(&self) -> usize {
        self.inner.n_params()
    }
    fn params(&self) -> Vec<f64> {
        self.inner.params()
    }
    fn set_params(&mut self, p: &[f64]) {
        self.set_log.push(p.to_vec());
        self.inner.set_params(p);
    }
    fn residuals_into(&mut self, r: MatMut<'_, f64>) -> Result<(), CoreError> {
        self.inner.residuals_into(r)
    }
    fn jacobian_into(&mut self, jac: MatMut<'_, f64>) -> Result<(), CoreError> {
        self.inner.jacobian_into(jac)
    }
    fn trust_scaling(&self, grad: &[f64]) -> Option<Vec<f64>> {
        match &self.bounds {
            Some(b) => Some(lm_style_trust_scaling(&self.inner.params(), b, grad)),
            None => self.inner.trust_scaling(grad),
        }
    }
    fn bounds(&self) -> Option<Vec<(f64, f64)>> {
        self.bounds.clone()
    }
}

/// 64-bit FNV-1a over a stream of f64 bit patterns (length-prefixed per
/// vector so different splits of the same numbers hash differently).
fn fnv1a_vecs(vs: &[Vec<f64>]) -> u64 {
    let mut h: u64 = 0xcbf2_9ce4_8422_2325;
    let mut eat = |w: u64| {
        for b in w.to_le_bytes() {
            h ^= u64::from(b);
            h = h.wrapping_mul(0x0000_0100_0000_01b3);
        }
    };
    for v in vs {
        eat(v.len() as u64);
        for x in v {
            eat(x.to_bits());
        }
    }
    h
}

fn golden_problem(name: &str) -> (Box<dyn TrustRegionProblem>, Vec<(f64, f64)>) {
    match name {
        "linear" => (
            // Inconsistent overdetermined system: non-zero residual at the optimum.
            Box::new(LinearProblem {
                a: vec![
                    vec![1.0, 0.0],
                    vec![0.0, 1.0],
                    vec![1.0, 1.0],
                    vec![1.0, -2.0],
                ],
                b: vec![2.0, 1.0, 1.5, -0.25],
                x: vec![-3.0, 5.0],
                jac_points: Vec::new(),
            }),
            vec![(-40.0, 40.0), (-35.0, f64::INFINITY)],
        ),
        "rosenbrock" => (
            Box::new(RosenbrockProblem { x: [-1.2, 1.0] }),
            vec![(-25.0, 25.0), (f64::NEG_INFINITY, 30.0)],
        ),
        "twoexp" => (
            Box::new(TwoExpProblem::new([0.9, 1.4], [0.4, 2.4])),
            vec![(-20.0, 20.0), (-20.0, 20.0)],
        ),
        other => panic!("unknown golden problem {other}"),
    }
}

fn golden_config(name: &str) -> (StrategyConfig, bool) {
    let base = StrategyConfig::default();
    match name {
        "ne" => (cfg(StepKind::NormalEqLlt), false),
        "svd" => (cfg(StepKind::SvdSecular), false),
        "ne_geo" => (
            StrategyConfig {
                geodesic: true,
                ..base
            },
            false,
        ),
        "svd_geo" => (
            StrategyConfig {
                kind: StepKind::SvdSecular,
                geodesic: true,
                ..base
            },
            false,
        ),
        "ne_box" => (base, true),
        "ne_trf_box" => (
            StrategyConfig {
                bound_scaling: true,
                ..base
            },
            true,
        ),
        "svd_trf_box" => (
            StrategyConfig {
                kind: StepKind::SvdSecular,
                bound_scaling: true,
                ..base
            },
            true,
        ),
        "ne_geo_box" => (
            StrategyConfig {
                geodesic: true,
                ..base
            },
            true,
        ),
        other => panic!("unknown golden config {other}"),
    }
}

/// `(problem, config, set_params-log hash, n set_params calls, params_history
/// hash, final params bits, cost bits, termination, n_iter, n_residual_evals,
/// n_jacobian_evals)`, recorded from the driver before the active-set step.
type Golden = (
    &'static str,
    &'static str,
    u64,
    usize,
    u64,
    [u64; 2],
    u64,
    Termination,
    usize,
    usize,
    usize,
);

#[rustfmt::skip]
const GOLDEN: &[Golden] = &[
    ("linear", "ne", 0xa46437ff59b23b70, 3, 0xa58d125e4551e13a, [0x3ff52d2d2d2b1abb, 0x3fe70f0f0f1fe5d9], 0x3fdb2d2d2d2d2d2f, Termination::Ftol, 3, 4, 3),
    ("linear", "svd", 0x914badf8108dc8dd, 3, 0xa66164c3f865b2ff, [0x3ff52d2d2d2b1aba, 0x3fe70f0f0f1fe5d9], 0x3fdb2d2d2d2d2d2c, Termination::Ftol, 3, 4, 3),
    ("linear", "ne_geo", 0x6b6d04f2a635fa6f, 9, 0xacf3150d748a06ef, [0x3ff52d2d2d2b1a95, 0x3fe70f0f0f1fe5b1], 0x3fdb2d2d2d2d2d2e, Termination::Ftol, 3, 7, 3),
    ("linear", "svd_geo", 0x060f2f927264f2f5, 9, 0x178e15d718bacede, [0x3ff52d2d2d2b1ae2, 0x3fe70f0f0f1fe617], 0x3fdb2d2d2d2d2d2e, Termination::Ftol, 3, 7, 3),
    ("linear", "ne_box", 0xa46437ff59b23b70, 3, 0xa58d125e4551e13a, [0x3ff52d2d2d2b1abb, 0x3fe70f0f0f1fe5d9], 0x3fdb2d2d2d2d2d2f, Termination::Ftol, 3, 4, 3),
    ("linear", "ne_trf_box", 0x82106055b2c3c429, 3, 0xa1a52d41f6d618b7, [0x3ff52d2d2cdeac66, 0x3fe70f0f0ef8ac8e], 0x3fdb2d2d2d2d2d2a, Termination::Ftol, 3, 4, 3),
    ("linear", "svd_trf_box", 0xd8a1e115f97f0920, 3, 0x5de2f70dec93c5ee, [0x3ff52d2d2cdeac67, 0x3fe70f0f0ef8ac8e], 0x3fdb2d2d2d2d2d2d, Termination::Ftol, 3, 4, 3),
    ("linear", "ne_geo_box", 0x6b6d04f2a635fa6f, 9, 0xacf3150d748a06ef, [0x3ff52d2d2d2b1a95, 0x3fe70f0f0f1fe5b1], 0x3fdb2d2d2d2d2d2e, Termination::Ftol, 3, 7, 3),
    ("rosenbrock", "ne", 0xe2916355966da27c, 22, 0x9920b2629fdca544, [0x3fefffffff783ca1, 0x3feffffffef02f56], 0x3c2201fe760e6040, Termination::Gtol, 16, 20, 17),
    ("rosenbrock", "svd", 0xfb7301344ce84f16, 22, 0x1e9c701ede87f23c, [0x3fefffffff783ca1, 0x3feffffffef02f56], 0x3c2201fe760e6040, Termination::Gtol, 16, 20, 17),
    ("rosenbrock", "ne_geo", 0x26a2677001c5945a, 75, 0x571926d297b9c184, [0x3fefffffff8f42ff, 0x3fefffffff1e4b1a], 0x3c18d59b92862080, Termination::Gtol, 17, 47, 18),
    ("rosenbrock", "svd_geo", 0xf9d2c0ca73894d01, 75, 0xe700b3187c4c9ed3, [0x3fefffffff8f430a, 0x3fefffffff1e4b2f], 0x3c18d596d1689400, Termination::Gtol, 17, 47, 18),
    ("rosenbrock", "ne_box", 0xe2916355966da27c, 22, 0x9920b2629fdca544, [0x3fefffffff783ca1, 0x3feffffffef02f56], 0x3c2201fe760e6040, Termination::Gtol, 16, 20, 17),
    ("rosenbrock", "ne_trf_box", 0x536c42c615857d60, 15, 0x1d2a78388b62eff9, [0x3feffffffcf8a46e, 0x3feffffff9f01349], 0x3c7259db9581a090, Termination::Gtol, 13, 15, 14),
    ("rosenbrock", "svd_trf_box", 0x415e4ce868f9fa99, 15, 0x3dc3a5e21e6ee463, [0x3feffffffcf8a46e, 0x3feffffff9f01349], 0x3c7259db9581a090, Termination::Gtol, 13, 15, 14),
    ("rosenbrock", "ne_geo_box", 0x26a2677001c5945a, 75, 0x571926d297b9c184, [0x3fefffffff8f42ff, 0x3fefffffff1e4b1a], 0x3c18d59b92862080, Termination::Gtol, 17, 47, 18),
    ("twoexp", "ne", 0xbbf5c72208d24c3f, 6, 0x29a981a06f5f95c5, [0x3fecccccccaccf0d, 0x3ff666666682ff3c], 0x3bc02c6ebb214240, Termination::Gtol, 6, 7, 7),
    ("twoexp", "svd", 0x85bffa116c6bbb48, 6, 0x48315e6577ff019a, [0x3fecccccccaccf0d, 0x3ff666666682ff3c], 0x3bc02c6ebb214240, Termination::Gtol, 6, 7, 7),
    ("twoexp", "ne_geo", 0x955e325b6ba9d261, 15, 0x90063a8ac64283f6, [0x3fecccccccb1f055, 0x3ff66666667e7dc4], 0x3bb6d3076c1b0b80, Termination::Gtol, 5, 11, 6),
    ("twoexp", "svd_geo", 0xa0d405f6a392d83e, 15, 0xe35a492013262a64, [0x3fecccccccb1f03a, 0x3ff66666667e7dbc], 0x3bb6d32dd5b20080, Termination::Gtol, 5, 11, 6),
    ("twoexp", "ne_box", 0xbbf5c72208d24c3f, 6, 0x29a981a06f5f95c5, [0x3fecccccccaccf0d, 0x3ff666666682ff3c], 0x3bc02c6ebb214240, Termination::Gtol, 6, 7, 7),
    ("twoexp", "ne_trf_box", 0xfd9a1b11846457cd, 6, 0x93a5ab6d158f776b, [0x3feccccccc27e687, 0x3ff6666666f9e074], 0x3c0adc4304b8b344, Termination::Gtol, 6, 7, 7),
    ("twoexp", "svd_trf_box", 0xa22f9e97a8ad3163, 6, 0xead60f84f5175fdd, [0x3feccccccc27e687, 0x3ff6666666f9e074], 0x3c0adc4304b8b344, Termination::Gtol, 6, 7, 7),
    ("twoexp", "ne_geo_box", 0x955e325b6ba9d261, 15, 0x90063a8ac64283f6, [0x3fecccccccb1f055, 0x3ff66666667e7dc4], 0x3bb6d3076c1b0b80, Termination::Gtol, 5, 11, 6),
];

/// AS test (c): interior problems are bit-identical to the pre-AS driver,
/// including problems that expose a box which never becomes active.
#[test]
fn interior_trajectories_are_bit_identical_to_the_recorded_driver() {
    seq();
    let problems = ["linear", "rosenbrock", "twoexp"];
    let configs = [
        "ne",
        "svd",
        "ne_geo",
        "svd_geo",
        "ne_box",
        "ne_trf_box",
        "svd_trf_box",
        "ne_geo_box",
    ];
    let mut actual = Vec::new();
    let mut mismatches = Vec::new();
    for prob_name in problems {
        for cfg_name in configs {
            let (inner, box_) = golden_problem(prob_name);
            let (config, with_box) = golden_config(cfg_name);
            let mut rec = Recorder::new(inner, with_box.then(|| box_.clone()));
            let report = minimize(&mut rec, &config);

            if with_box {
                // The box must never come near an iterate, or the case is not
                // an interior problem.
                let mut points = rec.set_log.clone();
                points.extend(report.params_history.iter().cloned());
                for x in &points {
                    for (i, &xi) in x.iter().enumerate() {
                        let (lo, hi) = box_[i];
                        for b in [lo, hi] {
                            if b.is_finite() {
                                assert!(
                                    (xi - b).abs() > 1e-3 * b.abs().max(1.0),
                                    "{prob_name}/{cfg_name}: x[{i}] = {xi} comes near bound {b}"
                                );
                            }
                        }
                    }
                }
            }

            let fin = rec.params();
            let line: Golden = (
                prob_name,
                cfg_name,
                fnv1a_vecs(&rec.set_log),
                rec.set_log.len(),
                fnv1a_vecs(&report.params_history),
                [fin[0].to_bits(), fin[1].to_bits()],
                report.cost.to_bits(),
                report.termination,
                report.n_iter,
                report.n_residual_evals,
                report.n_jacobian_evals,
            );
            let rendered = format!(
                "    (\"{}\", \"{}\", 0x{:016x}, {}, 0x{:016x}, [0x{:016x}, 0x{:016x}], 0x{:016x}, Termination::{:?}, {}, {}, {}),",
                line.0, line.1, line.2, line.3, line.4, line.5[0], line.5[1], line.6, line.7, line.8, line.9, line.10
            );
            match GOLDEN.iter().find(|g| g.0 == prob_name && g.1 == cfg_name) {
                Some(g) if *g == line => {}
                Some(g) => mismatches.push(format!("expected {g:?}\n  actual {rendered}")),
                None => mismatches.push(format!("missing  {rendered}")),
            }
            actual.push(rendered);
        }
    }
    assert!(
        mismatches.is_empty(),
        "{} golden mismatches:\n{}\n\nfull actual table:\n{}",
        mismatches.len(),
        mismatches.join("\n"),
        actual.join("\n")
    );
}

// ---------------------------------------------------------------------------
// Active-set projected step at bounds (#93)
// ---------------------------------------------------------------------------

/// Copy of `spectrafit-solver::lm_problem::reflect_into_bounds`: reflect an
/// overshoot back into `[lo, hi]`, park at the violated bound on a double
/// bounce. A one-sided box never parks.
fn reflect_like_lm_problem(p: f64, lo: f64, hi: f64) -> f64 {
    if p < lo {
        let reflected = 2.0 * lo - p;
        if hi.is_finite() && reflected > hi {
            lo
        } else {
            reflected.min(if hi.is_finite() { hi } else { f64::MAX })
        }
    } else if p > hi {
        let reflected = 2.0 * hi - p;
        if lo.is_finite() && reflected < lo {
            hi
        } else {
            reflected.max(if lo.is_finite() { lo } else { f64::MIN })
        }
    } else {
        p
    }
}

/// Linear residual `A·x − b` on a box, with `LmProblem`'s bound semantics:
/// reflection in `set_params`, Coleman–Li `trust_scaling` (1.0 for a one-sided
/// bound) and the box exposed through `bounds()`. Counts residual evaluations
/// so a test can see rejected trials.
struct ReflectingBoxProblem {
    a: Vec<Vec<f64>>,
    b: Vec<f64>,
    x: Vec<f64>,
    bounds: Vec<(f64, f64)>,
}

impl ReflectingBoxProblem {
    /// `Aᵀ(A·x − b)` at the current point.
    fn gradient(&self) -> Vec<f64> {
        let r: Vec<f64> = self
            .a
            .iter()
            .zip(&self.b)
            .map(|(row, bi)| row.iter().zip(&self.x).map(|(a, x)| a * x).sum::<f64>() - bi)
            .collect();
        (0..self.x.len())
            .map(|c| self.a.iter().zip(&r).map(|(row, ri)| row[c] * ri).sum())
            .collect()
    }
}

impl TrustRegionProblem for ReflectingBoxProblem {
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
        for (i, &pi) in p.iter().enumerate() {
            let (lo, hi) = self.bounds[i];
            self.x[i] = reflect_like_lm_problem(pi, lo, hi);
        }
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
    fn trust_scaling(&self, grad: &[f64]) -> Option<Vec<f64>> {
        Some(lm_style_trust_scaling(&self.x, &self.bounds, grad))
    }
    fn bounds(&self) -> Option<Vec<(f64, f64)>> {
        Some(self.bounds.clone())
    }
}

/// Coupled 2-D problem whose constrained optimum is `x = (0, 2)` with
/// `x₀ ≥ 0` active and its gradient pointing out of the box (`g₀ = 3.5 > 0`).
fn coupled_lower_bound_problem(x0: [f64; 2]) -> ReflectingBoxProblem {
    ReflectingBoxProblem {
        a: vec![vec![1.0, 0.0], vec![0.5, 1.0], vec![1.0, -1.0]],
        b: vec![-5.0, 3.0, -1.0],
        x: x0.to_vec(),
        bounds: vec![(0.0, f64::INFINITY), (f64::NEG_INFINITY, f64::INFINITY)],
    }
}

/// AS test (a): the optimum lies on a bound with an outward gradient. The
/// component at the bound is held, the free component converges, and the run
/// ends as a success at a stationary point: the held component sits exactly
/// on its bound and the free gradient vanishes.
#[test]
fn as_optimum_on_bound_with_outward_gradient_is_held_and_stationary() {
    seq();
    for kind in [StepKind::NormalEqLlt, StepKind::SvdSecular] {
        for (geodesic, bound_scaling) in [(false, false), (false, true), (true, false)] {
            let mut prob = coupled_lower_bound_problem([0.0, -4.0]);
            let config = StrategyConfig {
                kind,
                geodesic,
                bound_scaling,
                ..Default::default()
            };
            let report = minimize(&mut prob, &config);
            let tag = format!("{kind:?} geodesic={geodesic} trf={bound_scaling}");
            assert!(
                report.termination.was_successful(),
                "{tag}: {:?}",
                report.termination
            );
            assert_eq!(prob.x[0], 0.0, "{tag}: held component left its bound");
            let g = prob.gradient();
            assert!(
                g[0] > 0.0,
                "{tag}: gradient at the bound must point outward"
            );
            assert!(
                g[1].abs() <= 1e-6,
                "{tag}: free gradient {} not stationary",
                g[1]
            );
            assert_relative_eq!(prob.x[1], 2.0, epsilon = 1e-6);
        }
    }
}

/// AS test (b): every component is at a bound with an outward gradient, so
/// the projected step is fully clamped. That is a stationary point, not a
/// failed trial: the run stops at once as a success, without a rejected trial
/// and so without any growth of λ. Before the active-set step the clamped
/// trial was rejected, λ was raised 200 times and the run ended as
/// `NoImprovement`.
#[test]
fn as_fully_clamped_step_is_not_a_rejection() {
    seq();
    for kind in [StepKind::NormalEqLlt, StepKind::SvdSecular] {
        // x₀ ∈ [0, ∞) wants −5; x₁ ∈ (−∞, 4] wants 10.
        let mut prob = ReflectingBoxProblem {
            a: vec![vec![1.0, 0.0], vec![0.0, 1.0]],
            b: vec![-5.0, 10.0],
            x: vec![0.0, 4.0],
            bounds: vec![(0.0, f64::INFINITY), (f64::NEG_INFINITY, 4.0)],
        };
        let report = minimize(&mut prob, &cfg(kind));
        assert_eq!(report.termination, Termination::Gtol, "{kind:?}");
        assert_eq!(
            report.n_residual_evals, 1,
            "{kind:?}: a trial was evaluated"
        );
        assert_eq!(report.n_jacobian_evals, 1, "{kind:?}");
        assert_eq!(report.n_iter, 0, "{kind:?}");
        assert_eq!(prob.x, vec![0.0, 4.0]);
    }
}

/// AS test (b), second shape: one component is held and the free component
/// already sits at its conditional optimum, so the free-subspace step is zero.
/// Also stationary; also no rejected trial.
#[test]
fn as_zero_free_step_with_held_component_is_not_a_rejection() {
    seq();
    // x₀ ∈ [0, ∞) wants −5 (held); x₁ free, already at its optimum 3.
    let mut prob = ReflectingBoxProblem {
        a: vec![vec![1.0, 0.0], vec![0.0, 1.0]],
        b: vec![-5.0, 3.0],
        x: vec![0.0, 3.0],
        bounds: vec![(0.0, f64::INFINITY), (f64::NEG_INFINITY, f64::INFINITY)],
    };
    let report = minimize(&mut prob, &StrategyConfig::default());
    assert_eq!(report.termination, Termination::Gtol);
    assert_eq!(report.n_residual_evals, 1);
    assert_eq!(prob.x, vec![0.0, 3.0]);
}

/// The step is projected onto the box (not reflected) once a component is
/// held: the free component overshoots its upper bound, lands exactly on it,
/// is held in the next iteration, and the run ends stationary at the corner.
#[test]
fn as_projection_lands_free_component_on_its_bound() {
    seq();
    // x₀ ∈ [0, ∞) wants −5 (held from the start); x₁ ∈ (−∞, 1] wants 2.
    let mut prob = ReflectingBoxProblem {
        a: vec![vec![1.0, 0.0], vec![0.0, 1.0]],
        b: vec![-5.0, 2.0],
        x: vec![0.0, -3.0],
        bounds: vec![(0.0, f64::INFINITY), (f64::NEG_INFINITY, 1.0)],
    };
    let report = minimize(&mut prob, &StrategyConfig::default());
    assert!(
        report.termination.was_successful(),
        "{:?}",
        report.termination
    );
    assert_eq!(prob.x, vec![0.0, 1.0]);
    assert_eq!(report.n_iter, 1, "one projected step reaches the corner");
}

/// A non-zero free step that rounds away against `p` (λ grown by repeated
/// rejections) is a stall, not a fully clamped step: it must not end as a
/// success. The Jacobian reports the wrong sign for the free component, so
/// every trial raises the cost and is rejected.
#[test]
fn as_step_rounded_away_by_lambda_growth_is_not_a_success() {
    seq();
    struct WrongJacobian(ReflectingBoxProblem);
    impl TrustRegionProblem for WrongJacobian {
        fn n_residuals(&self) -> usize {
            self.0.n_residuals()
        }
        fn n_params(&self) -> usize {
            self.0.n_params()
        }
        fn params(&self) -> Vec<f64> {
            self.0.params()
        }
        fn set_params(&mut self, p: &[f64]) {
            self.0.set_params(p);
        }
        fn residuals_into(&mut self, r: MatMut<'_, f64>) -> Result<(), CoreError> {
            self.0.residuals_into(r)
        }
        fn jacobian_into(&mut self, mut jac: MatMut<'_, f64>) -> Result<(), CoreError> {
            self.0.jacobian_into(jac.as_mut())?;
            jac[(1, 1)] = -jac[(1, 1)];
            Ok(())
        }
        fn trust_scaling(&self, grad: &[f64]) -> Option<Vec<f64>> {
            self.0.trust_scaling(grad)
        }
        fn bounds(&self) -> Option<Vec<(f64, f64)>> {
            self.0.bounds()
        }
    }
    // x₀ ∈ [0, ∞) wants −5 (held); x₁ free wants 3 but J says the opposite.
    let mut prob = WrongJacobian(ReflectingBoxProblem {
        a: vec![vec![1.0, 0.0], vec![0.0, 1.0]],
        b: vec![-5.0, 3.0],
        x: vec![0.0, -4.0],
        bounds: vec![(0.0, f64::INFINITY), (f64::NEG_INFINITY, f64::INFINITY)],
    });
    let report = minimize(&mut prob, &StrategyConfig::default());
    assert!(
        !report.termination.was_successful(),
        "stall reported as {:?} after {} evaluations",
        report.termination,
        report.n_residual_evals
    );
    assert_eq!(report.termination, Termination::NoImprovement);
}

/// Clamp-AS (#93): a trial point that crosses a bound is projected onto the
/// box (Kanzow, Yamashita, Fukushima 2004, projected LM step), not reflected.
/// Nothing is held at the start (interior start), so this is the unbounded
/// step path: the first accepted point must lie exactly on the crossed bound,
/// where the 1e-12 entry rule of the active-set step then holds it. With
/// reflection the first point was `2·b − t`, off the bound, and a one-sided
/// bound was never reached exactly.
#[test]
fn clamp_trial_crossing_a_bound_lands_exactly_on_it() {
    seq();
    // (label, box of x₀, b₀ = unconstrained optimum of x₀, start, crossed bound)
    type Case = (&'static str, (f64, f64), f64, [f64; 2], f64);
    let cases: [Case; 3] = [
        (
            "upper one-sided",
            (f64::NEG_INFINITY, 1.0),
            2.0,
            [-3.0, 0.0],
            1.0,
        ),
        (
            "lower one-sided",
            (-1.0, f64::INFINITY),
            -4.0,
            [3.0, 0.0],
            -1.0,
        ),
        ("two-sided", (-10.0, 1.0), 2.0, [-3.0, 0.0], 1.0),
    ];
    let configs: [(&str, StrategyConfig); 3] = [
        ("lm", StrategyConfig::default()),
        (
            "trf",
            StrategyConfig {
                bound_scaling: true,
                ..Default::default()
            },
        ),
        (
            "geodesic",
            StrategyConfig {
                geodesic: true,
                ..Default::default()
            },
        ),
    ];
    for (label, bx, b0, x0, bound) in cases {
        for (cname, config) in &configs {
            let tag = format!("{label} / {cname}");
            // x₁ is free and wants 3.
            let mut prob = ReflectingBoxProblem {
                a: vec![vec![1.0, 0.0], vec![0.0, 1.0]],
                b: vec![b0, 3.0],
                x: x0.to_vec(),
                bounds: vec![bx, (f64::NEG_INFINITY, f64::INFINITY)],
            };
            let report = minimize(&mut prob, config);
            assert!(
                report.termination.was_successful(),
                "{tag}: {:?}",
                report.termination
            );
            assert!(report.params_history.len() >= 2, "{tag}: no step taken");
            assert_eq!(
                report.params_history[1][0], bound,
                "{tag}: first accepted point {:?} not on the crossed bound",
                report.params_history[1]
            );
            assert_eq!(prob.x[0], bound, "{tag}: endpoint left the bound");
            assert_relative_eq!(prob.x[1], 3.0, epsilon = 1e-6);
        }
    }
}

/// Clamp-AS (#93): the geodesic probe point `p + h·δ` is projected onto the
/// box like every trial point. Started just below the upper bound, the probe
/// (h = 0.1) and the trial both cross it; every vector the driver hands to
/// `set_params` must lie in the box, so the problem's own reflection is never
/// what keeps a point feasible.
#[test]
fn clamp_geodesic_probe_and_trials_are_passed_inside_the_box() {
    seq();
    struct Logging {
        inner: ReflectingBoxProblem,
        log: Vec<Vec<f64>>,
    }
    impl TrustRegionProblem for Logging {
        fn n_residuals(&self) -> usize {
            self.inner.n_residuals()
        }
        fn n_params(&self) -> usize {
            self.inner.n_params()
        }
        fn params(&self) -> Vec<f64> {
            self.inner.params()
        }
        fn set_params(&mut self, p: &[f64]) {
            self.log.push(p.to_vec());
            self.inner.set_params(p);
        }
        fn residuals_into(&mut self, r: MatMut<'_, f64>) -> Result<(), CoreError> {
            self.inner.residuals_into(r)
        }
        fn jacobian_into(&mut self, jac: MatMut<'_, f64>) -> Result<(), CoreError> {
            self.inner.jacobian_into(jac)
        }
        fn trust_scaling(&self, grad: &[f64]) -> Option<Vec<f64>> {
            self.inner.trust_scaling(grad)
        }
        fn bounds(&self) -> Option<Vec<(f64, f64)>> {
            self.inner.bounds()
        }
    }
    let bx = (f64::NEG_INFINITY, 1.0);
    // x₀ ≤ 1 wants 2, starts at 0.9: δ₀ ≈ 1.1, so the probe at 0.9 + 0.1·δ₀
    // already crosses the bound. x₁ is free and wants 3.
    let mut prob = Logging {
        inner: ReflectingBoxProblem {
            a: vec![vec![1.0, 0.0], vec![0.0, 1.0]],
            b: vec![2.0, 3.0],
            x: vec![0.9, 0.0],
            bounds: vec![bx, (f64::NEG_INFINITY, f64::INFINITY)],
        },
        log: Vec::new(),
    };
    let config = StrategyConfig {
        geodesic: true,
        ..Default::default()
    };
    let report = minimize(&mut prob, &config);
    assert!(
        report.termination.was_successful(),
        "{:?}",
        report.termination
    );
    assert!(!prob.log.is_empty());
    for p in &prob.log {
        assert!(p[0] <= bx.1, "set_params got {p:?}, outside the box");
    }
    assert_eq!(prob.inner.x[0], 1.0);
}
