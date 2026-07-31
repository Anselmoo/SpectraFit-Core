use crate::Model;

/// Pearson VII peak: `A / [1 + ((x − c)/σ)² · (2^{1/m} − 1)]^m`.
///
/// Parameters (in order): `[amplitude, center, sigma, m]`
///
/// - `amplitude` is the peak height attained at `x == center`.
/// - `center` is the peak location.
/// - `sigma` is the half-width at half-maximum (the `2^{1/m}−1` factor normalizes
///   so `σ` is the HWHM for any shape exponent).
/// - `m` is the shape exponent: `m → 1` gives a Lorentzian, `m → ∞` a Gaussian.
///
/// The numpy benchmark oracle is identical —
/// `A / (1 + ((x−c)/σ)² · (2**(1/m) − 1))**m` — so numpy↔Rust parity is exact.
pub struct Pearson7;

impl Model for Pearson7 {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, c, sigma, m) = (params[0], params[1], params[2], params[3]);
        let z = (x[0] - c) / sigma;
        let base = 1.0 + z * z * (2.0_f64.powf(1.0 / m) - 1.0);
        a / base.powf(m)
    }

    /// Central finite-difference Jacobian (the `2^{1/m}` term makes the analytic
    /// `m`-derivative awkward, so a numerical Jacobian is used, matching `log_normal`).
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
        vec![
            "amplitude".into(),
            "center".into(),
            "sigma".into(),
            "m".into(),
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn eval_at_center_equals_amplitude() {
        // At x == center, z = 0 ⇒ base = 1, so value == amplitude for any m.
        let m = Pearson7;
        assert_relative_eq!(m.eval(&[1.5], &[3.0, 1.5, 0.8, 2.0]), 3.0, epsilon = 1e-12);
    }

    #[test]
    fn sigma_is_hwhm() {
        // At |x − c| == sigma the normalization gives exactly half-maximum.
        let m = Pearson7;
        let v = m.eval(&[2.3], &[4.0, 1.5, 0.8, 2.5]); // x = c + sigma
        assert_relative_eq!(v, 2.0, epsilon = 1e-12); // A/2
    }

    #[test]
    fn param_names_are_canonical() {
        assert_eq!(
            Pearson7
                .param_names()
                .iter()
                .map(|c| c.as_ref())
                .collect::<Vec<_>>(),
            &["amplitude", "center", "sigma", "m"]
        );
    }

    #[test]
    fn jacobian_shape_and_amplitude() {
        let j = Pearson7.jacobian(&[1.5], &[3.0, 1.5, 0.8, 2.0]);
        assert_eq!(j.len(), 4);
        // ∂/∂amplitude at x == center is 1/base = 1.
        assert_relative_eq!(j[0], 1.0, epsilon = 1e-6);
        // ∂/∂center at the peak is 0 (stationary).
        assert_relative_eq!(j[1], 0.0, epsilon = 1e-6);
    }
}
