//! The [`TrustRegionProblem`] trait — the only coupling point between this
//! numerics-only crate and a concrete model/graph.
//!
//! An implementor owns the parameter state and is responsible for any
//! parameterisation-level projection (bounds reflection, expression-tied
//! parameters) inside [`set_params`](TrustRegionProblem::set_params). The
//! driver treats the problem as an opaque source of weighted residuals and a
//! weighted Jacobian written into caller-owned `faer` buffers — no allocation
//! on the hot path.

use faer::{Mat, MatMut};
use spectrafit_types::CoreError;

/// A weighted nonlinear least-squares problem driven by the trust-region core.
///
/// Conventions:
/// * "weighted" means residuals and Jacobian already carry the per-point `1/σ`
///   factor, so the driver minimises `½‖r‖²` directly.
/// * `n_params` is the number of **free** parameters (tied/fixed excluded).
/// * Bounds reflection and tied-parameter application live in [`set_params`];
///   the driver never sees them, it only proposes raw steps.
pub trait TrustRegionProblem {
    /// Number of residual rows `m` (total points across datasets).
    fn n_residuals(&self) -> usize;

    /// Number of free parameters `p`.
    fn n_params(&self) -> usize;

    /// Current free-parameter vector (length `p`).
    ///
    /// Called after [`set_params`] so the driver can read back the value the
    /// problem actually applied (e.g. after bounds reflection).
    fn params(&self) -> Vec<f64>;

    /// Install a proposed free-parameter vector `p` (length `n_params`).
    ///
    /// The implementor applies any reflection / tied-plan here, so a subsequent
    /// [`params`] may differ from `p`.
    fn set_params(&mut self, p: &[f64]);

    /// Write the weighted residual vector `r` (shape `m × 1`) for the current
    /// parameters into `r`.
    fn residuals_into(&mut self, r: MatMut<'_, f64>) -> Result<(), CoreError>;

    /// Write the weighted Jacobian `J` (shape `m × p`) for the current
    /// parameters into `jac`.
    fn jacobian_into(&mut self, jac: MatMut<'_, f64>) -> Result<(), CoreError>;

    /// Apply the weighted Jacobian as a linear operator: write `out = J·v`
    /// (length `m`) for the current parameters, where `v` has length `p`.
    ///
    /// This is the **matrix-free** half of the problem contract, used by
    /// Krylov subproblem solvers (truncated-CG / Steihaug) that need only
    /// Jacobian–vector products, never the dense `J`. The default materializes
    /// `J` via [`jacobian_into`](Self::jacobian_into) and multiplies — correct
    /// but `O(m·p)` storage per call; a matrix-free implementor overrides both
    /// operators to avoid forming `J`. Implementations must stay consistent with
    /// `jacobian_into`: `apply_jacobian(v) == J·v`.
    fn apply_jacobian(&mut self, v: &[f64], out: &mut [f64]) -> Result<(), CoreError> {
        let m = self.n_residuals();
        let p = self.n_params();
        let mut jac = Mat::<f64>::zeros(m, p);
        self.jacobian_into(jac.as_mut())?;
        for (i, o) in out.iter_mut().enumerate().take(m) {
            let mut s = 0.0;
            for (c, &vc) in v.iter().enumerate().take(p) {
                s += jac[(i, c)] * vc;
            }
            *o = s;
        }
        Ok(())
    }

    /// Apply the transposed weighted Jacobian: write `out = Jᵀ·u` (length `p`)
    /// for the current parameters, where `u` has length `m`.
    ///
    /// The transpose-multiply companion to [`apply_jacobian`](Self::apply_jacobian)
    /// (forms the Krylov normal-equation operator `v ↦ Jᵀ(J·v)` without `JᵀJ`).
    /// The default materializes `J` and multiplies; matrix-free implementors
    /// override it. Must satisfy `apply_jacobian_transpose(u) == Jᵀ·u`.
    fn apply_jacobian_transpose(&mut self, u: &[f64], out: &mut [f64]) -> Result<(), CoreError> {
        let m = self.n_residuals();
        let p = self.n_params();
        let mut jac = Mat::<f64>::zeros(m, p);
        self.jacobian_into(jac.as_mut())?;
        for (c, o) in out.iter_mut().enumerate().take(p) {
            let mut s = 0.0;
            for (i, &ui) in u.iter().enumerate().take(m) {
                s += jac[(i, c)] * ui;
            }
            *o = s;
        }
        Ok(())
    }

    /// Per-parameter scale factors (length `p`) used for column scaling of the
    /// damping diagonal. Defaults to all-ones (Levenberg damping). Wired to
    /// `Parameter.scale` by the solver crate in a later milestone.
    fn scales(&self) -> Vec<f64> {
        vec![1.0; self.n_params()]
    }

    /// Coleman–Li trust-region scaling `v ∈ (0, 1]` per free parameter for the
    /// current point and gradient `grad`, or `None` when the problem is
    /// unbounded. `v_i → 0` as parameter `i` approaches the active bound; the
    /// driver folds `D_i ← D_i / √v_i`, so the trust region shrinks near bounds
    /// (the "reflective" part of Trust-Region-Reflective). Default: `None`.
    fn trust_scaling(&self, _grad: &[f64]) -> Option<Vec<f64>> {
        None
    }
}
