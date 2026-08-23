use crate::Model;

/// Cauchy refractive-index dispersion: `n(x) = a + b/x² + c/x⁴`.
///
/// Parameters (in order): `[a, b, c]`
///
/// - `a` is the high-frequency (constant) refractive-index offset.
/// - `b` is the first dispersion coefficient (units of x²).
/// - `c` is the second dispersion coefficient (units of x⁴).
///
/// The independent variable `x` is a wavelength and must be `> 0`; the kernel is smooth
/// and analytic there. At `x == 0` the `1/x²` / `1/x⁴` terms are undefined, so the kernel
/// returns `0.0` (matching the numpy oracle `np.where(x > 0, a + b/x² + c/x⁴, 0)`), keeping
/// numpy↔Rust parity exact. The analytical Jacobian is `[1, 1/x², 1/x⁴]`.
pub struct CauchyDispersion;

impl Model for CauchyDispersion {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, b, c) = (params[0], params[1], params[2]);
        if x[0] > 0.0 {
            let x2 = x[0] * x[0];
            let x4 = x2 * x2;
            a + b / x2 + c / x4
        } else {
            0.0
        }
    }

    /// Analytical Jacobian: `∂n/∂a = 1`, `∂n/∂b = 1/x²`, `∂n/∂c = 1/x⁴` (for `x > 0`);
    /// all zero at `x ≤ 0` where the kernel is clamped to `0`.
    fn jacobian(&self, x: &[f64], _params: &[f64]) -> Vec<f64> {
        if x[0] > 0.0 {
            let x2 = x[0] * x[0];
            let x4 = x2 * x2;
            vec![1.0, 1.0 / x2, 1.0 / x4]
        } else {
            vec![0.0, 0.0, 0.0]
        }
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["a".into(), "b".into(), "c".into()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn dispersion_value() {
        // a + b/x² + c/x⁴ at x = 2: 1.5 + 0.4/4 + 0.2/16 = 1.5 + 0.1 + 0.0125.
        let m = CauchyDispersion;
        assert_relative_eq!(
            m.eval(&[2.0], &[1.5, 0.4, 0.2]),
            1.5 + 0.1 + 0.0125,
            epsilon = 1e-12
        );
    }

    #[test]
    fn non_positive_x_is_zero() {
        let m = CauchyDispersion;
        assert_eq!(m.eval(&[0.0], &[1.5, 0.4, 0.2]), 0.0);
        assert_eq!(m.eval(&[-1.0], &[1.5, 0.4, 0.2]), 0.0);
    }

    #[test]
    fn analytical_jacobian_matches_closed_form() {
        let m = CauchyDispersion;
        let j = m.jacobian(&[2.0], &[1.5, 0.4, 0.2]);
        assert_eq!(j.len(), 3);
        assert_relative_eq!(j[0], 1.0, epsilon = 1e-12);
        assert_relative_eq!(j[1], 1.0 / 4.0, epsilon = 1e-12);
        assert_relative_eq!(j[2], 1.0 / 16.0, epsilon = 1e-12);
    }

    #[test]
    fn param_names_are_canonical() {
        assert_eq!(
            CauchyDispersion
                .param_names()
                .iter()
                .map(|c| c.as_ref())
                .collect::<Vec<_>>(),
            &["a", "b", "c"]
        );
    }

    #[test]
    fn jacobian_matches_central_difference_across_regimes() {
        // Central difference is O(h^2); the old forward-difference pattern
        // (see fano.rs::jacobian_finite_diff_check) was O(h), i.e. its own
        // truncation error was the size of the 1e-4 tolerance it asserted
        // against.
        let m = CauchyDispersion;
        let param_sets = [
            [1.5, 0.4, 0.2],    // nominal
            [1e-3, 1e-3, 1e-3], // small coefficients
            [5.0, -2.0, 8.0],   // large / negative coefficients
        ];
        for p in param_sets {
            // x <= 0 clamps eval (and jacobian) to 0.0 regardless of params, so
            // the central difference agrees trivially there (0 == 0), proving
            // the clamp itself doesn't leak a spurious derivative. x = 0.3 is
            // the smallest positive point kept: below that, c/x^4 for the
            // large-coefficient regime dwarfs the ~1e-6-scaled perturbation of
            // `a`, and the resulting catastrophic cancellation in the finite
            // difference (not the analytic Jacobian, which is exactly
            // param-independent here) pushes its own error above 1e-7.
            for &x in &[0.3_f64, 0.5, 1.0, 2.0, 7.0, 0.0, -1.0] {
                let j = m.jacobian(&[x], &p);
                for i in 0..p.len() {
                    let h = 1e-6 * p[i].abs().max(1.0);
                    let (mut a, mut b) = (p, p);
                    a[i] += h;
                    b[i] -= h;
                    let fd = (m.eval(&[x], &a) - m.eval(&[x], &b)) / (2.0 * h);
                    assert_relative_eq!(j[i], fd, epsilon = 1e-7, max_relative = 1e-6);
                }
            }
        }
    }
}
