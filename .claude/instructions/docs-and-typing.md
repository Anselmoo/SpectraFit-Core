> Applies to: **/*.{py,rs}

# Docstrings & Type annotations — Python and Rust

Who: all contributors and reviewers.  When: on any PR that adds or modifies `.py` or `.rs` files under the repository.  Why: clear, verifiable public APIs and a stable JSON FFI boundary between Python and Rust.

## Rules (Python)

- Public modules, packages, classes, and functions under `python/` MUST have docstrings following PEP 257 semantics: triple-double quotes, a one-line summary, a blank line, then details. Use explicit sections for `Args:`, `Returns:`, `Raises:`, and `Examples:` for non-trivial APIs.

- Use PEP 484 type hints for all public functions and methods: annotate every argument and the return type. For class constructors annotate `-> None` on `__init__`.

- Prefer modern builtin generics (PEP 585) when targeting Python >=3.9 (e.g., `list[str]`, `dict[str, int]`). Use `typing` helpers (`TypeVar`, `Annotated`, `Optional`) when required.

- In modules with forward references, prefer `from __future__ import annotations` to keep annotations readable and avoid runtime import cycles.

- Pydantic v2 models (public) MUST:
  - declare explicit types for every field (no `Any` for public models),
  - set `model_config = ConfigDict(strict=True)` for public-facing schemas unless a documented exception is provided,
  - include a short docstring describing the JSON shape and an `Examples:` JSON snippet,
  - use `model_dump_json()` when serializing to pass to Rust; use `model_validate_json()` when validating Rust-returned JSON.

- Docstring style: adopt a single, machine-parseable style (we recommend Google-style `Args:`/`Returns:` blocks). Enforce with linters (e.g., `pydocstyle` / `ruff`).

## Rules (Rust)

- All `pub` items (crate-level, modules, structs, enums, functions) MUST have rustdoc comments (`///`) with a one-line summary, optional details, and at least one copy-pasteable `Examples` code block where applicable. Use `//!` for crate/module front-page docs in `lib.rs`.

- Document `Panics`, `Errors`, and `Safety` when relevant. Prefer examples that compile and run as doctests so `cargo test --doc` verifies them.

- JSON boundary types:
  - Use `serde::{Serialize, Deserialize}` with explicit attributes to guarantee field naming (e.g. `#[serde(rename_all = "snake_case")]`) so Rust JSON matches Pydantic output.
  - Public FFI functions that cross to Python MUST accept/return JSON strings. Signature pattern: `fn fit(json: &str) -> Result<String, Error>` (or `PyResult<String>` for `#[pyfunction]`). Document the expected JSON schema in the doc comment.

- Public Rust APIs must use explicit, concrete types in signatures. Return `Result<T, crate::error::Error>` for fallible APIs and implement `std::error::Error` + `Display` for your error type.

- For pyo3 wrappers: annotate with `#[pyfunction]`/`#[pymethods]`, keep the Python-visible signature simple (strings for JSON boundaries), and set `text_signature` and doc comments so Python `help()` shows correct docs.

## Cross-language rules (FFI / JSON boundary)

- The Python↔Rust boundary must always use JSON strings. Do not pass typed Python objects across FFI directly.

- Use snake_case for JSON field names across both sides. In Python, ensure `model_dump_json()` emits snake_case (use `model_config` aliases if needed). In Rust, use `#[serde(rename_all = "snake_case")]` on structs.

- Document the schema in both the Pydantic model docstring and the Rust struct doc comment; include a minimal JSON example in both places. Tests must include a round-trip assertion that `serde_json::to_string()` of the Rust type matches Pydantic `model_dump_json()` shape (keys and types).

## Tooling & enforcement

- CI must run: `ruff`/`pydocstyle` (docstring checks), a type checker (`mypy` or `pyright`) for Python, `cargo fmt`, `cargo clippy`, and `cargo test --doc` for Rust doctests. PRs touching public APIs should be blocked until linters, type checks, and doctests pass.

- Use `pydocstyle` + `ruff` for Python docstring enforcement, and `rustdoc` (doctests) plus `cargo test --doc` for Rust.

## Do not

- Do not omit docstrings for exported/public items. Do not use single-quote or non-standard delimiters for Python docstrings — use triple double quotes `"""`.

- Do not expose internal or private types in public APIs. Do not use `Any` for public schema fields.

- Do not mix snake_case and camelCase in JSON across languages; pick snake_case for this repository.

## Examples (recommended forms)

Python (Google-style docstring + type hints):

```python
def fit(graph: FitGraph) -> FitResult:
    """Run a fit using the Rust core.

    Args:
        graph: a validated `FitGraph` pydantic model.

    Returns:
        FitResult: validated result model.

    Example:
        >>> graph = FitGraph(...)
        >>> res = fit(graph)
    """
    json_in = graph.model_dump_json()
    json_out = _core.fit(json_in)
    return FitResult.model_validate_json(json_out)
```

Rust (rustdoc + serde + pyo3 signature):

```rust
/// Fit the provided JSON-encoded graph and return a JSON-encoded result.
///
/// # Examples
///
/// ```
/// let json = r#"{"nodes": []}"#;
/// let out = mycrate::core::fit(json).unwrap();
/// ```
#[pyfunction]
fn fit(json: &str) -> PyResult<String> {
    // parse/validate with serde_json, do work, return JSON string
}
```

---

Recommended path: `.github/instructions/docs-and-typing.instructions.md`
Recommended scope: workspace-wide; run enforcement in CI and as pre-commit checks.
