//! Generic trust-region outcome types, shared by every method built on this
//! framework (Levenberg–Marquardt, dogleg, Newton-CG/Steihaug, …).
//!
//! A method's driver constructs a [`Report`] with a [`Termination`] reason; the
//! framework owns these so consumers speak one vocabulary regardless of which
//! method ran.

/// Why the solve stopped.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Termination {
    /// `‖Jᵀr‖_∞ ≤ gtol` — first-order optimality.
    Gtol,
    /// Relative cost decrease `≤ ftol`.
    Ftol,
    /// Relative step size `≤ xtol`.
    Xtol,
    /// Residuals are (numerically) zero.
    ResidualsZero,
    /// Exhausted the residual-evaluation budget.
    MaxEval,
    /// The trust-region control diverged without an accepted step.
    NoImprovement,
    /// A residual/Jacobian evaluation failed.
    NumericalError,
}

impl Termination {
    /// Whether the run reached a convergence criterion (vs. a budget/error stop).
    pub fn was_successful(&self) -> bool {
        matches!(
            self,
            Termination::Gtol | Termination::Ftol | Termination::Xtol | Termination::ResidualsZero
        )
    }
}

/// Outcome of a solve. The optimised parameters live in the `problem` (read via
/// [`TrustRegionProblem::params`](crate::TrustRegionProblem::params)); this only
/// carries diagnostics.
///
/// Not `Copy`: it carries the per-iteration convergence trajectory (`cost_history`
/// / `gradient_norm_history`) as owned `Vec`s. These are observability only — they
/// do not affect the optimisation and are recorded once per accepted point plus the
/// terminal point.
#[derive(Debug, Clone)]
pub struct Report {
    /// Why the loop stopped.
    pub termination: Termination,
    /// Accepted iterations.
    pub n_iter: usize,
    /// Residual evaluations.
    pub n_residual_evals: usize,
    /// Jacobian evaluations.
    pub n_jacobian_evals: usize,
    /// Final `½‖r‖²`.
    pub cost: f64,
    /// `‖Jᵀr‖_∞` **at the most recent point where the Jacobian was evaluated**
    /// — the start of the final outer iteration.
    ///
    /// This is the definition for every termination reason, and it is what
    /// makes the number comparable across them. It is deliberately *not*
    /// "‖Jᵀr‖_∞ at the returned parameters": on an `Ftol`/`Xtol`/`MaxEval` stop
    /// the loop exits after accepting a step, and no Jacobian has been
    /// evaluated at that new point, so reporting a gradient there would mean
    /// either paying for an extra Jacobian evaluation or pairing the stale `J`
    /// with the new `r` — a product that is the gradient at neither point. The
    /// drivers therefore report the last genuinely-evaluated gradient instead.
    /// On a `Gtol` stop the two coincide, since that test fires before any
    /// step is taken.
    pub gradient_norm: f64,
    /// `½‖r‖²` at each accepted point (index 0 = initial), ending at the terminal
    /// cost. Empty only for an immediate pre-iteration numerical failure.
    pub cost_history: Vec<f64>,
    /// `‖Jᵀr‖_∞` recorded alongside each `cost_history` entry, under the same
    /// "at the most recent Jacobian evaluation" definition as
    /// [`gradient_norm`](Self::gradient_norm) — so the terminal entry repeats
    /// the previous iteration's gradient when the loop stopped after an
    /// accepted step.
    pub gradient_norm_history: Vec<f64>,
    /// The free-parameter vector `θ` at each accepted point, recorded alongside
    /// each `cost_history` entry (same length and ordering). This is the raw
    /// material for the convergence-to-truth metric `dₖ = ‖(θₖ − θ_true)/s‖₂`
    /// on synthetic cases — observability only, it does not affect the solve.
    /// Empty for solvers that do not track it (only the faer LM driver records
    /// it today; the trust-region / dogleg / newton-cg drivers leave it empty).
    pub params_history: Vec<Vec<f64>>,
}
