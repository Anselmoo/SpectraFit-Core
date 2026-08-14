use crate::Model;

/// Skewed Gaussian: a Gaussian modulated by an error-function skew factor.
///
/// `A · exp(−½((x−c)/σ)²) · (1 + erf(γ·(x−c)/(σ·√2)))`
///
/// Parameters (in order): `[amplitude, center, sigma, gamma]`
///
/// - `gamma` is the skewness: `0` ⇒ symmetric Gaussian, `γ>0` ⇒ tail toward high
///   `x`, `γ<0` ⇒ tail toward low `x`. Uses `libm::erf`.
pub struct SkewedGaussian;

impl Model for SkewedGaussian {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, c, sigma, gamma) = (params[0], params[1], params[2], params[3]);
        let dx = x[0] - c;
        let g = (-0.5 * (dx / sigma) * (dx / sigma)).exp();
        let beta = gamma / (sigma * std::f64::consts::SQRT_2);
        a * g * (1.0 + libm::erf(beta * dx))
    }

    /// Analytical Jacobian of the skewed Gaussian.
    ///
    /// Let `g = exp(−½(dx/σ)²)`, `β = γ/(σ√2)`, `skew = 1 + erf(β·dx)`,
    /// `erf_d = (2/√π)·exp(−(β·dx)²)` (the erf derivative factor).
    ///
    /// ∂f/∂A      = g · skew
    /// ∂f/∂center = A·g · [  dx/σ² · skew − β · erf_d ]   (∂dx/∂c = −1)
    /// ∂f/∂sigma  = A·g · [ dx²/σ³ · skew − β·dx/σ · erf_d ]
    /// ∂f/∂gamma  = A·g · [ dx/(σ√2) · erf_d ]
    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let (a, c, sigma, gamma) = (params[0], params[1], params[2], params[3]);
        let sqrt2 = std::f64::consts::SQRT_2;
        let dx = x[0] - c;
        let inv_sigma = 1.0 / sigma;
        let u = dx * inv_sigma; // dx/σ
        let g = (-0.5 * u * u).exp();
        let beta = gamma / (sigma * sqrt2); // γ/(σ√2)
        let beta_dx = beta * dx;
        let skew = 1.0 + libm::erf(beta_dx);
        // erf_d = (2/√π)·exp(−(β·dx)²)
        let erf_d = (2.0 / std::f64::consts::PI.sqrt()) * (-beta_dx * beta_dx).exp();

        let da = g * skew;
        // ∂f/∂c = A·g·[dx/σ²·skew − β·erf_d]
        // Note: ∂g/∂c = g·u/σ (positive for dx>0, ∂(−½u²)/∂c = u·(−∂u/∂c) = u/σ);
        //       ∂skew/∂c = erf_d·β·(∂dx/∂c) = erf_d·β·(−1)
        let dc = a * g * (u * inv_sigma * skew - beta * erf_d);
        // ∂f/∂σ: ∂g/∂σ = g·u²/σ; ∂(β·dx)/∂σ = −β·u
        let ds = a * g * (u * u * inv_sigma * skew - beta * dx * inv_sigma * erf_d);
        // ∂f/∂γ: ∂(β·dx)/∂γ = dx/(σ√2)
        let dg = a * g * (dx / (sigma * sqrt2)) * erf_d;

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
    fn gamma_zero_reduces_to_gaussian() {
        // erf(0)=0 ⇒ factor (1+0)=1 ⇒ pure Gaussian (value A at center).
        let m = SkewedGaussian;
        assert_relative_eq!(m.eval(&[0.0], &[3.0, 0.0, 1.0, 0.0]), 3.0, epsilon = 1e-12);
    }

    #[test]
    fn positive_skew_lifts_high_side() {
        // γ>0: the high-x side is enhanced relative to the symmetric mirror point.
        let m = SkewedGaussian;
        let hi = m.eval(&[1.0], &[1.0, 0.0, 1.0, 1.5]);
        let lo = m.eval(&[-1.0], &[1.0, 0.0, 1.0, 1.5]);
        assert!(hi > lo);
    }
}
