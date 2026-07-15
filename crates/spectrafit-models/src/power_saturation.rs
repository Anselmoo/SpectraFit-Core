use crate::Model;

/// Power-law saturation: `amplitude · (1 − (1 + rate·x/2)^(−2))`
///
/// Parameters (in order): `[amplitude, rate]`
///
/// This is the Misra1b NIST StRD model.  It describes a growth process
/// approaching a saturation level `amplitude` with a power-law rather than
/// exponential approach.  For `rate > 0` and `x ≥ 0` the function rises
/// monotonically from `0` to `amplitude`.
///
/// Analytic Jacobian:
///   Let `u = 1 + rate·x/2`.
///   - ∂y/∂amplitude = 1 − u^(−2)
///   - ∂y/∂rate      = amplitude · x · u^(−3)
///
/// Note: `amplitude` is the asymptotic saturation level, NOT a peak-at-center
/// value as in the peak-model convention documented in `MODELS.md`.
pub struct PowerSaturation;

impl Model for PowerSaturation {
    fn eval(&self, x: &[f64], p: &[f64]) -> f64 {
        let xi = x[0];
        let u = 1.0 + p[1] * xi / 2.0;
        p[0] * (1.0 - u.powi(-2))
    }

    fn jacobian_into(&self, x: &[f64], p: &[f64], out: &mut [f64]) {
        let xi = x[0];
        let u = 1.0 + p[1] * xi / 2.0;
        let u_neg2 = u.powi(-2);
        let u_neg3 = u.powi(-3);
        out[0] = 1.0 - u_neg2; // ∂y/∂amplitude = 1 − (1+rate·x/2)^−2
        out[1] = p[0] * xi * u_neg3; // ∂y/∂rate      = amplitude·x·(1+rate·x/2)^−3
    }

    fn jacobian(&self, x: &[f64], p: &[f64]) -> Vec<f64> {
        let xi = x[0];
        let u = 1.0 + p[1] * xi / 2.0;
        let u_neg2 = u.powi(-2);
        let u_neg3 = u.powi(-3);
        vec![
            1.0 - u_neg2,       // ∂y/∂amplitude
            p[0] * xi * u_neg3, // ∂y/∂rate
        ]
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["amplitude".into(), "rate".into()]
    }

    fn eval_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        debug_assert_eq!(out.len(), xs.len());
        let (amplitude, rate) = (params[0], params[1]);
        for (slot, &xi) in out.iter_mut().zip(xs.iter()) {
            let u = 1.0 + rate * xi / 2.0;
            *slot = amplitude * (1.0 - u.powi(-2));
        }
    }

    fn jac_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        debug_assert_eq!(out.len(), xs.len() * 2);
        let (amplitude, rate) = (params[0], params[1]);
        for (i, &xi) in xs.iter().enumerate() {
            let u = 1.0 + rate * xi / 2.0;
            let u_neg2 = u.powi(-2);
            let u_neg3 = u.powi(-3);
            out[i * 2] = 1.0 - u_neg2; // ∂y/∂amplitude
            out[i * 2 + 1] = amplitude * xi * u_neg3; // ∂y/∂rate
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    fn model() -> PowerSaturation {
        PowerSaturation
    }

    // amplitude=10, rate=0.5, x=0: 10*(1-(1+0)^-2) = 10*(1-1) = 0
    #[test]
    fn eval_at_zero() {
        let v = model().eval(&[0.0], &[10.0, 0.5]);
        assert_relative_eq!(v, 0.0, epsilon = 1e-12);
    }

    // amplitude=10, rate=0, x=5: u=1, 10*(1-1^-2) = 0  (rate=0 → no growth)
    #[test]
    fn eval_zero_rate() {
        let v = model().eval(&[5.0], &[10.0, 0.0]);
        assert_relative_eq!(v, 0.0, epsilon = 1e-12);
    }

    // At very large x*rate the function → amplitude (u → ∞, u^-2 → 0)
    #[test]
    fn eval_saturates_to_amplitude() {
        let amplitude = 5.0;
        let v = model().eval(&[1_000_000.0], &[amplitude, 1.0]);
        assert_relative_eq!(v, amplitude, epsilon = 1e-6);
    }

    #[test]
    fn jacobian_shape() {
        let j = model().jacobian(&[2.0], &[10.0, 0.5]);
        assert_eq!(j.len(), 2);
    }

    // FD check for ∂y/∂amplitude
    #[test]
    fn jacobian_numerical_amplitude() {
        let x = &[3.0f64];
        let p = [10.0, 0.001];
        let h = 1e-6;
        let mut pp = p;
        pp[0] += h;
        let fd = (model().eval(x, &pp) - model().eval(x, &p)) / h;
        let j = model().jacobian(x, &p);
        assert_relative_eq!(j[0], fd, epsilon = 1e-5);
    }

    // FD check for ∂y/∂rate
    #[test]
    fn jacobian_numerical_rate() {
        let x = &[3.0f64];
        let p = [10.0, 0.001];
        let h = 1e-8;
        let mut pp = p;
        pp[1] += h;
        let fd = (model().eval(x, &pp) - model().eval(x, &p)) / h;
        let j = model().jacobian(x, &p);
        assert_relative_eq!(j[1], fd, epsilon = 1e-4);
    }

    #[test]
    fn jacobian_into_matches_jacobian() {
        let x = &[5.0f64];
        let p = [300.0, 0.0004];
        let j_vec = model().jacobian(x, &p);
        let mut out = [0.0_f64; 2];
        model().jacobian_into(x, &p, &mut out);
        assert_relative_eq!(out[0], j_vec[0], epsilon = 1e-12);
        assert_relative_eq!(out[1], j_vec[1], epsilon = 1e-12);
    }

    #[test]
    fn eval_slice_matches_scalar() {
        let xs: Vec<f64> = (0..10).map(|i| i as f64 * 100.0).collect();
        let p = [300.0, 0.0004];
        let mut out = vec![0.0_f64; xs.len()];
        model().eval_slice_into(&xs, &p, &mut out);
        for (xi, &bi) in xs.iter().zip(out.iter()) {
            assert_relative_eq!(bi, model().eval(&[*xi], &p), epsilon = 1e-10);
        }
    }

    #[test]
    fn jac_slice_matches_scalar() {
        let xs: Vec<f64> = (0..8).map(|i| i as f64 * 100.0).collect();
        let p = [300.0, 0.0004];
        let n = xs.len();
        let mut out = vec![0.0_f64; n * 2];
        model().jac_slice_into(&xs, &p, &mut out);
        for (i, xi) in xs.iter().enumerate() {
            let j = model().jacobian(&[*xi], &p);
            for k in 0..2 {
                assert_relative_eq!(out[i * 2 + k], j[k], epsilon = 1e-10);
            }
        }
    }

    // Known value check: x=200, amplitude=337.997, rate=0.000390
    // u = 1 + 0.000390*200/2 = 1 + 0.039 = 1.039
    // y = 337.997 * (1 - 1.039^-2) = 337.997 * (1 - 0.926637) ≈ 24.79
    #[test]
    fn known_value() {
        let x = &[200.0f64];
        let p = [337.997_463_63, 3.903_909_128_7e-4];
        let y = model().eval(x, &p);
        // Approximate: u≈1.0390391, u^-2≈0.9267..., 1-u^-2≈0.0733...
        // y ≈ 337.997*0.0733 ≈ 24.78
        assert!(y > 20.0 && y < 30.0, "Known-value sanity: y={y}");
    }
}
