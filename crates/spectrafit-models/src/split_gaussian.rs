use crate::Model;

/// Split (asymmetric) Gaussian: a Gaussian with a different width on each side of
/// the center. Covers both "asymmetric split-σ Gaussian" and "bi-Gaussian".
///
/// `f(x) = A · exp(−(x−c)² / (2σ²))` with `σ = σ_L` for `x < c`, else `σ_R`.
///
/// Parameters (in order): `[amplitude, center, sigma_l, sigma_r]`
///
/// - `amplitude` is the peak height at `x == center` (both branches equal `A` there,
///   so the curve is continuous).
/// - `center` is the peak location.
/// - `sigma_l` / `sigma_r` are the left/right Gaussian widths.
///
/// The numpy oracle is identical —
/// `np.where(x < c, A·exp(−½((x−c)/σ_L)²), A·exp(−½((x−c)/σ_R)²))` — so parity is exact.
pub struct SplitGaussian;

impl Model for SplitGaussian {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, c, sl, sr) = (params[0], params[1], params[2], params[3]);
        let dx = x[0] - c;
        let sigma = if x[0] < c { sl } else { sr };
        a * (-(dx * dx) / (2.0 * sigma * sigma)).exp()
    }

    /// Central finite-difference Jacobian (the side-selecting branch makes the
    /// analytic derivative piecewise; numerical is simpler and matches `log_normal`).
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
        vec!["amplitude".into(), "center".into(), "sigma_l".into(), "sigma_r".into()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn eval_at_center_equals_amplitude() {
        let m = SplitGaussian;
        assert_relative_eq!(m.eval(&[1.5], &[3.0, 1.5, 0.6, 1.2]), 3.0, epsilon = 1e-12);
    }

    #[test]
    fn left_and_right_use_their_own_width() {
        // At ±σ from center the value is A·exp(−0.5) on each side, using its own σ.
        let m = SplitGaussian;
        let p = [4.0, 0.0, 0.6, 1.2];
        assert_relative_eq!(m.eval(&[-0.6], &p), 4.0 * (-0.5_f64).exp(), epsilon = 1e-12);
        assert_relative_eq!(m.eval(&[1.2], &p), 4.0 * (-0.5_f64).exp(), epsilon = 1e-12);
    }

    #[test]
    fn param_names_are_canonical() {
        assert_eq!(
            SplitGaussian.param_names().iter().map(|c| c.as_ref()).collect::<Vec<_>>(),
            &["amplitude", "center", "sigma_l", "sigma_r"]
        );
    }

    #[test]
    fn jacobian_shape() {
        let j = SplitGaussian.jacobian(&[0.5], &[3.0, 0.0, 0.6, 1.2]);
        assert_eq!(j.len(), 4);
        // x = 0.5 > center ⇒ right width 1.2; ∂/∂A = exp(−0.5²/(2·1.2²)).
        assert_relative_eq!(j[0], (-0.25_f64 / (2.0 * 1.44)).exp(), epsilon = 1e-6);
    }

    // ----- Limiting-case asymptotic (ground-truth verification, Cycle 3) -----
    //
    // SplitGaussian reduces to a plain symmetric Gaussian when σ_l == σ_r:
    //
    //     A · exp(−(x−c)²/(2σ²))   with σ_l = σ_r = σ
    //
    // Both branches give the same value at any x, so the curve is identical to
    // a plain Gaussian everywhere — pin this across left/right/center points.

    #[test]
    fn symmetric_widths_equal_plain_gaussian() {
        use crate::gaussian::Gaussian;
        let split = SplitGaussian;
        let gauss = Gaussian;
        let sigma = 0.8_f64;
        let a = 3.5_f64;
        let c = 0.4_f64;
        let p_split = [a, c, sigma, sigma]; // σ_l = σ_r
        let p_gauss = [a, c, sigma];
        for &xi in &[-2.0_f64, -0.6, c, 0.6, 2.0] {
            assert_relative_eq!(
                split.eval(&[xi], &p_split),
                gauss.eval(&[xi], &p_gauss),
                epsilon = 1e-12
            );
        }
    }
}
