> Applies to: python/extras/**/*.py

# Extras typing rules

Apply these rules to all Python files under `python/extras/`.

## Rules

- Do not use `Any` in public or module-level annotations.
- Prefer explicit models (`pydantic.BaseModel`) or concrete `TypedDict` for structured payloads.
- Public functions must have explicit parameter and return types.
- Public Pydantic models must set `model_config = ConfigDict(strict=True)` unless a documented exemption exists.
- Scenario and benchmark functions must return typed contracts for API surfaces (e.g., `BenchmarkResponse`) rather than untyped dictionaries.

## Do not

- Do not introduce `dict[str, Any]` in new code.
- Do not expose loosely typed JSON payloads when a typed schema can be defined.
