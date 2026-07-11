//! 2-D Gaussian kernel scaffold (TDD U2).
//!
//! This is **scaffolding** for 2-D / N-D fitting.  The `eval` and analytical
//! Jacobian bodies are implemented for the axis-aligned (no rotation) MVP so
//! the kernel compiles and can be exercised by `#[ignore]` round-trip /
//! finite-difference tests.  Rotation (`theta`) is intentionally omitted from
//! the MVP — see the parameter note below.

use crate::Model;

/// Axis-aligned 2-D Gaussian peak.
///
/// Formula (no rotation):
///
/// ```text
/// f(x, y) = A · exp( −(x − cₓ)² / (2·σₓ²) − (y − c_y)² / (2·σ_y²) )
/// ```
///
/// Parameters (in order):
/// `[amplitude, center_x, center_y, sigma_x, sigma_y]`
///
/// - `amplitude` — peak value at `(center_x, center_y)` (not area).
/// - `center_x`, `center_y` — peak location.
/// - `sigma_x`, `sigma_y` — standard deviations along each axis
///   (FWHM ≈ 2.355·σ).
///
/// MVP note: a `theta` rotation parameter is intentionally **omitted** to keep
/// the first 2-D kernel minimal; rotated Gaussians are a follow-up unit.
pub struct Gaussian2D;

impl Model for Gaussian2D {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, cx, cy, sx, sy) = (params[0], params[1], params[2], params[3], params[4]);
        let dx = x[0] - cx;
        let dy = x[1] - cy;
        let z = -(dx * dx) / (2.0 * sx * sx) - (dy * dy) / (2.0 * sy * sy);
        a * z.exp()
    }

    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let mut out = vec![0.0_f64; self.param_names().len()];
        self.jacobian_into(x, params, &mut out);
        out
    }

    #[inline]
    fn jacobian_into(&self, x: &[f64], params: &[f64], out: &mut [f64]) {
        let (a, cx, cy, sx, sy) = (params[0], params[1], params[2], params[3], params[4]);
        let dx = x[0] - cx;
        let dy = x[1] - cy;
        let sx2 = sx * sx;
        let sy2 = sy * sy;
        let g = (-(dx * dx) / (2.0 * sx2) - (dy * dy) / (2.0 * sy2)).exp();

        // ∂/∂amplitude = g
        out[0] = g;
        // ∂/∂center_x  = A · g · (x − cₓ) / σₓ²
        out[1] = a * g * dx / sx2;
        // ∂/∂center_y  = A · g · (y − c_y) / σ_y²
        out[2] = a * g * dy / sy2;
        // ∂/∂sigma_x   = A · g · (x − cₓ)² / σₓ³
        out[3] = a * g * dx * dx / (sx2 * sx);
        // ∂/∂sigma_y   = A · g · (y − c_y)² / σ_y³
        out[4] = a * g * dy * dy / (sy2 * sy);
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["amplitude".into(), "center_x".into(), "center_y".into(), "sigma_x".into(), "sigma_y".into()]
    }

    fn n_dims(&self) -> usize {
        2
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn n_dims_is_two() {
        assert_eq!(Gaussian2D.n_dims(), 2);
    }

    #[test]
    fn param_names_match_convention() {
        assert_eq!(
            Gaussian2D.param_names().iter().map(|c| c.as_ref()).collect::<Vec<_>>(),
            &["amplitude", "center_x", "center_y", "sigma_x", "sigma_y"]
        );
    }

    #[test]
    fn eval_at_center_equals_amplitude() {
        // At (cx, cy) the 2-D Gaussian equals amplitude.
        let v = Gaussian2D.eval(&[0.5, -1.0], &[3.0, 0.5, -1.0, 1.0, 2.0]);
        assert_relative_eq!(v, 3.0, epsilon = 1e-12);
    }

    #[test]
    fn jacobian_into_matches_finite_difference() {
        let m = Gaussian2D;
        let x = [0.7f64, -0.3f64]; // off-center for non-trivial derivatives
        let params = [2.0f64, 0.5, -1.0, 1.0, 1.5];
        let h = 1e-6;
        let mut analytic = vec![0.0_f64; params.len()];
        m.jacobian_into(&x, &params, &mut analytic);
        let f0 = m.eval(&x, &params);
        for i in 0..params.len() {
            let mut p = params;
            p[i] += h;
            let fd = (m.eval(&x, &p) - f0) / h;
            assert_relative_eq!(analytic[i], fd, epsilon = 1e-5, max_relative = 1e-5);
        }
    }
}
