//! IRLS — Iteratively Reweighted Least Squares for robust fitting.
//!
//! Wraps the existing LM solver in an outer loop that reweights residuals
//! using a robust loss function (Huber, Bisquare, or Cauchy) to down-weight
//! outlier points.  Each outer iteration:
//!   1. Run LM on the current weighted problem, warm-started from the most
//!      recent **successful** outer pass's fitted parameter values (pass 1, and
//!      every pass until one succeeds, starts from the graph's initial values).
//!      Only free parameter *values* carry over — bounds, fixed parameters and
//!      expression-tied parameters are untouched.
//!   2. Compute standardised residuals `r_i / σ_scale`, where `σ_scale` is the
//!      MAD (median absolute deviation) of the raw residuals `obs − pred` —
//!      the user-supplied per-point σ is not folded into this standardisation.
//!   3. Update per-point weights `w_i = ρ'(r_i) / r_i` (IRLS weight formula).
//!   4. Repeat until weights converge or `max_outer_iter` is reached.
//!
//! Reference: Holland & Welsch (1977), Fox & Weisberg (2002).

use spectrafit_types::{CoreError, FitGraphSpec, FitOptionsSpec, FitResultSpec, MeasurementSpec};

use crate::dispatch::fit as lm_fit;
use crate::error::SolverError;

/// Default IRLS outer-iteration cap used by the `solver="irls"` dispatch path.
///
/// Named per this crate's own convention for comparable tunables (see
/// `postfit::apply_postfit_guards`'s `OFF_DOMAIN_R2_FLOOR`/`SOFT_SUCCESS_R2_FLOOR`)
/// instead of a bare literal at the call site.
pub(crate) const DEFAULT_MAX_OUTER_ITER: usize = 20;

/// Default IRLS weight-convergence tolerance used by the `solver="irls"`
/// dispatch path: the outer loop stops once `max_i |w_i − w_i^prev| <` this.
///
/// This is a tolerance on the *weights*, not on the cost, so it is deliberately
/// independent of `FitOptionsSpec::tolerance` (the LM `ftol`/`xtol`/`gtol`,
/// 1e-8 by default). IRLS weights are `O(1)` quantities bounded by 1, and the
/// Holland & Welsch (1977) formulation treats the reweighting as converged once
/// they stop moving at the 1e-4 level; demanding 1e-8 on them just burns extra
/// outer passes chasing digits the robust weights do not carry. Dispatch used
/// to pass `options.tolerance` here, which coupled the two.
pub(crate) const DEFAULT_TOL_WEIGHTS: f64 = 1e-4;

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/// Robust weight function used by the IRLS outer loop.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum WeightFn {
    /// Huber loss with tuning constant `k` (default: 1.345).
    ///
    /// `w(r) = 1` when `|r| ≤ k`, else `w(r) = k / |r|`.
    Huber(f64),
    /// Tukey bisquare (biweight) with tuning constant `c` (default: 4.685).
    ///
    /// `w(r) = (1 − (r/c)²)²` when `|r| ≤ c`, else `w(r) = 0`.
    Bisquare(f64),
    /// Cauchy loss with scale parameter `γ` (default: 2.385).
    ///
    /// `w(r) = 1 / (1 + (r/γ)²)`.
    Cauchy(f64),
}

impl Default for WeightFn {
    fn default() -> Self {
        WeightFn::Huber(1.345)
    }
}

impl WeightFn {
    /// Compute the IRLS weight for a single standardised residual `r`.
    #[inline]
    pub fn weight(&self, r: f64) -> f64 {
        match *self {
            WeightFn::Huber(k) => {
                let ar = r.abs();
                if ar <= k {
                    1.0
                } else {
                    k / ar
                }
            }
            WeightFn::Bisquare(c) => {
                let rc = r / c;
                if rc.abs() >= 1.0 {
                    0.0
                } else {
                    let t = 1.0 - rc * rc;
                    t * t
                }
            }
            WeightFn::Cauchy(gamma) => {
                let rg = r / gamma;
                1.0 / (1.0 + rg * rg)
            }
        }
    }
}

impl std::str::FromStr for WeightFn {
    type Err = SolverError;

    /// Parse a weight function from the string name stored in `FitOptionsSpec`.
    ///
    /// Recognised names: `"huber"`, `"bisquare"` (or `"biweight"`), `"cauchy"`.
    /// Any other name is rejected. Previously an unrecognised name silently
    /// fell back to Huber, masking typos (e.g. `"irls:buisquare"` silently
    /// ran Huber instead of Bisquare).
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "huber" => Ok(WeightFn::Huber(1.345)),
            "bisquare" | "biweight" => Ok(WeightFn::Bisquare(4.685)),
            "cauchy" => Ok(WeightFn::Cauchy(2.385)),
            other => Err(SolverError::UnrecognisedWeightFn(other.to_string())),
        }
    }
}

// ---------------------------------------------------------------------------
// Solver entry point
// ---------------------------------------------------------------------------

/// Run IRLS on `graph` against `datasets`.
///
/// The solver wraps the standard LM solver in an outer reweighting loop.
/// Per-point weights are folded into each dataset's `sigma` field as
/// `σ_eff_i = σ_i / sqrt(w_i)`, so the existing weighted LM path handles
/// the rest without modification. Each outer pass after the first is
/// **warm-started**: the LM solve begins at the fitted free parameter values of
/// the most recent pass that *succeeded* (bounds, fixed parameters and
/// expression-tied parameters are left exactly as the caller wrote them). The
/// robust scale used to standardise residuals before computing weights is the
/// MAD of the raw residuals `obs − pred`; the user-supplied per-point σ is not
/// folded into it.
///
/// # Warm-start gating
/// Only a pass whose LM result reports `success == true` may become the next
/// pass's starting point. A pass that stopped on `max_iterations`, hit a
/// `numerical_error`, or was downgraded by a post-fit guard leaves
/// `parameters` at wherever the solve stalled; seeding from that point would
/// propagate the stall into every later pass and can leave the loop worse off
/// than a cold start. On a failed pass the previous warm-start point is kept
/// unchanged, and if no pass has succeeded yet the next pass restarts from the
/// caller's original `graph`.
///
/// # Returned counters
/// The returned [`FitResultSpec`] is the **final** outer pass's LM result, so
/// `n_iter`, `n_func_evals` and `n_jac_evals` are that last pass's counts, not
/// totals summed over the outer loop. The same is true of `cost_history`,
/// `gradient_norm_history` and `params_history`: each is the final pass's
/// trajectory only, and — per the warm-start gating above — index 0 of each
/// is the **warm-start point** (the previous successful pass's solution),
/// not the caller's original initial guess. `init_fit` is the one exception:
/// it is restored from pass 1 so it keeps describing the caller's original
/// starting point rather than the point the final pass warm-started from.
///
/// # Arguments
/// * `graph`    — model DAG.
/// * `datasets` — one or more measurement datasets.
/// * `options`  — fit options; `solver` field should be `"irls"`.
/// * `weight_fn` — robust weight function.
/// * `max_outer_iter` — maximum IRLS outer iterations (default [`DEFAULT_MAX_OUTER_ITER`]).
/// * `tol_weights` — convergence threshold on max weight change; as dispatched
///   from `solver::dispatch`'s `dispatch_solver`, this is
///   [`DEFAULT_TOL_WEIGHTS`] (1e-4), independent of the LM cost tolerance
///   `options.tolerance`.
///
/// # Errors
/// Returns [`CoreError`] when the inner LM fit ([`lm_fit`]) fails on any
/// outer pass, or (defensively; `max_outer_iter.max(1)` means the loop always
/// runs at least once) `SolverError::IrlsFailure` if the loop somehow
/// completes zero iterations.
pub fn solve_irls(
    graph: &FitGraphSpec,
    datasets: Vec<MeasurementSpec>,
    options: &FitOptionsSpec,
    weight_fn: WeightFn,
    max_outer_iter: usize,
    tol_weights: f64,
) -> Result<FitResultSpec, CoreError> {
    solve_irls_traced(
        graph,
        datasets,
        options,
        weight_fn,
        max_outer_iter,
        tol_weights,
    )
    .map(|run| run.result)
}

/// One completed IRLS run: the fit result plus the outer-pass count.
///
/// The pass count is not part of [`FitResultSpec`] (it is IRLS-specific and
/// nothing downstream consumes it), but it is the only observable that
/// distinguishes a warm-started outer loop from a cold-started one, so it is
/// surfaced here for [`solve_irls_traced`]'s in-crate callers and tests.
pub(crate) struct IrlsRun {
    /// The final outer pass's LM result.
    pub(crate) result: FitResultSpec,
    /// Number of outer reweighting passes actually executed (≥ 1).
    ///
    /// Read only by this crate's tests today — production callers go through
    /// [`solve_irls`], which drops it. Annotated rather than made a
    /// `#[cfg(test)]` field so the struct has one shape in both builds.
    #[cfg_attr(not(test), allow(dead_code))]
    pub(crate) n_outer_passes: usize,
    /// Starting point handed to each outer pass's LM solve, one entry per
    /// executed pass, as produced by [`start_point_snapshot`].
    ///
    /// This is the only observable that distinguishes "pass `k` warm-started
    /// from pass `k−1`" from "pass `k` restarted from the caller's graph",
    /// which is what the warm-start gating rule documented on [`solve_irls`]
    /// turns on. Same read-only-in-tests status (and same one-shape-in-both-
    /// builds reasoning) as [`n_outer_passes`](Self::n_outer_passes); the
    /// recording cost is one sorted `Vec<f64>` of the graph's parameter values
    /// per outer pass, bounded by `max_outer_iter`.
    #[cfg_attr(not(test), allow(dead_code))]
    pub(crate) pass_start_values: Vec<Vec<f64>>,
}

/// [`solve_irls`] with the outer-pass count surfaced — see [`IrlsRun`].
///
/// # Errors
/// Same as [`solve_irls`].
pub(crate) fn solve_irls_traced(
    graph: &FitGraphSpec,
    datasets: Vec<MeasurementSpec>,
    options: &FitOptionsSpec,
    weight_fn: WeightFn,
    max_outer_iter: usize,
    tol_weights: f64,
) -> Result<IrlsRun, CoreError> {
    let n_total: usize = datasets.iter().map(|ds| ds.y.len()).sum();

    // Initialise IRLS weights to 1 (unweighted first pass).
    let mut irls_weights: Vec<f64> = vec![1.0; n_total];

    // Inner LM options: run as ordinary LM.
    let inner_options = FitOptionsSpec {
        solver: "lm".to_string(),
        ..options.clone()
    };

    let mut result: Option<FitResultSpec> = None;
    let mut prev_weights = irls_weights.clone();
    let mut n_outer_passes = 0usize;
    let mut pass_start_values: Vec<Vec<f64>> = Vec::new();
    // Pass 1 starts from the caller's graph; every later pass starts from the
    // most recent SUCCESSFUL pass's fitted values (warm start). Stays `None`
    // until some pass succeeds, so a run whose passes all fail is a cold start
    // every time rather than a chain of stalled points.
    let mut warm_graph: Option<FitGraphSpec> = None;
    // `init_fit` must describe the ORIGINAL starting point (the user's initial
    // parameter values), not the point the final pass warm-started from — so
    // capture pass 1's and stamp it onto the returned result below. It is the
    // only initial-point-derived field on `FitResultSpec`.
    let mut original_init_fit: Option<Vec<f64>> = None;

    for _outer in 0..max_outer_iter.max(1) {
        n_outer_passes += 1;
        // Build sigma-adjusted datasets from current IRLS weights.
        let weighted_datasets = apply_irls_weights(&datasets, &irls_weights);

        // Run LM on the weighted problem, from the warm-started point if we
        // have one.
        let fit = {
            let pass_graph = warm_graph.as_ref().unwrap_or(graph);
            pass_start_values.push(start_point_snapshot(pass_graph));
            lm_fit(pass_graph, weighted_datasets, &inner_options)?
        };
        if original_init_fit.is_none() {
            original_init_fit = Some(fit.init_fit.clone());
        }
        // Warm-start gate: only a successful pass may seed the next one. See
        // the "Warm-start gating" section on `solve_irls` — a failed pass's
        // `parameters` describe where the solve stalled, not a better starting
        // point, so on failure the previous seed (or the caller's graph) is
        // retried instead.
        if fit.success {
            warm_graph = Some(warm_started_graph(graph, &fit));
        }

        // Compute MAD-based scale estimate for standardisation.
        let scale = mad_scale(&fit.residuals);
        let safe_scale = scale.max(1e-12);

        // Update IRLS weights from current residuals.
        let mut offset = 0usize;
        for ds in &datasets {
            let n = ds.y.len();
            for i in 0..n {
                let r = fit.residuals[offset + i] / safe_scale;
                irls_weights[offset + i] = weight_fn.weight(r);
            }
            offset += n;
        }

        // Check convergence: max change in weights.
        let max_delta = irls_weights
            .iter()
            .zip(prev_weights.iter())
            .map(|(&w, &pw)| (w - pw).abs())
            .fold(0.0_f64, f64::max);

        result = Some(fit);
        if max_delta < tol_weights {
            break;
        }
        prev_weights.clone_from(&irls_weights);
    }

    let mut result =
        result.ok_or_else(|| SolverError::IrlsFailure("no iterations completed".into()))?;
    if let Some(init_fit) = original_init_fit {
        result.init_fit = init_fit;
    }
    Ok(IrlsRun {
        result,
        n_outer_passes,
        pass_start_values,
    })
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

/// Every parameter `value` in `graph`, ordered by `"node_id.param_name"` — the
/// starting point a single IRLS outer pass hands to LM, in a form two passes
/// can be compared in.
///
/// The sort is load-bearing: `ModelNodeSpec::parameters` is a `HashMap`, so
/// without it the same graph could snapshot to two differently-ordered vectors
/// and "did this pass start where the last one did?" would be unanswerable.
/// Fixed parameters are included; they never move, so they cost nothing and
/// keep the snapshot a straight description of the graph.
fn start_point_snapshot(graph: &FitGraphSpec) -> Vec<f64> {
    let mut keyed: Vec<(String, f64)> = graph
        .nodes
        .iter()
        .flat_map(|node| {
            node.parameters
                .iter()
                .map(|(pname, pspec)| (format!("{}.{}", node.id, pname), pspec.value))
        })
        .collect();
    keyed.sort_by(|a, b| a.0.cmp(&b.0));
    keyed.into_iter().map(|(_, value)| value).collect()
}

/// Clone `graph` and seed each **free** parameter's `value` with the value the
/// previous IRLS outer pass fitted for it, so the next pass's LM solve starts
/// where the last one finished instead of at the user's initial guess.
///
/// Only ever called for a pass whose fit reported `success == true` — the
/// caller ([`solve_irls_traced`]) gates it, because a failed pass's
/// `fit.parameters` record where the solve stalled rather than a better guess.
///
/// Deliberately narrower than `global::seed_refined_graph`, which also tightens
/// infinite bounds to the DE search box: bounds are the user's contract and an
/// IRLS reweighting is not a reason to narrow them. Fixed (`vary == false`) and
/// expression-constrained parameters are skipped — their values are not the
/// solver's to choose — as are non-finite fitted values, which would poison the
/// next pass's starting point.
fn warm_started_graph(graph: &FitGraphSpec, fit: &FitResultSpec) -> FitGraphSpec {
    let tied: std::collections::HashSet<(&str, &str)> = graph
        .expr_edges
        .iter()
        .map(|e| (e.target_node.as_str(), e.target_param.as_str()))
        .collect();
    let mut next = graph.clone();
    for node in &mut next.nodes {
        for (pname, pspec) in &mut node.parameters {
            if !pspec.vary
                || pspec.expr.is_some()
                || tied.contains(&(node.id.as_str(), pname.as_str()))
            {
                continue;
            }
            let key = format!("{}.{}", node.id, pname);
            if let Some(fitted) = fit.parameters.get(&key) {
                if fitted.value.is_finite() {
                    pspec.value = fitted.value;
                }
            }
        }
    }
    next
}

/// Fold IRLS weights into each dataset's `sigma` field.
///
/// `σ_eff_i = σ_i / sqrt(w_i)` so the LM solver minimises the re-weighted
/// sum-of-squares `Σ w_i · r_i²` via the standard weighted path.
fn apply_irls_weights(datasets: &[MeasurementSpec], weights: &[f64]) -> Vec<MeasurementSpec> {
    let mut out = Vec::with_capacity(datasets.len());
    let mut offset = 0usize;
    for ds in datasets {
        let n = ds.y.len();
        let sigma_slice: Vec<f64> = (0..n)
            .map(|i| {
                let w = weights[offset + i].max(1e-12);
                let base_sigma = ds
                    .sigma
                    .as_ref()
                    .and_then(|s| s.get(i).copied())
                    .unwrap_or(1.0);
                base_sigma / w.sqrt()
            })
            .collect();
        out.push(MeasurementSpec {
            sigma: Some(sigma_slice),
            ..ds.clone()
        });
        offset += n;
    }
    out
}

/// Median absolute deviation scale estimate: `MAD / 0.6745`.
///
/// This is a robust estimate of the residual standard deviation.
/// The factor `0.6745` makes it consistent with σ under normality.
fn mad_scale(residuals: &[f64]) -> f64 {
    if residuals.is_empty() {
        return 1.0;
    }
    let mut abs_res: Vec<f64> = residuals.iter().map(|r| r.abs()).collect();
    abs_res.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let median = if abs_res.len().is_multiple_of(2) {
        (abs_res[abs_res.len() / 2 - 1] + abs_res[abs_res.len() / 2]) / 2.0
    } else {
        abs_res[abs_res.len() / 2]
    };
    median / 0.6745
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use spectrafit_types::{FitGraphSpec, FitOptionsSpec, MeasurementSpec};
    use std::collections::HashMap;
    use std::str::FromStr;

    #[test]
    fn huber_weight_at_boundary() {
        let w = WeightFn::Huber(1.345);
        // At r = k, weight should be exactly 1.0
        assert!((w.weight(1.345) - 1.0).abs() < 1e-12);
        // At r = 2k, weight should be 0.5
        assert!((w.weight(2.69) - 0.5).abs() < 1e-4);
    }

    #[test]
    fn bisquare_weight_beyond_c() {
        let w = WeightFn::Bisquare(4.685);
        // Beyond tuning constant → zero weight (outlier rejected)
        assert_eq!(w.weight(5.0), 0.0);
        // At center → full weight
        assert!((w.weight(0.0) - 1.0).abs() < 1e-12);
    }

    #[test]
    fn cauchy_weight_decreases_monotonically() {
        let w = WeightFn::Cauchy(2.385);
        let w0 = w.weight(0.0);
        let w1 = w.weight(1.0);
        let w5 = w.weight(5.0);
        assert!(w0 > w1 && w1 > w5);
        assert!((w0 - 1.0).abs() < 1e-12);
    }

    #[test]
    fn mad_scale_constant_residuals() {
        let residuals = vec![1.0; 20];
        let s = mad_scale(&residuals);
        // All residuals = 1, MAD = 0 → scale = 0/0.6745 ≈ 0, clamped to 1
        // Wait: abs(1-1)=0 for deviations from median 1, so MAD=0 → safe clamp applies
        // Here we test that it doesn't panic and returns a finite value
        assert!(s.is_finite());
    }

    #[test]
    fn weight_fn_from_str() {
        assert!(matches!(
            WeightFn::from_str("bisquare"),
            Ok(WeightFn::Bisquare(_))
        ));
        assert!(matches!(
            WeightFn::from_str("biweight"),
            Ok(WeightFn::Bisquare(_))
        ));
        assert!(matches!(
            WeightFn::from_str("cauchy"),
            Ok(WeightFn::Cauchy(_))
        ));
        assert!(matches!(
            WeightFn::from_str("huber"),
            Ok(WeightFn::Huber(_))
        ));
    }

    #[test]
    fn weight_fn_from_str_rejects_unrecognised_name() {
        // Previously "unknown" silently fell back to Huber — masking typos
        // like "irls:buisquare". It must now be rejected.
        match WeightFn::from_str("unknown") {
            Err(SolverError::UnrecognisedWeightFn(name)) => assert_eq!(name, "unknown"),
            other => panic!("expected UnrecognisedWeightFn, got {other:?}"),
        }
    }

    /// True `(amplitude, center, sigma)` of the outlier fixture below.
    const OUTLIER_TRUTH: (f64, f64, f64) = (5.0, 0.0, 1.0);

    /// A Gaussian sampled on 80 points with three large injected outliers,
    /// plus a deliberately-off initial guess. Shared by every IRLS test that
    /// needs a robust-fitting problem so the warm-start pass count and the
    /// parameter recovery are measured on the SAME problem.
    fn outlier_gaussian_fixture() -> (FitGraphSpec, MeasurementSpec, FitOptionsSpec) {
        use spectrafit_types::{ModelNodeSpec, ModelTypeStr, ParameterSpec};

        let (true_a, true_c, true_s) = OUTLIER_TRUTH;
        let n = 80usize;
        let x: Vec<f64> = (0..n)
            .map(|i| -4.0 + 8.0 * i as f64 / (n - 1) as f64)
            .collect();
        let mut y: Vec<f64> = x
            .iter()
            .map(|&xi| true_a * (-(xi - true_c).powi(2) / (2.0 * true_s * true_s)).exp())
            .collect();
        // Inject 3 large outliers
        y[10] += 50.0;
        y[40] -= 30.0;
        y[70] += 40.0;

        let mut params = HashMap::new();
        params.insert(
            "amplitude".into(),
            ParameterSpec {
                value: 4.0,
                min: f64::NEG_INFINITY,
                max: f64::INFINITY,
                vary: true,
                expr: None,
                scale: None,
            },
        );
        params.insert(
            "center".into(),
            ParameterSpec {
                value: 0.3,
                min: f64::NEG_INFINITY,
                max: f64::INFINITY,
                vary: true,
                expr: None,
                scale: None,
            },
        );
        params.insert(
            "sigma".into(),
            ParameterSpec {
                value: 1.2,
                min: 1e-6,
                max: f64::INFINITY,
                vary: true,
                expr: None,
                scale: None,
            },
        );

        let graph = FitGraphSpec {
            schema_version: "0.1".into(),
            nodes: vec![ModelNodeSpec {
                id: "g1".into(),
                model_type: ModelTypeStr::Gaussian,
                dataset_index: None,
                parameters: params,
            }],
            expr_edges: vec![],
        };
        let dataset = MeasurementSpec {
            schema_version: None,
            x: vec![x],
            y,
            sigma: None,
            label: None,
        };
        let options = FitOptionsSpec {
            schema_version: None,
            solver: "irls".into(),
            max_iterations: 200,
            tolerance: 1e-8,
            delta0: None,
            max_delta: None,
            eta: None,
        };
        (graph, dataset, options)
    }

    /// Accuracy floor for the outlier fixture, shared by every test that
    /// asserts parameter recovery on it.
    ///
    /// Bisquare gives all three injected outliers weight exactly 0, and the 77
    /// surviving points are a noiseless Gaussian, so IRLS recovers the truth to
    /// machine precision. Measured on this tree: amplitude relative error
    /// 8.2e-12, centre absolute error 1.2e-13, sigma relative error 6.5e-12 —
    /// against the 15 % / 0.3 / 20 % this used to allow, which a regression of
    /// nine orders of magnitude would still have satisfied.
    ///
    /// The bound is set at 1e-6 rather than the ~2× of the achieved error a
    /// straight tightening would give, because `FitOptionsSpec::tolerance` on
    /// this fixture is 1e-8: below that the assertion stops measuring accuracy
    /// and starts measuring whether LM took one iteration more or fewer, which
    /// BLAS-ordering differences between platforms can flip. 1e-6 sits two
    /// decades above that floor and still five decades below the achieved
    /// error, so any real accuracy regression trips it.
    const RECOVERY_TOL: f64 = 1e-6;

    #[test]
    fn irls_recovers_gaussian_with_outlier() {
        let (true_a, true_c, true_s) = OUTLIER_TRUTH;
        let (graph, dataset, options) = outlier_gaussian_fixture();

        let result = solve_irls(
            &graph,
            vec![dataset],
            &options,
            WeightFn::Bisquare(4.685),
            15,
            DEFAULT_TOL_WEIGHTS,
        )
        .expect("IRLS should not error");

        // IRLS with bisquare should recover parameters better than plain LM on outlier data
        let a = result.parameters["g1.amplitude"].value;
        let c = result.parameters["g1.center"].value;
        let s = result.parameters["g1.sigma"].value;

        // Bisquare zeroes the outliers outright, so this is a noiseless fit —
        // see `RECOVERY_TOL` for the measured errors behind the bound.
        assert!(
            (a - true_a).abs() / true_a < RECOVERY_TOL,
            "amplitude error too large: {a}"
        );
        assert!(
            (c - true_c).abs() < RECOVERY_TOL,
            "center error too large: {c}"
        );
        assert!(
            (s - true_s).abs() / true_s < RECOVERY_TOL,
            "sigma error too large: {s}"
        );
    }

    /// Warm start: each outer pass begins from the previous pass's fitted
    /// values instead of re-running LM from the user's initial guess every
    /// time. Measured on this fixture, the cold-started loop never converged
    /// at all — it ran all 15 permitted outer passes and stopped on the cap,
    /// because every pass threw away the previous pass's solution and the
    /// weights kept moving by more than `DEFAULT_TOL_WEIGHTS`. Warm-starting
    /// must reach the weight-convergence break strictly inside the cap, with
    /// the same parameter recovery the cold loop produced. (Measured at the
    /// time of writing: 3 passes warm vs 15 cold. The assertion is left as
    /// "fewer than the cap" rather than "== 3" so it stays a statement about
    /// warm-vs-cold rather than a golden number that any LM tweak would
    /// re-baseline.)
    #[test]
    fn irls_warm_start_converges_in_fewer_outer_passes() {
        const MAX_OUTER: usize = 15;
        const COLD_START_PASSES: usize = MAX_OUTER; // measured: hit the cap

        let (true_a, true_c, true_s) = OUTLIER_TRUTH;
        let (graph, dataset, options) = outlier_gaussian_fixture();
        let run = solve_irls_traced(
            &graph,
            vec![dataset],
            &options,
            WeightFn::Bisquare(4.685),
            MAX_OUTER,
            DEFAULT_TOL_WEIGHTS,
        )
        .expect("IRLS should not error");

        assert!(
            run.n_outer_passes < COLD_START_PASSES,
            "warm-started IRLS should converge in fewer than the {COLD_START_PASSES} \
             outer passes the cold-started loop needed, got {}",
            run.n_outer_passes
        );
        // `< COLD_START_PASSES` alone is satisfied by anything short of the cap,
        // including a 14-pass crawl that would be no evidence of warm-starting.
        // Pin an absolute ceiling near the measured 3 so a regression that
        // merely converges *eventually* still fails.
        assert!(
            run.n_outer_passes <= 6,
            "warm-started IRLS converged in {} outer passes; measured 3 on this \
             fixture, so anything above 6 is a warm-start regression rather than \
             normal variation",
            run.n_outer_passes
        );

        let a = run.result.parameters["g1.amplitude"].value;
        let c = run.result.parameters["g1.center"].value;
        let s = run.result.parameters["g1.sigma"].value;
        // Same measured errors and same reasoning as the cold entry point —
        // see `RECOVERY_TOL`.
        assert!(
            (a - true_a).abs() / true_a < RECOVERY_TOL,
            "amplitude error too large: {a}"
        );
        assert!(
            (c - true_c).abs() < RECOVERY_TOL,
            "center error too large: {c}"
        );
        assert!(
            (s - true_s).abs() / true_s < RECOVERY_TOL,
            "sigma error too large: {s}"
        );
    }

    /// Warm-start gating: a pass that did NOT succeed must never become the
    /// next pass's starting point.
    ///
    /// Driven by `max_iterations: 1` on the inner LM options, which makes every
    /// outer pass stop with `success == false`, so no pass is ever eligible to
    /// seed and every pass must start from the caller's original graph. Before
    /// the gate this test was red on pass 2: the loop called
    /// `warm_started_graph` unconditionally, so pass 2 started from pass 1's
    /// stalled point and its snapshot diverged from the original.
    #[test]
    fn irls_does_not_warm_start_from_a_failed_pass() {
        const MAX_OUTER: usize = 4;

        let (graph, dataset, mut options) = outlier_gaussian_fixture();
        options.max_iterations = 1;

        let run = solve_irls_traced(
            &graph,
            vec![dataset],
            &options,
            WeightFn::Bisquare(4.685),
            MAX_OUTER,
            DEFAULT_TOL_WEIGHTS,
        )
        .expect("IRLS should not error");

        assert!(
            !run.result.success,
            "fixture precondition: `max_iterations: 1` must make the pass fail, \
             got success with message {:?}",
            run.result.message
        );
        assert!(
            run.pass_start_values.len() >= 2,
            "fixture precondition: need at least two outer passes to observe a \
             warm start, got {}",
            run.pass_start_values.len()
        );

        let original = start_point_snapshot(&graph);
        for (i, start) in run.pass_start_values.iter().enumerate() {
            assert_eq!(
                start,
                &original,
                "pass {} started from {start:?}, but no pass succeeded so every \
                 pass must restart from the caller's graph {original:?}",
                i + 1
            );
        }
    }

    /// The other half of the gating rule: a pass that DID succeed must seed the
    /// next one. Pass 1 starts from the caller's graph and pass 2 must not —
    /// otherwise the gate added by
    /// [`irls_does_not_warm_start_from_a_failed_pass`] would be satisfiable by
    /// never warm-starting at all.
    #[test]
    fn irls_warm_starts_from_a_successful_pass() {
        let (graph, dataset, options) = outlier_gaussian_fixture();
        let run = solve_irls_traced(
            &graph,
            vec![dataset],
            &options,
            WeightFn::Bisquare(4.685),
            15,
            DEFAULT_TOL_WEIGHTS,
        )
        .expect("IRLS should not error");

        assert!(
            run.pass_start_values.len() >= 2,
            "need at least two outer passes to observe a warm start, got {}",
            run.pass_start_values.len()
        );
        let original = start_point_snapshot(&graph);
        assert_eq!(
            run.pass_start_values[0], original,
            "pass 1 must start from the caller's graph"
        );
        assert_ne!(
            run.pass_start_values[1], original,
            "pass 2 must start from pass 1's fitted values, not the caller's graph"
        );
    }

    /// Result integrity under warm start: `init_fit` must keep describing the
    /// USER's starting point, not whatever the last outer pass warm-started
    /// from. Pinned against a plain `lm` fit of the same graph, which by
    /// construction evaluates the model at the original initial parameters.
    #[test]
    fn irls_init_fit_describes_the_original_starting_point() {
        let (graph, dataset, options) = outlier_gaussian_fixture();

        let lm_options = FitOptionsSpec {
            solver: "lm".into(),
            ..options.clone()
        };
        let lm_result = crate::dispatch::fit(&graph, vec![dataset.clone()], &lm_options)
            .expect("plain LM reference fit should not error");

        let irls_result = solve_irls(
            &graph,
            vec![dataset],
            &options,
            WeightFn::Bisquare(4.685),
            15,
            DEFAULT_TOL_WEIGHTS,
        )
        .expect("IRLS should not error");

        assert_eq!(irls_result.init_fit.len(), lm_result.init_fit.len());
        for (i, (got, want)) in irls_result
            .init_fit
            .iter()
            .zip(lm_result.init_fit.iter())
            .enumerate()
        {
            assert!(
                (got - want).abs() <= 1e-12 * want.abs().max(1.0),
                "init_fit[{i}] = {got}, expected the original starting point {want}"
            );
        }
    }
}
