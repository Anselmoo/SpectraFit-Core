---
name: python-stream
description: |
  Conductor for the Python python/ stream. Owns Pydantic schemas, the
  oracles benchmark engine, the BenchReport contract, test coverage,
  and Python architecture decisions. Absorbs spectrafit-schemas,
  spectrafit-tests, spectrafit-tdd, python-arch-proposer, and
  python-pattern-advisor — their specialist content lives in references/.
  Use when a task touches python/oracles/, python/spectrafit_core/,
  the Pydantic models, the benchmark engine, the contract, or pytest.
  Also when the user pastes Python and asks "is this Pythonic?",
  "review this Python", or "how can I improve this code?".
  Composes with superpowers:test-driven-development and
  superpowers:verification-before-completion. Serena-first.
license: MIT
---

# python-stream

The single entry point for any Python-side work in spectrafit-core. Reads
`.claude/skills/INDEX.yaml § python-stream` for its anchor slice, then
dispatches to a `references/` sub-document for the specialist matter.

## Anchors (load these into context)

**CLAUDE.md sections** (read these before acting):
- *Code Conventions (pydantic-first)* — BaseModel over @dataclass,
  match over if/elif chains, registry over per-call maps.
- *Benchmark Engine (`oracles`) + Report* — registry-driven pipeline,
  frozen `BenchReport` contract, two consumption paths.
- *Regenerate the contract (OpenAPI flow)* — the `npm run contract`
  step that follows any `contract.py` edit.

**Hooks that will fire** (respect their contract):
- `enforce-pydantic-native.sh` — Edit/Write on benchmark/test Python:
  block dict-key contract access; require typed accessors.
- `enforce-match-dispatch.sh` — Edit/Write on `python/extras/**`,
  `tests/**`: 2+ if/elif `==` branches on a discriminator must be `match`.
- `enforce-modeltype-parity.sh` — warns when Python `ModelType` and
  Rust `ModelTypeStr` drift.
- `contract-sync-reminder.sh` — non-blocking nudge after `contract.py`
  edits (regenerate `openapi.gen.ts`).
- `pre-merge-schema-sync.sh` — pre-merge gate that the contract round-
  trips.

## Serena first (non-negotiable)

The first action on any code-touching task **MUST** be a serena MCP call,
not a Grep:

```
mcp__serena__get_symbols_overview          → file orientation
mcp__serena__find_symbol BenchReport       → locate a Pydantic model
mcp__serena__find_referencing_symbols      → who consumes this contract
mcp__serena__replace_symbol_body           → edit a method/class body
```

For schema work especially: every contract change touches multiple
consumers — `find_referencing_symbols` on the renamed field is the only
way to stay safe.

## Analyzer-MCP companion (CLAUDE.md anchor)

Per CLAUDE.md: **before any `git push` touching `python/**` or `tests/**`**,
run `mcp__analyzer__ruff-check-ci` + `mcp__analyzer__ty-check`. This is
the same contract `lint:python` runs in CI, executed in <2 s instead of
waiting 3 min. CLI fallback: `uv run poe lint_ci`.

Pair with `uv run poe scenario_smoke` for a fast (<500 ms) spectrafit/lmfit
cross-check before pushing model changes.

## Decision: which sub-document?

| Subject of the task | Reference |
|---------------------|-----------|
| Pydantic schemas, serde drift, field rename, alias, round-trip | `references/schemas.md` |
| pytest coverage, quick_validation reproducers, flaky tests | `references/tests.md` |
| Failing pytest → which agent owns the fix? | `references/tdd.md` |
| Project structure, module responsibilities, refactor proposals | `references/arch.md` |
| Pattern advice (registry, Borg, lazy_property, …) | `references/patterns.md` |
| "Is this Pythonic?" / PEP 20/8 code review, before/after rewrites | `references/pythonic.md` |

## Composes with (call these in order)

1. **Before** touching code: `superpowers:test-driven-development` —
   the failing test first. For Python-stream, the contract test (a
   `BenchReport.model_validate(...)` round-trip) is often the right one.
2. **While** fixing: this skill's reference for the domain matter,
   serena-driven.
3. **After**: `mcp__analyzer__ruff-check-ci` + `mcp__analyzer__ty-check`
   + `superpowers:verification-before-completion`. Evidence before
   assertions — never claim "done" without the analyzer output.
4. **If stuck**: `andon-loop/references/stuck-mode.md`.

## Three-pillar reporting

- **PERF**: name the bench fast path touched (e.g. `fit_fast`); quote
  `manifest.geomean_speedup_vs_baseline` if applicable.
- **RIGOR**: name the `_SHAPE_BOUNDS` entry or model-registry change;
  state any |Δr²| signal change.
- **PRESENTATION**: name the contract field changed and the web panel
  that consumes it (read via `mcp__serena__find_referencing_symbols`
  on the renamed/added field).

Pillars are reports in tier 1; gates in `harden` intent.

## Tier-1 status

This SKILL.md is the conductor scaffold. References currently link back
to the originals; tier 2 will relocate the bodies.
