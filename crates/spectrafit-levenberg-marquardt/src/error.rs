//! Error variants for the Levenberg–Marquardt step computation.
//!
//! Mirrors the workspace convention established by `spectrafit-types`,
//! `spectrafit-graph`, and `spectrafit-solver`: a crate that owns an error type
//! declares it as a `thiserror` enum in its own `error.rs`, so the type
//! implements `Display` and `std::error::Error` and can be `?`-converted by
//! callers instead of only matched structurally.

use thiserror::Error;

/// Why a step could not be computed for the current `λ`.
#[derive(Debug, Clone, Error)]
pub enum StepError {
    /// `(JᵀJ + λD²)` was not positive-definite — caller should raise `λ`.
    #[error("(JᵀJ + λD²) was not positive-definite — raise λ and retry")]
    NotPositiveDefinite,
    /// A dense factorization (SVD) failed.
    #[error("dense factorization (SVD) failed: {0}")]
    Factorization(String),
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::error::Error;

    fn assert_is_error<E: Error + 'static>() {}

    #[test]
    fn step_error_implements_std_error() {
        assert_is_error::<StepError>();
    }

    #[test]
    fn not_positive_definite_display_renders() {
        let err = StepError::NotPositiveDefinite;
        assert_eq!(
            format!("{err}"),
            "(JᵀJ + λD²) was not positive-definite — raise λ and retry"
        );
    }

    #[test]
    fn factorization_display_renders_with_payload() {
        let err = StepError::Factorization("rank-deficient thin SVD".to_string());
        assert_eq!(
            format!("{err}"),
            "dense factorization (SVD) failed: rank-deficient thin SVD"
        );
    }
}
