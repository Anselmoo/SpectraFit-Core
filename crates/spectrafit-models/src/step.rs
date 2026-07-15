use crate::Model;

/// Arctan step: `A · (½ + (1/π) · arctan((x − x₀) / σ))`
///
/// Parameters (in order): `[amplitude, center, sigma]`
///
/// ∂/∂amplitude = (½ + (1/π)·arctan(ε))
/// ∂/∂center    = −A / (π · σ · (1 + ε²))       [ε = (x−x₀)/σ]
/// ∂/∂sigma     = −A · ε / (π · σ · (1 + ε²))
pub struct ArctanStep;

impl Model for ArctanStep {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, x0, sigma) = (params[0], params[1], params[2]);
        let eps = (x[0] - x0) / sigma;
        a * (0.5 + eps.atan() / std::f64::consts::PI)
    }

    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let (a, x0, sigma) = (params[0], params[1], params[2]);
        let pi = std::f64::consts::PI;
        let eps = (x[0] - x0) / sigma;
        let eps2_1 = 1.0 + eps * eps;
        let atan_term = 0.5 + eps.atan() / pi;

        let da = atan_term;
        let dx0 = -a / (pi * sigma * eps2_1);
        let ds = -a * eps / (pi * sigma * eps2_1);

        vec![da, dx0, ds]
    }

    #[inline]
    fn jacobian_into(&self, x: &[f64], params: &[f64], out: &mut [f64]) {
        let (a, x0, sigma) = (params[0], params[1], params[2]);
        let pi = std::f64::consts::PI;
        let eps = (x[0] - x0) / sigma;
        let eps2_1 = 1.0 + eps * eps;
        out[0] = 0.5 + eps.atan() / pi;
        out[1] = -a / (pi * sigma * eps2_1);
        out[2] = -a * eps / (pi * sigma * eps2_1);
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["amplitude".into(), "center".into(), "sigma".into()]
    }
}

/// Tanh step: `(A / 2) · (1 + tanh((x − x₀) / σ))`
///
/// Parameters (in order): `[amplitude, center, sigma]`
///
/// ∂/∂amplitude = ½ · (1 + tanh(ε))
/// ∂/∂center    = −A / (2σ) · sech²(ε)
/// ∂/∂sigma     = −A · ε / (2σ) · sech²(ε)
pub struct TanhStep;

impl Model for TanhStep {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, x0, sigma) = (params[0], params[1], params[2]);
        let eps = (x[0] - x0) / sigma;
        a * 0.5 * (1.0 + eps.tanh())
    }

    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let (a, x0, sigma) = (params[0], params[1], params[2]);
        let eps = (x[0] - x0) / sigma;
        let t = eps.tanh();
        let sech2 = 1.0 - t * t; // sech²(ε)

        let da = 0.5 * (1.0 + t);
        let dx0 = -a * sech2 / (2.0 * sigma);
        let ds = -a * eps * sech2 / (2.0 * sigma);

        vec![da, dx0, ds]
    }

    #[inline]
    fn jacobian_into(&self, x: &[f64], params: &[f64], out: &mut [f64]) {
        let (a, x0, sigma) = (params[0], params[1], params[2]);
        let eps = (x[0] - x0) / sigma;
        let t = eps.tanh();
        let sech2 = 1.0 - t * t;
        out[0] = 0.5 * (1.0 + t);
        out[1] = -a * sech2 / (2.0 * sigma);
        out[2] = -a * eps * sech2 / (2.0 * sigma);
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["amplitude".into(), "center".into(), "sigma".into()]
    }
}

/// Erfc step: `(A / 2) · erfc((x − x₀) / (σ · √2))`
///
/// Parameters (in order): `[amplitude, center, sigma]`
///
/// Uses `libm::erfc`. Commonly used for XANES / XPS pre-edge backgrounds.
///
/// ∂/∂amplitude = ½ · erfc(u)
/// ∂/∂center    = A / (σ · √(2π)) · exp(−u²)    [u = (x−x₀)/(σ√2)]
/// ∂/∂sigma     = A · u / (σ · √(2π)) · exp(−u²)
pub struct ErfcStep;

impl Model for ErfcStep {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, x0, sigma) = (params[0], params[1], params[2]);
        let u = (x[0] - x0) / (sigma * std::f64::consts::SQRT_2);
        0.5 * a * libm::erfc(u)
    }

    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let (a, x0, sigma) = (params[0], params[1], params[2]);
        let sqrt2 = std::f64::consts::SQRT_2;
        let u = (x[0] - x0) / (sigma * sqrt2);
        let gauss = (-u * u).exp() / (sigma * (2.0 * std::f64::consts::PI).sqrt());

        let da = 0.5 * libm::erfc(u);
        let dx0 = a * gauss;
        // ∂f/∂σ = A·exp(−u²)·u / (σ·√π) = √2 · u · (gauss as computed above)
        let ds = a * u * gauss * std::f64::consts::SQRT_2;

        vec![da, dx0, ds]
    }

    #[inline]
    fn jacobian_into(&self, x: &[f64], params: &[f64], out: &mut [f64]) {
        let (a, x0, sigma) = (params[0], params[1], params[2]);
        let sqrt2 = std::f64::consts::SQRT_2;
        let u = (x[0] - x0) / (sigma * sqrt2);
        let gauss = (-u * u).exp() / (sigma * (2.0 * std::f64::consts::PI).sqrt());
        out[0] = 0.5 * libm::erfc(u);
        out[1] = a * gauss;
        out[2] = a * u * gauss * sqrt2;
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["amplitude".into(), "center".into(), "sigma".into()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    // ── ArctanStep ────────────────────────────────────────────────────────────

    #[test]
    fn arctan_at_center_is_half_amplitude() {
        let v = ArctanStep.eval(&[0.0], &[2.0, 0.0, 1.0]);
        assert_relative_eq!(v, 1.0, epsilon = 1e-12); // A/2 = 1
    }

    #[test]
    fn arctan_large_x_approaches_amplitude() {
        let v = ArctanStep.eval(&[1e6], &[1.0, 0.0, 1.0]);
        assert_relative_eq!(v, 1.0, epsilon = 1e-6);
    }

    #[test]
    fn arctan_jacobian_shape() {
        let j = ArctanStep.jacobian(&[0.5], &[1.0, 0.0, 1.0]);
        assert_eq!(j.len(), 3);
    }

    #[test]
    fn arctan_jacobian_finite_diff_check() {
        // Compare analytical Jacobian vs FD default baseline
        let p = [2.0, 0.5, 0.8];
        let x = [0.3];
        let j_analytical = ArctanStep.jacobian(&x, &p);
        let h = 1e-5;
        for (i, &ja) in j_analytical.iter().enumerate() {
            let mut pp = p;
            pp[i] += h;
            let fd = (ArctanStep.eval(&x, &pp) - ArctanStep.eval(&x, &p)) / h;
            assert_relative_eq!(ja, fd, epsilon = 1e-4);
        }
    }

    // ── TanhStep ──────────────────────────────────────────────────────────────

    #[test]
    fn tanh_at_center_is_half_amplitude() {
        let v = TanhStep.eval(&[0.0], &[2.0, 0.0, 1.0]);
        assert_relative_eq!(v, 1.0, epsilon = 1e-12);
    }

    #[test]
    fn tanh_large_x_approaches_amplitude() {
        let v = TanhStep.eval(&[1e2], &[1.0, 0.0, 1.0]);
        assert_relative_eq!(v, 1.0, epsilon = 1e-6);
    }

    #[test]
    fn tanh_jacobian_finite_diff_check() {
        let p = [1.5, 1.0, 0.5];
        let x = [1.2];
        let j_analytical = TanhStep.jacobian(&x, &p);
        let h = 1e-5;
        for (i, &ja) in j_analytical.iter().enumerate() {
            let mut pp = p;
            pp[i] += h;
            let fd = (TanhStep.eval(&x, &pp) - TanhStep.eval(&x, &p)) / h;
            assert_relative_eq!(ja, fd, epsilon = 1e-4);
        }
    }

    // ── ErfcStep ──────────────────────────────────────────────────────────────

    #[test]
    fn erfc_at_center_is_half_amplitude() {
        // erfc(0) = 1 → A/2
        let v = ErfcStep.eval(&[0.0], &[2.0, 0.0, 1.0]);
        assert_relative_eq!(v, 1.0, epsilon = 1e-12);
    }

    #[test]
    fn erfc_large_neg_x_approaches_amplitude() {
        let v = ErfcStep.eval(&[-1e6], &[1.0, 0.0, 1.0]);
        assert_relative_eq!(v, 1.0, epsilon = 1e-6);
    }

    #[test]
    fn erfc_jacobian_finite_diff_check() {
        let p = [1.0, 0.0, 1.0];
        let x = [0.5];
        let j_analytical = ErfcStep.jacobian(&x, &p);
        let h = 1e-5;
        for (i, &ja) in j_analytical.iter().enumerate() {
            let mut pp = p;
            pp[i] += h;
            let fd = (ErfcStep.eval(&x, &pp) - ErfcStep.eval(&x, &p)) / h;
            assert_relative_eq!(ja, fd, epsilon = 1e-5);
        }
    }
}
