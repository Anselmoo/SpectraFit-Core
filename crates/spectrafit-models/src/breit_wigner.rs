use crate::Model;

/// Breit-Wigner-Fano (BWF) resonance: `A·(q·g + (x − c))² / (g² + (x − c)²)`, `g = σ/2`.
///
/// Parameters (in order): `[amplitude, center, sigma, q]`. `amplitude` is a scale factor
/// (peak ≠ A — the asymmetric Fano family, like `fano`); `q` is the asymmetry. numpy oracle
/// identical: `g = σ/2; A*(q*g + (x-c))**2 / (g*g + (x-c)**2)`.
pub struct BreitWigner;

impl Model for BreitWigner {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, c, sigma, q) = (params[0], params[1], params[2], params[3]);
        let g = sigma / 2.0;
        let dx = x[0] - c;
        a * (q * g + dx) * (q * g + dx) / (g * g + dx * dx)
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
        vec!["amplitude".into(), "center".into(), "sigma".into(), "q".into()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn eval_at_center_is_amp_times_q_squared() {
        // At x == center, dx = 0 ⇒ A·(q·g)² / g² = A·q².
        let v = BreitWigner.eval(&[1.5], &[2.0, 1.5, 1.0, 1.7]);
        assert_relative_eq!(v, 2.0 * 1.7 * 1.7, epsilon = 1e-12);
    }

    #[test]
    fn param_names_and_jacobian() {
        assert_eq!(
            BreitWigner.param_names().iter().map(|c| c.as_ref()).collect::<Vec<_>>(),
            &["amplitude", "center", "sigma", "q"]
        );
        assert_eq!(BreitWigner.jacobian(&[1.0], &[2.0, 1.5, 1.0, 1.7]).len(), 4);
    }
}
