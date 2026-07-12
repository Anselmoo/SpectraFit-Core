use crate::Model;

/// Tauc optical band-gap edge: `A · ((x − e_gap) · H(x − e_gap))^p`.
///
/// Parameters (in order): `[amplitude, e_gap, exponent]`
///
/// - `amplitude` (`A`) scales the absorption above the gap.
/// - `e_gap` is the optical band-gap energy: the edge onset. Below it the model is
///   exactly `0` (Heaviside `H(x − e_gap)`); at and above it the absorption rises as a
///   power law in the excess energy `(x − e_gap)`.
/// - `exponent` (`p`) is the Tauc power (`p = 2` for an allowed indirect transition,
///   `p = 1/2` for an allowed direct one). The classic Tauc plot fits `(α·hν)^{1/p}`
///   linearly in `hν`; here we expose the forward edge `A·(hν − E_g)^p` directly.
///
/// The kernel is `0` for `x ≤ e_gap` (where the base `(x − e_gap)` is non-positive and
/// a fractional `exponent` would otherwise be NaN). The numpy benchmark formula is
/// identical — `np.where(x > e_gap, A·(x − e_gap)^p, 0)` — so numpy↔Rust parity is exact.
pub struct Tauc;

impl Model for Tauc {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, e_gap, exponent) = (params[0], params[1], params[2]);
        let excess = x[0] - e_gap;
        if excess > 0.0 {
            a * excess.powf(exponent)
        } else {
            0.0
        }
    }

    /// Central finite-difference Jacobian. The Heaviside cut-off makes the closed-form
    /// derivative piecewise (and the power law's `∂/∂e_gap` diverges as `x → e_gap⁺` for
    /// `exponent < 1`), so a numerical Jacobian is used — matching `log_normal`.
    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let mut p = params.to_vec();
        (0..params.len())
            .map(|i| {
                let h = 1e-7_f64 * params[i].abs().max(1e-7);
                p[i] = params[i] + h;
                let f_plus = self.eval(x, &p);
                p[i] = params[i] - h;
                let f_minus = self.eval(x, &p);
                p[i] = params[i];
                (f_plus - f_minus) / (2.0 * h)
            })
            .collect()
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["amplitude".into(), "e_gap".into(), "exponent".into()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn below_gap_is_zero() {
        let m = Tauc;
        assert_eq!(m.eval(&[1.0], &[2.0, 1.5, 2.0]), 0.0);
        assert_eq!(m.eval(&[1.5], &[2.0, 1.5, 2.0]), 0.0); // exactly at the gap
    }

    #[test]
    fn above_gap_power_law() {
        // (x − e_gap) = 2.0, p = 2 ⇒ A·4.0.
        let m = Tauc;
        assert_relative_eq!(m.eval(&[3.5], &[2.0, 1.5, 2.0]), 2.0 * 4.0, epsilon = 1e-12);
    }

    #[test]
    fn param_names_are_canonical() {
        assert_eq!(
            Tauc.param_names().iter().map(|c| c.as_ref()).collect::<Vec<_>>(),
            &["amplitude", "e_gap", "exponent"]
        );
    }

    #[test]
    fn jacobian_shape_and_amplitude() {
        let m = Tauc;
        let j = m.jacobian(&[3.5], &[2.0, 1.5, 2.0]);
        assert_eq!(j.len(), 3);
        // ∂/∂amplitude above the gap is (x − e_gap)^p = 4.0.
        assert_relative_eq!(j[0], 4.0, epsilon = 1e-6);
    }
}
