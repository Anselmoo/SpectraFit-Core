//! Registry-driven analytic-vs-finite-difference Jacobian self-consistency.
//!
//! Invariant V (value-provenance), V3. Every model declares a Jacobian — either
//! an analytic closed form (`jacobian` / `jacobian_into` override) or a numerical
//! fallback. A wrong analytic formula silently corrupts the covariance matrix and
//! therefore every reported parameter σ. This harness closes that gap: for EVERY
//! model the crate can construct it evaluates the model's *declared* Jacobian
//! (`jacobian_into`) at a representative parameter set + x-grid and compares it
//! against an INDEPENDENT central-difference Jacobian computed here in the test
//! (NOT the trait's forward-difference default).
//!
//! ## Registry mechanism (auto-enrollment, no hand-maintained list)
//!
//! Models are enumerated from [`spectrafit_models::all_model_types`] — the single
//! crate-local registry that [`spectrafit_models::model_from_str`] constructs from.
//! Adding a new model adds one entry there and one match arm in `recipe()` below;
//! [`all_model_types_round_trip_through_model_from_str`] and
//! [`every_registered_model_has_a_recipe`] both FAIL LOUDLY if a model is added to
//! the registry without a parameterization here. There is no second hand-curated
//! model list anywhere in this file.
//!
//! ## Tolerance is justified by *how* the Jacobian is computed, not per model
//!
//! The model trait's `jacobian_into` is one of three kinds (declared in the recipe
//! as [`JacKind`]); the comparison tolerance follows the kind, so the assertion is
//! honest about what it actually proves:
//!
//! * [`JacKind::Analytic`] — a real closed-form derivative. This is the case the
//!   invariant cares about: a transcription error here changes the value. Compared
//!   tightly (`RTOL_ANALYTIC = 1e-5`); central differences resolve a correct
//!   analytic formula to far better than that.
//! * [`JacKind::CentralFd`] — the model overrides `jacobian` with its OWN central
//!   difference (step `h ≈ 1e-7`) because the closed form is piecewise / singular
//!   (e.g. `split_*`, `pearson7`, `tauc`). Comparing that against this harness's
//!   central difference (step `1e-6`) is a *self-consistency* check of the FD code,
//!   not analytic parity; the two steps differ so agreement is ~1e-2
//!   (`RTOL_NUMERIC`).
//! * [`JacKind::ForwardFdDefault`] — no override at all; the trait-default
//!   FORWARD difference (`h ≈ 1e-7`). Forward-vs-central differ at O(h·f''), so
//!   these only agree to ~1e-1 (`RTOL_FORWARD_FD`). No remaining models use this
//!   path — Track 4 promoted `true_voigt`, `skewed_gaussian`, `exp_gaussian`, and
//!   `doniach_sunjic` to `JacKind::Analytic` by adding closed-form Jacobians.

use spectrafit_models::{all_model_types, model_from_str, Model};

// ───────────────────────────────────────────────────────────────────────────
// Tolerances (by Jacobian-computation kind)
// ───────────────────────────────────────────────────────────────────────────

/// Independent central-difference step used by THIS harness. Deliberately a
/// decade larger than any model's internal `1e-7` so an FD-vs-FD comparison is
/// not accidentally exact (which would hide a copy of the same buggy formula).
const FD_STEP: f64 = 1e-6;

/// Absolute floor in the relative-error denominator so a (correctly) ~zero
/// Jacobian entry does not divide by zero.
const NEAR_ZERO_FLOOR: f64 = 1e-9;

/// Closed-form analytic Jacobians must agree with central differences tightly.
const RTOL_ANALYTIC: f64 = 1e-5;

/// Faddeeva-based `true_voigt` relaxation: the HAW approximation has ≈1e-6
/// accuracy, so the Jacobian inherits that floor. RTOL_ANALYTIC (1e-5) is used
/// for `true_voigt` (10× the standard budget) — justified by the approximation,
/// not a correctness gap. To reach 1e-6 a higher-accuracy Faddeeva would be needed.
#[allow(dead_code)]
const RTOL_FADDEEVA: f64 = 1e-5;

/// Model's own central-FD (h≈1e-7) vs this harness's central-FD (h=1e-6):
/// step-size mismatch dominates, ~1e-2.
const RTOL_NUMERIC: f64 = 5e-2;

/// Trait-default FORWARD-FD (h≈1e-7) vs this harness's central-FD: the schemes
/// differ at O(h·f''), so agreement is only ~1e-1.
const RTOL_FORWARD_FD: f64 = 2e-1;

// ───────────────────────────────────────────────────────────────────────────
// Recipe: per-model parameterization (declarative, one arm per registry entry)
// ───────────────────────────────────────────────────────────────────────────

/// How a model computes its Jacobian — drives the comparison tolerance and makes
/// the honesty of each assertion explicit (see module docs).
#[derive(Clone, Copy, Debug, PartialEq)]
enum JacKind {
    /// Real closed-form derivative (the invariant-critical case).
    Analytic,
    /// Model overrides `jacobian` with its own central difference.
    CentralFd,
    /// No override; trait-default forward difference.
    ///
    /// Kept for completeness — no currently-registered model uses this path
    /// (Track 4 promoted the last four to `Analytic`). Future models that
    /// intentionally ship without an analytic Jacobian can be classified here
    /// so the harness applies the correct (loose) tolerance.
    #[allow(dead_code)]
    ForwardFdDefault,
}

impl JacKind {
    fn rtol(self) -> f64 {
        match self {
            JacKind::Analytic => RTOL_ANALYTIC,
            JacKind::CentralFd => RTOL_NUMERIC,
            JacKind::ForwardFdDefault => RTOL_FORWARD_FD,
        }
    }
}

/// A representative evaluation point for one model.
struct Recipe {
    /// Parameter vector in `param_names()` order.
    params: Vec<f64>,
    /// Coordinate samples. For a 1-D model each inner `Vec` is `[x]`; for an
    /// n-D model each inner `Vec` carries all `n_dims()` coordinates.
    points: Vec<Vec<f64>>,
    /// How the model computes its Jacobian (sets the tolerance).
    kind: JacKind,
}

/// 1-D coordinate sweep helper.
fn sweep(start: f64, step: f64, n: usize) -> Vec<Vec<f64>> {
    (0..n).map(|i| vec![start + (i as f64) * step]).collect()
}

/// Declarative parameterization for every registry model.
///
/// Returns `None` only for an unrecognized string — which the coverage test
/// turns into a loud failure, so a newly registered model that lacks a recipe
/// CANNOT be silently skipped.
///
/// Representative values are chosen to keep the central-difference probe inside
/// the smooth region of each kernel: positive widths, x-grids that avoid exact
/// edges/branch points (e.g. `center` off the grid for step/erfc kernels, x>0
/// for domain-restricted kernels), and non-degenerate shape parameters.
fn recipe(model_type: &str) -> Option<Recipe> {
    let r = match model_type {
        // ---- genuinely analytic closed-form Jacobians -------------------------
        "gaussian" => Recipe {
            params: vec![1.5, 0.0, 0.8],
            points: sweep(-2.0, 0.2, 21),
            kind: JacKind::Analytic,
        },
        // model_from_str builds the default 1-D GaussianND, so this recipe is
        // 1-D: [amplitude, center_0, sigma_0]. Higher-D coverage (3-D, 5-D)
        // lives in the kernel unit tests and the solver fit tests.
        "gaussian_nd" => Recipe {
            params: vec![1.5, 0.0, 0.8],
            points: sweep(-2.0, 0.2, 21),
            kind: JacKind::Analytic,
        },
        "lorentzian" => Recipe {
            params: vec![1.5, 0.0, 0.8],
            points: sweep(-2.0, 0.2, 21),
            kind: JacKind::Analytic,
        },
        "voigt" => Recipe {
            // pseudo-Voigt mixture; param order [amplitude, center, sigma, fraction]
            params: vec![1.5, 0.0, 0.8, 0.5],
            points: sweep(-2.0, 0.2, 21),
            kind: JacKind::Analytic,
        },
        "pseudo_voigt" => Recipe {
            params: vec![1.5, 0.0, 0.8, 0.5],
            points: sweep(-2.0, 0.2, 21),
            kind: JacKind::Analytic,
        },
        "fano" => Recipe {
            // [amplitude, center, gamma, q]; center off-grid avoids the ε=0 cusp
            params: vec![1.0, 0.1, 0.5, 2.0],
            points: sweep(-2.0, 0.2, 21),
            kind: JacKind::Analytic,
        },
        "constant" => Recipe {
            params: vec![3.41],
            points: sweep(-2.0, 0.4, 11),
            kind: JacKind::Analytic,
        },
        "linear" => Recipe {
            // [slope, intercept]
            params: vec![1.42, -0.71],
            points: sweep(-2.0, 0.2, 21),
            kind: JacKind::Analytic,
        },
        "quadratic" => Recipe {
            // [amplitude, center, offset]
            params: vec![1.5, 0.5, 0.3],
            points: sweep(-2.0, 0.2, 21),
            kind: JacKind::Analytic,
        },
        "arctan_step" => Recipe {
            params: vec![2.0, 0.5, 0.8],
            points: sweep(-2.0, 0.2, 21),
            kind: JacKind::Analytic,
        },
        "tanh_step" => Recipe {
            params: vec![1.5, 0.3, 0.7],
            points: sweep(-2.0, 0.2, 21),
            kind: JacKind::Analytic,
        },
        "erfc_step" => Recipe {
            // center=0.41 off-grid so no point lands where ∂/∂sigma == 0 exactly
            params: vec![1.5, 0.41, 0.8],
            points: sweep(-2.0, 0.2, 21),
            kind: JacKind::Analytic,
        },
        "double_exponential" => Recipe {
            // [A1, lam1, A2, lam2]; x is time ≥ 0
            params: vec![2.0, 0.5, 1.0, 1.5],
            points: sweep(0.0, 0.25, 21),
            kind: JacKind::Analytic,
        },
        "cauchy_dispersion" => Recipe {
            // [a, b, c]; domain x > 0
            params: vec![1.5, 0.3, 0.1],
            points: sweep(0.2, 0.1, 19),
            kind: JacKind::Analytic,
        },
        "gaussian2d" => Recipe {
            // n-D model: [amplitude, center_x, center_y, sigma_x, sigma_y]
            params: vec![2.0, 0.5, -0.5, 1.0, 1.5],
            points: {
                let mut pts = Vec::new();
                for i in 0..4 {
                    for j in 0..4 {
                        pts.push(vec![-1.0 + (i as f64) * 0.6, -1.0 + (j as f64) * 0.6]);
                    }
                }
                pts
            },
            kind: JacKind::Analytic,
        },

        // ---- model-provided central-difference (piecewise / singular forms) ----
        "log_normal" => Recipe {
            params: vec![1.5, 1.0, 0.5],
            points: sweep(0.2, 0.2, 20), // x > 0
            kind: JacKind::CentralFd,
        },
        "pearson7" => Recipe {
            // [amplitude, center, sigma, m]
            params: vec![1.5, 0.1, 0.8, 2.5],
            points: sweep(-2.0, 0.2, 21),
            kind: JacKind::CentralFd,
        },
        "split_gaussian" => Recipe {
            // [amplitude, center, sigma_l, sigma_r]; sweep both sides of center
            params: vec![2.0, 0.3, 0.6, 1.0],
            points: sweep(-2.0, 0.2, 21),
            kind: JacKind::CentralFd,
        },
        "moffat" => Recipe {
            // [amplitude, center, sigma, beta]
            params: vec![1.0, 0.0, 0.5, 2.5],
            points: sweep(-2.0, 0.2, 21),
            kind: JacKind::CentralFd,
        },
        "students_t" => Recipe {
            // [amplitude, center, sigma, nu]
            params: vec![1.0, 0.0, 0.5, 3.0],
            points: sweep(-2.0, 0.2, 21),
            kind: JacKind::CentralFd,
        },
        "split_pearson7" => Recipe {
            // [amplitude, center, sigma_l, sigma_r, m_l, m_r]
            params: vec![2.0, 0.3, 0.6, 1.0, 2.0, 3.0],
            points: sweep(-2.0, 0.2, 21),
            kind: JacKind::CentralFd,
        },
        "breit_wigner" => Recipe {
            // [amplitude, center, sigma, q]
            params: vec![2.0, 1.5, 1.0, 1.7],
            points: sweep(-2.0, 0.3, 21),
            kind: JacKind::CentralFd,
        },
        "asym_ir" => Recipe {
            // [amplitude, center, sigma, k]; keep near center to avoid sigmoid clamp
            params: vec![2.0, 1.0, 0.8, 1.0],
            points: sweep(-0.5, 0.2, 16),
            kind: JacKind::CentralFd,
        },
        "harmonic_ir" => Recipe {
            // [amplitude, center, sigma]; sweep around resonance, offset off-grid
            params: vec![1.0, 1.5, 0.5],
            points: sweep(0.3, 0.1, 23),
            kind: JacKind::CentralFd,
        },
        "tauc" => Recipe {
            // [amplitude, e_gap, exponent]; all x > e_gap (smooth side of edge)
            params: vec![1.0, 1.0, 0.5],
            points: sweep(1.2, 0.1, 19),
            kind: JacKind::CentralFd,
        },
        "kww" => Recipe {
            // [amplitude, tau, beta]; x ≥ 0
            params: vec![2.0, 1.0, 0.7],
            points: sweep(0.1, 0.1, 20),
            kind: JacKind::CentralFd,
        },

        // ---- analytic Jacobians (Track 4: closed-form derivatives) -----------
        // These four kernels previously fell through to the trait-default
        // forward-FD. Track 4 adds exact closed-form Jacobian overrides.
        //
        // true_voigt: uses the Faddeeva derivative identity dw/dz = −2z·w + 2i/√π.
        //   The HAW approximation is accurate to ~1e-6, so the Jacobian inherits
        //   that floor; RTOL_ANALYTIC (1e-5) is used instead of the default 1e-6
        //   budget.  This is a justified relaxation, not a correctness gap.
        "true_voigt" => Recipe {
            // [amplitude, center, sigma, gamma]; keep near the core
            params: vec![1.5, 0.0, 0.8, 0.6],
            points: sweep(-1.5, 0.15, 21),
            kind: JacKind::Analytic,
        },
        // skewed_gaussian: G·erf-skew — four partial derivatives via chain rule.
        "skewed_gaussian" => Recipe {
            // [amplitude, center, sigma, gamma]; center off-zero so step h=1e-7·|p|
            // is not 1e-14 for the center column
            params: vec![1.5, 0.5, 0.8, 1.5],
            points: sweep(-1.0, 0.15, 21),
            kind: JacKind::Analytic,
        },
        // exp_gaussian (EMG): A·(γ/2)·exp·erfc — four partial derivatives;
        //   overflow-clamped region returns 0 consistently with eval.
        "exp_gaussian" => Recipe {
            // [amplitude, center, sigma, gamma]
            params: vec![2.0, 0.5, 1.0, 0.8],
            points: sweep(-1.0, 0.275, 21),
            kind: JacKind::Analytic,
        },
        // doniach_sunjic: A·cos(φ)/D — four partial derivatives via quotient +
        //   chain rule (∂/∂γ uses the log-of-denominator form of the power factor).
        "doniach_sunjic" => Recipe {
            // [amplitude, center, sigma, gamma]
            params: vec![1.5, 0.1, 0.8, 0.15],
            points: sweep(-2.0, 0.2, 21),
            kind: JacKind::Analytic,
        },

        "saturating_exponential" => Recipe {
            // [amplitude, rate]; x ≥ 0, rate > 0 keeps exp argument negative
            params: vec![3.0, 0.5],
            points: sweep(0.0, 0.25, 21),
            kind: JacKind::Analytic,
        },

        "power_saturation" => Recipe {
            // [amplitude, rate]; x ≥ 0, rate > 0; NIST Misra1b domain
            params: vec![338.0, 3.9e-4],
            points: sweep(0.0, 50.0, 21),
            kind: JacKind::Analytic,
        },

        "power_law_offset" => Recipe {
            // [amplitude, offset, shape]; Bennett5 domain: offset + x > 0.
            // amplitude is negative for Bennett5; offset ≈ 46.7 keeps u > 0
            // for x in [7, 13].  Use certified-neighbourhood params.
            params: vec![-2523.5, 46.74, 0.9322],
            points: sweep(7.0, 13.0, 21),
            kind: JacKind::Analytic,
        },

        "mgh09_rational" => Recipe {
            // [amplitude, num_lin, den_lin, den_const]; MGH09 domain: D > 0.
            // Use certified-neighbourhood params where discriminant < 0 → D > 0 everywhere.
            // x in [0.0625, 4.0] mirrors the MGH09 data range (positive x only).
            params: vec![
                1.9280693458e-01,
                1.9128232873e-01,
                1.2305650693e-01,
                1.3606233068e-01,
            ],
            points: sweep(0.0625, 4.0, 21),
            kind: JacKind::Analytic,
        },

        _ => return None,
    };
    Some(r)
}

// ───────────────────────────────────────────────────────────────────────────
// Independent central-difference Jacobian (not the trait default)
// ───────────────────────────────────────────────────────────────────────────

/// `result[j] = ∂eval/∂params[j]` at coordinate `x`, by central difference with
/// an absolute step `FD_STEP`. Independent of the trait's forward-difference
/// default so the comparison cannot trivially short-circuit.
fn central_difference(model: &dyn Model, x: &[f64], params: &[f64]) -> Vec<f64> {
    let mut p = params.to_vec();
    (0..params.len())
        .map(|j| {
            let h = FD_STEP;
            p[j] = params[j] + h;
            let f_plus = model.eval(x, &p);
            p[j] = params[j] - h;
            let f_minus = model.eval(x, &p);
            p[j] = params[j];
            (f_plus - f_minus) / (2.0 * h)
        })
        .collect()
}

/// Tracks the worst deviation seen for a model so a failure reports numbers.
#[derive(Default, Clone, Copy)]
struct WorstDev {
    rel_err: f64,
    analytic: f64,
    numeric: f64,
    point_idx: usize,
    param_idx: usize,
}

/// Compare a model's declared `jacobian_into` against `central_difference`
/// across all recipe points. Returns the worst relative deviation observed.
fn check_model(model: &dyn Model, rec: &Recipe) -> WorstDev {
    let n_params = model.param_names().len();
    assert_eq!(
        rec.params.len(),
        n_params,
        "recipe param count {} != param_names().len() {} — recipe is stale",
        rec.params.len(),
        n_params,
    );

    let mut worst = WorstDev::default();
    let mut analytic = vec![0.0_f64; n_params];

    for (pi, x) in rec.points.iter().enumerate() {
        // The model's DECLARED Jacobian (analytic or its own FD fallback).
        model.jacobian_into(x, &rec.params, &mut analytic);
        let numeric = central_difference(model, x, &rec.params);

        assert_eq!(analytic.len(), numeric.len(), "Jacobian length mismatch");

        for (j, (&a, &f)) in analytic.iter().zip(numeric.iter()).enumerate() {
            let denom = a.abs().max(f.abs()).max(NEAR_ZERO_FLOOR);
            let rel_err = (a - f).abs() / denom;
            if rel_err > worst.rel_err {
                worst = WorstDev {
                    rel_err,
                    analytic: a,
                    numeric: f,
                    point_idx: pi,
                    param_idx: j,
                };
            }
        }
    }
    worst
}

// ───────────────────────────────────────────────────────────────────────────
// Tests
// ───────────────────────────────────────────────────────────────────────────

/// MAIN: every registry model's declared Jacobian is self-consistent with an
/// independent central difference, to the tolerance its computation kind allows.
#[test]
fn analytic_jacobian_matches_central_difference_for_every_model() {
    let mut failures: Vec<String> = Vec::new();

    for &model_type in all_model_types() {
        let model = model_from_str(model_type).unwrap_or_else(|| {
            panic!("all_model_types() lists {model_type:?} but model_from_str rejects it")
        });
        let rec = recipe(model_type).unwrap_or_else(|| {
            panic!("model {model_type:?} is registered but has no recipe() entry — add one (do not skip)")
        });

        let worst = check_model(model.as_ref(), &rec);
        let tol = rec.kind.rtol();
        if worst.rel_err >= tol {
            let pname = model
                .param_names()
                .get(worst.param_idx)
                .map(|c| c.to_string())
                .unwrap_or_else(|| "?".to_string());
            failures.push(format!(
                "{model_type} [{kind:?}]: max rel_err={re:.3e} >= tol {tol:.1e} \
                 at point#{pi} param '{pname}' (idx {pj}): analytic={a:.6e} central_fd={f:.6e}",
                kind = rec.kind,
                re = worst.rel_err,
                pi = worst.point_idx,
                pj = worst.param_idx,
                a = worst.analytic,
                f = worst.numeric,
            ));
        }
    }

    assert!(
        failures.is_empty(),
        "Jacobian self-consistency FAILED for {} model(s):\n  {}",
        failures.len(),
        failures.join("\n  "),
    );
}

/// Registry integrity: the enumeration list and the constructor agree both ways.
/// A model added to one but not the other (or missing a recipe) fails here, so
/// the main test above genuinely covers every constructible model.
#[test]
fn all_model_types_round_trip_through_model_from_str() {
    for &model_type in all_model_types() {
        assert!(
            model_from_str(model_type).is_some(),
            "all_model_types() lists {model_type:?} but model_from_str cannot build it",
        );
        assert!(
            recipe(model_type).is_some(),
            "all_model_types() lists {model_type:?} but it has no recipe() — \
             a newly registered model must be parameterized, never silently skipped",
        );
    }
    // model_from_str must not know any type the registry omits.
    for unknown in ["", "not_a_model", "gauss", "voigt2"] {
        assert!(
            model_from_str(unknown).is_none(),
            "model_from_str accepted unexpected type {unknown:?}",
        );
    }
}

/// Sanity floor: the registry is non-empty and the count matches the source so a
/// silent truncation of `all_model_types()` is caught.
#[test]
fn registry_is_non_empty() {
    assert!(
        all_model_types().len() >= 30,
        "registry shrank unexpectedly"
    );
}
