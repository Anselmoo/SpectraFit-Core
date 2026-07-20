use crate::math_backend::batch_exp;
use crate::Model;

/// Saturating exponential: `amplitude · (1 − exp(−rate · x))`
///
/// Parameters (in order): `[amplitude, rate]`
///
/// This is the BoxBOD model (NIST StRD): it describes processes that grow
/// toward a saturation level `amplitude` with characteristic rate `rate`.
/// For `rate > 0` and `x ≥ 0` the function rises monotonically from `0`
/// to `amplitude`.
///
/// Note: here `amplitude` is the asymptotic saturation level — the plateau the
/// curve approaches as `x → ∞` — NOT a peak-at-center value as in the
/// peak-model convention documented in `MODELS.md`.
pub struct SaturatingExponential;

impl Model for SaturatingExponential {
    fn eval(&self, x: &[f64], p: &[f64]) -> f64 {
        let xi = x[0];
        p[0] * (1.0 - (-p[1] * xi).exp())
    }

    fn jacobian_into(&self, x: &[f64], p: &[f64], out: &mut [f64]) {
        let xi = x[0];
        let e = (-p[1] * xi).exp();
        out[0] = 1.0 - e; // ∂y/∂amplitude = 1 − exp(−rate·x)
        out[1] = p[0] * xi * e; // ∂y/∂rate      = amplitude · x · exp(−rate·x)
    }

    fn jacobian(&self, x: &[f64], p: &[f64]) -> Vec<f64> {
        let xi = x[0];
        let e = (-p[1] * xi).exp();
        vec![
            1.0 - e,       // ∂y/∂amplitude
            p[0] * xi * e, // ∂y/∂rate
        ]
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["amplitude".into(), "rate".into()]
    }

    fn eval_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        assert_eq!(out.len(), xs.len());
        let (amplitude, rate) = (params[0], params[1]);
        let args: Vec<f64> = xs.iter().map(|xi| -rate * xi).collect();
        let mut exps = vec![0.0_f64; xs.len()];
        batch_exp(&mut exps, &args);
        for (slot, e) in out.iter_mut().zip(exps.iter()) {
            *slot = amplitude * (1.0 - e);
        }
    }

    fn jac_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        assert_eq!(out.len(), xs.len() * 2);
        let (amplitude, rate) = (params[0], params[1]);
        let args: Vec<f64> = xs.iter().map(|xi| -rate * xi).collect();
        let mut exps = vec![0.0_f64; xs.len()];
        batch_exp(&mut exps, &args);
        for (i, (xi, e)) in xs.iter().zip(exps.iter()).enumerate() {
            out[i * 2] = 1.0 - e; // ∂y/∂amplitude
            out[i * 2 + 1] = amplitude * xi * e; // ∂y/∂rate
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    fn model() -> SaturatingExponential {
        SaturatingExponential
    }

    // amplitude=3, rate=0.5, x=0: 3*(1-exp(0)) = 3*(1-1) = 0
    #[test]
    fn eval_at_zero() {
        let v = model().eval(&[0.0], &[3.0, 0.5]);
        assert_relative_eq!(v, 0.0, epsilon = 1e-12);
    }

    // amplitude=3, rate=0, x=2: 3*(1-exp(0)) = 0  (rate=0 → no decay)
    #[test]
    fn eval_zero_rate() {
        let v = model().eval(&[2.0], &[3.0, 0.0]);
        assert_relative_eq!(v, 0.0, epsilon = 1e-12);
    }

    // At very large x*rate the function → amplitude
    #[test]
    fn eval_saturates_to_amplitude() {
        let amplitude = 5.0;
        let v = model().eval(&[1000.0], &[amplitude, 1.0]);
        assert_relative_eq!(v, amplitude, epsilon = 1e-9);
    }

    #[test]
    fn jacobian_shape() {
        let j = model().jacobian(&[1.0], &[3.0, 0.5]);
        assert_eq!(j.len(), 2);
    }

    #[test]
    fn jacobian_numerical_amplitude() {
        let x = &[1.5f64];
        let p = [3.0, 0.5];
        let h = 1e-6;
        let mut pp = p;
        pp[0] += h;
        let fd = (model().eval(x, &pp) - model().eval(x, &p)) / h;
        let j = model().jacobian(x, &p);
        assert_relative_eq!(j[0], fd, epsilon = 1e-5);
    }

    #[test]
    fn jacobian_numerical_rate() {
        let x = &[1.5f64];
        let p = [3.0, 0.5];
        let h = 1e-6;
        let mut pp = p;
        pp[1] += h;
        let fd = (model().eval(x, &pp) - model().eval(x, &p)) / h;
        let j = model().jacobian(x, &p);
        assert_relative_eq!(j[1], fd, epsilon = 1e-5);
    }

    #[test]
    fn jacobian_into_matches_jacobian() {
        let x = &[2.0f64];
        let p = [3.0, 0.5];
        let j_vec = model().jacobian(x, &p);
        let mut out = [0.0_f64; 2];
        model().jacobian_into(x, &p, &mut out);
        assert_relative_eq!(out[0], j_vec[0], epsilon = 1e-12);
        assert_relative_eq!(out[1], j_vec[1], epsilon = 1e-12);
    }

    #[test]
    fn eval_slice_matches_scalar() {
        let xs: Vec<f64> = (0..10).map(|i| i as f64 * 0.5).collect();
        let p = [3.0, 0.5];
        let mut out = vec![0.0_f64; xs.len()];
        model().eval_slice_into(&xs, &p, &mut out);
        for (xi, &bi) in xs.iter().zip(out.iter()) {
            assert_relative_eq!(bi, model().eval(&[*xi], &p), epsilon = 1e-10);
        }
    }

    #[test]
    fn jac_slice_matches_scalar() {
        let xs: Vec<f64> = (0..8).map(|i| i as f64 * 0.5).collect();
        let p = [3.0, 0.5];
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
}
