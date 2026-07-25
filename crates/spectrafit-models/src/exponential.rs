use crate::math_backend::batch_exp;
use crate::Model;

/// Double-exponential decay: `A1·exp(-λ1·x) + A2·exp(-λ2·x)`
///
/// Parameters (in order): `[A1, lam1, A2, lam2]`
pub struct DoubleExponential;

impl Model for DoubleExponential {
    fn eval(&self, x: &[f64], p: &[f64]) -> f64 {
        let xi = x[0];
        p[0] * (-p[1] * xi).exp() + p[2] * (-p[3] * xi).exp()
    }

    fn jacobian_into(&self, x: &[f64], p: &[f64], out: &mut [f64]) {
        let xi = x[0];
        let e1 = (-p[1] * xi).exp();
        let e2 = (-p[3] * xi).exp();
        out[0] = e1; // ∂/∂A1
        out[1] = -p[0] * xi * e1; // ∂/∂lam1
        out[2] = e2; // ∂/∂A2
        out[3] = -p[2] * xi * e2; // ∂/∂lam2
    }

    fn jacobian(&self, x: &[f64], p: &[f64]) -> Vec<f64> {
        let xi = x[0];
        let e1 = (-p[1] * xi).exp();
        let e2 = (-p[3] * xi).exp();
        vec![e1, -p[0] * xi * e1, e2, -p[2] * xi * e2]
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["A1".into(), "lam1".into(), "A2".into(), "lam2".into()]
    }

    fn eval_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        assert_eq!(out.len(), xs.len());
        let (a1, lam1, a2, lam2) = (params[0], params[1], params[2], params[3]);
        // Compute exp arguments for each component separately then sum.
        let args1: Vec<f64> = xs.iter().map(|xi| -lam1 * xi).collect();
        let args2: Vec<f64> = xs.iter().map(|xi| -lam2 * xi).collect();
        let mut e1 = vec![0.0_f64; xs.len()];
        let mut e2 = vec![0.0_f64; xs.len()];
        batch_exp(&mut e1, &args1);
        batch_exp(&mut e2, &args2);
        for ((slot, v1), v2) in out.iter_mut().zip(e1.iter()).zip(e2.iter()) {
            *slot = a1 * v1 + a2 * v2;
        }
    }

    fn jac_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        assert_eq!(out.len(), xs.len() * 4);
        let (a1, lam1, a2, lam2) = (params[0], params[1], params[2], params[3]);
        let n = xs.len();
        let args1: Vec<f64> = xs.iter().map(|xi| -lam1 * xi).collect();
        let args2: Vec<f64> = xs.iter().map(|xi| -lam2 * xi).collect();
        let mut e1 = vec![0.0_f64; n];
        let mut e2 = vec![0.0_f64; n];
        batch_exp(&mut e1, &args1);
        batch_exp(&mut e2, &args2);
        for (i, xi) in xs.iter().enumerate() {
            out[i * 4] = e1[i]; // ∂/∂A1
            out[i * 4 + 1] = -a1 * xi * e1[i]; // ∂/∂lam1
            out[i * 4 + 2] = e2[i]; // ∂/∂A2
            out[i * 4 + 3] = -a2 * xi * e2[i]; // ∂/∂lam2
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    fn model() -> DoubleExponential {
        DoubleExponential
    }

    // A1=2, lam1=0.5, A2=1, lam2=2 at x=0: 2*1 + 1*1 = 3
    #[test]
    fn eval_at_zero() {
        let v = model().eval(&[0.0], &[2.0, 0.5, 1.0, 2.0]);
        assert_relative_eq!(v, 3.0, epsilon = 1e-12);
    }

    #[test]
    fn jacobian_shape() {
        let j = model().jacobian(&[1.0], &[2.0, 0.5, 1.0, 2.0]);
        assert_eq!(j.len(), 4);
    }

    #[test]
    fn jacobian_numerical_a1() {
        let x = &[1.0f64];
        let p = [2.0, 0.5, 1.0, 2.0];
        let h = 1e-6;
        let mut pp = p;
        pp[0] += h;
        let fd = (model().eval(x, &pp) - model().eval(x, &p)) / h;
        let j = model().jacobian(x, &p);
        assert_relative_eq!(j[0], fd, epsilon = 1e-5);
    }

    #[test]
    fn jacobian_numerical_lam1() {
        let x = &[1.0f64];
        let p = [2.0, 0.5, 1.0, 2.0];
        let h = 1e-6;
        let mut pp = p;
        pp[1] += h;
        let fd = (model().eval(x, &pp) - model().eval(x, &p)) / h;
        let j = model().jacobian(x, &p);
        assert_relative_eq!(j[1], fd, epsilon = 1e-5);
    }

    #[test]
    fn jacobian_numerical_a2() {
        let x = &[1.0f64];
        let p = [2.0, 0.5, 1.0, 2.0];
        let h = 1e-6;
        let mut pp = p;
        pp[2] += h;
        let fd = (model().eval(x, &pp) - model().eval(x, &p)) / h;
        let j = model().jacobian(x, &p);
        assert_relative_eq!(j[2], fd, epsilon = 1e-5);
    }

    #[test]
    fn jacobian_numerical_lam2() {
        let x = &[1.0f64];
        let p = [2.0, 0.5, 1.0, 2.0];
        let h = 1e-6;
        let mut pp = p;
        pp[3] += h;
        let fd = (model().eval(x, &pp) - model().eval(x, &p)) / h;
        let j = model().jacobian(x, &p);
        assert_relative_eq!(j[3], fd, epsilon = 1e-5);
    }

    #[test]
    fn eval_slice_matches_scalar() {
        let xs: Vec<f64> = (0..10).map(|i| i as f64 * 0.5).collect();
        let p = [2.0, 0.5, 1.0, 2.0];
        let mut out = vec![0.0_f64; xs.len()];
        model().eval_slice_into(&xs, &p, &mut out);
        for (xi, &bi) in xs.iter().zip(out.iter()) {
            assert_relative_eq!(bi, model().eval(&[*xi], &p), epsilon = 1e-10);
        }
    }

    #[test]
    fn jac_slice_matches_scalar() {
        let xs: Vec<f64> = (0..8).map(|i| i as f64 * 0.5).collect();
        let p = [2.0, 0.5, 1.0, 2.0];
        let n = xs.len();
        let mut out = vec![0.0_f64; n * 4];
        model().jac_slice_into(&xs, &p, &mut out);
        for (i, xi) in xs.iter().enumerate() {
            let j = model().jacobian(&[*xi], &p);
            for k in 0..4 {
                assert_relative_eq!(out[i * 4 + k], j[k], epsilon = 1e-10);
            }
        }
    }
}
