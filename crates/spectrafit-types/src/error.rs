use thiserror::Error;

/// Top-level error type for the spectrafit workspace.
#[derive(Error, Debug)]
pub enum CoreError {
    /// JSON serialisation or deserialisation failed.
    #[error("parse error: {0}")]
    Parse(#[from] serde_json::Error),
    /// A runtime evaluation, compilation, or solver error occurred.
    #[error("evaluation error: {0}")]
    Eval(String),
    /// The solver failed to converge or encountered a numerical issue.
    #[error("solver error: {0}")]
    Solver(String),
}

#[cfg(test)]
mod error_trait_tests {
    use super::*;
    use std::error::Error;

    fn assert_is_error<E: Error + 'static>() {}

    #[test]
    fn core_error_implements_std_error() {
        assert_is_error::<CoreError>();
    }

    #[test]
    fn core_error_display_renders() {
        let err = CoreError::Eval("test evaluation failure".to_string());
        let msg = format!("{err}");
        assert_eq!(msg, "evaluation error: test evaluation failure");
    }

    #[test]
    fn core_error_solver_display_renders() {
        let err = CoreError::Solver("did not converge".to_string());
        let msg = format!("{err}");
        assert_eq!(msg, "solver error: did not converge");
    }

    #[test]
    fn core_error_parse_has_source() {
        let json_err = serde_json::from_str::<serde_json::Value>("not json").unwrap_err();
        let err = CoreError::Parse(json_err);
        assert!(err.source().is_some());
    }
}
