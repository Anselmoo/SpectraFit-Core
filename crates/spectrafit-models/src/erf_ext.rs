//! Scaled complementary error function `erfcx(x) = exp(x²)·erfc(x)`.
//!
//! `libm` provides `erfc` but not `erfcx`, and naively computing
//! `exp(x²)·erfc(x)` overflows for `x > 26.6` (where `exp(x²) > f64::MAX`).
//! `erfcx` itself is well-conditioned and bounded (`erfcx(0)=1`,
//! `erfcx(x) ~ 1/(x√π)` as `x→∞`), so the stable EMG kernel computes it directly.
//!
//! Implementation: W. J. Cody's rational Chebyshev approximation for the error
//! functions (W. J. Cody, "Rational Chebyshev approximation for the error
//! function", Math. Comp. 23 (1969) 631–637), the same coefficient sets used by
//! SLATEC/Cephes/SciPy's `calerf`. Accuracy is ~1e-15 relative for `x >= 0`.
//! Only `x >= 0` is needed by the EMG kernel (the `z < 0` regime there uses
//! `exp(arg)·erfc` directly, where `arg < 0` is overflow-safe).

// The Cody coefficient tables below are reproduced at their published precision
// (more digits than f64 holds); the compiler truncates to the nearest f64.
// Keeping the authoritative digits is intentional, so allow clippy's lint.
#![allow(clippy::excessive_precision)]

// One-over-sqrt(pi), used by the asymptotic regime.
const ONE_OVER_SQRT_PI: f64 = 0.564_189_583_547_756_286_948_079_451_560_77;

// W. J. Cody (1969) calerf coefficient sets, full double precision as published in
// SLATEC `derfc`/Netlib `calerf.f`. A/B → erf on [0, 0.46875]; C/D → erfc·exp on
// [0.46875, 4]; P/Q → asymptotic erfc·exp on (4, ∞).
const A: [f64; 5] = [
    3.16112374387056560e0,
    1.13864154151050156e2,
    3.77485237685302021e2,
    3.20937758913846947e3,
    1.85777706184603153e-1,
];
const B: [f64; 4] = [
    2.36012909523441209e1,
    2.44024637934444173e2,
    1.28261652607737228e3,
    2.84423683343917062e3,
];
const C: [f64; 9] = [
    5.64188496988670089e-1,
    8.88314979438837594e0,
    6.61191906371416295e1,
    2.98635138197400131e2,
    8.81952221241769090e2,
    1.71204761263407058e3,
    2.05107837782607147e3,
    1.23033935479799725e3,
    2.15311535474403846e-8,
];
const D: [f64; 8] = [
    1.57449261107098347e1,
    1.17693950891312499e2,
    5.37181101862009858e2,
    1.62138957456669019e3,
    3.29079923573345963e3,
    4.36261909014324716e3,
    3.43936767414372164e3,
    1.23033935480374942e3,
];
const P: [f64; 6] = [
    3.05326634961232344e-1,
    3.60344899949804439e-1,
    1.25781726111229246e-1,
    1.60837851487422766e-2,
    6.58749161529837803e-4,
    1.63153871373020978e-2,
];
const Q: [f64; 5] = [
    2.56852019228982242e0,
    1.87295284992346047e0,
    5.27905102951428412e-1,
    6.05183413124413191e-2,
    2.33520497626869185e-3,
];

/// Scaled complementary error function `erfcx(x) = exp(x²)·erfc(x)` for `x >= 0`.
///
/// Bounded on `[0, ∞)`: `erfcx(0) = 1`, monotonically decreasing toward 0 as
/// `erfcx(x) ~ 1/(x√π)`. Accurate to ~1e-15 relative across the whole range,
/// and (unlike `exp(x²)·erfc(x)`) never overflows. Coefficients are W. J. Cody's
/// `calerf` rational Chebyshev sets (Math. Comp. 23, 1969).
pub(crate) fn erfcx(x: f64) -> f64 {
    debug_assert!(x >= 0.0, "erfcx is only implemented for x >= 0");
    if x.is_nan() {
        return f64::NAN;
    }
    if x < 0.46875 {
        // Region 1: erf via the A/B rational, then erfcx = exp(x²)·(1 − erf(x)).
        let z = x * x;
        let mut num = A[4] * z;
        let mut den = z;
        for i in 0..3 {
            num = (num + A[i]) * z;
            den = (den + B[i]) * z;
        }
        let erf = x * (num + A[3]) / (den + B[3]);
        z.exp() * (1.0 - erf)
    } else if x <= 4.0 {
        // Region 2: C/D rational gives erfc(x)·exp(x²) = erfcx(x) directly.
        let mut num = C[8] * x;
        let mut den = x;
        for i in 0..7 {
            num = (num + C[i]) * x;
            den = (den + D[i]) * x;
        }
        (num + C[7]) / (den + D[7])
    } else {
        // Region 3 (x > 4): asymptotic P/Q rational in 1/x², scaled by 1/(x√π).
        let z = 1.0 / (x * x);
        let mut num = P[5] * z;
        let mut den = z;
        for i in 0..4 {
            num = (num + P[i]) * z;
            den = (den + Q[i]) * z;
        }
        let r = z * (num + P[4]) / (den + Q[4]);
        (ONE_OVER_SQRT_PI - r) / x
    }
}

#[cfg(test)]
mod tests {
    use super::erfcx;
    use approx::assert_relative_eq;

    #[test]
    fn known_values() {
        // References from scipy.special.erfcx (machine precision).
        assert_relative_eq!(erfcx(0.0), 1.0, epsilon = 1e-12);
        assert_relative_eq!(erfcx(0.1), 0.896_456_979_969_126_8, epsilon = 1e-12);
        assert_relative_eq!(erfcx(0.25), 0.770_346_547_730_997_0, epsilon = 1e-12);
        assert_relative_eq!(erfcx(0.5), 0.615_690_344_192_925_8, epsilon = 1e-12);
        assert_relative_eq!(erfcx(1.0), 0.427_583_576_155_807_0, epsilon = 1e-12);
        assert_relative_eq!(erfcx(2.0), 0.255_395_676_310_505_8, epsilon = 1e-12);
        assert_relative_eq!(erfcx(4.0), 0.136_999_457_625_061_4, epsilon = 1e-12);
        assert_relative_eq!(erfcx(5.0), 0.110_704_637_733_068_6, epsilon = 1e-12);
        assert_relative_eq!(erfcx(26.5), 0.021_275_046_685_371_1, epsilon = 1e-12);
        // Far tail: erfcx(x) ~ 1/(x√π); guard against overflow of exp(x²)·erfc.
        assert_relative_eq!(erfcx(100.0), 0.005_641_613_782_989_4, epsilon = 1e-12);
    }

    #[test]
    fn monotone_decreasing_and_bounded() {
        let mut prev = erfcx(0.0);
        assert!((prev - 1.0).abs() < 1e-12);
        let mut x = 0.1;
        while x <= 50.0 {
            let v = erfcx(x);
            assert!(v.is_finite() && v > 0.0 && v < 1.0, "erfcx({x}) = {v}");
            assert!(v < prev, "not decreasing at x={x}");
            prev = v;
            x += 0.1;
        }
    }
}
