use crate::Model;

/// Hui–Armstrong–Wray (1978) rational-approximation coefficients.
///
/// Reference: Hui, Armstrong & Wray, JQSRT **19** 509 (1978).
/// Accuracy ≈ 1e-6 over the spectroscopy domain (|z| not too large).
/// Literals are the shortest decimal that round-trips to the same f64
/// (clippy `excessive_precision` flagged the original 17-digit values).
const HAW_A: [f64; 7] = [
    122.607_931_777_104_33,
    214.382_388_694_706_44,
    181.928_533_092_181_54,
    93.155_580_458_138_45,
    30.180_142_196_210_59,
    5.912_626_209_773_153,
    0.564_189_583_562_615,
];
const HAW_B: [f64; 8] = [
    122.607_931_773_875_35,
    352.730_625_110_963_56,
    457.334_478_783_897_74,
    348.703_917_719_495_8,
    170.354_001_821_091_47,
    53.992_906_912_940_21,
    10.479_857_114_260_4,
    1.0,
];

/// Full complex Faddeeva function `w(z) = exp(−z²)·erfc(−iz)` for `Im(z) ≥ 0`,
/// via the Hui–Armstrong–Wray (1978) 6th-order rational approximation.
///
/// Returns `(Re[w(z)], Im[w(z)])`. The approximation accuracy is ≈1e-6.
fn faddeeva_complex(zr: f64, zi: f64) -> (f64, f64) {
    // t = -i·z = (zi, -zr)
    let (tr, ti) = (zi, -zr);
    let (mut nr, mut ni) = (HAW_A[6], 0.0);
    for k in (0..6).rev() {
        let (pr, pi) = (nr * tr - ni * ti, nr * ti + ni * tr);
        nr = pr + HAW_A[k];
        ni = pi;
    }
    let (mut dr, mut di) = (HAW_B[7], 0.0);
    for k in (0..7).rev() {
        let (pr, pi) = (dr * tr - di * ti, dr * ti + di * tr);
        dr = pr + HAW_B[k];
        di = pi;
    }
    let denom = dr * dr + di * di;
    // Re[N/D] and Im[N/D]
    let wr = (nr * dr + ni * di) / denom;
    let wi = (ni * dr - nr * di) / denom;
    (wr, wi)
}

/// Real part of the Faddeeva function (convenience wrapper used by `eval`).
fn faddeeva_re(zr: f64, zi: f64) -> f64 {
    faddeeva_complex(zr, zi).0
}

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
        let peak = faddeeva_re(0.0, zi); // Re[w(z₀)] at the center
        a * faddeeva_re(zr, zi) / peak
    }

    /// Analytical Jacobian of the true Voigt profile.
    ///
    /// Uses the Faddeeva derivative identity: `dw(z)/dz = −2z·w(z) + 2i/√π`,
    /// which gives (treating `z_r` and `z_i` as independent real parameters):
    ///
    ///   `∂Re[w]/∂z_r = Re[dw/dz]  = −2(z_r·w_r − z_i·w_i)`
    ///   `∂Re[w]/∂z_i = −Im[dw/dz] =  2(z_r·w_i + z_i·w_r) − 2/√π`
    ///
    /// where `(w_r, w_i) = faddeeva_complex(z_r, z_i)`.
    ///
    /// For the profile `f = A·w_r / peak0` (with `peak0 = Re[w(0, z_i)]`):
    ///
    ///   ∂f/∂A = w_r / peak0
    ///   ∂f/∂c = A / peak0 · dwr_dzr · (−inv)      [∂z_r/∂c = −inv]
    ///   ∂f/∂σ and ∂f/∂γ use the quotient rule because `peak0` also changes.
    ///
    /// # Accuracy note
    ///
    /// The HAW approximation has ≈1e-6 accuracy; the Jacobian inherits that
    /// floor, so the self-consistency test uses tolerance 1e-5 (10× the default
    /// analytic budget). This is a justified relaxation, not a correctness gap.
    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let (a, c, sigma, gamma) = (params[0], params[1], params[2], params[3]);
        let sqrt2 = std::f64::consts::SQRT_2;
        let inv_sqrt_pi = 1.0 / std::f64::consts::PI.sqrt();
        let inv = 1.0 / (sigma * sqrt2);

        let zr = (x[0] - c) * inv;
        let zi = gamma.abs() * inv;

        // Full complex Faddeeva at the profile point and at the peak centre.
        let (wr, wi) = faddeeva_complex(zr, zi);
        let (w0r, w0i) = faddeeva_complex(0.0, zi);

        // ∂Re[w]/∂z_r and ∂Re[w]/∂z_i at (z_r, z_i)
        let dwr_dzr = -2.0 * (zr * wr - zi * wi);
        let dwr_dzi = 2.0 * (zr * wi + zi * wr) - 2.0 * inv_sqrt_pi;

        // ∂Re[w0]/∂z_i at (0, z_i)
        let dw0r_dzi = 2.0 * zi * w0r - 2.0 * inv_sqrt_pi;
        // Note: at z_r=0, the term (z_r·w0i) = 0, so dw0r_dzi = 2·z_i·w0r − 2/√π.
        // We also don't need w0i except for the above; reference it via the full form:
        let _ = w0i; // unused — the formula above is already simplified for z_r=0.

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
        // With a vanishing Lorentzian width the Voigt collapses to a Gaussian:
        // Re[w((x-c)/(σ√2), 0)] = exp(-(x-c)²/(2σ²)).
        let m = TrueVoigt;
        let (a, c, sigma) = (3.0, 0.0, 1.0);
        for i in -30..=30 {
            let x = i as f64 * 0.15;
            let got = m.eval(&[x], &[a, c, sigma, 1e-6]);
            let gauss = a * (-0.5 * (x / sigma) * (x / sigma)).exp();
            assert_relative_eq!(got, gauss, epsilon = 5e-4, max_relative = 5e-4);
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
}
