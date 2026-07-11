use crate::Model;

/// Split Pearson VII: a Pearson VII with a different width AND exponent on each side.
///
/// `f(x) = A / [1 + ((x − c)/σ_i)²·(2^{1/m_i} − 1)]^{m_i}`, with `(σ_i, m_i) = (σ_L, m_L)`
/// for `x < c`, else `(σ_R, m_R)`.
///
/// Parameters (in order): `[amplitude, center, sigma_l, sigma_r, m_l, m_r]`. `amplitude` is
/// the peak height at `x == center` (continuous: both branches give `A` there). numpy oracle
/// identical via `np.where(x < c, left, right)`.
pub struct SplitPearson7;

fn p7(a: f64, z: f64, m: f64) -> f64 {
    a / (1.0 + z * z * (2.0_f64.powf(1.0 / m) - 1.0)).powf(m)
}

impl Model for SplitPearson7 {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, c, sl, sr, ml, mr) = (
            params[0], params[1], params[2], params[3], params[4], params[5],
        );
        if x[0] < c {
            p7(a, (x[0] - c) / sl, ml)
        } else {
            p7(a, (x[0] - c) / sr, mr)
        }
    }

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
        vec!["amplitude".into(), "center".into(), "sigma_l".into(), "sigma_r".into(), "m_l".into(), "m_r".into()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn eval_at_center_equals_amplitude() {
        let v = SplitPearson7.eval(&[1.5], &[3.0, 1.5, 0.6, 1.2, 2.0, 3.0]);
        assert_relative_eq!(v, 3.0, epsilon = 1e-12);
    }

    #[test]
    fn param_names_and_jacobian() {
        assert_eq!(
            SplitPearson7.param_names().iter().map(|c| c.as_ref()).collect::<Vec<_>>(),
            &["amplitude", "center", "sigma_l", "sigma_r", "m_l", "m_r"]
        );
        let j = SplitPearson7.jacobian(&[1.0], &[3.0, 1.5, 0.6, 1.2, 2.0, 3.0]);
        assert_eq!(j.len(), 6);
    }

    // ----- Limiting-case asymptotic (ground-truth verification, Cycle 3) -----
    //
    // SplitPearson7 reduces to a plain (symmetric) Pearson VII when
    // σ_l = σ_r and m_l = m_r:
    //
    //     A / [1 + ε²·(2^(1/m) − 1)]^m   uniformly for x < c and x ≥ c
    //
    // Verify against the plain Pearson7 kernel across symmetric x points.

    #[test]
    fn symmetric_widths_and_exponents_equal_plain_pearson7() {
        use crate::pearson7::Pearson7;
        let split = SplitPearson7;
        let plain = Pearson7;
        let sigma = 0.7_f64;
        let m = 2.3_f64;
        let a = 4.2_f64;
        let c = 0.3_f64;
        let p_split = [a, c, sigma, sigma, m, m]; // symmetric collapse
        let p_plain = [a, c, sigma, m];
        for &xi in &[-1.5_f64, -0.3, c, 0.5, 1.5] {
            assert_relative_eq!(
                split.eval(&[xi], &p_split),
                plain.eval(&[xi], &p_plain),
                epsilon = 1e-12
            );
        }
    }
}
