//! spectrafit-types — shared IR types and error variants for the spectrafit workspace.
#![warn(missing_docs)]

/// Error variants for the spectrafit engine.
pub mod error;
/// Core type definitions for graphs, parameters, measurements, and results.
pub mod types;

// Explicit named re-exports (workspace convention: 10 of 11 crates do this).
// A glob here made the public surface of the crate that owns the model wire
// format unreviewable — see house rule 9. The list below is derived from
// rustdoc's `all.html`, NOT from a `^pub` grep: `ModelTypeStr` is generated
// inside the `model_manifest!` macro and does not match such a grep, so a
// hand-assembled list silently drops the single source of truth for the serde
// wire string. Regenerate with `cargo doc -p spectrafit-types --no-deps`.
pub use error::CoreError;
pub use types::{
    DatasetSliceSpec, ExprEdge, FitGraphSpec, FitOptionsSpec, FitResultSpec, MeasurementInput,
    MeasurementSpec, ModelNodeSpec, ModelTypeStr, ParameterResultSpec, ParameterSpec,
    TerminationReason,
};
