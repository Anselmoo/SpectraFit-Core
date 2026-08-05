use crate::Model;

/// Power-law with offset: `amplitude · (offset + x)^(−1/shape)`
///
/// Parameters (in order): `[amplitude, offset, shape]`
///
/// This is the NIST StRD Bennett5 model. It describes a power-law relationship
/// of the form `y = b1·(b2 + x)^(−1/b3)` with the mapping:
/// - `amplitude` = b1 (≈ −2524 for Bennett5; may be negative)
/// - `offset`    = b2 (≈ 46.7 for Bennett5; shifts x-origin)
/// - `shape`     = b3 (≈ 0.932 for Bennett5; controls the exponent)
///
/// **Domain guard:** `u = offset + x` must be strictly positive so that `ln(u)`
/// and `u^p` (with `p = −1/shape`) are finite. If `u ≤ 0` the function returns
/// `f64::NAN` (the LM solver will reject the step and backtrack).
///
/// **Note:** `amplitude` is the overall scale, NOT a peak-at-center value as in
/// the spectral-peak convention documented in `MODELS.md`. For Bennett5 the
/// certified b1 is large and negative.
///
/// Analytic Jacobian (let `u = offset + x`, `p = −1/shape`):
/// - ∂y/∂amplitude = u^p
/// - ∂y/∂offset   = amplitude · p · u^(p−1)
/// - ∂y/∂shape    = amplitude · u^p · ln(u) · (1/shape²)
pub struct PowerLawOffset;

impl Model for PowerLawOffset {
    fn eval(&self, x: &[f64], p: &[f64]) -> f64 {
        let amplitude = p[0];
        let offset = p[1];
        let shape = p[2];
        let u = offset + x[0];
        if u <= 0.0 {
            return f64::NAN;
        }
        let exponent = -1.0 / shape;
        amplitude * u.powf(exponent)
    }

    fn jacobian_into(&self, x: &[f64], p: &[f64], out: &mut [f64]) {
        let amplitude = p[0];
        let offset = p[1];
        let shape = p[2];
        let u = offset + x[0];
        if u <= 0.0 {
            out[0] = f64::NAN;
            out[1] = f64::NAN;
            out[2] = f64::NAN;
            return;
        }
        let exponent = -1.0 / shape;
        let u_pow = u.powf(exponent); // u^(−1/shape)
        let u_pow_m1 = u_pow / u; // u^(−1/shape − 1) = u_pow / u

        out[0] = u_pow; // ∂y/∂amplitude
        out[1] = amplitude * exponent * u_pow_m1; // ∂y/∂offset
        out[2] = amplitude * u_pow * u.ln() / (shape * shape); // ∂y/∂shape
    }

    fn jacobian(&self, x: &[f64], p: &[f64]) -> Vec<f64> {
        let amplitude = p[0];
        let offset = p[1];
        let shape = p[2];
        let u = offset + x[0];
        if u <= 0.0 {
            return vec![f64::NAN, f64::NAN, f64::NAN];
        }
        let exponent = -1.0 / shape;
        let u_pow = u.powf(exponent);
        let u_pow_m1 = u_pow / u;
        vec![
            u_pow,                                        // ∂y/∂amplitude
            amplitude * exponent * u_pow_m1,              // ∂y/∂offset
            amplitude * u_pow * u.ln() / (shape * shape), // ∂y/∂shape
        ]
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["amplitude".into(), "offset".into(), "shape".into()]
    }

    fn eval_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        debug_assert_eq!(out.len(), xs.len());
        let amplitude = params[0];
        let offset = params[1];
        let shape = params[2];
        let exponent = -1.0 / shape;
        for (slot, &xi) in out.iter_mut().zip(xs.iter()) {
            let u = offset + xi;
            *slot = if u <= 0.0 {
                f64::NAN
            } else {
                amplitude * u.powf(exponent)
            };
        }
    }

    fn jac_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        debug_assert_eq!(out.len(), xs.len() * 3);
        let amplitude = params[0];
        let offset = params[1];
        let shape = params[2];
        let exponent = -1.0 / shape;
        let inv_shape2 = 1.0 / (shape * shape);
        for (i, &xi) in xs.iter().enumerate() {
            let u = offset + xi;
            if u <= 0.0 {
                out[i * 3] = f64::NAN;
                out[i * 3 + 1] = f64::NAN;
                out[i * 3 + 2] = f64::NAN;
            } else {
                let u_pow = u.powf(exponent);
                let u_pow_m1 = u_pow / u;
                out[i * 3] = u_pow;
                out[i * 3 + 1] = amplitude * exponent * u_pow_m1;
                out[i * 3 + 2] = amplitude * u_pow * u.ln() * inv_shape2;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    fn model() -> PowerLawOffset {
        PowerLawOffset
    }

    // Bennett5 certified params: amplitude=-2523.5, offset=46.74, shape=0.9322
    // At x=7.447168 (first data point):
    //   u = 46.74 + 7.447 = 54.187, exponent = -1/0.9322 ≈ -1.0727
    //   y = -2523.5 * 54.187^(-1.0727) ≈ -34.8  (matches NIST first point ~-34.83)
    #[test]
    fn eval_first_bennett5_point_approx() {
        let p = [-2523.5_f64, 46.74, 0.9322];
        let y = model().eval(&[7.447168], &p);
        assert!((y - (-34.8)).abs() < 0.3, "Expected ~-34.8, got {y}");
    }

    // Domain guard: u = offset + x ≤ 0 → NaN.
    #[test]
    fn eval_negative_u_returns_nan() {
        let p = [1.0_f64, 1.0, 0.5];
        let y = model().eval(&[-5.0], &p); // u = 1 - 5 = -4
        assert!(y.is_nan(), "Expected NaN for u≤0, got {y}");
    }

    #[test]
    fn jacobian_shape() {
        let j = model().jacobian(&[5.0], &[1.0, 2.0, 0.5]);
        assert_eq!(j.len(), 3);
        assert!(
            j.iter().all(|v| v.is_finite()),
            "Jacobian must be finite: {j:?}"
        );
    }

    // FD check for ∂y/∂amplitude
    #[test]
    fn jacobian_fd_amplitude() {
        let x = &[8.0_f64];
        let p = [-2500.0_f64, 46.7, 0.93];
        let h = 1e-4;
        let mut pp = p;
        pp[0] += h;
        let fd = (model().eval(x, &pp) - model().eval(x, &p)) / h;
        let j = model().jacobian(x, &p);
        assert_relative_eq!(j[0], fd, max_relative = 1e-4);
    }

    // FD check for ∂y/∂offset
    #[test]
    fn jacobian_fd_offset() {
        let x = &[8.0_f64];
        let p = [-2500.0_f64, 46.7, 0.93];
        let h = 1e-5;
        let mut pp = p;
        pp[1] += h;
        let fd = (model().eval(x, &pp) - model().eval(x, &p)) / h;
        let j = model().jacobian(x, &p);
        assert_relative_eq!(j[1], fd, max_relative = 1e-4);
    }

    // FD check for ∂y/∂shape
    #[test]
    fn jacobian_fd_shape() {
        let x = &[8.0_f64];
        let p = [-2500.0_f64, 46.7, 0.93];
        let h = 1e-7;
        let mut pp = p;
        pp[2] += h;
        let fd = (model().eval(x, &pp) - model().eval(x, &p)) / h;
        let j = model().jacobian(x, &p);
        assert_relative_eq!(j[2], fd, max_relative = 1e-4);
    }

    #[test]
    fn jacobian_into_matches_jacobian() {
        let x = &[10.0_f64];
        let p = [-2500.0_f64, 46.7, 0.93];
        let j_vec = model().jacobian(x, &p);
        let mut out = [0.0_f64; 3];
        model().jacobian_into(x, &p, &mut out);
        assert_relative_eq!(out[0], j_vec[0], epsilon = 1e-12);
        assert_relative_eq!(out[1], j_vec[1], epsilon = 1e-12);
        assert_relative_eq!(out[2], j_vec[2], epsilon = 1e-12);
    }

    #[test]
    fn eval_slice_matches_scalar() {
        let xs: Vec<f64> = (0..10).map(|i| 7.0 + i as f64 * 0.5).collect();
        let p = [-2500.0_f64, 46.7, 0.93];
        let mut out = vec![0.0_f64; xs.len()];
        model().eval_slice_into(&xs, &p, &mut out);
        for (&xi, &bi) in xs.iter().zip(out.iter()) {
            assert_relative_eq!(bi, model().eval(&[xi], &p), epsilon = 1e-10);
        }
    }

    #[test]
    fn jac_slice_matches_scalar() {
        let xs: Vec<f64> = (0..8).map(|i| 8.0 + i as f64 * 0.4).collect();
        let p = [-2500.0_f64, 46.7, 0.93];
        let n = xs.len();
        let mut out = vec![0.0_f64; n * 3];
        model().jac_slice_into(&xs, &p, &mut out);
        for (i, xi) in xs.iter().enumerate() {
            let j = model().jacobian(&[*xi], &p);
            for k in 0..3 {
                assert_relative_eq!(out[i * 3 + k], j[k], epsilon = 1e-10);
            }
        }
    }
}
