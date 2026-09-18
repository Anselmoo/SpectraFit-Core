use crate::Model;

/// Moffat peak: `A / (((x − c)/σ)² + 1)^β`.
///
/// Parameters (in order): `[amplitude, center, sigma, beta]`. `amplitude` is the peak
/// height at `x == center`; `beta` controls the wings (β→∞ Gaussian-like, small β heavier
/// tails). numpy oracle identical: `A / (((x-c)/σ)**2 + 1)**β`.
pub struct Moffat;

impl Model for Moffat {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, c, sigma, beta) = (params[0], params[1], params[2], params[3]);
        let z = (x[0] - c) / sigma;
        a / (z * z + 1.0).powf(beta)
    }

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
            "beta".into(),
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn eval_at_center_equals_amplitude() {
        assert_relative_eq!(
            Moffat.eval(&[1.5], &[3.0, 1.5, 0.8, 2.0]),
            3.0,
            epsilon = 1e-12
        );
    }

    #[test]
    fn param_names_and_jacobian() {
        assert_eq!(
            Moffat
                .param_names()
                .iter()
                .map(|c| c.as_ref())
                .collect::<Vec<_>>(),
            &["amplitude", "center", "sigma", "beta"]
        );
        let j = Moffat.jacobian(&[1.5], &[3.0, 1.5, 0.8, 2.0]);
        assert_eq!(j.len(), 4);
        assert_relative_eq!(j[0], 1.0, epsilon = 1e-6); // ∂/∂A at center = 1
    }
}
