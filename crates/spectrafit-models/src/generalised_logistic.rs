use crate::Model;

/// Generalised logistic (Richards) curve.
///
/// ```text
/// y = amplitude / (1 + exp(shift − rate·x))^(1/shape)
/// ```
///
/// Parameters (in order): `[amplitude, shift, rate, shape]`
///
/// One kernel covers two NIST StRD datasets, because the plain logistic is this
/// form at `shape = 1`:
/// - Rat43 is the full four-parameter Richards curve.
/// - Rat42 is `b1/(1 + exp(b2 − b3·x))`: hold `shape` fixed at 1 and the other
///   three map straight onto NIST's b1..b3.
///
/// **Domain guard:** `shape` must be non-zero, and `1 + exp(...)` is always > 1 so
/// the power is well defined for finite arguments. A zero `shape` returns
/// `f64::NAN` rather than an infinity, so the solver backs off instead of
/// poisoning the residual vector.
///
/// **Analytic Jacobian** (let `u = exp(shift − rate·x)`, `s = 1 + u`, `q = s^(−1/shape)`):
/// - ∂y/∂amplitude = q
/// - ∂y/∂shift     = −amplitude·q·u / (shape·s)
/// - ∂y/∂rate      =  amplitude·q·u·x / (shape·s)
/// - ∂y/∂shape     =  amplitude·q·ln(s) / shape²
pub struct GeneralisedLogistic;

#[inline]
fn parts(xi: f64, p: &[f64]) -> (f64, f64, f64) {
    let u = (p[1] - p[2] * xi).exp();
    let s = 1.0 + u;
    let q = s.powf(-1.0 / p[3]);
    (u, s, q)
}

#[inline]
fn jac_at(xi: f64, p: &[f64], out: &mut [f64]) {
    if p[3] == 0.0 {
        out[..4].fill(f64::NAN);
        return;
    }
    let (u, s, q) = parts(xi, p);
    let common = p[0] * q * u / (p[3] * s);
    out[0] = q;
    out[1] = -common;
    out[2] = common * xi;
    out[3] = p[0] * q * s.ln() / (p[3] * p[3]);
}

impl Model for GeneralisedLogistic {
    fn eval(&self, x: &[f64], p: &[f64]) -> f64 {
        if p[3] == 0.0 {
            return f64::NAN;
        }
        parts(x[0], p).2 * p[0]
    }

    fn jacobian_into(&self, x: &[f64], p: &[f64], out: &mut [f64]) {
        jac_at(x[0], p, out);
    }

    fn jacobian(&self, x: &[f64], p: &[f64]) -> Vec<f64> {
        let mut out = vec![0.0_f64; 4];
        jac_at(x[0], p, &mut out);
        out
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec![
            "amplitude".into(),
            "shift".into(),
            "rate".into(),
            "shape".into(),
        ]
    }

    fn eval_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        debug_assert_eq!(out.len(), xs.len());
        for (slot, &xi) in out.iter_mut().zip(xs.iter()) {
            *slot = if params[3] == 0.0 {
                f64::NAN
            } else {
                params[0] * parts(xi, params).2
            };
        }
    }

    fn jac_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        debug_assert_eq!(out.len(), xs.len() * 4);
        for (i, &xi) in xs.iter().enumerate() {
            jac_at(xi, params, &mut out[i * 4..i * 4 + 4]);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    fn model() -> GeneralisedLogistic {
        GeneralisedLogistic
    }

    // Rat43's certified values.
    const RAT43: [f64; 4] = [
        6.9964151270e02,
        5.2771253025e00,
        7.5962938329e-01,
        1.2792483859e00,
    ];

    // Anchored on the certified fit, not the observations: at these parameters the
    // model reproduces Rat43's certified residual sum of squares (8.786405e3)
    // exactly. The endpoints are where that fit sits furthest from the data
    // (20.30 against an observed 16.08 at x=1), so an observation-anchored test
    // would be measuring the dataset's scatter rather than the kernel.
    #[test]
    fn eval_rat43_reproduces_the_certified_fit() {
        assert_relative_eq!(
            model().eval(&[1.0], &RAT43),
            20.301_882_778_86,
            max_relative = 1e-10
        );
        assert_relative_eq!(
            model().eval(&[15.0], &RAT43),
            698.438_251,
            max_relative = 1e-6
        );
    }

    #[test]
    fn shape_one_is_the_plain_logistic() {
        // Rat42's form: amplitude / (1 + exp(shift − rate·x)).
        let p = [72.0_f64, 2.6, 0.067, 1.0];
        for x in [9.0, 30.0, 80.0] {
            let want = p[0] / (1.0 + (p[1] - p[2] * x).exp());
            assert_relative_eq!(model().eval(&[x], &p), want, max_relative = 1e-12);
        }
    }

    #[test]
    fn zero_shape_returns_nan() {
        let p = [1.0_f64, 0.5, 0.5, 0.0];
        assert!(model().eval(&[1.0], &p).is_nan());
        assert!(model().jacobian(&[1.0], &p).iter().all(|v| v.is_nan()));
    }

    #[test]
    fn jacobian_matches_finite_difference() {
        // Already a central difference; widened from one regime/x-point to
        // three regimes and several x-points (shape kept away from 0, the
        // domain-guard boundary).
        let param_sets = [
            RAT43,                      // certified Rat43 fit (nominal)
            [1e-3_f64, 0.0, 1e-2, 0.5], // small amplitude/rate, sub-unit shape
            [5.0_f64, -2.0, 3.0, -1.5], // offset shift, wide, negative shape
        ];
        for p in param_sets {
            for &x in &[0.1_f64, 1.0, 5.0, 7.5, 15.0] {
                let j = model().jacobian(&[x], &p);
                for k in 0..4 {
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
        let xs = [1.0_f64, 5.0, 10.0, 15.0];
        let mut ys = vec![0.0_f64; xs.len()];
        model().eval_slice_into(&xs, &RAT43, &mut ys);
        let mut js = vec![0.0_f64; xs.len() * 4];
        model().jac_slice_into(&xs, &RAT43, &mut js);
        for (i, &xi) in xs.iter().enumerate() {
            assert_relative_eq!(ys[i], model().eval(&[xi], &RAT43), epsilon = 1e-12);
            let j = model().jacobian(&[xi], &RAT43);
            for k in 0..4 {
                assert_relative_eq!(js[i * 4 + k], j[k], epsilon = 1e-12);
            }
        }
    }
}
