use crate::Model;

/// Kowalik–Osborne rational function (NIST StRD MGH09 model).
///
/// ```text
/// y = amplitude · (x² + num_lin · x) / (x² + den_lin · x + den_const)
/// ```
///
/// Parameters (in order): `[amplitude, num_lin, den_lin, den_const]`
///
/// Mapping from NIST MGH09 b-parameters:
/// - `amplitude` = b1 (≈ 0.1928)
/// - `num_lin`   = b2 (≈ 0.1913; coefficient of x in the numerator)
/// - `den_lin`   = b3 (≈ 0.1231; coefficient of x in the denominator)
/// - `den_const` = b4 (≈ 0.1361; constant term in the denominator)
///
/// **Domain guard:** `D = x² + den_lin·x + den_const` must be non-zero.
/// The MGH09 certified parameters satisfy `discriminant = den_lin² − 4·den_const < 0`,
/// which means D > 0 for all x. If `D = 0` (or becomes zero during LM search), the
/// function returns `f64::NAN` so the solver backs off.
///
/// **Analytic Jacobian** (let `N = x² + num_lin·x`, `D = x² + den_lin·x + den_const`):
/// - ∂y/∂amplitude = N/D
/// - ∂y/∂num_lin   = amplitude · x / D
/// - ∂y/∂den_lin   = −amplitude · N · x / D²
/// - ∂y/∂den_const = −amplitude · N / D²
pub struct Mgh09Rational;

impl Model for Mgh09Rational {
    fn eval(&self, x: &[f64], p: &[f64]) -> f64 {
        let amplitude = p[0];
        let num_lin = p[1];
        let den_lin = p[2];
        let den_const = p[3];
        let xi = x[0];
        let n = xi * xi + num_lin * xi;
        let d = xi * xi + den_lin * xi + den_const;
        if d == 0.0 {
            return f64::NAN;
        }
        amplitude * n / d
    }

    fn jacobian_into(&self, x: &[f64], p: &[f64], out: &mut [f64]) {
        let amplitude = p[0];
        let num_lin = p[1];
        let den_lin = p[2];
        let den_const = p[3];
        let xi = x[0];
        let n = xi * xi + num_lin * xi;
        let d = xi * xi + den_lin * xi + den_const;
        if d == 0.0 {
            out[0] = f64::NAN;
            out[1] = f64::NAN;
            out[2] = f64::NAN;
            out[3] = f64::NAN;
            return;
        }
        let n_over_d = n / d;
        let inv_d2 = 1.0 / (d * d);
        out[0] = n_over_d;                           // ∂y/∂amplitude = N/D
        out[1] = amplitude * xi / d;                 // ∂y/∂num_lin   = amplitude·x/D
        out[2] = -amplitude * n * xi * inv_d2;       // ∂y/∂den_lin   = −amplitude·N·x/D²
        out[3] = -amplitude * n * inv_d2;            // ∂y/∂den_const = −amplitude·N/D²
    }

    fn jacobian(&self, x: &[f64], p: &[f64]) -> Vec<f64> {
        let amplitude = p[0];
        let num_lin = p[1];
        let den_lin = p[2];
        let den_const = p[3];
        let xi = x[0];
        let n = xi * xi + num_lin * xi;
        let d = xi * xi + den_lin * xi + den_const;
        if d == 0.0 {
            return vec![f64::NAN, f64::NAN, f64::NAN, f64::NAN];
        }
        let n_over_d = n / d;
        let inv_d2 = 1.0 / (d * d);
        vec![
            n_over_d,                           // ∂y/∂amplitude
            amplitude * xi / d,                 // ∂y/∂num_lin
            -amplitude * n * xi * inv_d2,       // ∂y/∂den_lin
            -amplitude * n * inv_d2,            // ∂y/∂den_const
        ]
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["amplitude".into(), "num_lin".into(), "den_lin".into(), "den_const".into()]
    }

    fn eval_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        debug_assert_eq!(out.len(), xs.len());
        let amplitude = params[0];
        let num_lin = params[1];
        let den_lin = params[2];
        let den_const = params[3];
        for (slot, &xi) in out.iter_mut().zip(xs.iter()) {
            let n = xi * xi + num_lin * xi;
            let d = xi * xi + den_lin * xi + den_const;
            *slot = if d == 0.0 {
                f64::NAN
            } else {
                amplitude * n / d
            };
        }
    }

    fn jac_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        debug_assert_eq!(out.len(), xs.len() * 4);
        let amplitude = params[0];
        let num_lin = params[1];
        let den_lin = params[2];
        let den_const = params[3];
        for (i, &xi) in xs.iter().enumerate() {
            let n = xi * xi + num_lin * xi;
            let d = xi * xi + den_lin * xi + den_const;
            if d == 0.0 {
                out[i * 4] = f64::NAN;
                out[i * 4 + 1] = f64::NAN;
                out[i * 4 + 2] = f64::NAN;
                out[i * 4 + 3] = f64::NAN;
            } else {
                let inv_d2 = 1.0 / (d * d);
                out[i * 4] = n / d;                           // ∂y/∂amplitude
                out[i * 4 + 1] = amplitude * xi / d;          // ∂y/∂num_lin
                out[i * 4 + 2] = -amplitude * n * xi * inv_d2; // ∂y/∂den_lin
                out[i * 4 + 3] = -amplitude * n * inv_d2;     // ∂y/∂den_const
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    fn model() -> Mgh09Rational {
        Mgh09Rational
    }

    // MGH09 certified params: b1=0.1928, b2=0.1913, b3=0.1231, b4=0.1361
    // At x=4.0 (first data point):
    //   N = 16 + 0.1913*4 = 16.7652
    //   D = 16 + 0.1231*4 + 0.1361 = 16.6285
    //   y = 0.1928 * 16.7652 / 16.6285 ≈ 0.1944  (matches NIST first obs ~0.1957)
    #[test]
    fn eval_first_mgh09_point_approx() {
        let p = [1.9280693458e-01_f64, 1.9128232873e-01, 1.2305650693e-01, 1.3606233068e-01];
        let y = model().eval(&[4.0], &p);
        assert!(
            (y - 0.1957).abs() < 5e-3,
            "Expected ~0.1957, got {y}"
        );
    }

    // Domain guard: D = x² + den_lin·x + den_const = 0 → NaN.
    // Construct such a case: x=0, den_const=0 → D=0.
    #[test]
    fn eval_zero_denominator_returns_nan() {
        let p = [1.0_f64, 0.5, 0.0, 0.0];  // D = 0 + 0 + 0 = 0 at x=0
        let y = model().eval(&[0.0], &p);
        assert!(y.is_nan(), "Expected NaN for D=0, got {y}");
    }

    #[test]
    fn jacobian_shape() {
        let j = model().jacobian(&[2.0], &[0.19, 0.19, 0.12, 0.14]);
        assert_eq!(j.len(), 4);
        assert!(j.iter().all(|v| v.is_finite()), "Jacobian must be finite: {j:?}");
    }

    // At x=0, N=0 so y=0 and ∂y/∂amplitude=0, ∂y/∂num_lin=0, ∂y/∂den_lin=0, ∂y/∂den_const=0
    #[test]
    fn jacobian_at_x_zero() {
        let p = [0.2_f64, 0.2, 0.12, 0.14];
        let j = model().jacobian(&[0.0], &p);
        assert_eq!(j.len(), 4);
        assert_relative_eq!(j[0], 0.0, epsilon = 1e-12);  // N/D = 0/D = 0
        assert_relative_eq!(j[1], 0.0, epsilon = 1e-12);  // amplitude·x/D = 0
        assert_relative_eq!(j[2], 0.0, epsilon = 1e-12);  // -amplitude·N·x/D² = 0
        assert_relative_eq!(j[3], 0.0, epsilon = 1e-12);  // -amplitude·N/D² = 0
    }

    // FD check for ∂y/∂amplitude
    #[test]
    fn jacobian_fd_amplitude() {
        let x = &[2.0_f64];
        let p = [0.19_f64, 0.19, 0.12, 0.14];
        let h = 1e-5;
        let mut pp = p;
        pp[0] += h;
        let fd = (model().eval(x, &pp) - model().eval(x, &p)) / h;
        let j = model().jacobian(x, &p);
        assert_relative_eq!(j[0], fd, max_relative = 1e-5);
    }

    // FD check for ∂y/∂num_lin
    #[test]
    fn jacobian_fd_num_lin() {
        let x = &[2.0_f64];
        let p = [0.19_f64, 0.19, 0.12, 0.14];
        let h = 1e-7;
        let mut pp = p;
        pp[1] += h;
        let fd = (model().eval(x, &pp) - model().eval(x, &p)) / h;
        let j = model().jacobian(x, &p);
        assert_relative_eq!(j[1], fd, max_relative = 1e-4);
    }

    // FD check for ∂y/∂den_lin
    #[test]
    fn jacobian_fd_den_lin() {
        let x = &[2.0_f64];
        let p = [0.19_f64, 0.19, 0.12, 0.14];
        let h = 1e-7;
        let mut pp = p;
        pp[2] += h;
        let fd = (model().eval(x, &pp) - model().eval(x, &p)) / h;
        let j = model().jacobian(x, &p);
        assert_relative_eq!(j[2], fd, max_relative = 1e-4);
    }

    // FD check for ∂y/∂den_const
    #[test]
    fn jacobian_fd_den_const() {
        let x = &[2.0_f64];
        let p = [0.19_f64, 0.19, 0.12, 0.14];
        let h = 1e-7;
        let mut pp = p;
        pp[3] += h;
        let fd = (model().eval(x, &pp) - model().eval(x, &p)) / h;
        let j = model().jacobian(x, &p);
        assert_relative_eq!(j[3], fd, max_relative = 1e-4);
    }

    #[test]
    fn jacobian_into_matches_jacobian() {
        let x = &[1.5_f64];
        let p = [0.19_f64, 0.19, 0.12, 0.14];
        let j_vec = model().jacobian(x, &p);
        let mut out = [0.0_f64; 4];
        model().jacobian_into(x, &p, &mut out);
        for k in 0..4 {
            assert_relative_eq!(out[k], j_vec[k], epsilon = 1e-12);
        }
    }

    #[test]
    fn eval_slice_matches_scalar() {
        let xs: Vec<f64> = [4.0, 2.0, 1.0, 0.5, 0.25, 0.167, 0.125, 0.1, 0.0833, 0.0714, 0.0625].to_vec();
        let p = [1.9280693458e-01_f64, 1.9128232873e-01, 1.2305650693e-01, 1.3606233068e-01];
        let mut out = vec![0.0_f64; xs.len()];
        model().eval_slice_into(&xs, &p, &mut out);
        for (&xi, &bi) in xs.iter().zip(out.iter()) {
            assert_relative_eq!(bi, model().eval(&[xi], &p), epsilon = 1e-10);
        }
    }

    #[test]
    fn jac_slice_matches_scalar() {
        let xs: Vec<f64> = [4.0, 2.0, 1.0, 0.5, 0.25].to_vec();
        let p = [0.19_f64, 0.19, 0.12, 0.14];
        let n = xs.len();
        let mut out = vec![0.0_f64; n * 4];
        model().jac_slice_into(&xs, &p, &mut out);
        for (i, xi) in xs.iter().enumerate() {
            let j = model().jacobian(&[*xi], &p);
            for k in 0..4 {
                assert_relative_eq!(out[i * 4 + k], j[k], epsilon = 1e-10);
            }
        }
    }
}
