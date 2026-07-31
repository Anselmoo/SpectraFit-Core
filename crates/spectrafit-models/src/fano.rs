use crate::Model;

/// Fano resonance lineshape used in XPS asymmetric peaks.
///
/// Formula: `A · (q + ε)² / (1 + ε²)`,  ε = (x − x₀) / Γ
///
/// Parameters (in order): `[amplitude, center, gamma, q]`
///
/// - `amplitude` — overall scale factor `A`
/// - `center`    — resonance centre `x₀`
/// - `gamma`     — half-width at half-maximum `Γ` (> 0)
/// - `q`         — Fano asymmetry parameter (dimensionless)
///
/// Jacobians are fully analytical.
pub struct Fano;

impl Model for Fano {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, x0, gamma, q) = (params[0], params[1], params[2], params[3]);
        let eps = (x[0] - x0) / gamma;
        let num = (q + eps) * (q + eps);
        let den = 1.0 + eps * eps;
        a * num / den
    }

    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let (a, x0, gamma, q) = (params[0], params[1], params[2], params[3]);
        let dx = x[0] - x0;
        let eps = dx / gamma;
        let qe = q + eps;
        let e2_1 = 1.0 + eps * eps;
        let fano = qe * qe / e2_1; // normalised Fano value

        // ∂/∂amplitude
        let da = fano;

        // d(fano)/d(eps): use quotient rule
        // f(ε) = (q+ε)²/(1+ε²)
        // f'(ε) = [2(q+ε)(1+ε²) − (q+ε)²·2ε] / (1+ε²)²
        //       = 2(q+ε)[(1+ε²) − (q+ε)ε] / (1+ε²)²
        let dfano_deps = 2.0 * qe * (e2_1 - qe * eps) / (e2_1 * e2_1);

        // ε = (x − x₀)/γ  →  ∂ε/∂x₀ = −1/γ,  ∂ε/∂γ = −ε/γ
        let dc = a * dfano_deps * (-1.0 / gamma);
        let dg = a * dfano_deps * (-eps / gamma);

        // ∂/∂q:  d/dq [(q+ε)²/(1+ε²)] = 2(q+ε)/(1+ε²)
        let dq = a * 2.0 * qe / e2_1;

        vec![da, dc, dg, dq]
    }

    #[inline]
    fn jacobian_into(&self, x: &[f64], params: &[f64], out: &mut [f64]) {
        let (a, x0, gamma, q) = (params[0], params[1], params[2], params[3]);
        let dx = x[0] - x0;
        let eps = dx / gamma;
        let qe = q + eps;
        let e2_1 = 1.0 + eps * eps;
        let fano = qe * qe / e2_1;
        let dfano_deps = 2.0 * qe * (e2_1 - qe * eps) / (e2_1 * e2_1);
        out[0] = fano;
        out[1] = a * dfano_deps * (-1.0 / gamma);
        out[2] = a * dfano_deps * (-eps / gamma);
        out[3] = a * 2.0 * qe / e2_1;
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec![
            "amplitude".into(),
            "center".into(),
            "gamma".into(),
            "q".into(),
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn at_center_eps_zero() {
        // ε=0 → (q+0)²/(1+0) = q², so f = A·q²
        let v = Fano.eval(&[0.0], &[1.0, 0.0, 1.0, 2.0]);
        assert_relative_eq!(v, 4.0, epsilon = 1e-12);
    }

    #[test]
    fn zero_at_eps_minus_q() {
        // ε = −q → numerator = 0 → f = 0
        let v = Fano.eval(&[-2.0], &[1.0, 0.0, 1.0, 2.0]);
        assert_relative_eq!(v, 0.0, epsilon = 1e-12);
    }

    #[test]
    fn jacobian_shape() {
        let j = Fano.jacobian(&[0.5], &[1.0, 0.0, 1.0, 1.5]);
        assert_eq!(j.len(), 4);
    }

    #[test]
    fn jacobian_finite_diff_check() {
        let p = [2.0, 0.2, 0.8, 1.5];
        let x = [0.4];
        let j_anal = Fano.jacobian(&x, &p);
        let h = 1e-5;
        for (i, &ja) in j_anal.iter().enumerate() {
            let mut pp = p;
            pp[i] += h;
            let fd = (Fano.eval(&x, &pp) - Fano.eval(&x, &p)) / h;
            assert_relative_eq!(ja, fd, epsilon = 1e-4);
        }
    }

    #[test]
    fn da_equals_fano_value_over_amplitude() {
        // ∂/∂amplitude is just the normalised lineshape
        let p = [3.0, 0.0, 1.0, 1.0];
        let x = [0.5];
        let j = Fano.jacobian(&x, &p);
        let expected_da = Fano.eval(&x, &[1.0, p[1], p[2], p[3]]);
        assert_relative_eq!(j[0], expected_da, epsilon = 1e-12);
    }

    // ----- Limiting-case asymptotic (ground-truth verification, Cycle 3) -----
    //
    // For very large q, the Fano lineshape collapses to a Lorentzian scaled by q²:
    //
    //     A·(q+ε)²/(1+ε²)  →  A·q²/(1+ε²)         as q → ∞
    //
    // So Fano(A=1, q=Q)/Q² should converge to a Lorentzian of unit amplitude as
    // Q grows. The remaining error is the 2qε + ε² subleading term, of relative
    // order 1/q. Test at q = 1e6 → relative error ≤ ~1e-5.

    #[test]
    fn fano_q_large_normalised_matches_lorentzian() {
        use crate::lorentzian::Lorentzian;
        let x = [0.4_f64];
        let q = 1.0e6;
        let p_fano = [1.0, 0.0, 1.0, q]; // A=1, c=0, γ=1, q huge
        let p_lor = [1.0, 0.0, 1.0]; // A=1, c=0, σ=γ=1
        let fano_normalised = Fano.eval(&x, &p_fano) / (q * q);
        let lor = Lorentzian.eval(&x, &p_lor);
        // Subleading 1/q term gives ~1e-6 relative error at q=1e6.
        assert_relative_eq!(fano_normalised, lor, epsilon = 1e-5);
    }
}
