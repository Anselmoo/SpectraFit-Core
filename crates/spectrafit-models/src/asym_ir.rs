use crate::Model;

/// Asymmetric IR band: a Gaussian multiplied by a logistic sigmoid.
///
/// `f(x) = A·exp(−(x − c)²/(2σ²)) · 1/(1 + exp(−k·(x − c)))`.
///
/// Parameters (in order): `[amplitude, center, sigma, k]`. `amplitude` is the Gaussian scale
/// (peak ≈ A/2 at center because of the sigmoid); `k` is the asymmetry. The sigmoid exponent
/// is clamped to ≤ 50 to avoid overflow — the numpy oracle clamps identically
/// (`np.clip(-k*(x-c), None, 50.0)`), so numpy↔Rust parity is exact.
pub struct AsymIr;

impl Model for AsymIr {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, c, sigma, k) = (params[0], params[1], params[2], params[3]);
        let dx = x[0] - c;
        let g = a * (-(dx * dx) / (2.0 * sigma * sigma)).exp();
        let arg = (-(k * dx)).min(50.0);
        g / (1.0 + arg.exp())
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
            "k".into(),
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn eval_at_center_is_half_amplitude() {
        // At x == center, dx = 0 ⇒ Gaussian = A, sigmoid = 1/(1+1) = 0.5.
        let v = AsymIr.eval(&[1.5], &[4.0, 1.5, 0.8, 1.0]);
        assert_relative_eq!(v, 2.0, epsilon = 1e-12);
    }

    #[test]
    fn param_names_and_jacobian() {
        assert_eq!(
            AsymIr
                .param_names()
                .iter()
                .map(|c| c.as_ref())
                .collect::<Vec<_>>(),
            &["amplitude", "center", "sigma", "k"]
        );
        assert_eq!(AsymIr.jacobian(&[1.0], &[4.0, 1.5, 0.8, 1.0]).len(), 4);
    }

    // ----- Limiting-case asymptotic (ground-truth verification, Cycle 4) -----
    //
    // At k = 0 the sigmoid collapses to a constant 1/2 (1/(1+exp(0))):
    //
    //     AsymIr(A, c, σ, k=0)  ≡  Gaussian(A/2, c, σ)   at every x
    //
    // Catches: missing/wrong constant factor in the no-asymmetry case,
    // sigmoid-evaluation bugs that break the k=0 symmetric reduction.

    #[test]
    fn k_zero_equals_half_gaussian() {
        use crate::gaussian::Gaussian;
        let asym = AsymIr;
        let gauss = Gaussian;
        let a = 5.0_f64;
        let c = 0.3_f64;
        let sigma = 0.8_f64;
        let p_asym = [a, c, sigma, 0.0]; // k = 0 → symmetric
        let p_gauss = [a / 2.0, c, sigma];
        for &xi in &[-2.0_f64, -0.5, c, 0.5, 2.0] {
            assert_relative_eq!(
                asym.eval(&[xi], &p_asym),
                gauss.eval(&[xi], &p_gauss),
                epsilon = 1e-12
            );
        }
    }
}
