> Applies to: python/**

# Pydantic v2 & typing rules

This file mandates idiomatic, verifiable rules for Pydantic v2 usage and for JSON round-trips across the Python↔Rust boundary.

## Rules

- Use Pydantic v2 BaseModel for all public schema types (e.g., `FitGraph`, `FitResult`).

- Prefer `model_dump_json()` when sending data to the Rust boundary and accept JSON strings from Rust via `model_validate_json()` or `parse_raw_model`.

- Declare explicit types and avoid permissive `Any` for public models. Use `typing.Annotated[...]` and `pydantic.Field()` for metadata where needed.

- Model configuration: prefer `model_config = ConfigDict(strict=True)` for public-facing models to catch invalid types early.

## Example usage (rules must be followed):

- When calling the Rust layer: `json = my_model.model_dump_json()` then pass `json` to `_core.fit(json)`.
- When receiving JSON from Rust: `FitResult.model_validate_json(returned_json)` and assert required fields.

## Do not

- Do not marshal Python objects across the FFI boundary; always use JSON strings.
