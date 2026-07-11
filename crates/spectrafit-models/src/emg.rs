use crate::Model;
use crate::erf_ext::erfcx;

/// Exponentially-modified Gaussian (EMG) — a Gaussian convolved with a one-sided
/// exponential, the canonical asymmetric/tailing chromatography & spectroscopy peak.
///
/// `A · (γ/2) · exp[γ(c−x) + (γσ)²/2] · erfc[(c + γσ² − x)/(σ√2)]`
///
/// Parameters (in order): `[amplitude, center, sigma, gamma]`
///
/// - `gamma` is the exponential decay rate of the tail (toward high `x`); as `γ→0`
///   the shape approaches a Gaussian.
///
/// # Numerical stability (no clamp)
///
/// The naive form computes `exp(arg_exp)·erfc(z)`, which overflows to `inf·0 → NaN`
/// for `arg_exp > 709` (e.g. `γσ > 37`). Instead we use the algebraic identity
/// `arg_exp − z² = −(x−c)²/(2σ²)` and split on the sign of `z`:
///
/// - `z ≥ 0`: `A·(γ/2)·exp(−(x−c)²/(2σ²))·erfcx(z)` — both factors are bounded
///   (`erfcx(z) ∈ (0,1]`, the Gaussian `≤ 1`), so there is no overflow.
/// - `z < 0`: `A·(γ/2)·exp(arg_exp)·erfc(z)` — here `arg_exp < 0`, so the `exp`
///   cannot overflow, and `erfc(z) ∈ (1,2)`.
///
/// The two branches are continuous at `z = 0` (`erfcx(0) = erfc(0) = 1` and the
/// Gaussian factor equals `exp(arg_exp)` there). A final `is_finite` guard remains
/// as belt-and-suspenders. The numpy benchmark oracle uses the identical split with
/// `scipy.special.erfcx`, so numpy↔Rust parity holds to machine precision.
pub struct ExpGaussian;

impl Model for ExpGaussian {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, c, sigma, gamma) = (params[0], params[1], params[2], params[3]);
        let u = c - x[0];
        let arg_exp = gamma * u + 0.5 * (gamma * sigma) * (gamma * sigma);
        let z = (c + gamma * sigma * sigma - x[0]) / (std::f64::consts::SQRT_2 * sigma);
        let v = if z >= 0.0 {
            // Overflow-free: exp(arg_exp)·erfc(z) == exp(-(x-c)²/(2σ²))·erfcx(z).
            let gauss = (-(x[0] - c) * (x[0] - c) / (2.0 * sigma * sigma)).exp();
            a * 0.5 * gamma * gauss * erfcx(z)
        } else {
            // arg_exp < 0 here, so exp is safe; erfc(z) ∈ (1, 2).
            a * 0.5 * gamma * arg_exp.exp() * libm::erfc(z)
        };
        if v.is_finite() { v } else { 0.0 }
    }

    /// Analytical Jacobian of the EMG (exponentially-modified Gaussian).
    ///
    /// Define: `e_arg = γ(c−x) + (γσ)²/2`, `u = (c + γσ² − x)/(σ√2)`,
    /// `E = exp(e_arg)`, `C = erfc(u)`, `g_u = (2/√π)·exp(−u²)`.
    ///
    /// Then `f = A·(γ/2)·E·C`.
    ///
    /// ∂f/∂A      = (γ/2)·E·C
    /// ∂f/∂center = A·(γ/2)·E·[ γ·C − g_u/(σ√2) ]
    /// ∂f/∂sigma  = A·(γ/2)·E·[ γ²σ·C − g_u·(γ√2 − u/σ) ]
    /// ∂f/∂gamma  = (A/2)·E·C + A·(γ/2)·E·[ (c−x+γσ²)·C − g_u·σ/√2 ]
    ///
    /// When the overflow-clamped region returns f=0, all derivatives are 0.
    ///
    /// # Numerical stability
    ///
    /// The Jacobian uses the same identity as `eval`:
    ///   `E·C = gauss·erfcx(u)` for z ≥ 0  (overflow-free)
    ///   `E·C = exp(e_arg)·erfc(u)` for z < 0 (safe, e_arg < 0 here)
    ///
    /// In both branches, `E·g_u = gauss·(2/√π)` where
    /// `gauss = exp(−(x−c)²/(2σ²))`, because the identity
    /// `e_arg − u² = −(x−c)²/(2σ²)` holds exactly.
    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let (a, c, sigma, gamma) = (params[0], params[1], params[2], params[3]);
        let sqrt2 = std::f64::consts::SQRT_2;
        let inv_sqrt_pi = 1.0 / std::f64::consts::PI.sqrt();
        let e_arg = gamma * (c - x[0]) + 0.5 * (gamma * sigma) * (gamma * sigma);
        let u = (c + gamma * sigma * sigma - x[0]) / (sqrt2 * sigma);
        let gauss = (-(x[0] - c) * (x[0] - c) / (2.0 * sigma * sigma)).exp();

        // E·C — the stable product, matching eval().
        let ec = if u >= 0.0 {
            gauss * erfcx(u)
        } else {
            e_arg.exp() * libm::erfc(u)
        };

        if !(a * 0.5 * gamma * ec).is_finite() {
            return vec![0.0; 4];
        }

        // E·g_u = gauss·(2/√π)  — works in both z branches.
        let e_g_u = gauss * 2.0 * inv_sqrt_pi;

        let da = 0.5 * gamma * ec;
        let dc = a * 0.5 * gamma * (gamma * ec - e_g_u / (sigma * sqrt2));
        let ds = a * 0.5 * gamma * (gamma * gamma * sigma * ec
            - e_g_u * (gamma * sqrt2 - u / sigma));
        let c_minus_x_plus_gss = c - x[0] + gamma * sigma * sigma;
        let dg = 0.5 * a * ec
            + a * 0.5 * gamma * (c_minus_x_plus_gss * ec - e_g_u * sigma / sqrt2);

        vec![da, dc, ds, dg]
    }

    #[inline]
    fn jacobian_into(&self, x: &[f64], params: &[f64], out: &mut [f64]) {
        let jac = self.jacobian(x, params);
        out[..4].copy_from_slice(&jac);
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["amplitude".into(), "center".into(), "sigma".into(), "gamma".into()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finite_over_a_reasonable_grid() {
        let m = ExpGaussian;
        let p = [4.0, 0.0, 1.0, 0.8];
        for i in -50..=50 {
            let v = m.eval(&[i as f64 * 0.2], &p);
            assert!(v.is_finite(), "non-finite at x={}", i as f64 * 0.2);
        }
    }

    #[test]
    fn asymmetric_tail_toward_high_x() {
        // EMG tails toward high x: the high side decays slower than the low side.
        let m = ExpGaussian;
        let p = [4.0, 0.0, 1.0, 0.8];
        let hi = m.eval(&[2.5], &p);
        let lo = m.eval(&[-2.5], &p);
        assert!(hi > lo);
    }

    #[test]
    fn extreme_tail_matches_mpmath_reference() {
        // gamma=38, sigma=1 → arg_exp ≈ 703 at x=0.5 (overflow regime for the naive
        // exp·erfc form). The stable erfcx split must match a 50-digit mpmath
        // reference: value = A·0.5·γ·exp(arg_exp)·erfc(z).
        use approx::assert_relative_eq;
        let m = ExpGaussian;
        let p = [1.0, 0.0, 1.0, 38.0];
        // (x, mpmath 50-digit reference value)
        let refs = [
            (0.5_f64, 0.356_506_374_757_193_2_f64),
            (0.0, 0.398_666_576_586_319_1),
            (1.0, 0.248_329_343_171_832_5),
            (-2.0, 0.051_259_420_971_274_5),
            (3.0, 0.004_807_802_777_736_4),
        ];
        for (x, want) in refs {
            let got = m.eval(&[x], &p);
            assert!(got.is_finite(), "non-finite at x={x}");
            assert_relative_eq!(got, want, max_relative = 1e-9);
        }
    }
}
