//! Regime-adaptive Levenberg–Marquardt step solvers.
//!
//! Both strategies solve the damped Gauss–Newton (Levenberg–Marquardt) system
//! ```text
//!   (JᵀJ + λ·D²) δ = −g ,   g = Jᵀr
//! ```
//! where `D = diag(diag)` is the column-scaling diagonal. They differ only in
//! how the linear algebra is carried out:
//!
//! * [`StepKind::NormalEqLlt`] — form the `p×p` normal-equations matrix and
//!   Cholesky-solve. One streaming `JᵀJ` reduction collapses all `O(m)` work,
//!   so it dominates when `m ≫ p`. The predicted reduction is then computed
//!   from the `p×p` Hessian `H` — no second `O(m)` pass per `λ` trial.
//! * [`StepKind::SvdSecular`] — one thin SVD of the (column-scaled) Jacobian,
//!   then a closed-form damped solution. Avoids forming `JᵀJ`, so it does not
//!   square the condition number — preferred when `p` is large / `J` is
//!   ill-conditioned.

use faer::prelude::*;
use faer::{Mat, MatRef, Side};

/// Which linear-algebra path the step uses. Chosen per-fit by [`select_regime`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StepKind {
    /// Normal equations + Cholesky (`m ≫ p`).
    NormalEqLlt,
    /// SVD + secular/closed-form damped solve (large `p` / ill-conditioned).
    SvdSecular,
}

/// Choose the step factorization path from the problem shape.
///
/// * Many parameters (`p > 40`) ⇒ [`StepKind::SvdSecular`] to avoid squaring the
///   condition number on an ill-conditioned `J`.
/// * Tall and thin (`m ≥ 8·p`) ⇒ [`StepKind::NormalEqLlt`]: the `JᵀJ` reduction
///   collapses the `O(m)` work and the `p×p` Cholesky is trivially cheap.
/// * Otherwise default to [`StepKind::NormalEqLlt`]; milestone M3 adds a cheap
///   conditioning probe (column-norm ratio) to escalate borderline cases.
///
/// The `p > 40` and `m ≥ 8·p` constants are documented heuristics, not tuned
/// thresholds — revisit alongside the benchmark.
pub fn select_regime(n_residuals: usize, n_params: usize) -> StepKind {
    // `m ≥ 8·p` is the clean normal-equations regime. Borderline shapes
    // (`p ≤ 40` but `m < 8·p`) also default to NE today; M3 adds a cheap
    // conditioning probe (column-norm ratio) to escalate them to SVD when `J`
    // is ill-conditioned. `n_residuals` is named for that future use.
    let _ = n_residuals;
    if n_params > 40 {
        StepKind::SvdSecular
    } else {
        StepKind::NormalEqLlt
    }
}

/// Why a step could not be computed for the current `λ`.
#[derive(Debug, Clone)]
pub enum StepError {
    /// `(JᵀJ + λD²)` was not positive-definite — caller should raise `λ`.
    NotPositiveDefinite,
    /// A dense factorization (SVD) failed.
    Factorization(String),
}

/// A computed trial step and the cost reduction the linear model predicts for it.
pub struct StepOutput {
    /// Trial step `δ` (shape `p × 1`).
    pub delta: Mat<f64>,
    /// Predicted decrease of `½‖r‖²`: `−gᵀδ − ½δᵀJᵀJδ` (positive for descent).
    pub predicted_reduction: f64,
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

/// A once-per-outer-iteration factorization of the (column-scaled) Jacobian,
/// reused across every `λ` trial *and* by geodesic acceleration. This is the key
/// to keeping the inner `λ` search cheap: the `O(m·p²)` work (forming `JᵀJ`, or
/// the thin SVD of `J`) happens once; each `λ` trial is then only `O(p³)`
/// (Cholesky) or `O(p²)` (closed form).
///
/// Both `J` and the column scaling `D = diag(diag)` are fixed across the inner
/// loop (only `λ` changes), so this is sound.
pub enum StepFactor {
    /// Normal equations: stores `H = JᵀJ` (`p×p`).
    Ne { h: Mat<f64> },
    /// Thin SVD of the column-scaled `J̃ = J·diag(1/D)`: `U, s, V`.
    Svd {
        u: Mat<f64>,
        s: Vec<f64>,
        v: Mat<f64>,
    },
}

/// Factor the step operator once for the current Jacobian and column scaling.
/// `diag` (`D`) is the per-iteration damping scale; for the SVD path it is baked
/// into the factorization (`J̃ = J/D`), for the NE path it is applied per `λ`.
pub fn factorize(
    kind: StepKind,
    j: MatRef<'_, f64>,
    diag: &[f64],
) -> Result<StepFactor, StepError> {
    match kind {
        StepKind::NormalEqLlt => Ok(StepFactor::Ne {
            h: j.transpose() * j,
        }),
        StepKind::SvdSecular => {
            let m = j.nrows();
            let p = j.ncols();
            let j_scaled = Mat::from_fn(m, p, |i, c| j[(i, c)] / diag[c]);
            let svd = j_scaled
                .as_ref()
                .thin_svd()
                .map_err(|e| StepError::Factorization(format!("{e:?}")))?;
            let uu = svd.U();
            let vv = svd.V();
            let sv = svd.S().column_vector();
            let k = sv.nrows();
            Ok(StepFactor::Svd {
                u: Mat::from_fn(uu.nrows(), uu.ncols(), |i, jx| uu[(i, jx)]),
                v: Mat::from_fn(vv.nrows(), vv.ncols(), |i, jx| vv[(i, jx)]),
                s: (0..k).map(|i| sv[i]).collect(),
            })
        }
    }
}

impl StepFactor {
    /// Solve `(JᵀJ + λD²) δ = −g` for the trial step `δ` and its predicted
    /// reduction `−gᵀδ − ½‖Jδ‖²`. `r` is the residual (used by the SVD path).
    pub fn solve(
        &self,
        g: MatRef<'_, f64>,
        r: MatRef<'_, f64>,
        diag: &[f64],
        lambda: f64,
    ) -> Result<StepOutput, StepError> {
        match self {
            StepFactor::Ne { h } => {
                let p = h.ncols();
                let mut a = h.clone();
                for i in 0..p {
                    a[(i, i)] += lambda * diag[i] * diag[i];
                }
                let llt = a
                    .as_ref()
                    .llt(Side::Lower)
                    .map_err(|_| StepError::NotPositiveDefinite)?;
                let neg_g = Mat::from_fn(p, 1, |i, _| -g[(i, 0)]);
                let delta = llt.solve(neg_g.as_ref());
                // pred = −gᵀδ − ½ δᵀHδ, both O(p²).
                let hd = h.as_ref() * delta.as_ref();
                let predicted_reduction =
                    -col_dot(g, delta.as_ref()) - 0.5 * col_dot(delta.as_ref(), hd.as_ref());
                Ok(StepOutput {
                    delta,
                    predicted_reduction,
                })
            }
            StepFactor::Svd { u, s, v } => {
                let p = v.nrows();
                let k = s.len();
                // δ = D⁻¹ V diag(s/(s²+λ)) Uᵀr  (SVD of J̃ = J/D).
                let utr = u.as_ref().transpose() * r; // k×1
                let coef = Mat::from_fn(k, 1, |i, _| {
                    let si = s[i];
                    -(si / (si * si + lambda)) * utr[(i, 0)]
                });
                let y = v.as_ref() * coef.as_ref(); // p×1
                let delta = Mat::from_fn(p, 1, |i, _| y[(i, 0)] / diag[i]);
                // ‖Jδ‖² = ‖J̃(D∘δ)‖² = Σ_i (s_i·(Vᵀ(D∘δ))_i)².
                let z = Mat::from_fn(p, 1, |i, _| diag[i] * delta[(i, 0)]);
                let vtz = v.as_ref().transpose() * z.as_ref(); // k×1
                let mut jd2 = 0.0;
                for i in 0..k {
                    let x = s[i] * vtz[(i, 0)];
                    jd2 += x * x;
                }
                let predicted_reduction = -col_dot(g, delta.as_ref()) - 0.5 * jd2;
                Ok(StepOutput {
                    delta,
                    predicted_reduction,
                })
            }
        }
    }

    /// Solve `(JᵀJ + λD²) x = rhs` for an arbitrary right-hand side (geodesic
    /// acceleration: `rhs = −Jᵀr_vv`). Reuses this factorization — no re-forming.
    pub fn solve_rhs(
        &self,
        diag: &[f64],
        lambda: f64,
        rhs: MatRef<'_, f64>,
    ) -> Result<Mat<f64>, StepError> {
        match self {
            StepFactor::Ne { h } => {
                let p = h.ncols();
                let mut a = h.clone();
                for i in 0..p {
                    a[(i, i)] += lambda * diag[i] * diag[i];
                }
                let llt = a
                    .as_ref()
                    .llt(Side::Lower)
                    .map_err(|_| StepError::NotPositiveDefinite)?;
                Ok(llt.solve(rhs))
            }
            StepFactor::Svd { s, v, .. } => {
                let p = v.nrows();
                let k = s.len();
                // x = D⁻¹ V diag(1/(s²+λ)) Vᵀ D⁻¹ rhs.
                let dinv_rhs = Mat::from_fn(p, 1, |i, _| rhs[(i, 0)] / diag[i]);
                let w = v.as_ref().transpose() * dinv_rhs.as_ref(); // k×1
                let w_scaled = Mat::from_fn(k, 1, |i, _| {
                    let si = s[i];
                    w[(i, 0)] / (si * si + lambda)
                });
                let y = v.as_ref() * w_scaled.as_ref(); // p×1
                Ok(Mat::from_fn(p, 1, |i, _| y[(i, 0)] / diag[i]))
            }
        }
    }
}
