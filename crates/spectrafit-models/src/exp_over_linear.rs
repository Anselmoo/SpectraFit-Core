use crate::Model;

/// Exponential decay divided by a line.
///
/// ```text
/// y = exp(−rate·x) / (lin_const + lin_slope·x)
/// ```
///
/// Parameters (in order): `[rate, lin_const, lin_slope]`
///
/// This is the NIST StRD Chwirut model, shared by two datasets: Chwirut1 (214
/// observations) and Chwirut2 (54), which differ only in the data.
///
/// **Domain guard:** the denominator must be non-zero. Unlike a quadratic
/// denominator this one has a single root at `x = −lin_const/lin_slope`, which a
/// solver can walk onto during search even when the certified parameters keep it
/// clear of the data, so `D = 0` returns `f64::NAN`.
///
/// **Analytic Jacobian** (let `E = exp(−rate·x)`, `D = lin_const + lin_slope·x`):
/// - ∂y/∂rate      = −x·E / D
/// - ∂y/∂lin_const = −E / D²
/// - ∂y/∂lin_slope   = −x·E / D²
pub struct ExpOverLinear;

#[inline]
fn ed(xi: f64, p: &[f64]) -> (f64, f64) {
    ((-p[0] * xi).exp(), p[1] + p[2] * xi)
}

#[inline]
fn jac_at(xi: f64, p: &[f64], out: &mut [f64]) {
    let (e, d) = ed(xi, p);
    if d == 0.0 {
        out[..3].fill(f64::NAN);
        return;
    }
    let inv_d = 1.0 / d;
    let e_over_d2 = e * inv_d * inv_d;
    out[0] = -xi * e * inv_d;
    out[1] = -e_over_d2;
    out[2] = -xi * e_over_d2;
}

impl Model for ExpOverLinear {
    fn eval(&self, x: &[f64], p: &[f64]) -> f64 {
        let (e, d) = ed(x[0], p);
        if d == 0.0 {
            return f64::NAN;
        }
        e / d
    }

    fn jacobian_into(&self, x: &[f64], p: &[f64], out: &mut [f64]) {
        jac_at(x[0], p, out);
    }

    fn jacobian(&self, x: &[f64], p: &[f64]) -> Vec<f64> {
        let mut out = vec![0.0_f64; 3];
        jac_at(x[0], p, &mut out);
        out
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec!["rate".into(), "lin_const".into(), "lin_slope".into()]
    }

    fn eval_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        debug_assert_eq!(out.len(), xs.len());
        for (slot, &xi) in out.iter_mut().zip(xs.iter()) {
            let (e, d) = ed(xi, params);
            *slot = if d == 0.0 { f64::NAN } else { e / d };
        }
    }

    fn jac_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        debug_assert_eq!(out.len(), xs.len() * 3);
        for (i, &xi) in xs.iter().enumerate() {
            jac_at(xi, params, &mut out[i * 3..i * 3 + 3]);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    fn model() -> ExpOverLinear {
        ExpOverLinear
    }

    // Chwirut2's certified values.
    const CHWIRUT: [f64; 3] = [1.6657666537e-01, 5.1653291286e-03, 1.2150007096e-02];

    // Anchored on the certified fit, not the observations: at these parameters the
    // model reproduces Chwirut2's certified residual sum of squares (5.130480e2)
    // exactly. The data scatters widely about it (92.9 observed against 81.86
    // fitted at x=0.5), so an observation-anchored test measures the scatter.
    #[test]
    fn eval_chwirut_reproduces_the_certified_fit() {
        assert_relative_eq!(
            model().eval(&[0.5], &CHWIRUT),
            81.855_746_144_55,
            max_relative = 1e-10
        );
        assert_relative_eq!(model().eval(&[6.0], &CHWIRUT), 4.715_0, max_relative = 1e-3);
    }

    #[test]
    fn zero_denominator_returns_nan() {
        // D = lin_const + lin_slope·x = 0 at x = 1 when lin_const = -lin_slope.
        let p = [0.1_f64, -1.0, 1.0];
        assert!(model().eval(&[1.0], &p).is_nan());
        assert!(model().jacobian(&[1.0], &p).iter().all(|v| v.is_nan()));
    }

    #[test]
    fn jacobian_matches_finite_difference() {
        // Already a central difference; widened from one regime/x-point to
        // three regimes and several x-points (avoiding D = lin_const +
        // lin_slope·x = 0, the domain-guard boundary), and tightened epsilon
        // from 1e-6 toward 1e-7.
        let param_sets = [
            CHWIRUT,                // certified Chwirut2 fit (nominal)
            [1e-3_f64, 1e-2, 1e-3], // small rate/slope
            [5.0_f64, -2.0, 8.0],   // large rate, offset/steep line
        ];
        for p in param_sets {
            for &x in &[0.1_f64, 0.5, 2.5, 6.0, 12.0] {
                let j = model().jacobian(&[x], &p);
                for k in 0..3 {
                    let h = 1e-6 * p[k].abs().max(1.0);
                    let mut pp = p;
                    pp[k] += h;
                    let mut pm = p;
                    pm[k] -= h;
                    let fd = (model().eval(&[x], &pp) - model().eval(&[x], &pm)) / (2.0 * h);
                    assert_relative_eq!(j[k], fd, max_relative = 1e-6, epsilon = 1e-7);
                }
            }
        }
    }

    #[test]
    fn slices_match_scalar() {
        let xs = [0.5_f64, 1.0, 3.0, 6.0];
        let mut ys = vec![0.0_f64; xs.len()];
        model().eval_slice_into(&xs, &CHWIRUT, &mut ys);
        let mut js = vec![0.0_f64; xs.len() * 3];
        model().jac_slice_into(&xs, &CHWIRUT, &mut js);
        for (i, &xi) in xs.iter().enumerate() {
            assert_relative_eq!(ys[i], model().eval(&[xi], &CHWIRUT), epsilon = 1e-12);
            let j = model().jacobian(&[xi], &CHWIRUT);
            for k in 0..3 {
                assert_relative_eq!(js[i * 3 + k], j[k], epsilon = 1e-12);
            }
        }
    }
}
