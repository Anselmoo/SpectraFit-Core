> Applies to: python/benchmarkmark/**/*.py|tests/**/*.py

# Benchmark/test Pydantic-native contract rules

## Rules

- Treat benchmark runner payloads as typed Pydantic models, not raw dictionaries.
- Use `model_validate(...)` / `model_validate_json(...)` when reading JSON payloads at test boundaries.
- Use `model_dump(...)` / `model_dump_json(...)` at serialization boundaries.
- Keep typed `Path` fields in payload models for artifact paths instead of stringly-typed path values.
- Prefer explicit, strict contract models (`ConfigDict(strict=True)`) for public benchmark/test payload surfaces.

## Do not

- Do not access benchmark runner payload contracts via dictionary indexing (for example, `payload["report_dir"]`).
- Do not parse benchmark contract JSON with `json.loads(...)` and then navigate nested keys as the primary contract path in tests.
