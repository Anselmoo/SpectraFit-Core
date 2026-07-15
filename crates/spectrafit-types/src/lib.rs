//! spectrafit-types — shared IR types and error variants for the spectrafit workspace.
#![warn(missing_docs)]

/// Error variants for the spectrafit engine.
pub mod error;
/// Core type definitions for graphs, parameters, measurements, and results.
pub mod types;

pub use error::*;
pub use types::*;
