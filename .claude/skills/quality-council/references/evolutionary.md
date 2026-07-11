# Evolutionary reference — Vista traps and Rosetta roadmaps

Self-contained essentials. Historical specialist content lives in git
history under `.claude/skills/evolutionary-platform-thinking/`.

## The premise

Apple's unbroken line from NeXTSTEP → OS X → macOS on Apple Silicon
shows that an architecture can evolve across decades without a rewrite.
Microsoft's Vista is the counter-example: a forced restart that broke
forward compatibility and bled users for years.

This voice asks: **will the design decisions we're making now force a
rewrite, or allow incremental evolution?**

## When this voice applies

- "will this scale?" / "future-proof this" / "API versioning"
- "avoid breaking changes" / "design for change"
- "is this extensible?" / "will I regret this architecture?"
- "monolith vs modular" / "plugin system" / "stable interface"

## The Vista Trap Table

For any architectural decision, list:

| Decision | Vista trap? | Why | Mitigation |
|----------|-------------|-----|------------|
| Hardcoded backend ids | YES | A new backend forces edits everywhere | `solversOf(report)` enumeration |
| `?? PRIMARY` silent fallback | YES | Hides the missing-data case until prod | No fallback; honest error |
| Per-crate `model_type_to_str` table | YES | A new model forces N-crate updates | One canonical `ModelTypeStr::as_str()` |
| Frozen contract with optional fields + migrator | NO | New fields don't break old payloads | SCHEMA_VERSION policy + `migrate.py` |

## Evolution Readiness Score (6 dimensions, 1–5 each)

1. **Contract stability** — additive changes preserve old consumers.
2. **Registry over map** — new entries are data, not code paths.
3. **Boundary clarity** — every wire has a named contract.
4. **Migration story** — every breaking change has a registered upgrader.
5. **Deprecation discipline** — old paths are marked, not silently removed.
6. **Plurality of backends** — no hidden single-backend assumption.

Sum / 30 → fitness. <20 → needs a Rosetta roadmap (the incremental path
to higher fitness; named after Rosetta the binary translator, which
bridged the Intel → Apple Silicon transition without breakage).

## In this repo

`solversOf(report)` enumeration, the `noHardcodedBackend.test.ts`
guard, the `ModelTypeStr::as_str()` canonical string, the `migrate.py`
registry, the `BenchReport.baseline_solver_id` named-baseline — these
are all Vista-trap avoidances earned across cycles. The skill catalog
consolidation (this work) is itself a Rosetta roadmap — moving from
28 → 7 without losing the specialist knowledge.

## The voice in the council

When the council convenes on an architectural decision, this voice
forces the **long view** — the other voices critique what feels right
now; this voice asks whether it will still be right in 12 months.
