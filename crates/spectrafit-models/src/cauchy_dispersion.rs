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
}
