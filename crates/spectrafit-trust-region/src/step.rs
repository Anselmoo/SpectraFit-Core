//! The trust-region **subproblem** contract shared by the Δ-radius methods
//! (dogleg, Newton-CG/Steihaug).
//!
//! At each outer iteration the [`driver`](crate::driver) hands a subproblem
//! solver the local quadratic model in **scaled coordinates** `δ̃ = D·δ`:
//! minimise
//! ```text
//!   m(δ̃) = g̃ᵀδ̃ + ½ δ̃ᵀ J̃ᵀJ̃ δ̃     subject to   ‖δ̃‖ ≤ Δ
//! ```
//! where `J̃ = J·diag(1/D)` is the column-scaled Jacobian and `g̃ = diag(1/D)·g`
//! the scaled gradient (`g = Jᵀr`). Working in scaled coordinates turns the
//! trust region into a plain Euclidean ball, so each method solves the standard
//! subproblem and the driver maps the result back with `δ = diag(1/D)·δ̃`.
//!
//! The Gauss–Newton Hessian `J̃ᵀJ̃` is never formed: [`Subproblem`] exposes only
//! the matrix-free products `J̃·v` and `J̃ᵀ·u`, which is exactly what a Krylov
//! method (Steihaug-CG) needs and what keeps the large-residual case cheap.

use faer::{Mat, MatRef};

/// The trust-region subproblem at one outer iteration, in scaled coordinates.
///
/// Holds the column-scaled Jacobian `J̃` and scaled gradient `g̃`; a solver
/// returns a scaled step `δ̃` with `‖δ̃‖ ≤ Δ`.
pub struct Subproblem<'a> {
    /// Column-scaled Jacobian `J̃ = J·diag(1/D)` (`m×p`).
    jacobian: MatRef<'a, f64>,
    /// Scaled gradient `g̃ = diag(1/D)·Jᵀr` (`p×1`).
    gradient: MatRef<'a, f64>,
}

impl<'a> Subproblem<'a> {
    /// Build a subproblem view over the scaled Jacobian and scaled gradient.
    pub fn new(jacobian: MatRef<'a, f64>, gradient: MatRef<'a, f64>) -> Self {
        Self { jacobian, gradient }
    }

    /// Number of free parameters `p`.
    pub fn n_params(&self) -> usize {
        self.jacobian.ncols()
    }

    /// The scaled gradient `g̃` (`p×1`).
    pub fn gradient(&self) -> MatRef<'_, f64> {
        self.gradient
    }

    /// The column-scaled Jacobian `J̃` (`m×p`). Dense methods (dogleg) form the
    /// Gauss–Newton system from it; Krylov methods should prefer [`hvec`](Self::hvec).
    pub fn jacobian(&self) -> MatRef<'_, f64> {
        self.jacobian
    }

    /// Matrix-free product `J̃·v` (`m×1`) — never forms `J̃ᵀJ̃`.
    pub fn jvec(&self, v: MatRef<'_, f64>) -> Mat<f64> {
        self.jacobian * v
    }

    /// Matrix-free product `J̃ᵀ·u` (`p×1`).
    pub fn jtvec(&self, u: MatRef<'_, f64>) -> Mat<f64> {
        self.jacobian.transpose() * u
    }

    /// Hessian–vector product `H·v = J̃ᵀ(J̃·v)` (`p×1`) without forming `H`.
    pub fn hvec(&self, v: MatRef<'_, f64>) -> Mat<f64> {
        let jv = self.jacobian * v;
        self.jacobian.transpose() * jv.as_ref()
    }

    /// Predicted reduction of `½‖r‖²` for a scaled step `δ̃`:
    /// `−g̃ᵀδ̃ − ½‖J̃δ̃‖²` (positive for a descent step).
    pub fn predicted_reduction(&self, s: MatRef<'_, f64>) -> f64 {
        let gs = self.gradient.transpose() * s; // 1×1
        let js = self.jacobian * s;
        -gs[(0, 0)] - 0.5 * js.as_ref().squared_norm_l2()
    }
}

/// A scaled step produced by a [`SubproblemStep`].
pub struct StepResult {
    /// The scaled step `δ̃` (`p×1`); the driver maps it back via `δ = δ̃/D`.
    pub step: Mat<f64>,
    /// Predicted reduction `−g̃ᵀδ̃ − ½‖J̃δ̃‖²` (≥ 0 for a useful step).
    pub predicted_reduction: f64,
    /// Whether the step reached the trust-region boundary `‖δ̃‖ = Δ` (the driver
    /// expands Δ on a very good boundary step).
    pub hit_boundary: bool,
}

/// A trust-region subproblem solver: minimise the local quadratic model within
/// the scaled radius `Δ`. One implementation per method (dogleg, Steihaug-CG).
pub trait SubproblemStep {
    /// Solve the subproblem for trust radius `radius` (in scaled units).
    fn solve(&self, sub: &Subproblem<'_>, radius: f64) -> StepResult;
}
