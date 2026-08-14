use crate::Model;

/// Proper Pseudo-Voigt: `η · L(x) + (1 − η) · G(x)`
///
/// where η ∈ [0,1] is the Lorentzian fraction (fitted parameter),
/// G is a Gaussian, and L is a Lorentzian with the **same** width parameter.
///
/// Parameters (in order): `[amplitude, center, sigma, fraction]`
///
/// Gaussian term:   `G = exp(−(x−c)²/(2σ²))`
/// Lorentzian term: `L = 1 / (1 + (x−c)²/σ²)`
///
/// Jacobians are computed via the chain rule through G, L, and η.
pub struct PseudoVoigt;

impl Model for PseudoVoigt {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, c, sigma, eta) = (params[0], params[1], params[2], params[3]);
        // Clip the mixing fraction to [0,1]: η outside this range is unphysical
        // (it would extrapolate past pure-Lorentzian/Gaussian). Matches the numpy
        // oracle's np.clip(fraction, 0, 1) so an LM search that overshoots the
        // bound measures the solver, not a formula divergence.
        let eta = eta.clamp(0.0, 1.0);
        let dx = x[0] - c;
        let g = (-dx * dx / (2.0 * sigma * sigma)).exp();
        let l = 1.0 / (1.0 + dx * dx / (sigma * sigma));
        a * (eta * l + (1.0 - eta) * g)
    }

    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let (a, c, sigma, raw_eta) = (params[0], params[1], params[2], params[3]);
        // η is clamped to [0,1] in eval; clamp here too so the analytic Jacobian
        // is consistent with the (clamped) value, and zero ∂/∂fraction outside the
        // bound where the clamped output is constant in fraction.
        let eta = raw_eta.clamp(0.0, 1.0);
        let in_range = (0.0..=1.0).contains(&raw_eta);
        let dx = x[0] - c;
        let dx2 = dx * dx;
        let s2 = sigma * sigma;

        let g = (-dx2 / (2.0 * s2)).exp();
        let denom = 1.0 + dx2 / s2;
        let l = 1.0 / denom;
        let mix = eta * l + (1.0 - eta) * g;

        // ∂/∂amplitude
        let da = mix;

        // ∂/∂center
        let dg_dc = g * dx / s2;
        let dl_dc = 2.0 * dx / (s2 * denom * denom);
        let dc = a * (eta * dl_dc + (1.0 - eta) * dg_dc);

        // ∂/∂sigma
        let dg_ds = g * dx2 / (s2 * sigma);
        let dl_ds = 2.0 * dx2 / (s2 * sigma * denom * denom);
        let ds = a * (eta * dl_ds + (1.0 - eta) * dg_ds);

        // ∂/∂fraction (eta): zero outside the clamp where the output is flat.
        let df = if in_range { a * (l - g) } else { 0.0 };

        vec![da, dc, ds, df]
    }

    #[inline]
    fn jacobian_into(&self, x: &[f64], params: &[f64], out: &mut [f64]) {
        let (a, c, sigma, raw_eta) = (params[0], params[1], params[2], params[3]);
        let eta = raw_eta.clamp(0.0, 1.0);
        let in_range = (0.0..=1.0).contains(&raw_eta);
        let dx = x[0] - c;
        let dx2 = dx * dx;
        let s2 = sigma * sigma;
        let g = (-dx2 / (2.0 * s2)).exp();
        let denom = 1.0 + dx2 / s2;
        let l = 1.0 / denom;
        let denom2 = denom * denom;
        let dg_dc = g * dx / s2;
        let dl_dc = 2.0 * dx / (s2 * denom2);
        let dg_ds = g * dx2 / (s2 * sigma);
        let dl_ds = 2.0 * dx2 / (s2 * sigma * denom2);
        out[0] = eta * l + (1.0 - eta) * g;
        out[1] = a * (eta * dl_dc + (1.0 - eta) * dg_dc);
        out[2] = a * (eta * dl_ds + (1.0 - eta) * dg_ds);
        out[3] = if in_range { a * (l - g) } else { 0.0 };
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
    use approx::assert_relative_eq;

    #[test]
    fn pure_gaussian_at_eta_zero() {
        // fraction=0 → pure Gaussian, value at center = amplitude
        let v = PseudoVoigt.eval(&[0.0], &[3.0, 0.0, 1.0, 0.0]);
        assert_relative_eq!(v, 3.0, epsilon = 1e-12);
    }

    #[test]
    fn pure_lorentzian_at_eta_one() {
        // fraction=1 → pure Lorentzian, value at center = amplitude
        let v = PseudoVoigt.eval(&[0.0], &[3.0, 0.0, 1.0, 1.0]);
        assert_relative_eq!(v, 3.0, epsilon = 1e-12);
    }

    #[test]
    fn jacobian_shape() {
        let j = PseudoVoigt.jacobian(&[0.5], &[1.0, 0.0, 1.0, 0.5]);
        assert_eq!(j.len(), 4);
    }

    #[test]
    fn jacobian_finite_diff_check() {
        let p = [2.0, 0.3, 0.9, 0.4];
        let x = [0.1];
        let j_anal = PseudoVoigt.jacobian(&x, &p);
        let h = 1e-5;
        for (i, &ja) in j_anal.iter().enumerate() {
            let mut pp = p;
            pp[i] += h;
            let fd = (PseudoVoigt.eval(&x, &pp) - PseudoVoigt.eval(&x, &p)) / h;
            assert_relative_eq!(ja, fd, epsilon = 1e-4);
        }
    }

    #[test]
    fn fraction_clamped_to_unit_interval() {
        // fraction > 1 behaves as fraction = 1 (pure Lorentzian); fraction < 0 as 0.
        let over = PseudoVoigt.eval(&[0.7], &[2.5, 0.0, 1.3, 1.3]);
        let one = PseudoVoigt.eval(&[0.7], &[2.5, 0.0, 1.3, 1.0]);
        assert_relative_eq!(over, one, epsilon = 1e-12);
        let under = PseudoVoigt.eval(&[0.7], &[2.5, 0.0, 1.3, -0.4]);
        let zero = PseudoVoigt.eval(&[0.7], &[2.5, 0.0, 1.3, 0.0]);
        assert_relative_eq!(under, zero, epsilon = 1e-12);
        // ∂/∂fraction is zero outside the clamp (output is flat in fraction there).
        let j = PseudoVoigt.jacobian(&[0.7], &[2.5, 0.0, 1.3, 1.3]);
        assert_relative_eq!(j[3], 0.0, epsilon = 1e-12);
    }

    #[test]
    fn da_at_center() {
        // ∂/∂amplitude at center: G=1, L=1 → da = eta + (1-eta) = 1
        let j = PseudoVoigt.jacobian(&[0.0], &[1.0, 0.0, 1.0, 0.5]);
        assert_relative_eq!(j[0], 1.0, epsilon = 1e-12);
    }
}
