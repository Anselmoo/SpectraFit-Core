use crate::Model;

/// Lorentzian kernel: `A / (1 + ((x₀ - c) / σ)²)`
///
/// Parameters (in order): `[amplitude, center, sigma]`
pub struct Lorentzian;

impl Model for Lorentzian {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, c, sigma) = (params[0], params[1], params[2]);
        let d = (x[0] - c) / sigma;
        a / (1.0 + d * d)
    }

    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let (a, c, sigma) = (params[0], params[1], params[2]);
        let dx = x[0] - c;
        let d = dx / sigma;
        let big_d = 1.0 + d * d;

        // ∂/∂amplitude = 1/D
        let da = 1.0 / big_d;
        // ∂/∂center    = 2*A*(x₀-c) / (σ²*D²)
        let dc = 2.0 * a * dx / (sigma * sigma * big_d * big_d);
        // ∂/∂sigma     = 2*A*(x₀-c)² / (σ³*D²)
        let ds = 2.0 * a * dx * dx / (sigma * sigma * sigma * big_d * big_d);

        vec![da, dc, ds]
    }

    #[inline]
    fn jacobian_into(&self, x: &[f64], params: &[f64], out: &mut [f64]) {
        let (a, c, sigma) = (params[0], params[1], params[2]);
        let dx = x[0] - c;
        let d = dx / sigma;
        let big_d = 1.0 + d * d;
        let big_d2 = big_d * big_d;
        let s2 = sigma * sigma;
        out[0] = 1.0 / big_d;
        out[1] = 2.0 * a * dx / (s2 * big_d2);
        out[2] = 2.0 * a * dx * dx / (s2 * sigma * big_d2);
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["amplitude".into(), "center".into(), "sigma".into()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn eval_at_center() {
        // At x=center the Lorentzian equals amplitude.
        let l = Lorentzian;
        let v = l.eval(&[0.0], &[3.0, 0.0, 1.0]);
        assert_relative_eq!(v, 3.0, epsilon = 1e-12);
    }

    #[test]
    fn eval_at_sigma_offset() {
        // At x = center + σ: A / (1 + 1) = A/2.
        let l = Lorentzian;
        let v = l.eval(&[1.0], &[4.0, 0.0, 1.0]);
        assert_relative_eq!(v, 2.0, epsilon = 1e-12);
    }

    #[test]
    fn jacobian_shape() {
        let l = Lorentzian;
        let j = l.jacobian(&[0.5], &[1.0, 0.0, 1.0]);
        assert_eq!(j.len(), 3);
    }

    #[test]
    fn jacobian_at_center_dc_zero() {
        // ∂/∂center at x == center is 0.
        let l = Lorentzian;
        let j = l.jacobian(&[0.0], &[1.0, 0.0, 1.0]);
        assert_relative_eq!(j[1], 0.0, epsilon = 1e-12);
    }

    #[test]
    fn jacobian_numerical_check_amplitude() {
        let l = Lorentzian;
        let x = &[0.5f64];
        let params = [2.0f64, 0.0, 1.5];
        let h = 1e-6;
        let mut p_plus = params;
        p_plus[0] += h;
        let fd = (l.eval(x, &p_plus) - l.eval(x, &params)) / h;
        let j = l.jacobian(x, &params);
        assert_relative_eq!(j[0], fd, epsilon = 1e-5);
    }

    #[test]
    fn jacobian_numerical_check_center() {
        let l = Lorentzian;
        let x = &[0.5f64];
        let params = [2.0f64, 0.0, 1.5];
        let h = 1e-6;
        let mut p_plus = params;
        p_plus[1] += h;
        let fd = (l.eval(x, &p_plus) - l.eval(x, &params)) / h;
        let j = l.jacobian(x, &params);
        assert_relative_eq!(j[1], fd, epsilon = 1e-5);
    }

    #[test]
    fn jacobian_numerical_check_sigma() {
        let l = Lorentzian;
        let x = &[0.5f64];
        let params = [2.0f64, 0.0, 1.5];
        let h = 1e-6;
        let mut p_plus = params;
        p_plus[2] += h;
        let fd = (l.eval(x, &p_plus) - l.eval(x, &params)) / h;
        let j = l.jacobian(x, &params);
        assert_relative_eq!(j[2], fd, epsilon = 1e-5);
    }
}
