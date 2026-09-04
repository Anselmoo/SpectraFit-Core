use crate::Model;

/// Rational function, cubic over cubic, with the denominator constant pinned at 1.
///
/// ```text
/// y = (a0 + a1·x + a2·x² + a3·x³) / (1 + b1·x + b2·x² + b3·x³)
/// ```
///
/// Parameters (in order): `[a0, a1, a2, a3, b1, b2, b3]`
///
/// One kernel covers three NIST StRD datasets because a lower-order rational is
/// this form with the unused coefficients held at zero:
/// - Hahn1 and Thurber are cubic/cubic and use all seven.
/// - Kirby2 is quadratic/quadratic: fix `a3 = 0` and `b3 = 0` and the remaining
///   five map straight onto NIST's b1..b5.
///
/// The denominator constant is pinned at 1 rather than fitted because NIST writes
/// these models that way. Fitting it too would make numerator and denominator
/// jointly scalable — `(kN)/(kD)` is the same curve — and hand the solver an exact
/// rank deficiency.
///
/// **Domain guard:** `D` must be non-zero. A rational's denominator can cross zero
/// mid-search even when the certified parameters keep it clear of the data, so
/// `D = 0` returns `f64::NAN` and the solver backs off rather than emitting an
/// infinity that would poison the residual vector.
///
/// **Analytic Jacobian** (let `N` and `D` be numerator and denominator):
/// - ∂y/∂a_k = x^k / D          for k = 0,1,2,3
/// - ∂y/∂b_k = −N · x^k / D²    for k = 1,2,3
pub struct RationalCubic;

#[inline]
fn nd(xi: f64, p: &[f64]) -> (f64, f64) {
    let x2 = xi * xi;
    let x3 = x2 * xi;
    let n = p[0] + p[1] * xi + p[2] * x2 + p[3] * x3;
    let d = 1.0 + p[4] * xi + p[5] * x2 + p[6] * x3;
    (n, d)
}

#[inline]
fn jac_at(xi: f64, p: &[f64], out: &mut [f64]) {
    let x2 = xi * xi;
    let x3 = x2 * xi;
    let (n, d) = nd(xi, p);
    if d == 0.0 {
        out[..7].fill(f64::NAN);
        return;
    }
    let inv_d = 1.0 / d;
    let scale = -n * inv_d * inv_d;
    out[0] = inv_d;
    out[1] = xi * inv_d;
    out[2] = x2 * inv_d;
    out[3] = x3 * inv_d;
    out[4] = scale * xi;
    out[5] = scale * x2;
    out[6] = scale * x3;
}

impl Model for RationalCubic {
    fn eval(&self, x: &[f64], p: &[f64]) -> f64 {
        let (n, d) = nd(x[0], p);
        if d == 0.0 {
            return f64::NAN;
        }
        n / d
    }

    fn jacobian_into(&self, x: &[f64], p: &[f64], out: &mut [f64]) {
        jac_at(x[0], p, out);
    }

    fn jacobian(&self, x: &[f64], p: &[f64]) -> Vec<f64> {
        let mut out = vec![0.0_f64; 7];
        jac_at(x[0], p, &mut out);
        out
    }

    fn param_names(&self) -> Vec<std::borrow::Cow<'static, str>> {
        vec![
            "a0".into(),
            "a1".into(),
            "a2".into(),
            "a3".into(),
            "b1".into(),
            "b2".into(),
            "b3".into(),
        ]
    }

    fn eval_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        debug_assert_eq!(out.len(), xs.len());
        for (slot, &xi) in out.iter_mut().zip(xs.iter()) {
            let (n, d) = nd(xi, params);
            *slot = if d == 0.0 { f64::NAN } else { n / d };
        }
    }

    fn jac_slice_into(&self, xs: &[f64], params: &[f64], out: &mut [f64]) {
        debug_assert_eq!(out.len(), xs.len() * 7);
        for (i, &xi) in xs.iter().enumerate() {
            jac_at(xi, params, &mut out[i * 7..i * 7 + 7]);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use approx::assert_relative_eq;

    fn model() -> RationalCubic {
        RationalCubic
    }

    // Kirby2's certified values, carried in the quadratic/quadratic slots with the
    // cubic coefficients at zero. First observation is x=9.65, y=0.0082.
    const KIRBY2: [f64; 7] = [
        1.6745063063e00,
        -1.3927397867e-01,
        2.5961181191e-03,
        0.0,
        -1.7241811870e-03,
        2.1664802578e-05,
        0.0,
    ];

    // Anchored at two points where the certified fit tracks the data, NOT at the
    // first observation: Kirby2's x=9.65 point is the largest residual in all 151
    // observations (data 0.0082, certified fit 0.5808), so a test written there
    // measures the dataset's outlier rather than the kernel.
    #[test]
    fn eval_kirby2_matches_data_where_the_certified_fit_holds() {
        let mid = model().eval(&[100.0], &KIRBY2);
        assert!(
            (mid - 12.944).abs() < 0.25,
            "at x=100 expected ~12.94, got {mid}"
        );
        let top = model().eval(&[371.3], &KIRBY2);
        assert!(
            (top - 92.2).abs() < 0.25,
            "at x=371.3 expected ~92.2, got {top}"
        );
    }

    #[test]
    fn zero_denominator_returns_nan() {
        // D = 1 + b1·x = 0 at x = 1 when b1 = -1.
        let p = [1.0_f64, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0];
        assert!(model().eval(&[1.0], &p).is_nan());
        let j = model().jacobian(&[1.0], &p);
        assert!(j.iter().all(|v| v.is_nan()));
    }

    #[test]
    fn constant_when_all_but_a0_vanish() {
        // N = a0, D = 1 → y = a0 for every x.
        let p = [2.5_f64, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        for x in [-3.0, 0.0, 1.0, 7.5] {
            assert_relative_eq!(model().eval(&[x], &p), 2.5, epsilon = 1e-12);
        }
    }

    #[test]
    fn jacobian_shape_and_finiteness() {
        let j = model().jacobian(&[2.0], &KIRBY2);
        assert_eq!(j.len(), 7);
        assert!(j.iter().all(|v| v.is_finite()), "{j:?}");
    }

    #[test]
    fn jacobian_matches_finite_difference() {
        // Already a central difference; widened from one regime/x-point to
        // three regimes and an x-range spanning all three NIST StRD datasets
        // this kernel backs (docs/reference/models/index.md): Thurber
        // (x: −3.07…2.20), Kirby2 (x: 9.65…371.30), Hahn1 (x: 14.13…851.61).
        //
        // CORRECTION to an earlier version of this comment: it attributed the
        // original failure at x=100 to a generic "fixed-h step too large"
        // effect. That was wrong on the facts — the step below was already
        // relative, `h = 1e-6 * |p[k]|.max(1.0)`, identical in form to every
        // other file in this pass. The real mechanism is a *degenerate*
        // relative step: Kirby2 is quadratic/quadratic, so b3 = 0 exactly,
        // and `|0|.max(1.0)` collapses the "relative" step to the absolute
        // floor of 1.0 — an effective h of 1e-6 regardless of scale. That
        // fixed 1e-6 is then amplified by ∂y/∂b3 = −N·x³/D², which grows as
        // x³: at x=50 (reproduced independently), h·x³ ≈ 0.125 against a D
        // of only a few, no longer an infinitesimal probe:
        //
        //   step rule                              rel_err at x=50, k=b3
        //   h = 1e-6 · |p|.max(1.0)  (old, degenerate on b3=0)   1.7e-2
        //   h = 1e-6 / x³                                        3.7e-11
        //   h = 1e-9 fixed                                       1.7e-8
        //
        // Fix: for the denominator coefficients (b1, b2, b3 — indices 4..7,
        // multiplying x¹, x², x³ respectively) the step is no longer
        // parameter-relative but **D-relative**: h = (1e-4·|D|).max(1e-9) /
        // |x|.max(1.0)^power. This targets a fixed ~0.01% perturbation of
        // the denominator itself, so it stays large enough to clear
        // floating-point rounding noise even when a coefficient is exactly
        // 0 (unlike `1e-6/x³`, which underflows toward the f64 rounding
        // floor at large x once combined with a *nonzero* small b2/b3 in the
        // "offset/negative" regime below — confirmed by re-running this
        // exact grid with a plain `1e-6/x^power` rule, which failed at
        // x≥100 there) and small enough to stay a good local-slope probe
        // even when D is enormous (up to ~3e7 at x=850). Numerator
        // coefficients (a0..a3, indices 0..4) are exactly linear in y, so
        // their original parameter-relative step is untouched and exact up
        // to floating-point rounding.
        let param_sets = [
            KIRBY2,                                   // certified Kirby2 fit (nominal)
            [1e-3, 1e-3, 1e-3, 0.0, 1e-3, 1e-3, 0.0], // small coefficients
            [5.0, -2.0, 3.0, -0.5, 0.2, -0.1, 0.05],  // offset/negative, cubic terms active
        ];
        // Spans Thurber's negative domain, Kirby2's up to ~371, and Hahn1's
        // up to ~852.
        let xs = [
            -3.0_f64, 0.5, 1.0, 2.0, 3.25, 5.0, 10.0, 50.0, 100.0, 300.0, 850.0,
        ];
        for p in param_sets {
            for &x in &xs {
                let (_, d0) = nd(x, &p);
                if d0 == 0.0 {
                    continue; // domain-guard boundary, covered by its own test
                }
                let j = model().jacobian(&[x], &p);
                for k in 0..7 {
                    let h = if k >= 4 {
                        let power = (k - 3) as i32; // b1->x¹, b2->x², b3->x³
                        (1e-4 * d0.abs()).max(1e-9) / x.abs().max(1.0).powi(power)
                    } else {
                        1e-6 * p[k].abs().max(1.0)
                    };
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
    fn jacobian_into_matches_jacobian() {
        let x = &[1.5_f64];
        let j_vec = model().jacobian(x, &KIRBY2);
        let mut out = [0.0_f64; 7];
        model().jacobian_into(x, &KIRBY2, &mut out);
        for k in 0..7 {
            assert_relative_eq!(out[k], j_vec[k], epsilon = 1e-12);
        }
    }

    #[test]
    fn eval_slice_matches_scalar() {
        let xs = [9.65_f64, 10.74, 20.42, 40.12, 100.5, 200.0];
        let mut out = vec![0.0_f64; xs.len()];
        model().eval_slice_into(&xs, &KIRBY2, &mut out);
        for (&xi, &got) in xs.iter().zip(out.iter()) {
            assert_relative_eq!(got, model().eval(&[xi], &KIRBY2), epsilon = 1e-12);
        }
    }

    #[test]
    fn jac_slice_matches_scalar() {
        let xs = [9.65_f64, 20.42, 100.5];
        let mut out = vec![0.0_f64; xs.len() * 7];
        model().jac_slice_into(&xs, &KIRBY2, &mut out);
        for (i, &xi) in xs.iter().enumerate() {
            let j = model().jacobian(&[xi], &KIRBY2);
            for k in 0..7 {
                assert_relative_eq!(out[i * 7 + k], j[k], epsilon = 1e-12);
            }
        }
    }
}
