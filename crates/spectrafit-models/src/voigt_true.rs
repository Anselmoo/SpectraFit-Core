use crate::faddeeva;
use crate::Model;

/// True Voigt profile (Gaussian ⊗ Lorentzian) via the Faddeeva function.
///
/// `A · Re[w(z)] / Re[w(z₀)]`, with `z = ((x−c) + iγ)/(σ√2)` and
/// `z₀ = iγ/(σ√2)`, so `amplitude` is the peak height (`A` at `x=c`).
///
/// Parameters (in order): `[amplitude, center, sigma, gamma]`
///
/// - `sigma` is the Gaussian standard deviation, `gamma` the Lorentzian HWHM.
///   `γ→0` ⇒ Gaussian; `σ→0` ⇒ Lorentzian. Distinct from the `voigt`/`pseudo_voigt`
///   key, which is the linear pseudo-Voigt approximation.
pub struct TrueVoigt;

impl Model for TrueVoigt {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, c, sigma, gamma) = (params[0], params[1], params[2], params[3]);
        let inv = 1.0 / (sigma * std::f64::consts::SQRT_2);
        let zr = (x[0] - c) * inv;
        let zi = gamma.abs() * inv;
        let peak = faddeeva::w(0.0, zi).0; // Re[w(z₀)] at the center
        a * faddeeva::w(zr, zi).0 / peak
    }

    /// Analytical Jacobian of the true Voigt profile.
    ///
    /// Uses the Faddeeva derivative `w'(z) = −2z·w(z) + 2i/√π` (from
    /// `faddeeva::w_with_derivative`); by the Cauchy–Riemann equations
    ///
    ///   `∂Re[w]/∂z_r = Re[w'(z)]`,  `∂Re[w]/∂z_i = −Im[w'(z)]`.
    ///
    /// For the profile `f = A·w_r / peak0` (with `peak0 = Re[w(0, z_i)]`):
    ///
    ///   ∂f/∂A = w_r / peak0
    ///   ∂f/∂c = A / peak0 · dwr_dzr · (−inv)      [∂z_r/∂c = −inv]
    ///   ∂f/∂σ and ∂f/∂γ use the quotient rule because `peak0` also changes.
    ///
    /// `w` and `w'` are evaluated at full double precision (see the `faddeeva`
    /// module), so the Jacobian carries no approximation floor.
    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let (a, c, sigma, gamma) = (params[0], params[1], params[2], params[3]);
        let inv = 1.0 / (sigma * std::f64::consts::SQRT_2);

        let zr = (x[0] - c) * inv;
        let zi = gamma.abs() * inv;

        // Faddeeva value and derivative at the profile point and at the peak centre.
        let ((wr, _), (dwr, dwi)) = faddeeva::w_with_derivative(zr, zi);
        let ((w0r, _), (_, dw0i)) = faddeeva::w_with_derivative(0.0, zi);

        // ∂Re[w]/∂z_r and ∂Re[w]/∂z_i at (z_r, z_i)
        let dwr_dzr = dwr;
        let dwr_dzi = -dwi;

        // ∂Re[w0]/∂z_i at (0, z_i)
        let dw0r_dzi = -dw0i;

        let peak0 = w0r;

        // ∂f/∂A
        let da = wr / peak0;

        // ∂f/∂c : ∂z_r/∂c = −inv, ∂z_i/∂c = 0
        let dc = a / peak0 * dwr_dzr * (-inv);

        // ∂f/∂σ : ∂z_r/∂σ = −z_r/σ, ∂z_i/∂σ = −z_i/σ
        let dwr_dsigma = dwr_dzr * (-zr / sigma) + dwr_dzi * (-zi / sigma);
        let dpeak0_dsigma = dw0r_dzi * (-zi / sigma);
        let ds = a * (dwr_dsigma * peak0 - wr * dpeak0_dsigma) / (peak0 * peak0);

        // ∂f/∂γ : ∂z_r/∂γ = 0, ∂z_i/∂γ = sign(γ)·inv
        let sign_gamma = if gamma >= 0.0 { 1.0 } else { -1.0 };
        let dzi_dgamma = sign_gamma * inv;
        let dwr_dgamma = dwr_dzi * dzi_dgamma;
        let dpeak0_dgamma = dw0r_dzi * dzi_dgamma;
        let dg = a * (dwr_dgamma * peak0 - wr * dpeak0_dgamma) / (peak0 * peak0);

        vec![da, dc, ds, dg]
    }

    #[inline]
    fn jacobian_into(&self, x: &[f64], params: &[f64], out: &mut [f64]) {
        let jac = self.jacobian(x, params);
        out[..4].copy_from_slice(&jac);
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec![
            "amplitude".into(),
            "center".into(),
            "sigma".into(),
            "gamma".into(),
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn peak_height_is_amplitude() {
        let m = TrueVoigt;
        assert_relative_eq!(m.eval(&[1.5], &[4.0, 1.5, 1.0, 0.7]), 4.0, epsilon = 1e-9);
    }

    #[test]
    fn gamma_to_zero_is_gaussian() {
        // With no Lorentzian width the Voigt is a Gaussian:
        // Re[w((x-c)/(σ√2), 0)] = exp(-(x-c)²/(2σ²)) and Re[w(0)] = 1.
        let m = TrueVoigt;
        let (a, c, sigma) = (3.0, 0.4, 1.3);
        for i in -30..=30 {
            let x = c + f64::from(i) * 0.15;
            let got = m.eval(&[x], &[a, c, sigma, 0.0]);
            let gauss = a * (-0.5 * ((x - c) / sigma) * ((x - c) / sigma)).exp();
            assert_relative_eq!(got, gauss, epsilon = 0.0, max_relative = 1e-14);
        }
    }

    #[test]
    fn sigma_to_zero_is_lorentzian() {
        // For σ ≪ γ the Voigt tends to the Lorentzian γ²/((x-c)² + γ²), with a
        // relative correction of order (σ/γ)²; σ/γ = 1e-4 leaves ~1e-8.
        let m = TrueVoigt;
        let (a, c, gamma) = (2.0, -0.3, 0.8);
        let sigma = 1e-4 * gamma;
        for i in -20..=20 {
            let x = c + f64::from(i) * 0.25;
            let got = m.eval(&[x], &[a, c, sigma, gamma]);
            let lorentz = a * gamma * gamma / ((x - c) * (x - c) + gamma * gamma);
            assert_relative_eq!(got, lorentz, epsilon = 0.0, max_relative = 1e-7);
        }
    }

    #[test]
    fn symmetric_about_center() {
        let m = TrueVoigt;
        let p = [2.0, 0.5, 1.1, 0.6];
        assert_relative_eq!(
            m.eval(&[0.5 + 1.3], &p),
            m.eval(&[0.5 - 1.3], &p),
            epsilon = 1e-9
        );
    }

    #[test]
    fn jacobian_matches_central_difference_across_regimes() {
        // Central difference is O(h^2); with h = 1e-6·max(|p|, 1) its truncation
        // and rounding errors stay well below the 1e-7 bound used for the exact
        // closed-form kernels (cauchy_dispersion, doniach, skewed_gaussian).
        // The Faddeeva value and derivative are full double precision, so the
        // sweep covers the wings out to |x-c| = 8σ.
        let m = TrueVoigt;
        let param_sets = [
            [4.0, 0.5, 1.0, 0.7],    // nominal
            [1e-3, 0.0, 0.05, 0.05], // small amplitude, width and Lorentzian HWHM
            [5.0, -2.0, 3.0, -1.2],  // offset centre, wide, negative gamma
            [1.5, 0.3, 0.2, 4.0],    // Lorentzian-dominated: z₀ deep on the imaginary axis
        ];
        for p in param_sets {
            let (center, sigma) = (p[1], p[2]);
            for &mult in &[
                -8.0_f64, -4.0, -2.0, -1.0, -0.1, 0.0, 0.1, 1.0, 2.0, 4.0, 8.0,
            ] {
                let x = center + mult * sigma;
                let j = m.jacobian(&[x], &p);
                for i in 0..p.len() {
                    let h = 1e-6 * p[i].abs().max(1.0);
                    let (mut a, mut b) = (p, p);
                    a[i] += h;
                    b[i] -= h;
                    let fd = (m.eval(&[x], &a) - m.eval(&[x], &b)) / (2.0 * h);
                    // Absolute floor scaled to the profile height for entries
                    // that vanish by symmetry (e.g. ∂f/∂c at x = c).
                    assert_relative_eq!(j[i], fd, epsilon = 1e-7 * p[0].abs(), max_relative = 1e-7);
                }
            }
        }
    }
}
