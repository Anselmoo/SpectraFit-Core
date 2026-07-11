use crate::math_backend::batch_exp;
use crate::Model;

/// Gaussian kernel: `A * exp(-(x₀ - c)² / (2σ²))`
///
/// Parameters (in order): `[amplitude, center, sigma]`
pub struct Gaussian;

impl Model for Gaussian {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, c, sigma) = (params[0], params[1], params[2]);
        let z = -(x[0] - c).powi(2) / (2.0 * sigma * sigma);
        a * z.exp()
    }

    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let (a, c, sigma) = (params[0], params[1], params[2]);
        let dx = x[0] - c;
        let z = -dx * dx / (2.0 * sigma * sigma);
        let g = z.exp();

        // ∂/∂amplitude = g
        let da = g;
        // ∂/∂center    = A * g * (x₀ - c) / σ²
        let dc = a * g * dx / (sigma * sigma);
        // ∂/∂sigma     = A * g * (x₀ - c)² / σ³
        let ds = a * g * dx * dx / (sigma * sigma * sigma);

        vec![da, dc, ds]
    }

    #[inline]
    fn jacobian_into(&self, x: &[f64], params: &[f64], out: &mut [f64]) {
        let (a, c, sigma) = (params[0], params[1], params[2]);
        let dx = x[0] - c;
        let s2 = sigma * sigma;
        let g = (-dx * dx / (2.0 * s2)).exp();
        out[0] = g;
        out[1] = a * g * dx / s2;
        out[2] = a * g * dx * dx / (s2 * sigma);
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["amplitude".into(), "center".into(), "sigma".into()]
    }

    fn eval_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        assert_eq!(out.len(), xs.len());
        let (a, c, sigma) = (params[0], params[1], params[2]);
        let inv_2s2 = 1.0 / (2.0 * sigma * sigma);
        // Pass 1: write exp arguments into a temporary (vvexp requires
        // non-aliased src/dst pointers — Rust's borrow rules guarantee this).
        let args: Vec<f64> = xs
            .iter()
            .map(|xi| {
                let dx = xi - c;
                -(dx * dx) * inv_2s2
            })
            .collect();
        // Pass 2: vectorized exp — platform backend (vvexp on macOS, scalar elsewhere).
        batch_exp(out, &args);
        // Pass 3: scale by amplitude (LLVM auto-vectorizes this simple loop).
        for slot in out.iter_mut() {
            *slot *= a;
        }
    }

    fn jac_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        assert_eq!(out.len(), xs.len() * 3);
        let (a, c, sigma) = (params[0], params[1], params[2]);
        let s2 = sigma * sigma;
        let inv_2s2 = 0.5 / s2;
        let inv_s2 = 1.0 / s2;
        let inv_s3 = inv_s2 / sigma;
        let n = xs.len();
        // Compute exp arguments (loop-invariants hoisted outside).
        let args: Vec<f64> = xs
            .iter()
            .map(|xi| {
                let dx = xi - c;
                -(dx * dx) * inv_2s2
            })
            .collect();
        // Vectorized exp into a separate output buffer.
        let mut g = vec![0.0_f64; n];
        batch_exp(&mut g, &args);
        // Fill Jacobian row-major: [∂/∂amplitude, ∂/∂center, ∂/∂sigma].
        for (i, (&xi, &gi)) in xs.iter().zip(g.iter()).enumerate() {
            let dx = xi - c;
            out[i * 3] = gi;
            out[i * 3 + 1] = a * gi * dx * inv_s2;
            out[i * 3 + 2] = a * gi * dx * dx * inv_s3;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn eval_at_center() {
        // At x=center the Gaussian equals amplitude.
        let g = Gaussian;
        let v = g.eval(&[0.0], &[1.0, 0.0, 1.0]);
        assert_relative_eq!(v, 1.0, epsilon = 1e-12);
    }

    #[test]
    fn eval_at_sigma_offset() {
        // At x = center + σ the Gaussian equals A * exp(-0.5) = A / sqrt(e).
        let g = Gaussian;
        let v = g.eval(&[1.0], &[1.0, 0.0, 1.0]);
        let expected = 1.0 / std::f64::consts::E.sqrt();
        assert_relative_eq!(v, expected, epsilon = 1e-12);
    }

    #[test]
    fn jacobian_shape() {
        let g = Gaussian;
        let j = g.jacobian(&[0.5], &[2.0, 0.0, 1.0]);
        assert_eq!(j.len(), 3);
    }

    #[test]
    fn jacobian_at_center_da() {
        // ∂/∂amplitude at center: g = exp(0) = 1, so jac[0] = 1.0
        let g = Gaussian;
        let j = g.jacobian(&[0.0], &[1.0, 0.0, 1.0]);
        assert_relative_eq!(j[0], 1.0, epsilon = 1e-12);
    }

    #[test]
    fn jacobian_at_center_dc_zero() {
        // ∂/∂center at x == center is 0 (symmetric peak).
        let g = Gaussian;
        let j = g.jacobian(&[0.0], &[1.0, 0.0, 1.0]);
        assert_relative_eq!(j[1], 0.0, epsilon = 1e-12);
    }

    #[test]
    fn jacobian_numerical_check_amplitude() {
        // Numerical finite-difference comparison for ∂/∂amplitude.
        let g = Gaussian;
        let x = &[0.5f64];
        let params = [2.0f64, 0.0, 1.0];
        let h = 1e-6;
        let mut p_plus = params;
        p_plus[0] += h;
        let fd = (g.eval(x, &p_plus) - g.eval(x, &params)) / h;
        let j = g.jacobian(x, &params);
        assert_relative_eq!(j[0], fd, epsilon = 1e-5);
    }

    #[test]
    fn jacobian_numerical_check_center() {
        let g = Gaussian;
        let x = &[0.5f64];
        let params = [2.0f64, 0.0, 1.0];
        let h = 1e-6;
        let mut p_plus = params;
        p_plus[1] += h;
        let fd = (g.eval(x, &p_plus) - g.eval(x, &params)) / h;
        let j = g.jacobian(x, &params);
        assert_relative_eq!(j[1], fd, epsilon = 1e-5);
    }

    #[test]
    fn jacobian_numerical_check_sigma() {
        let g = Gaussian;
        let x = &[0.5f64];
        let params = [2.0f64, 0.0, 1.0];
        let h = 1e-6;
        let mut p_plus = params;
        p_plus[2] += h;
        let fd = (g.eval(x, &p_plus) - g.eval(x, &params)) / h;
        let j = g.jacobian(x, &params);
        assert_relative_eq!(j[2], fd, epsilon = 1e-5);
    }

    // ── batch path correctness ────────────────────────────────────────────────

    #[test]
    fn eval_slice_into_matches_scalar() {
        let g = Gaussian;
        let xs: Vec<f64> = (-5..=5).map(|i| i as f64 * 0.5).collect();
        let params = [3.0f64, 0.5, 1.2];
        let mut batch_out = vec![0.0_f64; xs.len()];
        g.eval_slice_into(&xs, &params, &mut batch_out);
        for (xi, &bi) in xs.iter().zip(batch_out.iter()) {
            let scalar = g.eval(&[*xi], &params);
            assert_relative_eq!(bi, scalar, epsilon = 1e-10, max_relative = 1e-10);
        }
    }

    #[test]
    fn jac_slice_into_matches_scalar() {
        let g = Gaussian;
        let xs: Vec<f64> = (-3..=3).map(|i| i as f64 * 0.75).collect();
        let params = [2.0f64, -0.5, 0.8];
        let n = xs.len();
        let mut jac_out = vec![0.0_f64; n * 3];
        g.jac_slice_into(&xs, &params, &mut jac_out);
        for (i, xi) in xs.iter().enumerate() {
            let scalar = g.jacobian(&[*xi], &params);
            assert_relative_eq!(jac_out[i * 3], scalar[0], epsilon = 1e-10);
            assert_relative_eq!(jac_out[i * 3 + 1], scalar[1], epsilon = 1e-10);
            assert_relative_eq!(jac_out[i * 3 + 2], scalar[2], epsilon = 1e-10);
        }
    }
}
