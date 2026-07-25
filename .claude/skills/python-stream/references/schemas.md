# Schemas reference — Pydantic models, serde drift, contract round-trip

Self-contained essentials for schema drift triage. Historical content
lives in git history under `.claude/skills/spectrafit-schemas/`.

## Failure modes this reference covers

- Pydantic field rename without serde wire alignment (Rust serializes
  field A; Python validates field B).
- JSON round-trip failure: `BenchReport.model_validate(payload)` raises
  `ValidationError`.
- `model_type` string drift: Rust `ModelTypeStr::as_str()` and Python
  `ModelType.value` diverge.
- Alias rules: Pydantic field renamed but no `validation_alias=` set,
  breaking the legacy payload path.

## python-stream contract additions

1. **Serena first** — `mcp__serena__find_referencing_symbols
   <FieldName>` before renaming or removing any contract field. The
   web side reads via OpenAPI; a missed reference shows up as a Δr²
   gate failure or a runtime TypeError in a panel.
2. **Hook contracts** — `enforce-pydantic-native.sh` blocks dict-key
   access on `BenchReport`; `contract-sync-reminder.sh` nudges to
   regen `openapi.gen.ts`; `pre-merge-schema-sync.sh` is the final gate.
3. **SCHEMA_VERSION policy** (CLAUDE.md):
   - Additive minor: optional field with default → no migrator entry,
     Pydantic fills in for old payloads.
   - Breaking major: rename/removal → register an upgrader in
     `python/oracles/migrate.py` via `@register_migration("from", "to")`.

## Quick paths

- Contract: `python/oracles/contract.py` (the `BenchReport` family).
- API serving the contract: `python/oracles/api.py`.
- Generated TS view: `web/src/openapi.gen.ts` (regenerate via
  `cd web && npm run contract` with `uv run poe serve` running).
- Re-exports: `web/src/contract.ts` (named view types).
- Migrator registry: `python/oracles/migrate.py`.

## Stuck-mode entry

Two reopens on a schema wire ⇒ the rename touched a consumer not on the
known caller list. Curiosity sub-cycle: `mcp__serena__find_symbol
<field>` + `find_referencing_symbols` across `python/`, `web/src/`,
`tests/`. The hidden caller is almost always a panel registry entry.
