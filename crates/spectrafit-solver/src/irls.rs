//! IRLS — Iteratively Reweighted Least Squares for robust fitting.
//!
//! Wraps the existing LM solver in an outer loop that reweights residuals
//! using a robust loss function (Huber, Bisquare, or Cauchy) to down-weight
//! outlier points.  Each outer iteration:
//!   1. Run LM on the current weighted problem.
//!   2. Compute standardised residuals `r_i / σ_scale`.
//!   3. Update per-point weights `w_i = ρ'(r_i) / r_i` (IRLS weight formula).
//!   4. Repeat until weights converge or `max_outer_iter` is reached.
//!
//! Reference: Holland & Welsch (1977), Fox & Weisberg (2002).

use spectrafit_types::{CoreError, FitGraphSpec, FitOptionsSpec, FitResultSpec, MeasurementSpec};

use crate::dispatch::fit as lm_fit;
use crate::error::SolverError;

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

    /// Parse a weight function from the string name stored in `FitOptionsSpec`.
    ///
    /// Recognised names: `"huber"`, `"bisquare"`, `"cauchy"`.  Unknown names
    /// fall back to the Huber default.
    // Infallible, lenient parser (unknown → default); not the fallible
    // `std::str::FromStr` contract, so the trait is deliberately not implemented.
    #[allow(clippy::should_implement_trait)]
    pub fn from_str(s: &str) -> Self {
        match s {
            "bisquare" | "biweight" => WeightFn::Bisquare(4.685),
            "cauchy" => WeightFn::Cauchy(2.385),
            _ => WeightFn::Huber(1.345),
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
/// the rest without modification.
///
/// # Arguments
/// * `graph`    — model DAG.
/// * `datasets` — one or more measurement datasets.
/// * `options`  — fit options; `solver` field should be `"irls"`.
/// * `weight_fn` — robust weight function.
/// * `max_outer_iter` — maximum IRLS outer iterations (default 20).
/// * `tol_weights` — convergence threshold on max weight change (default 1e-4).
pub fn solve_irls(
    graph: &FitGraphSpec,
    datasets: Vec<MeasurementSpec>,
    options: &FitOptionsSpec,
    weight_fn: WeightFn,
    max_outer_iter: usize,
    tol_weights: f64,
) -> Result<FitResultSpec, CoreError> {
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

    for _outer in 0..max_outer_iter.max(1) {
        // Build sigma-adjusted datasets from current IRLS weights.
        let weighted_datasets = apply_irls_weights(&datasets, &irls_weights);

        // Run LM on the weighted problem.
        let fit = lm_fit(graph, weighted_datasets, &inner_options)?;

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

    result.ok_or_else(|| SolverError::IrlsFailure("no iterations completed".into()).into())
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

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
    use std::collections::HashMap;

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
            WeightFn::Bisquare(_)
        ));
        assert!(matches!(WeightFn::from_str("cauchy"), WeightFn::Cauchy(_)));
        assert!(matches!(WeightFn::from_str("huber"), WeightFn::Huber(_)));
        assert!(matches!(WeightFn::from_str("unknown"), WeightFn::Huber(_)));
    }

    #[test]
    fn irls_recovers_gaussian_with_outlier() {
        use spectrafit_types::{
            FitGraphSpec, MeasurementSpec, ModelNodeSpec, ModelTypeStr, ParameterSpec,
        };

        let (true_a, true_c, true_s) = (5.0_f64, 0.0_f64, 1.0_f64);
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

        let result = solve_irls(
            &graph,
            vec![dataset],
            &options,
            WeightFn::Bisquare(4.685),
            15,
            1e-4,
        )
        .expect("IRLS should not error");

        // IRLS with bisquare should recover parameters better than plain LM on outlier data
        let a = result.parameters["g1.amplitude"].value;
        let c = result.parameters["g1.center"].value;
        let s = result.parameters["g1.sigma"].value;

        // Looser tolerance than clean data — outliers still influence the first LM pass
        assert!(
            (a - true_a).abs() / true_a < 0.15,
            "amplitude error too large: {a}"
        );
        assert!((c - true_c).abs() < 0.3, "center error too large: {c}");
        assert!(
            (s - true_s).abs() / true_s < 0.20,
            "sigma error too large: {s}"
        );
    }
}
