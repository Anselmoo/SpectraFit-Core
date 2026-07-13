> Applies to: **/*.{py,rs}

# Pydantic ↔ Rust Schema Synchronization Rules

This file mandates imperative, testable rules for keeping Python (Pydantic v2) schemas synchronized with Rust (serde) models across the PyO3 JSON boundary.

## Context

- **Problem**: Python and Rust schemas are not in a single source of truth (acknowledged trade-off in DECISIONS.md)
- **Consequence**: Field additions, renames, type changes, or serialization name mismatches cause JSON round-trip failures and runtime validation errors
- **Scope**: All changes to either `python/spectrafit_core/schemas/` or `src/types.rs` that modify public models

## Core Rules

1. **Always update BOTH schemas** when modifying a public model (field add/remove/rename/type change)
   - Python change without Rust change → JSON parse failure when Rust sends data
   - Rust change without Python change → validation failure when Python receives data
   - **Action**: Before committing, verify both changes are present in the diff

2. **Match serde field names to Pydantic alias names exactly**
   - Pydantic: `Field(alias="model_name")` must match Rust: `#[serde(rename = "model_name")]`
   - Mismatch → JSON deserialization fails silently or panics
   - **Action**: When adding a field, use explicit `alias=` in Pydantic and `rename=` in Rust

3. **Use JSON strings only across the FFI boundary**
   - Never marshal Python objects or Rust structs directly
   - Always: `python_model.model_dump_json()` → pass to Rust → `RustModel::from_str()` → `model_validate_json()`
   - **Action**: Every Rust function exported via PyO3 must accept `&str` (JSON string) and return `Result<String>` (JSON string)

4. **Test JSON round-trips before merging**
   - Create a Python model instance → serialize to JSON → parse in Rust → serialize back → parse in Python
   - Verify all fields survive the round-trip unchanged
   - **Action**: Add a round-trip test to test suite for any schema change

## Extended Rules & Workflows

### Trigger Conditions

Schema sync is required when:

- **Field Addition**: Adding a new field to either Pydantic or Rust schema
  - Example: Adding `convergence_status: str` field to FitResult
  - Both: Add to Pydantic model + Rust struct + serde mappings + test

- **Field Rename**: Renaming a field in either schema
  - Example: `fit_params` → `parameters` (note: Pydantic alias differs from struct field name)
  - Both: Update struct field name + serde(rename) + Pydantic Field(alias)

- **Type Change**: Changing the type of a field
  - Example: `iterations: int` → `iterations: Optional[int]` (some solvers don't report this)
  - Both: Change Pydantic type annotation + Rust type + serde serialization + update tests

- **Optional/Required Flip**: Making a required field optional or vice versa
  - Example: `parameters: Dict[str, float]` → `Optional[Dict[str, float]]`
  - Both: Update type (add/remove `Option`), update serde(skip_serializing_if), update tests

### Workflow A: Adding a New Field

**Scenario**: Benchmark result needs `chi_squared: float` (goodness-of-fit metric).

**Step 1 (Python)**: Edit `python/spectrafit_core/schemas/fit_result.py`
```python
from pydantic import BaseModel, Field

class FitResult(BaseModel):
    model_dump_json: Optional[str] = None
    chi_squared: float = Field(
        ...,
        description="Chi-squared / (DOF). Lower is better. Computed post-fit.",
        ge=0.0,  # Non-negative constraint
    )
    # ... existing fields
```

**Step 2 (Rust)**: Edit `src/types.rs`
```rust
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct FitResult {
    #[serde(rename = "chi_squared")]
    pub chi_sq: f64,  // Note: serde name matches Pydantic alias
    // ... existing fields
}
```

**Step 3 (Validation)**: Create a round-trip test
```python
# tests/test_schema_roundtrip.py
def test_fit_result_chi_squared_roundtrip():
    result = FitResult(
        ...,
        chi_squared=1.23,
    )
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["chi_squared"] == 1.23
    
    # Simulate receiving from Rust
    rust_json = '{"...", "chi_squared": 1.5}'
    rehydrated = FitResult.model_validate_json(rust_json)
    assert rehydrated.chi_squared == 1.5
```

**Step 4 (Commit Checklist)**:
- [ ] Both Python and Rust files edited
- [ ] Serde rename matches Pydantic alias
- [ ] Round-trip test added and passing
- [ ] Type constraints (ge, le, max_length) enforced in both
- [ ] Default value matches in both (if any)

### Workflow B: Renaming a Field

**Scenario**: Renaming `fit_params` → `optimized_parameters` for clarity.

**Old Schema (Python)**:
```python
class FitResult(BaseModel):
    fit_params: Dict[str, float]
```

**Old Schema (Rust)**:
```rust
pub struct FitResult {
    pub fit_params: HashMap<String, f64>,
}
```

**New Schema (Python)** — Keep JSON name backwards-compatible:
```python
class FitResult(BaseModel):
    optimized_parameters: Dict[str, float] = Field(
        alias="fit_params",  # Keep JSON name for backwards compat with existing Rust
    )
```

**New Schema (Rust)** — Rename struct field, update serde:
```rust
pub struct FitResult {
    #[serde(rename = "fit_params")]  // Keep JSON name for backwards compat
    pub optimized_parameters: HashMap<String, f64>,
}
```

**Benefit**: Old JSON from Rust still deserializes in Python (serde(rename) sends old name), Python code uses new name.

**Validation**:
```python
def test_fit_params_backwards_compat():
    # Old Rust JSON still parses
    old_rust_json = '{"fit_params": {"a": 1.0}}'
    result = FitResult.model_validate_json(old_rust_json)
    assert result.optimized_parameters == {"a": 1.0}
```

### Workflow C: Type Change (Adding Optional)

**Scenario**: Not all solvers report `convergence_iterations`, so it should be Optional.

**Step 1 (Python)**:
```python
from typing import Optional

class FitResult(BaseModel):
    convergence_iterations: Optional[int] = Field(
        default=None,
        description="Iterations to convergence. None if solver doesn't report.",
    )
```

**Step 2 (Rust)**:
```rust
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct FitResult {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub convergence_iterations: Option<u32>,
}
```

**Step 3 (Tests)**: Verify both null and non-null cases:
```python
def test_convergence_iterations_optional():
    # With value
    result1 = FitResult(..., convergence_iterations=42)
    json1 = result1.model_dump_json()
    assert json.loads(json1)["convergence_iterations"] == 42
    
    # Without value (None)
    result2 = FitResult(..., convergence_iterations=None)
    json2 = result2.model_dump_json()
    # Verify field is omitted in JSON (due to skip_serializing_if)
    assert "convergence_iterations" not in json.loads(json2)
    
    # Rust sends null or omits field; both should parse
    rehydrated = FitResult.model_validate_json(json2)
    assert rehydrated.convergence_iterations is None
```

## Serialization Mappings Reference

Common type mappings between Python and Rust (all via JSON):

| Python Type | Rust Type | JSON Representation | Notes |
|-------------|-----------|---------------------|-------|
| `str` | `String` | `"text"` | Always quoted in JSON |
| `float` | `f64` | `1.23` | IEEE 754 double precision |
| `int` | `i64` or `u32` | `42` | No quotes in JSON |
| `bool` | `bool` | `true` or `false` | Lowercase in JSON |
| `Optional[T]` | `Option<T>` | `null` or valid T | Use `skip_serializing_if` in Rust |
| `List[T]` | `Vec<T>` | `[elem1, elem2]` | Square brackets in JSON |
| `Dict[str, T]` | `HashMap<String, T>` | `{"key": value}` | String keys required in JSON |
| `dict` | `serde_json::Value` | Any JSON value | Permissive but risky; avoid |

**Rule**: Every public schema should map cleanly to one of these standard JSON types. Avoid custom serializers unless documented in code.

## Anti-Patterns: What NOT To Do

### ❌ Anti-Pattern 1: Partial Schema Update

**Wrong**: Update Pydantic model but forget Rust struct
```python
# python/spectrafit_core/schemas/fit_result.py
class FitResult(BaseModel):
    new_field: str  # Added
```

```rust
// src/types.rs (NOT updated)
pub struct FitResult {
    // Missing new_field!
}
```

**Consequence**: Rust sends JSON with missing field → Pydantic validation fails.

**Fix**: Always update both schemas in the same commit.

### ❌ Anti-Pattern 2: Ignoring Serde Field Names

**Wrong**: Different names in Pydantic and Rust
```python
class FitResult(BaseModel):
    num_iterations: int  # Snake case
```

```rust
pub struct FitResult {
    // No serde(rename), defaults to "num_iterations"
    pub iterations: u32,
}
```

JSON from Rust: `{"num_iterations": 5}` ✓ Works because Rust field serializes as "num_iterations"

But if Rust is changed to:
```rust
pub struct FitResult {
    pub iteration_count: u32,  // Without serde(rename), serializes as "iteration_count"
}
```

JSON mismatch: Rust sends `{"iteration_count": ...}`, Python expects `{"num_iterations": ...}` ❌ Fail

**Fix**: Use explicit `serde(rename)` in Rust to match Pydantic field names (or aliases).

### ❌ Anti-Pattern 3: Schema Drift Over Time

**Wrong**: Making small, undocumented schema changes without updating the other side
```python
# Adds a new optional field
class FitResult(BaseModel):
    status: Optional[str] = None  # Not documented as schema change
```

Over time, the Rust side slowly falls out of sync. Developers add tests that only cover Python, so the Rust gap isn't caught.

**Fix**: Document schema changes in DECISIONS.md. Tag commits with `[SCHEMA]` prefix. Enforce round-trip tests in CI.

### ❌ Anti-Pattern 4: Skipping Serialization Tests

**Wrong**: Adding a field to both schemas but no round-trip test
```python
# Code change added field, reviewed and merged
# But no test validates round-trip behavior
```

Months later, someone refactors Rust serialization and breaks the field. Not caught until production.

**Fix**: Every schema change requires a round-trip test. CI must fail if missing.

### ❌ Anti-Pattern 5: Type Mismatch Between Schemas

**Wrong**: Different types for the same semantic value
```python
class FitResult(BaseModel):
    chi_squared: float  # Python: always a float
```

```rust
pub struct FitResult {
    pub chi_sq: Option<f64>,  // Rust: sometimes None
}
```

When Rust sends None, Python receives null → `model_validate_json()` fails because `chi_squared` is required (not Optional).

**Fix**: Match Optional/required status in both schemas.

### ❌ Anti-Pattern 6: Recursive Types Without Documentation

**Wrong**: Circular schema references without explicit handling
```python
class FitResult(BaseModel):
    metadata: Dict[str, "FitResult"]  # Self-reference
```

Rust doesn't support recursive types easily. JSON serialization may loop.

**Fix**: Flatten recursive structures or use IDs + external references. Document explicitly.

## Validation Tests (Copy-Paste Ready)

Add these tests to your test suite whenever you modify schemas:

```python
# tests/test_pydantic_rust_roundtrip.py
import json
from spectrafit_core.schemas import FitResult, GraphInput

def test_fit_result_roundtrip():
    """Verify FitResult serializes and deserializes cleanly."""
    original = FitResult(
        model_name="Gaussian",
        success=True,
        chi_squared=1.23,
        parameters={"amplitude": 5.0, "center": 100.0, "sigma": 10.0},
    )
    
    # Serialize to JSON
    json_str = original.model_dump_json()
    
    # Deserialize back
    parsed = json.loads(json_str)
    restored = FitResult.model_validate(parsed)
    
    # Verify all fields match
    assert restored.model_name == original.model_name
    assert restored.success == original.success
    assert restored.chi_squared == original.chi_squared
    assert restored.parameters == original.parameters

def test_optional_fields_roundtrip():
    """Verify optional fields survive round-trips."""
    result_with_none = FitResult(
        ...,
        convergence_iterations=None,
    )
    
    json_str = result_with_none.model_dump_json()
    parsed = json.loads(json_str)
    
    # Field should be absent due to skip_serializing_if
    if "convergence_iterations" in parsed:
        assert parsed["convergence_iterations"] is None
    
    restored = FitResult.model_validate_json(json_str)
    assert restored.convergence_iterations is None

def test_alias_mapping():
    """Verify serde(rename) aliases are handled correctly."""
    # Python uses alias for construction or old-format JSON
    old_json = '{"fit_params": {"a": 1.0}}'
    result = FitResult.model_validate_json(old_json)
    
    # Python field name is the new one
    assert hasattr(result, "optimized_parameters")
    assert result.optimized_parameters == {"a": 1.0}
```

## Datetime Serialization (Critical)

**Rule**: Always use `model_validate_json()` path for deserializing JSON that contains datetime fields. **Never use the `Model(**dict)` constructor** on raw dict data with datetime strings.

**Why**: Pydantic v2 only parses ISO 8601 datetime strings when using the JSON validation pipeline. Direct dict construction skips this, causing `ValidationError: Input should be a valid datetime`.

### ✅ Correct Pattern

```python
# When loading JSON from disk or API
with open("data.json") as f:
    data = json.load(f)  # dict, not JSON string

# Convert dict back to JSON string for proper datetime parsing
result = FitResult.model_validate_json(json.dumps(data))
```

### ❌ Broken Pattern

```python
# NEVER do this with datetime fields:
with open("data.json") as f:
    data = json.load(f)

result = FitResult(**data)  # ❌ Datetime strings not parsed!
# ValidationError: Input should be a valid datetime [type=datetime_type, ...]
```

### Rust Counterpart

In Rust, serialize datetime as ISO 8601 string using serde's default behavior:
```rust
#[derive(Serialize, Deserialize)]
pub struct FitResult {
    pub timestamp: DateTime<Utc>,  // Serializes to ISO 8601 string automatically
}
```

This is handled transparently by serde + chrono. Python's `model_validate_json()` will parse it correctly.

## Do Not

- Do not marshal Python objects across the FFI boundary; always serialize to JSON first
- Do not use `dict` or `Any` types in public schemas; use explicit `Dict[str, T]` or `T` variants
- Do not add a field to one schema without adding it to the other
- Do not rely on field ordering in JSON (JSON object keys are unordered)
- Do not modify serialization behavior (e.g., custom serializer) without updating tests
