use crate::Model;

/// Student's-t peak: `A / (1 + ((x − c)/σ)²/ν)^((ν+1)/2)`.
///
/// Parameters (in order): `[amplitude, center, sigma, nu]`. `amplitude` is the peak height
/// at `x == center`; `nu` is the degrees-of-freedom (ν→∞ Gaussian, small ν heavy tails).
/// numpy oracle identical: `A / (1 + ((x-c)/σ)**2/ν)**((ν+1)/2)`.
pub struct StudentsT;

impl Model for StudentsT {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let (a, c, sigma, nu) = (params[0], params[1], params[2], params[3]);
        let z = (x[0] - c) / sigma;
        a / (1.0 + z * z / nu).powf((nu + 1.0) / 2.0)
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
        vec![
            "amplitude".into(),
            "center".into(),
            "sigma".into(),
            "nu".into(),
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn eval_at_center_equals_amplitude() {
        assert_relative_eq!(
            StudentsT.eval(&[1.5], &[3.0, 1.5, 0.8, 3.0]),
            3.0,
            epsilon = 1e-12
        );
    }

    #[test]
    fn param_names_and_jacobian() {
        assert_eq!(
            StudentsT
                .param_names()
                .iter()
                .map(|c| c.as_ref())
                .collect::<Vec<_>>(),
            &["amplitude", "center", "sigma", "nu"]
        );
        let j = StudentsT.jacobian(&[1.5], &[3.0, 1.5, 0.8, 3.0]);
        assert_eq!(j.len(), 4);
        assert_relative_eq!(j[0], 1.0, epsilon = 1e-6);
    }
}
