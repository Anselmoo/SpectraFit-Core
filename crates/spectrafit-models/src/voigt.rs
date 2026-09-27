use crate::Model;

/// Pseudo-Voigt kernel: `A * (fraction * L̃ + (1 - fraction) * G̃)`
///
/// where `G̃` and `L̃` are unit-amplitude Gaussian and Lorentzian shapes:
/// - `G̃ = exp(-(x₀-c)² / (2σ²))`
/// - `L̃ = 1 / (1 + ((x₀-c)/σ)²)`
///
/// Parameters (in order): `[amplitude, center, sigma, fraction]`
///
/// - `fraction = 0.0` → pure Gaussian
/// - `fraction = 1.0` → pure Lorentzian
pub struct Voigt;

impl Model for Voigt {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, c, sigma, frac) = (params[0], params[1], params[2], params[3]);
        let dx = x[0] - c;
        let z = -dx * dx / (2.0 * sigma * sigma);
        let g_tilde = z.exp();
        let d = dx / sigma;
        let big_d = 1.0 + d * d;
        let l_tilde = 1.0 / big_d;

        a * (frac * l_tilde + (1.0 - frac) * g_tilde)
    }

    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let (a, c, sigma, frac) = (params[0], params[1], params[2], params[3]);
        let dx = x[0] - c;
        let z = -dx * dx / (2.0 * sigma * sigma);
        let g_tilde = z.exp();

        let d = dx / sigma;
        let big_d = 1.0 + d * d;
        let l_tilde = 1.0 / big_d;

        // Unit-amplitude shape derivatives (w.r.t. center, σ)
        // ∂G̃/∂c  = G̃ * (x₀-c) / σ²    (note: -(∂z/∂c) = +dx/σ²)
        let dg_dc = g_tilde * dx / (sigma * sigma);
        // ∂G̃/∂σ  = G̃ * (x₀-c)² / σ³
        let dg_ds = g_tilde * dx * dx / (sigma * sigma * sigma);

        // ∂L̃/∂c  = 2*(x₀-c) / (σ²*D²)
        let dl_dc = 2.0 * dx / (sigma * sigma * big_d * big_d);
        // ∂L̃/∂σ  = 2*(x₀-c)² / (σ³*D²)
        let dl_ds = 2.0 * dx * dx / (sigma * sigma * sigma * big_d * big_d);

        // ∂/∂amplitude = frac*L̃ + (1-frac)*G̃
        let da = frac * l_tilde + (1.0 - frac) * g_tilde;
        // ∂/∂center    = A*(frac*∂L̃/∂c + (1-frac)*∂G̃/∂c)
        let dc = a * (frac * dl_dc + (1.0 - frac) * dg_dc);
        // ∂/∂sigma     = A*(frac*∂L̃/∂σ + (1-frac)*∂G̃/∂σ)
        let ds = a * (frac * dl_ds + (1.0 - frac) * dg_ds);
        // ∂/∂frac      = A*(L̃ - G̃)
        let dfrac = a * (l_tilde - g_tilde);

        vec![da, dc, ds, dfrac]
    }

    #[inline]
    fn jacobian_into(&self, x: &[f64], params: &[f64], out: &mut [f64]) {
        let (a, c, sigma, frac) = (params[0], params[1], params[2], params[3]);
        let dx = x[0] - c;
        let s2 = sigma * sigma;
        let z = -dx * dx / (2.0 * s2);
        let g_tilde = z.exp();
        let d = dx / sigma;
        let big_d = 1.0 + d * d;
        let big_d2 = big_d * big_d;
        let l_tilde = 1.0 / big_d;
        let dg_dc = g_tilde * dx / s2;
        let dg_ds = g_tilde * dx * dx / (s2 * sigma);
        let dl_dc = 2.0 * dx / (s2 * big_d2);
        let dl_ds = 2.0 * dx * dx / (s2 * sigma * big_d2);
        out[0] = frac * l_tilde + (1.0 - frac) * g_tilde;
        out[1] = a * (frac * dl_dc + (1.0 - frac) * dg_dc);
        out[2] = a * (frac * dl_ds + (1.0 - frac) * dg_ds);
        out[3] = a * (l_tilde - g_tilde);
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec![
            "amplitude".into(),
            "center".into(),
            "sigma".into(),
            "fraction".into(),
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::gaussian::Gaussian;
    use crate::lorentzian::Lorentzian;
    use approx::assert_relative_eq;

    #[test]
    fn frac_zero_equals_gaussian() {
        let voigt = Voigt;
        let gauss = Gaussian;
        let x = &[0.7f64];
        let params_v = [2.0, 0.0, 1.0, 0.0]; // frac=0 → pure Gaussian
        let params_g = [2.0, 0.0, 1.0];
        assert_relative_eq!(
            voigt.eval(x, &params_v),
            gauss.eval(x, &params_g),
            epsilon = 1e-12
        );
    }

    #[test]
    fn frac_one_equals_lorentzian() {
        let voigt = Voigt;
        let lorentz = Lorentzian;
        let x = &[0.7f64];
        let params_v = [2.0, 0.0, 1.0, 1.0]; // frac=1 → pure Lorentzian
        let params_l = [2.0, 0.0, 1.0];
        assert_relative_eq!(
            voigt.eval(x, &params_v),
            lorentz.eval(x, &params_l),
            epsilon = 1e-12
        );
    }

    #[test]
    fn jacobian_shape() {
        let v = Voigt;
        let j = v.jacobian(&[0.5], &[1.0, 0.0, 1.0, 0.5]);
        assert_eq!(j.len(), 4);
    }

    // Central-difference (O(h^2)) sweep over three parameter regimes and
    // several x-points relative to the centre, replacing the old
    // single-point forward differences (h=1e-6, epsilon=1e-5). Each test
    // keeps its name (traceability) but now checks only its own parameter
    // index across the full regime/x-point grid.
    const VOIGT_REGIMES: [[f64; 4]; 3] = [
        [2.0, 0.0, 1.0, 0.4],   // nominal
        [1e-3, 0.0, 0.05, 0.2], // small amplitude/width
        [5.0, -2.0, 3.0, 0.8],  // offset centre, wide
    ];

    fn check_voigt_param_central_diff(idx: usize) {
        let v = Voigt;
        for p in VOIGT_REGIMES {
            let (c, sigma) = (p[1], p[2]);
            for &mult in &[-3.0_f64, -1.0, -0.1, 0.0, 0.1, 1.0, 3.0] {
                let x = [c + mult * sigma];
                let j = v.jacobian(&x, &p);
                let h = 1e-6 * p[idx].abs().max(1.0);
                let (mut a, mut b) = (p, p);
                a[idx] += h;
                b[idx] -= h;
                let fd = (v.eval(&x, &a) - v.eval(&x, &b)) / (2.0 * h);
                assert_relative_eq!(j[idx], fd, epsilon = 1e-7, max_relative = 1e-6);
            }
        }
    }

    #[test]
    fn jacobian_numerical_check_amplitude() {
        check_voigt_param_central_diff(0);
    }

    #[test]
    fn jacobian_numerical_check_center() {
        check_voigt_param_central_diff(1);
    }

    #[test]
    fn jacobian_numerical_check_sigma() {
        check_voigt_param_central_diff(2);
    }

    #[test]
    fn jacobian_numerical_check_frac() {
        check_voigt_param_central_diff(3);
    }
}
