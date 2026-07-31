use crate::Model;

/// Log-normal peak: `A · exp(−(ln(x/c))² / (2σ²))` for `x > 0`, else `0`.
///
/// Parameters (in order): `[amplitude, center, sigma]`
///
/// - `amplitude` is the peak height attained at `x == center`.
/// - `center > 0` is the peak location (log-space mode).
/// - `sigma` is the log-space width.
///
/// The kernel is defined only for `x > 0`; at `x <= 0` it returns `0.0` (the
/// log argument is undefined there). The numpy benchmark formula is identical —
/// `np.where(x > 0, A·exp(−(ln(x/c))²/(2σ²)), 0)` — so numpy↔Rust parity is exact.
pub struct LogNormal;

impl Model for LogNormal {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, c, sigma) = (params[0], params[1], params[2]);
        if x[0] > 0.0 {
            let l = (x[0] / c).ln();
            let z = -(l * l) / (2.0 * sigma * sigma);
            a * z.exp()
        } else {
            0.0
        }
    }

    /// Central finite-difference Jacobian.
    ///
    /// The closed form has a logarithmic singularity at `x == 0`, so a numerical
    /// (central-difference) Jacobian is used rather than an analytical one. Step
    /// `h = 1e-7 · |p[i]|.max(1e-7)` (relative + absolute floor), matching the
    /// trait's default magnitude.
    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let mut p = params.to_vec();
        (0..params.len())
            .map(|i| {
                let h = 1e-7_f64 * params[i].abs().max(1e-7);
                p[i] = params[i] + h;
                let f_plus = self.eval(x, &p);
                p[i] = params[i] - h;
                let f_minus = self.eval(x, &p);
                p[i] = params[i];
                (f_plus - f_minus) / (2.0 * h)
            })
            .collect()
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["amplitude".into(), "center".into(), "sigma".into()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn eval_at_center_equals_amplitude() {
        // At x == center, ln(x/c) = 0 ⇒ exp(0) = 1, so value == amplitude.
        let m = LogNormal;
        let v = m.eval(&[2.5], &[3.0, 2.5, 0.4]);
        assert_relative_eq!(v, 3.0, epsilon = 1e-12);
    }

    #[test]
    fn eval_non_positive_is_zero() {
        // x <= 0 (where ln is undefined) returns exactly 0.0.
        let m = LogNormal;
        assert_eq!(m.eval(&[0.0], &[1.0, 2.0, 0.5]), 0.0);
        assert_eq!(m.eval(&[-1.0], &[1.0, 2.0, 0.5]), 0.0);
    }

    #[test]
    fn param_names_are_canonical() {
        assert_eq!(
            LogNormal
                .param_names()
                .iter()
                .map(|c| c.as_ref())
                .collect::<Vec<_>>(),
            &["amplitude", "center", "sigma"]
        );
    }

    #[test]
    fn jacobian_shape() {
        let j = LogNormal.jacobian(&[1.5], &[2.0, 2.0, 0.6]);
        assert_eq!(j.len(), 3);
    }

    #[test]
    fn jacobian_amplitude_numerical_check() {
        // ∂/∂amplitude at x == center is exp(0) = 1.
        let m = LogNormal;
        let j = m.jacobian(&[2.0], &[3.0, 2.0, 0.5]);
        assert_relative_eq!(j[0], 1.0, epsilon = 1e-6);
    }

    #[test]
    fn jacobian_center_zero_at_peak() {
        // ∂/∂center at x == center is 0 (peak is stationary in log space).
        let m = LogNormal;
        let j = m.jacobian(&[2.0], &[3.0, 2.0, 0.5]);
        assert_relative_eq!(j[1], 0.0, epsilon = 1e-6);
    }
}
