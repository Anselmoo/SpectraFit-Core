//! Platform-abstracted vectorized exponential.
//!
//! Public surface: [`batch_exp`] — `dst[i] = exp(src[i])` for all `i`.
//!
//! # Backend selection
//!
//! | Platform                 | Backend                  | Notes                              |
//! |--------------------------|--------------------------|-------------------------------------|
//! | macOS (any arch)         | Apple Accelerate `vvexp` | NEON-vectorized on Apple Silicon    |
//! | everything else          | scalar `f64::exp` loop   | portable fallback; opt-in SIMD later |
//!
//! # Aliasing contract
//! `dst` and `src` **must not overlap** in memory.  This is enforced by the
//! Rust borrow checker for safe callers: `&mut [f64]` and `&[f64]` cannot
//! refer to the same allocation.

/// Compute `dst[i] = exp(src[i])` for every element.
///
/// Uses the platform-optimal backend (see module docs).
///
/// # Panics
/// Panics if `dst.len() != src.len()` or if the slice exceeds `i32::MAX`
/// elements (macOS vvexp limit).
#[inline]
pub fn batch_exp(dst: &mut [f64], src: &[f64]) {
    assert_eq!(
        dst.len(),
        src.len(),
        "batch_exp: dst and src must have the same length"
    );
    platform::batch_exp_impl(dst, src);
}

// ── macOS: Apple Accelerate / vForce ─────────────────────────────────────────
#[cfg(target_os = "macos")]
mod platform {
    // vvexp lives in the Accelerate / vecLib framework.
    // Linked via `cargo:rustc-link-lib=framework=Accelerate` in build.rs.
    // Signature: `void vvexp(double *y, const double *x, const int *n);`
    // Both `y` and `x` carry `__restrict__`; they must not alias.
    extern "C" {
        fn vvexp(y: *mut f64, x: *const f64, n: *const i32);
    }

    #[inline]
    pub fn batch_exp_impl(dst: &mut [f64], src: &[f64]) {
        // Short-circuit the empty case: an empty slice's `as_ptr()` /
        // `as_mut_ptr()` is a dangling (NonNull but unallocated) pointer, and we
        // do not rely on vvexp tolerating n==0 with such pointers. Nothing to
        // compute, so return before touching the FFI boundary.
        if src.is_empty() {
            return;
        }
        assert!(
            src.len() <= i32::MAX as usize,
            "batch_exp: slice length exceeds vvexp's i32 limit"
        );
        let n = src.len() as i32;
        // SAFETY: dst and src are guaranteed non-overlapping by the `&mut` /
        // `&` borrow rules; lengths are equal (asserted in `batch_exp`); and
        // `src` is non-empty (the empty case short-circuits above), so both
        // pointers reference a live `n`-element allocation with `n >= 1`.
        unsafe { vvexp(dst.as_mut_ptr(), src.as_ptr(), &n) }
    }
}

// ── all other platforms: portable scalar fallback ────────────────────────────
#[cfg(not(target_os = "macos"))]
mod platform {
    #[inline]
    pub fn batch_exp_impl(dst: &mut [f64], src: &[f64]) {
        // TODO: add x86-64 AVX2/SVML or ARM NEON backends here as feature flags.
        for (d, &s) in dst.iter_mut().zip(src.iter()) {
            *d = s.exp();
        }
    }
}

// ── tests ─────────────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn batch_exp_matches_scalar() {
        let src: Vec<f64> = (-10..=10).map(|i| i as f64 * 0.5).collect();
        let mut dst = vec![0.0_f64; src.len()];
        batch_exp(&mut dst, &src);
        for (&s, &d) in src.iter().zip(dst.iter()) {
            let expected = s.exp();
            let rel = (d - expected).abs() / expected.abs().max(1e-300);
            assert!(rel < 1e-12, "batch_exp({s}) = {d}, expected {expected}");
        }
    }

    #[test]
    fn batch_exp_empty_slice() {
        let mut dst: Vec<f64> = vec![];
        batch_exp(&mut dst, &[]);
    }

    #[test]
    #[should_panic(expected = "same length")]
    fn batch_exp_length_mismatch_panics() {
        let mut dst = vec![0.0_f64; 3];
        batch_exp(&mut dst, &[1.0, 2.0]);
    }
}
