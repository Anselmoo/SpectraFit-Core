> Applies to: crates/spectrafit-models/src/**/*.rs

# Rust Model Kernel Implementation Checklist

This file establishes the mandatory, verifiable checklist for implementing new spectroscopic models in `crates/spectrafit-models/src/`.

## Context

- **Problem**: Every new model in spectrafit-core must implement 5 requirements (trait methods, analytical Jacobian, bounds checking, tests, serialization)
- **Current State**: Developers reverse-engineer implementations from existing models (Gaussian, Lorentzian)
- **Goal**: Structured template + checklist eliminates errors and ensures 100% coverage

## Scope

This applies to **all public model implementations** in `crates/spectrafit-models/src/`:
- Gaussian, Lorentzian, Voigt, Exponential, Polynomial, custom models
- Every model is a `struct` implementing the `Model` trait with associated test module

## Core Rules

1. **Implement ALL 5 methods of the `Model` trait**
   - `eval(&self, x: &[f64], params: &[f64]) -> Result<Vec<f64>, ModelError>` — evaluate model at x
   - `jacobian(&self, x: &[f64], params: &[f64]) -> Result<Vec<Vec<f64>>, ModelError>` — first derivative
   - `bounds_check(&self, params: &[f64]) -> Result<(), ModelError>` — validate parameter ranges
   - `num_params(&self) -> usize` — number of model parameters
   - `param_names(&self) -> Vec<&str>` — parameter identifiers
   - **Rule**: Missing any method → compilation error (good). Don't provide dummy implementations.

2. **Jacobian MUST be analytical, not finite-difference**
   - Finite-difference is forbidden: it's slow, inaccurate, and masquerades as analytical
   - Every parameter derivative must be derived mathematically and hardcoded
   - **Action**: Before coding, derive ∂f/∂p for each parameter on paper. Document in code comments.

3. **Always call `bounds_check()` at the start of `eval()` and `jacobian()`**
   - Prevents silent NaN/infinity propagation
   - Example: `self.bounds_check(params)?;` before any computation
   - **Rule**: If bounds_check is bypassed, parameter errors will silently corrupt results

4. **Bounds checking must reject invalid parameter ranges**
   - Amplitude must be non-zero? Check it.
   - Sigma must be > 0.1? Enforce it.
   - Center within domain? Validate it.
   - **Action**: Never allow division by zero, negative square roots, or out-of-range parameters to proceed

5. **Test coverage must be 100% with numerical Jacobian comparison**
   - Every model must have a corresponding `#[cfg(test)] mod tests` block
   - Test must compare analytical Jacobian against finite-difference Jacobian
   - Tolerance: analytical ≈ numerical within 1e-6 (default) or explicit tolerance
   - **Rule**: If numerical-analytical comparison isn't in tests, the Jacobian is unverified

## Extended Rules & Implementation Workflow

### Phase 1: File Structure & Module Registration

**Location**: Create new file `crates/spectrafit-models/src/my_model.rs`

**File Template**:
```rust
//! My Model kernel for spectrafit-core
//!
//! Mathematical model: f(x; p₁, p₂, ..., pₙ) = ...
//! 
//! This module implements the `Model` trait for [descriptive name].
//!
//! # Parameters
//!
//! - **p₁**: [Name] ([typical range], [unit]). Controls [what].
//! - **p₂**: [Name] ([typical range], [unit]). Controls [what].
//!
//! # Mathematical Definition
//!
//! ```text
//! f(x; p) = [formula]
//! ∂f/∂p₁ = [derivative formula]
//! ∂f/∂p₂ = [derivative formula]
//! ```
//!
//! # References
//!
//! - [Citation or equation number if applicable]
//! - [If reproducing a paper, cite it here]

use crate::errors::ModelError;
use crate::traits::Model;
use serde::{Deserialize, Serialize};

// [Model implementation follows below]
```

**Module Registration** (`crates/spectrafit-models/src/lib.rs` or `mod.rs`):
```rust
pub mod my_model;
pub use my_model::MyModel;
```

### Phase 2: Struct Definition with Serde

**Template**:
```rust
/// MyModel: [One-line description]
///
/// A [broader description] model suitable for [application].
/// See module documentation for parameters and mathematical definition.
#[derive(Serialize, Deserialize, Debug, Clone, Default)]
#[serde(rename_all = "snake_case")]
pub struct MyModel {
    // Note: struct is a marker type; parameters are NOT stored here
    // They are passed as &[f64] to eval() and jacobian()
}

impl MyModel {
    /// Create a new instance of MyModel
    pub fn new() -> Self {
        Self {}
    }
}
```

**Rule**: Model structs are parameter containers OR pure trait impls (parameter-free). Choose one approach per model and document it.

### Phase 3: Trait Implementation

**CRITICAL: Implement all 5 methods.** Example below shows Gaussian model:

```rust
impl Model for MyModel {
    /// Evaluate the model at given x values and parameters
    ///
    /// # Arguments
    ///
    /// * `x` - Input x-values (e.g., wavelengths, frequencies)
    /// * `params` - Model parameters in order: [p₁, p₂, ..., pₙ]
    ///
    /// # Returns
    ///
    /// `Vec<f64>` of model values at x, or `ModelError` if bounds fail
    ///
    /// # Example
    ///
    /// ```ignore
    /// let model = MyModel::new();
    /// let result = model.eval(&[1.0, 2.0], &[1.5, 2.0, 0.5])?;
    /// ```
    fn eval(&self, x: &[f64], params: &[f64]) -> Result<Vec<f64>, ModelError> {
        // Step 1: Always validate parameters first
        self.bounds_check(params)?;

        // Step 2: Check parameter count
        if params.len() != self.num_params() {
            return Err(ModelError::ParameterCount {
                expected: self.num_params(),
                got: params.len(),
            });
        }

        // Step 3: Extract named parameters for clarity
        let amplitude = params[0];
        let center = params[1];
        let sigma = params[2];

        // Step 4: Compute model values
        Ok(x
            .iter()
            .map(|xi| {
                let z = (xi - center) / sigma;
                amplitude * (-0.5 * z * z).exp()
            })
            .collect())
    }

    /// Analytical Jacobian (first derivative w.r.t. each parameter)
    ///
    /// Returns a matrix where row i is ∂f/∂x_i and column j is ∂f/∂p_j
    ///
    /// # Jacobian Formulas (for Gaussian example)
    ///
    /// ```text
    /// f(x; a, c, σ) = a · exp(-0.5·((x-c)/σ)²)
    ///
    /// ∂f/∂a = exp(-0.5·((x-c)/σ)²)
    /// ∂f/∂c = a · exp(-0.5·z²) · (z / σ)     where z = (x-c)/σ
    /// ∂f/∂σ = a · exp(-0.5·z²) · (z² / σ)
    /// ```
    fn jacobian(&self, x: &[f64], params: &[f64]) -> Result<Vec<Vec<f64>>, ModelError> {
        // Step 1: Always validate parameters first
        self.bounds_check(params)?;

        if params.len() != self.num_params() {
            return Err(ModelError::ParameterCount {
                expected: self.num_params(),
                got: params.len(),
            });
        }

        let amplitude = params[0];
        let center = params[1];
        let sigma = params[2];

        let mut jacobian = vec![vec![0.0; 3]; x.len()];

        for (i, xi) in x.iter().enumerate() {
            let z = (xi - center) / sigma;
            let exp_term = (-0.5 * z * z).exp();

            // ∂f/∂a (amplitude)
            jacobian[i][0] = exp_term;

            // ∂f/∂c (center)
            jacobian[i][1] = amplitude * exp_term * (z / sigma);

            // ∂f/∂σ (sigma)
            jacobian[i][2] = amplitude * exp_term * (z * z / sigma);
        }

        Ok(jacobian)
    }

    /// Validate parameter ranges; reject invalid values early
    fn bounds_check(&self, params: &[f64]) -> Result<(), ModelError> {
        if params.len() != self.num_params() {
            return Err(ModelError::ParameterCount {
                expected: self.num_params(),
                got: params.len(),
            });
        }

        let amplitude = params[0];
        let sigma = params[2];

        // Amplitude can be positive or negative, but not zero
        if amplitude == 0.0 {
            return Err(ModelError::InvalidParameter {
                name: "amplitude".to_string(),
                reason: "Amplitude must be non-zero".to_string(),
            });
        }

        // Sigma must be strictly positive
        if sigma <= 0.1 {
            return Err(ModelError::InvalidParameter {
                name: "sigma".to_string(),
                reason: "Sigma must be > 0.1 to avoid numerical issues".to_string(),
            });
        }

        Ok(())
    }

    /// Number of parameters for this model
    fn num_params(&self) -> usize {
        3 // amplitude, center, sigma
    }

    /// Parameter names in order
    fn param_names(&self) -> Vec<&str> {
        vec!["amplitude", "center", "sigma"]
    }
}
```

### Phase 4: Bounds Checking Best Practices

**Template** (update for your model):
```rust
fn bounds_check(&self, params: &[f64]) -> Result<(), ModelError> {
    if params.len() != self.num_params() {
        return Err(ModelError::ParameterCount {
            expected: self.num_params(),
            got: params.len(),
        });
    }

    // Extract parameters with names for clarity
    let param_names = self.param_names();
    
    for (i, &value) in params.iter().enumerate() {
        // Check for NaN and Infinity
        if !value.is_finite() {
            return Err(ModelError::InvalidParameter {
                name: param_names[i].to_string(),
                reason: format!("Parameter must be finite, got {}", value),
            });
        }

        // Check parameter-specific constraints (customize for each model)
        match param_names[i] {
            "amplitude" => {
                if value == 0.0 {
                    return Err(ModelError::InvalidParameter {
                        name: "amplitude".to_string(),
                        reason: "Amplitude must be non-zero".to_string(),
                    });
                }
            }
            "sigma" | "width" => {
                if value <= 0.0 {
                    return Err(ModelError::InvalidParameter {
                        name: param_names[i].to_string(),
                        reason: format!("{} must be positive, got {}", param_names[i], value),
                    });
                }
            }
            _ => {} // Other parameters may have looser bounds
        }
    }

    Ok(())
}
```

### Phase 5: Test Module

**Critical**: Must include numerical Jacobian comparison

```rust
#[cfg(test)]
mod tests {
    use super::*;
    const EPSILON: f64 = 1e-6;  // Tolerance for numerical derivatives

    #[test]
    fn test_eval_basic() {
        let model = MyModel::new();
        let x = vec![0.0, 1.0, 2.0];
        let params = vec![1.0, 1.0, 0.5];  // amplitude=1, center=1, sigma=0.5

        let result = model.eval(&x, &params).expect("eval failed");
        
        assert_eq!(result.len(), 3);
        assert!(result[0] > 0.0 && result[0] < 1.0);  // Peak at x=center=1
        assert!(result[1].abs() < 1e-5);  // Should be close to peak (maximum at center)
        assert!(result[2] > 0.0 && result[2] < 1.0);
    }

    #[test]
    fn test_bounds_check_negative_sigma() {
        let model = MyModel::new();
        let params = vec![1.0, 1.0, -0.5];  // sigma < 0: invalid

        let result = model.bounds_check(&params);
        assert!(result.is_err(), "Should reject negative sigma");
    }

    #[test]
    fn test_bounds_check_zero_amplitude() {
        let model = MyModel::new();
        let params = vec![0.0, 1.0, 0.5];  // amplitude = 0: invalid

        let result = model.bounds_check(&params);
        assert!(result.is_err(), "Should reject zero amplitude");
    }

    #[test]
    fn test_jacobian_vs_numerical() {
        let model = MyModel::new();
        let x = vec![0.5, 1.0, 1.5, 2.0];
        let params = vec![2.0, 1.0, 0.8];

        // Compute analytical Jacobian
        let jacobian_analytical = model.jacobian(&x, &params)
            .expect("jacobian failed");

        // Compute numerical Jacobian using finite differences
        let h = 1e-7;
        let mut jacobian_numerical = vec![vec![0.0; 3]; x.len()];

        for j in 0..3 {
            let mut params_plus = params.clone();
            let mut params_minus = params.clone();
            params_plus[j] += h;
            params_minus[j] -= h;

            let f_plus = model.eval(&x, &params_plus).expect("eval+ failed");
            let f_minus = model.eval(&x, &params_minus).expect("eval- failed");

            for i in 0..x.len() {
                jacobian_numerical[i][j] = (f_plus[i] - f_minus[i]) / (2.0 * h);
            }
        }

        // Compare: analytical vs numerical
        for i in 0..x.len() {
            for j in 0..3 {
                let diff = (jacobian_analytical[i][j] - jacobian_numerical[i][j]).abs();
                let rel_error = diff / (jacobian_numerical[i][j].abs() + 1e-8);
                
                assert!(
                    rel_error < 1e-5,
                    "Jacobian mismatch at [{}][{}]: analytical={}, numerical={}, rel_error={}",
                    i, j,
                    jacobian_analytical[i][j],
                    jacobian_numerical[i][j],
                    rel_error
                );
            }
        }
    }

    #[test]
    fn test_serde_roundtrip() {
        let model = MyModel::new();
        
        // Serialize
        let json = serde_json::to_string(&model).expect("serialize failed");
        
        // Deserialize
        let restored: MyModel = serde_json::from_str(&json).expect("deserialize failed");
        
        assert_eq!(restored, model);
    }

    #[test]
    fn test_edge_case_center_at_boundary() {
        // Test model at domain edges (e.g., center = 0, σ → 0)
        let model = MyModel::new();
        let x = vec![-5.0, 0.0, 5.0];
        let params = vec![1.0, 0.0, 0.5];  // Center at 0

        let result = model.eval(&x, &params).expect("eval failed");
        assert_eq!(result.len(), 3);
    }

    #[test]
    fn test_param_names_consistency() {
        let model = MyModel::new();
        assert_eq!(model.param_names().len(), model.num_params());
    }
}
```

## Anti-Patterns: What NOT To Do

### ❌ Anti-Pattern 1: Incomplete Trait Implementation

**Wrong**: Missing one of the 5 required methods
```rust
impl Model for MyModel {
    fn eval(&self, x: &[f64], params: &[f64]) -> Result<Vec<f64>, ModelError> { /* ... */ }
    fn jacobian(&self, x: &[f64], params: &[f64]) -> Result<Vec<Vec<f64>>, ModelError> { /* ... */ }
    // Missing: bounds_check, num_params, param_names
}
```

**Consequence**: Compilation error. Good! But recognizing the error requires reading the compiler message.

**Fix**: Copy the full trait definition from above. Don't implement piecemeal.

### ❌ Anti-Pattern 2: Finite-Difference Jacobian Instead of Analytical

**Wrong**:
```rust
fn jacobian(&self, x: &[f64], params: &[f64]) -> Result<Vec<Vec<f64>>, ModelError> {
    let h = 1e-5;
    let mut jacobian = vec![vec![0.0; self.num_params()]; x.len()];
    let f_center = self.eval(x, params)?;
    
    for j in 0..self.num_params() {
        let mut params_plus = params.to_vec();
        params_plus[j] += h;
        let f_plus = self.eval(x, &params_plus)?;
        
        for i in 0..x.len() {
            jacobian[i][j] = (f_plus[i] - f_center[i]) / h;  // FORBIDDEN!
        }
    }
    
    Ok(jacobian)
}
```

**Consequence**: 
- Slow (3× the `eval` calls)
- Inaccurate (truncation error ~ 1e-5, misses optimization)
- Silent: looks like a Jacobian but is numerically inferior
- Reviews miss it because code "works"

**Fix**: Derive ∂f/∂p analytically and hardcode it. Test against finite-diff in unit tests, but never ship finite-diff.

### ❌ Anti-Pattern 3: Skipped Bounds Check at Start of eval()

**Wrong**:
```rust
fn eval(&self, x: &[f64], params: &[f64]) -> Result<Vec<f64>, ModelError> {
    // Skipped bounds_check! Starts computing directly
    Ok(x.iter().map(|xi| {
        let sigma = params[2];
        let z = (xi - 1.0) / sigma;  // If sigma=0, panics!
        (-0.5 * z * z).exp()
    }).collect())
}
```

**Consequence**: Division by zero panic, NaN propagation, silent corruption.

**Fix**: Call `self.bounds_check(params)?;` first, always.

### ❌ Anti-Pattern 4: Silent NaN/Infinity in Bounds Check

**Wrong**:
```rust
fn bounds_check(&self, params: &[f64]) -> Result<(), ModelError> {
    // No check for NaN or Inf
    let sigma = params[2];
    if sigma > 0.0 {
        Ok(())  // NaN > 0.0 is false, but no error message
    } else {
        Err(...)
    }
}
```

**Consequence**: `NaN > 0.0` evaluates to `false`, bounds_check passes, then later `z * z` produces `NaN` everywhere.

**Fix**: Explicitly check `value.is_finite()` for all parameters.

### ❌ Anti-Pattern 5: Zero Test Coverage

**Wrong**: No `#[cfg(test)]` module
```rust
pub struct MyModel {}
impl Model for MyModel { /* ... */ }
// No tests at all
```

**Consequence**: 
- Jacobian never verified against numerical
- Bounds checking never tested
- Edge cases (sigma=0.1, center at boundary) never exercised
- Later refactoring silently breaks the Jacobian

**Fix**: Add comprehensive test module with all 5+ test cases above.

### ❌ Anti-Pattern 6: Hardcoded Parameters Instead of Trait Method

**Wrong**:
```rust
fn num_params(&self) -> usize {
    3  // Always returns 3, even if trait changes
}

// Later, someone adds a 4th parameter and updates the struct/eval/jacobian
// but forgets to update num_params → mismatch
```

**Fix**: Use a constant or derive macro to ensure num_params matches param_names.

### ❌ Anti-Pattern 7: No Serialization / serde Attributes

**Wrong**:
```rust
pub struct MyModel;
// No #[derive(Serialize, Deserialize)]
// No #[serde(...)] attributes
```

**Consequence**: When Rust needs to send FitResult (which contains MyModel) to Python, serialization fails.

**Fix**: Always include `#[derive(Serialize, Deserialize, Debug, Clone)]`.

### ❌ Anti-Pattern 8: Parameter Order Mismatch Between Names and Implementation

**Wrong**:
```rust
fn param_names(&self) -> Vec<&str> {
    vec!["amplitude", "center", "sigma"]
}

fn eval(&self, x: &[f64], params: &[f64]) -> Result<Vec<f64>, ModelError> {
    let center = params[0];      // Wrong! Should be params[1]
    let sigma = params[1];       // Wrong! Should be params[2]
    let amplitude = params[2];   // Wrong! Should be params[0]
    // ...
}
```

**Consequence**: Model evaluates with scrambled parameters → completely wrong results, silently.

**Fix**: Document parameter order clearly. Add a test that verifies param_names order against expected eval behavior.

## Checklist for Each New Model

Before committing a new model, verify:

- [ ] Module docstring includes equation and parameter meanings
- [ ] `Model` trait: all 5 methods implemented (eval, jacobian, bounds_check, num_params, param_names)
- [ ] `bounds_check()` called at start of eval() and jacobian()
- [ ] Bounds checking rejects NaN, Infinity, and invalid ranges
- [ ] `num_params()` returns correct count
- [ ] `param_names()` matches parameter order in eval/jacobian
- [ ] Jacobian is analytical (not finite-difference)
- [ ] Jacobian formulas documented in comments
- [ ] Test module exists with ≥5 test functions
- [ ] `test_jacobian_vs_numerical()` compares analytical vs numerical Jacobian
- [ ] All tests pass locally (`cargo test --package spectrafit-models`)
- [ ] `#[derive(Serialize, Deserialize, Debug, Clone)]` on struct
- [ ] No `unwrap()` calls (use `?` or explicit error handling)
- [ ] Code reviewed by peer (at least 1 review)

## Success Criterion

A model implementation is complete when:

1. It compiles without warnings
2. All 5 trait methods are implemented and tested
3. Bounds checking prevents invalid parameters
4. Jacobian passes numerical comparison test (rel_error < 1e-5)
5. No panics occur on edge cases (sigma near 0, parameters at boundaries)
6. Serde roundtrip works (serialize → deserialize → serialize matches)
7. 100% test coverage (cargo tarpaulin or similar)
