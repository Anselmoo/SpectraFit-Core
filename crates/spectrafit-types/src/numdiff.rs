//! Finite-difference step sizes, shared by every numerical Jacobian in the
//! workspace.
//!
//! The solver's forward-difference Jacobian for tied graphs
//! (`spectrafit-solver`, `LmProblem::fd_weighted_jacobian_rowmajor`) and the
//! kernels in `spectrafit-models` that differentiate numerically both take
//! their step from [`fd_step`], so the two paths cannot drift apart again
//! (GitLab #51, #92).
//!
//! # The rule
//!
//! `h = η · max(|θ|, typ)`, with `η = √ε` for a forward difference and
//! `η = ε^{1/3}` for a central difference (`ε = f64::EPSILON`), and `typ` the
//! parameter's typical magnitude (`1` when nothing better is known). This is
//! the step of Dennis and Schnabel, *Numerical Methods for Unconstrained
//! Optimization and Nonlinear Equations* (SIAM Classics, 1996), Ch. 5:
//! §5.4 and Algorithm A5.4.1 (forward-difference Jacobian,
//! `√η · max(|x_j|, typx_j)`), and Algorithm A5.6.4 (central-difference
//! gradient, `η^{1/3} · max(|x_j|, typx_j)`). The exponents balance truncation
//! against rounding: `O(h)` against `O(ε/h)` gives `√ε` for a forward
//! difference, `O(h²)` against `O(ε/h)` gives `ε^{1/3}` for a central one
//! (Nocedal and Wright, *Numerical Optimization*, 2nd ed., 2006, §8.1).
//!
//! The floor `typ` is the point of the rule: a purely relative step
//! (`h ∝ |θ|`, or MINPACK `fdjac2`, which floors only at exactly `θ = 0`)
//! shrinks to nothing as `θ → 0`, and the difference quotient is then
//! dominated by rounding in the function values. The previous rule here,
//! `1e-7 · max(|θ|, 1e-7)`, gave `h = 1e-14` at `θ = 0` and a Jacobian column
//! error of order `1e-2`.

/// Which finite-difference formula the step is for.
///
/// The optimal step differs between the two: see the module documentation.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FdScheme {
    /// `(f(θ + h) − f(θ)) / h`, truncation error `O(h)`.
    Forward,
    /// `(f(θ + h) − f(θ − h)) / 2h`, truncation error `O(h²)`.
    Central,
}

/// Finite-difference step for a parameter at `theta` with typical magnitude
/// `typical`: `η · max(|θ|, typical)` (Dennis and Schnabel 1996, Ch. 5,
/// Algorithms A5.4.1 and A5.6.4).
///
/// `η = √ε ≈ 1.49e-8` for [`FdScheme::Forward`] and `η = ε^{1/3} ≈ 6.06e-6`
/// for [`FdScheme::Central`]. A `typical` that is not finite and positive is
/// replaced by `1.0`. The returned step is non-negative; the caller chooses the
/// direction (e.g. a backward step at an upper bound).
///
/// Callers should divide by the *representable* step, `(θ + h) − θ`, rather
/// than by `h` itself (Dennis and Schnabel, A5.4.1), so that the rounding of
/// `θ + h` does not enter the quotient.
///
/// # Examples
///
/// ```
/// use spectrafit_types::{fd_step, FdScheme};
///
/// // The step does not collapse at zero: it is floored at η · typical.
/// let h0 = fd_step(0.0, 1.0, FdScheme::Forward);
/// assert_eq!(h0, f64::EPSILON.sqrt());
///
/// // Away from the floor it is relative to |θ|.
/// let h = fd_step(-1e6, 1.0, FdScheme::Central);
/// assert_eq!(h, f64::EPSILON.cbrt() * 1e6);
///
/// // A parameter's typical scale raises the floor.
/// assert_eq!(fd_step(0.0, 10.0, FdScheme::Forward), 10.0 * f64::EPSILON.sqrt());
/// ```
#[inline]
#[must_use]
pub fn fd_step(theta: f64, typical: f64, scheme: FdScheme) -> f64 {
    let typ = if typical.is_finite() && typical > 0.0 {
        typical
    } else {
        1.0
    };
    let eta = match scheme {
        FdScheme::Forward => f64::EPSILON.sqrt(),
        FdScheme::Central => f64::EPSILON.cbrt(),
    };
    eta * theta.abs().max(typ)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn forward_step_is_sqrt_eps_times_max_abs_theta_and_typical() {
        let eta = f64::EPSILON.sqrt();
        assert_eq!(fd_step(0.0, 1.0, FdScheme::Forward), eta);
        assert_eq!(fd_step(1e-12, 1.0, FdScheme::Forward), eta);
        assert_eq!(fd_step(-1e-12, 1.0, FdScheme::Forward), eta);
        assert_eq!(fd_step(-3.0, 1.0, FdScheme::Forward), 3.0 * eta);
        assert_eq!(fd_step(1e6, 1.0, FdScheme::Forward), 1e6 * eta);
        assert_eq!(fd_step(0.5, 2.0, FdScheme::Forward), 2.0 * eta);
    }

    #[test]
    fn central_step_is_cbrt_eps_times_max_abs_theta_and_typical() {
        let eta = f64::EPSILON.cbrt();
        assert_eq!(fd_step(0.0, 1.0, FdScheme::Central), eta);
        assert_eq!(fd_step(-2.5, 1.0, FdScheme::Central), 2.5 * eta);
        assert_eq!(fd_step(0.0, 0.25, FdScheme::Central), 0.25 * eta);
        // Pin the constants against the textbook values, not just against the
        // expression that computes them.
        assert!((fd_step(0.0, 1.0, FdScheme::Forward) - 1.490_116_119_384_765_6e-8).abs() < 1e-22);
        assert!((fd_step(0.0, 1.0, FdScheme::Central) - 6.055_454_452_393_343e-6).abs() < 1e-20);
    }

    #[test]
    fn invalid_typical_falls_back_to_one() {
        let eta = f64::EPSILON.sqrt();
        for typ in [0.0, -1.0, f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            assert_eq!(fd_step(0.0, typ, FdScheme::Forward), eta, "typical = {typ}");
        }
    }

    #[test]
    fn step_never_collapses_near_zero() {
        // The defect of #51/#92: h ∝ |θ| → 0. The floor keeps h ≥ η · typical.
        for theta in [0.0, 1e-300, -1e-300, 1e-12, -1e-12, 1e-8] {
            assert!(fd_step(theta, 1.0, FdScheme::Forward) >= f64::EPSILON.sqrt());
            assert!(fd_step(theta, 1.0, FdScheme::Central) >= f64::EPSILON.cbrt());
        }
    }
}
