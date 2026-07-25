---
type: gap
title: "[Medium] audit: stored benchmark run artifacts have stale snake_case trustBlock fields"
description: ".spectrafit_reports/benchmark/2026-06-27_run_023/results.json and .../2026-06-27_run_024/results.json fail test_results_json_canonical_roundtrip — trustBlock sub-fields (n_claims_audited, wire_id, nist_validation, etc.) are still snake_case, predating the 2026-07-13 trust_ledger.py camelCase fix"
tags: ["kind:bug", "status:closed", "domain:audit", "severity:medium"]
timestamp: "2026-07-25T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `.spectrafit_reports/benchmark/2026-06-27_run_023/results.json`,
  `.spectrafit_reports/benchmark/2026-06-27_run_024/results.json`
- Finding domain: audit (discovered during final post-sweep sanity testing, not from the original
  self-assess brief or the unattributed-findings list — a genuinely new discovery)
- Suggested fix / explanation: N/A (new finding, no pre-existing suggested fix)
- Resolved by: [[evidence/unattributed-migrate-ev1]]
- Proposal: Root-caused via a corrected recursive diff (the first diagnostic script had a bug —
  it silently ignored empty-list/dict presence differences, hiding the real drift; a rewritten
  version caught it). Both stored files' `trustBlock` sub-object has old snake_case field names
  (`n_claims_audited`, `n_claims_total`, `nist_validation`, and each wire's `wire_id`) instead of
  the current camelCase contract (`nClaimsAudited`, `nClaimsTotal`, `nistValidation`, `wireId`) —
  from before DECISIONS.md's `[2026-07-13] trust_ledger.py contract camelCase fix` ADR landed.
  That fix did not bump `SCHEMA_VERSION` (still "1.7" both before and after), so
  `migrate_payload_to_current`'s version-gated migration chain has no hop to normalize this —
  by its own docstring, "The already-current identity path is left untouched (zero-cost, no
  validation)" for any payload whose `schemaVersion` already equals current, which both these
  files' do. Considered two fixes: (A) bump `SCHEMA_VERSION` to 1.8 and register a new migrator —
  architecturally correct per this project's own SCHEMA_VERSION policy (DECISIONS.md
  2026-06-06 ADR: a rename requires a registered upgrader), but high blast radius (ripples into
  every schema-version-pinned golden/snapshot/sentinel test across the repo) and deserves its own
  dedicated cycle, not a same-pass slip-in. (B) Bring the two specific stored artifacts into
  canonical form directly, since they are static generated benchmark-run fixtures (not live
  contract code) — chosen as the appropriately-scoped fix. Loaded each file once (confirmed
  `BenchReport.model_validate(raw)` already succeeds on the old snake_case shape — the Pydantic
  model accepts both casings on read, only emits camelCase via `by_alias=True`), re-emitted via
  `model.model_dump_json(by_alias=True)`, and overwrote each file with its own canonical
  re-emission (byte-identical to what the failing test itself computes as `re_emitted` — i.e. this
  IS the fix the test's own logic implies, just applied once and persisted rather than recomputed
  every test run). Verified: re-ran both previously-failing parametrized tests after the fixup —
  both pass. Flagged the SCHEMA_VERSION-bump path (option A) as a real, separate architectural
  follow-up the user may want to open as its own dedicated piece of work later — not attempted
  here. Strategy: a (functional — re-ran the actual failing tests against the fixed files).
  Blast radius: local+reversible. IMPORTANT SCOPE NOTE: both files live under
  `.spectrafit_reports/` which is gitignored (`.gitignore:63`) — they are NOT git-tracked, so this
  fix has ZERO footprint in `git diff`/the MR; it only makes THIS machine's local test runs green.
  The underlying `migrate_payload_to_current` completeness gap (option A above) remains real and
  unaddressed in the actual codebase — any other local checkout with its own old accumulated
  `.spectrafit_reports/` history predating the 2026-07-13 casing fix would hit the identical
  failure. Flagged explicitly to the user as a genuine follow-up, not silently closed by this
  local-only workaround.
