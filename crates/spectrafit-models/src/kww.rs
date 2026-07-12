use crate::Model;

/// Kohlrausch–Williams–Watts (KWW) stretched exponential: `A · exp(−(x/τ)^β)`.
///
/// Parameters (in order): `[amplitude, tau, beta]`
///
/// - `amplitude` (`A`) is the value at `x == 0` (where `(0/τ)^β = 0` ⇒ `exp(0) = 1`).
/// - `tau` (`τ > 0`) is the characteristic relaxation time.
/// - `beta` (`0 < β ≤ 1`) is the stretching exponent: `β = 1` recovers a plain
///   exponential, `β < 1` gives a stretched (multi-timescale) relaxation.
///
/// Defined for `x ≥ 0`. For `x < 0` the base `x/τ` is negative and a fractional `β`
/// would yield a NaN, so the kernel returns `0.0` there. The numpy benchmark formula is
/// identical — `np.where(x >= 0, A·exp(−(x/τ)^β), 0)` — so numpy↔Rust parity is exact.
pub struct Kww;

impl Model for Kww {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, tau, beta) = (params[0], params[1], params[2]);
        if x[0] >= 0.0 {
            a * (-(x[0] / tau).powf(beta)).exp()
        } else {
            0.0
        }
    }

    /// Central finite-difference Jacobian. `∂/∂β` involves `ln(x/τ)` which diverges as
    /// `x → 0⁺`, so a numerical Jacobian is used (matching `log_normal`).
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
        vec!["amplitude".into(), "tau".into(), "beta".into()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn value_at_zero_equals_amplitude() {
        // (0/τ)^β = 0 ⇒ exp(0) = 1 ⇒ value == amplitude.
        let m = Kww;
        assert_relative_eq!(m.eval(&[0.0], &[3.0, 2.0, 0.7]), 3.0, epsilon = 1e-12);
    }

    #[test]
    fn beta_one_is_plain_exponential() {
        // β = 1 ⇒ A·exp(−x/τ). At x = τ that is A·exp(−1).
        let m = Kww;
        assert_relative_eq!(
            m.eval(&[2.0], &[3.0, 2.0, 1.0]),
            3.0 * (-1.0_f64).exp(),
            epsilon = 1e-12
        );
    }

    #[test]
    fn negative_x_is_zero() {
        let m = Kww;
        assert_eq!(m.eval(&[-1.0], &[3.0, 2.0, 0.7]), 0.0);
    }

    #[test]
    fn param_names_are_canonical() {
        assert_eq!(
            Kww.param_names().iter().map(|c| c.as_ref()).collect::<Vec<_>>(),
            &["amplitude", "tau", "beta"]
        );
    }

    #[test]
    fn jacobian_shape_and_amplitude() {
        let m = Kww;
        let j = m.jacobian(&[2.0], &[3.0, 2.0, 0.7]);
        assert_eq!(j.len(), 3);
        // ∂/∂amplitude = exp(−(x/τ)^β).
        let expected = (-(2.0_f64 / 2.0).powf(0.7)).exp();
        assert_relative_eq!(j[0], expected, epsilon = 1e-6);
    }

    // ----- Limiting-case asymptotic (ground-truth verification, Cycle 3) -----
    //
    // KWW reduces to a plain single exponential when β = 1:
    //
    //     A · exp(−(x/τ)^β)  with β = 1  ≡  A · exp(−x/τ)
    //
    // Test at several x to pin the identity, not just the happy-path point.

    #[test]
    fn beta_one_equals_single_exponential() {
        let m = Kww;
        let a = 2.5_f64;
        let tau = 1.7_f64;
        let p = [a, tau, 1.0]; // β = 1 collapse
        for &xi in &[0.0_f64, 0.5, 1.0, 2.0, 5.0] {
            let kww_val = m.eval(&[xi], &p);
            let single_exp = a * (-xi / tau).exp();
            assert_relative_eq!(kww_val, single_exp, epsilon = 1e-12);
        }
    }
}
