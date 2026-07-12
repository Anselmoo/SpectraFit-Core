use crate::Model;

/// Doniach–Šunjić asymmetric lineshape (XPS core-level peaks).
///
/// `A · cos[πγ/2 + (1−γ)·atan((x−c)/σ)] / (1 + ((x−c)/σ)²)^((1−γ)/2)`
///
/// Parameters (in order): `[amplitude, center, sigma, gamma]`
///
/// - `gamma` is the asymmetry index (`0` ⇒ symmetric Lorentzian-like; larger ⇒
///   stronger high-binding-energy tail). `amplitude` scales the curve.
///
/// The area-normalising `1/σ^(1−γ)` prefactor of the textbook form is folded into
/// `amplitude` so the parameter set matches the other height-amplitude kernels;
/// the numpy benchmark formula is identical, so numpy↔Rust parity is exact.
pub struct DoniachSunjic;

impl Model for DoniachSunjic {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, c, sigma, gamma) = (params[0], params[1], params[2], params[3]);
        let u = (x[0] - c) / sigma;
        let num = (std::f64::consts::FRAC_PI_2 * gamma + (1.0 - gamma) * u.atan()).cos();
        let den = (1.0 + u * u).powf((1.0 - gamma) / 2.0);
        a * num / den
    }

    /// Analytical Jacobian of the Doniach–Šunjić lineshape.
    ///
    /// Let `u = (x−c)/σ`, `φ = πγ/2 + (1−γ)·atan(u)`,
    /// `D = (1+u²)^((1−γ)/2)`, so `f = A·cos(φ)/D`.
    ///
    /// ∂f/∂A = cos(φ)/D
    ///
    /// Shared factor for center/sigma (via ∂f/∂u):
    ///   ∂f/∂u = A·(1−γ)·[−sin(φ)−cos(φ)·u] / ((1+u²)·D)
    ///
    ///   ∂u/∂c = −1/σ  ⟹  ∂f/∂c = ∂f/∂u · (−1/σ)
    ///   ∂u/∂σ = −u/σ  ⟹  ∂f/∂σ = ∂f/∂u · (−u/σ)
    ///
    /// For gamma: `∂φ/∂γ = π/2 − atan(u)`, `∂D/∂γ = −½·ln(1+u²)·D`
    ///   ∂f/∂γ = A·[−sin(φ)·(π/2−atan(u)) + ½·cos(φ)·ln(1+u²)] / D
    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let (a, c, sigma, gamma) = (params[0], params[1], params[2], params[3]);
        let u = (x[0] - c) / sigma;
        let u2_1 = 1.0 + u * u;
        let atan_u = u.atan();
        let phi = std::f64::consts::FRAC_PI_2 * gamma + (1.0 - gamma) * atan_u;
        let d = u2_1.powf((1.0 - gamma) / 2.0);
        let cos_phi = phi.cos();
        let sin_phi = phi.sin();

        let da = cos_phi / d;

        // ∂f/∂u = A·(1−γ)·[−sin(φ)−cos(φ)·u] / (u2_1·D)
        // ∂f/∂c = ∂f/∂u · (−1/σ)
        let df_du_coeff = a * (1.0 - gamma) / (u2_1 * d);
        let du_core = -sin_phi - cos_phi * u;
        let dc = df_du_coeff * du_core * (-1.0 / sigma);
        let ds = df_du_coeff * du_core * (-u / sigma);

        // ∂f/∂γ
        let dg = a / d
            * (-sin_phi * (std::f64::consts::FRAC_PI_2 - atan_u)
                + 0.5 * cos_phi * u2_1.ln());

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
    use approx::assert_relative_eq;

    #[test]
    fn symmetric_at_gamma_zero_is_lorentzian_at_center() {
        // γ=0 ⇒ cos[(1)·atan(0)] / (1)^(1/2) = 1 at center, scaled by A.
        let m = DoniachSunjic;
        assert_relative_eq!(m.eval(&[0.0], &[2.0, 0.0, 1.0, 0.0]), 2.0, epsilon = 1e-12);
    }

    #[test]
    fn asymmetry_breaks_mirror_symmetry() {
        // With γ>0 the lineshape is asymmetric: f(c+d) != f(c-d).
        let m = DoniachSunjic;
        let left = m.eval(&[-1.0], &[1.0, 0.0, 1.0, 0.2]);
        let right = m.eval(&[1.0], &[1.0, 0.0, 1.0, 0.2]);
        assert!((left - right).abs() > 1e-3);
    }

    #[test]
    fn param_names_are_canonical() {
        assert_eq!(
            DoniachSunjic.param_names().iter().map(|c| c.as_ref()).collect::<Vec<_>>(),
            &["amplitude", "center", "sigma", "gamma"]
        );
    }

    // ----- Limiting-case asymptotic (ground-truth verification, Cycle 4) -----
    //
    // At γ = 0 the Doniach-Šunjić lineshape reduces *exactly* to a Lorentzian.
    // Identity derivation: with γ = 0,
    //
    //     num = cos[(1)·atan(u)] = 1/√(1+u²),  den = (1+u²)^(1/2)
    //     ⇒ A·num/den = A · (1/√(1+u²)) / √(1+u²) = A / (1+u²)
    //
    // which is the Lorentzian. Promote the existing one-point γ=0 check to a
    // full multi-point identity against the Lorentzian kernel — catches any
    // future formula tweak that breaks the no-asymmetry symmetric reduction.

    #[test]
    fn gamma_zero_equals_lorentzian_everywhere() {
        use crate::lorentzian::Lorentzian;
        let ds = DoniachSunjic;
        let lor = Lorentzian;
        let a = 2.5_f64;
        let c = 0.4_f64;
        let sigma = 0.9_f64;
        let p_ds = [a, c, sigma, 0.0]; // γ = 0
        let p_lor = [a, c, sigma];
        for &xi in &[-2.0_f64, -0.5, c, 0.5, 2.0] {
            assert_relative_eq!(
                ds.eval(&[xi], &p_ds),
                lor.eval(&[xi], &p_lor),
                epsilon = 1e-12
            );
        }
    }
}
