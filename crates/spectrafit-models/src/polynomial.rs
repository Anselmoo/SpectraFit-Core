use crate::Model;

/// Constant model: `f(x) = c`
///
/// Parameters (in order): `[c]`
pub struct Constant;

impl Model for Constant {
    fn eval(&self, _x: &[f64], params: &[f64]) -> f64 {
        params[0]
    }

    fn jacobian(&self, _x: &[f64], _params: &[f64]) -> Vec<f64> {
        vec![1.0]
    }

    #[inline]
    fn jacobian_into(&self, _x: &[f64], _params: &[f64], out: &mut [f64]) {
        out[0] = 1.0;
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["c".into()]
    }
}

/// Linear model: `f(x) = slope * x₀ + intercept`
///
/// Parameters (in order): `[slope, intercept]`
pub struct Linear;

impl Model for Linear {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        params[0] * x[0] + params[1]
    }

    fn jacobian(&self, x: &[f64], _params: &[f64]) -> Vec<f64> {
        vec![x[0], 1.0]
    }

    #[inline]
    fn jacobian_into(&self, x: &[f64], _params: &[f64], out: &mut [f64]) {
        out[0] = x[0];
        out[1] = 1.0;
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["slope".into(), "intercept".into()]
    }
}

/// Quadratic bowl model: `f(x) = amplitude · (x₀ − center)² + offset`
///
/// A convex parabola used for the `convex_baseline` benchmark family (clean
/// quadratic objectives). Summing several of these nodes builds a sum-of-squares
/// landscape; pairing one with a `Linear` node gives a tilted bowl.
///
/// Parameters (in order): `[amplitude, center, offset]`
pub struct Quadratic;

impl Model for Quadratic {
    fn eval(&self, x: &[f64], params: &[f64]) -> f64 {
        let d = x[0] - params[1];
        params[0] * d * d + params[2]
    }

    fn jacobian(&self, x: &[f64], params: &[f64]) -> Vec<f64> {
        let d = x[0] - params[1];
        // ∂/∂amplitude = d²; ∂/∂center = −2·A·d; ∂/∂offset = 1
        vec![d * d, -2.0 * params[0] * d, 1.0]
    }

    #[inline]
    fn jacobian_into(&self, x: &[f64], params: &[f64], out: &mut [f64]) {
        let d = x[0] - params[1];
        out[0] = d * d;
        out[1] = -2.0 * params[0] * d;
        out[2] = 1.0;
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["amplitude".into(), "center".into(), "offset".into()]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    #[test]
    fn constant_eval() {
        let c = Constant;
        assert_relative_eq!(c.eval(&[99.0], &[5.0]), 5.0, epsilon = 1e-12);
    }

    #[test]
    fn constant_jacobian() {
        let c = Constant;
        let j = c.jacobian(&[1.0], &[5.0]);
        assert_eq!(j.len(), 1);
        assert_relative_eq!(j[0], 1.0, epsilon = 1e-12);
    }

    #[test]
    fn linear_eval() {
        let l = Linear;
        // slope=3, intercept=1, x=2 → 3*2+1 = 7
        assert_relative_eq!(l.eval(&[2.0], &[3.0, 1.0]), 7.0, epsilon = 1e-12);
    }

    #[test]
    fn linear_jacobian_shape() {
        let l = Linear;
        let j = l.jacobian(&[2.0], &[3.0, 1.0]);
        assert_eq!(j.len(), 2);
    }

    #[test]
    fn linear_jacobian_values() {
        let l = Linear;
        // jac[0] = x₀ = 2.0; jac[1] = 1.0
        let j = l.jacobian(&[2.0], &[3.0, 1.0]);
        assert_relative_eq!(j[0], 2.0, epsilon = 1e-12);
        assert_relative_eq!(j[1], 1.0, epsilon = 1e-12);
    }

    #[test]
    fn linear_eval_at_zero() {
        let l = Linear;
        // x=0 → intercept only
        assert_relative_eq!(l.eval(&[0.0], &[5.0, 3.0]), 3.0, epsilon = 1e-12);
    }

    #[test]
    fn quadratic_eval() {
        let q = Quadratic;
        // A=2, c=0.5, b=0.3, x=2 → 2*(1.5)^2 + 0.3 = 4.8
        assert_relative_eq!(q.eval(&[2.0], &[2.0, 0.5, 0.3]), 4.8, epsilon = 1e-12);
        // at the vertex x=c the bowl equals the offset
        assert_relative_eq!(q.eval(&[0.5], &[2.0, 0.5, 0.3]), 0.3, epsilon = 1e-12);
    }

    #[test]
    fn quadratic_jacobian_matches_numerical() {
        let q = Quadratic;
        let params = [1.8, 0.4, -0.2];
        let x = [1.3];
        let analytic = q.jacobian(&x, &params);
        let h = 1e-6;
        for i in 0..params.len() {
            let mut pp = params;
            let mut pm = params;
            pp[i] += h;
            pm[i] -= h;
            let num = (q.eval(&x, &pp) - q.eval(&x, &pm)) / (2.0 * h);
            assert_relative_eq!(analytic[i], num, epsilon = 1e-6);
        }
    }
}
