use crate::Model;

/// Driven damped harmonic-oscillator IR absorption: `A / ((c² − x²)² + (σ·x)²)`.
///
/// Parameters (in order): `[amplitude, center, sigma]` — `center` is the resonance frequency,
/// `sigma` the damping; `amplitude` is a scale (peak ≠ A). Reuses the canonical
/// amplitude/center/sigma names. numpy oracle identical: `A / ((c**2 - x**2)**2 + (σ*x)**2)`.
pub struct HarmonicIr;

impl Model for HarmonicIr {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, c, sigma) = (params[0], params[1], params[2]);
        let d = c * c - x[0] * x[0];
        a / (d * d + (sigma * x[0]) * (sigma * x[0]))
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
        vec!["amplitude".into(), "center".into(), "sigma".into()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn eval_at_resonance() {
        // At x == center: A / ((0)² + (σ·c)²) = A / (σ·c)². With A=1,c=2,σ=0.5 → 1/1 = 1.
        assert_relative_eq!(
            HarmonicIr.eval(&[2.0], &[1.0, 2.0, 0.5]),
            1.0,
            epsilon = 1e-12
        );
    }

    #[test]
    fn param_names_and_jacobian() {
        assert_eq!(
            HarmonicIr.param_names().iter().map(|c| c.as_ref()).collect::<Vec<_>>(),
            &["amplitude", "center", "sigma"]
        );
        assert_eq!(HarmonicIr.jacobian(&[1.0], &[1.0, 2.0, 0.5]).len(), 3);
    }

    // ----- Limiting-case asymptotic (ground-truth verification, Cycle 4) -----
    //
    // The undamped limit (σ = 0) reduces to a closed-form rational:
    //
    //     HarmonicIr(A, c, σ=0)  =  A / (c² − x²)²   for x ≠ ±c
    //
    // The denominator vanishes at x = ±c (the resonance), so test only at
    // off-resonance points. Catches: wrong squaring of the damping term,
    // missing parenthesization that would couple σ into the undamped form.

    #[test]
    fn sigma_zero_undamped_matches_closed_form() {
        let m = HarmonicIr;
        let a = 2.0_f64;
        let c = 1.5_f64;
        let p = [a, c, 0.0]; // undamped
        for &xi in &[0.5_f64, 1.0, 2.0, 3.0, 5.0] {
            let d = c * c - xi * xi;
            let expected = a / (d * d);
            assert_relative_eq!(m.eval(&[xi], &p), expected, epsilon = 1e-12);
        }
    }
}
