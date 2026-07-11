# Three-Language Audit — 2026-07-02

Point-in-time audit of the three codebases (Rust `crates/`, Python `python/`,
TypeScript `web/`) on branch `code-review-faible`. Method: three parallel
exploration passes (doc inventory, code inventory, history mining of
`DECISIONS.md` + session memories), contradictions between passes resolved by
direct reads, then an *ideal-picture diff* — a from-scratch reference model of
what this product would look like, compared against what exists. The only
mutations in this audit are documentation fixes and deletions (§6); no code was
changed.

> Dated audit records are point-in-time by construction and are not maintained
> as living docs. For current state, trust the code and the guards named below.

---

## 1. Scope & method

- **Expected-by-docs vs is** — every major claim in README / CLAUDE.md /
  MODELS.md / LIMITATIONS.md / CHANGELOG cross-checked against code.
- **Must-have vs nice-to-have** — gap matrix in §3.
- **Ideal picture** — §2, designed independent of the current code, then
  diffed. Where the code *exceeds* the ideal, that is stated too.
- **History-grounded root causes** — §4 maps every gap to the 9-class
  recurring-challenge taxonomy mined from `DECISIONS.md` and session memories.

## 2. Ideal picture vs actual

### 2.1 Rust (`crates/`)

**Ideal:** one declarative model manifest as the single source of truth;
enum, wire strings, counts, and every downstream all-variants list derived
from it; kernels implement one trait; solver methods live in sibling crates
behind one dispatch layer; adding a model is data plus one kernel file.

**Actual:** converged to a striking degree. `model_manifest!` in
`crates/spectrafit-types/src/types.rs` generates `ModelTypeStr` (34 variants),
`ALL`, `VARIANT_COUNT`, and `as_str()`; the serde-wire/`as_str` byte-parity is
pinned by `model_type_as_str_matches_serde_wire_for_every_variant`. Downstream
lists (varpro classifier, parity guards) iterate `ALL`. 33 kernel files, 4
solver crates (LM / trust-region / dogleg / Newton-CG) + varpro + dispatch,
each with in-crate tests. Exactly **one** TODO in the whole workspace
(`math_backend.rs`, SIMD backends).

**Residual ideal-diff:**
- Adding a model still ripples ~6 crates / ~12 sites (kernel, manifest,
  builder fluent method + exhaustiveness gate + roundtrip list, Python
  `ModelType`, bench registry, case recipe). The macro collapsed the *string*
  surface, not the *registration* surface. Cost accepted by design
  (registry-over-map policy); documented in CLAUDE.md's model-add sequence.
- `GaussianNd` (SP-2) landed as a parametric-D kernel; the fixed-D vs
  parametric fork was resolved in code (parametric), but no panel consumes the
  output (see §2.3).

### 2.2 Python (`python/`)

**Ideal:** contract types generated from one schema source; one engine
package with one CLI namespace; cross-language parity mechanically exported,
never hand-mirrored; migrations registry-driven; docs derived from registries.

**Actual:** strong. `BenchReport` (schema 1.7) is the single Pydantic source;
OpenAPI → `web/src/openapi.gen.ts` is generated, with a snapshot vitest and a
Python golden watchdog. F13 (2026-06-27) consolidated `python/benchmark/` into
`python/oracles/` — one engine package, `python -m oracles.cli` (9 commands),
versioned `/api/v1/*` endpoints with RFC 8594 sunset on the legacy alias.
9-path migration registry. Rust→Python parity is mechanically exported:
`_core.model_type_wire_strings()` (`crates/spectrafit-core/src/lib.rs:488`)
with the guard test `tests/parity/test_schema_parity.py:123`. 33-entry
`MODEL_REGISTRY`, 151 cases across 9 `CategoryDef` categories, 5 backend
adapters. 149 test files across unit/integration/parity/scenario/audit/meta/
inference.

**Residual ideal-diff:**
- **Three checked-in contract mirrors** (`web/src/openapi.gen.ts`,
  `web/openapi.snapshot.json`, `tests/audit/golden/openapi_normalised.json`)
  where the ideal has one generated artifact. Guarded (`poe contract_regen` +
  snapshot/watchdog tests), but the resync surface is wide — SP-3 proved a
  missed mirror can go latently red on main.
- `MODELS.md` was hand-written and had drifted to 16/34 variants (fixed this
  audit, §6); the ideal generates that table from the manifest/registry —
  registered as a follow-up gap.

### 2.3 TypeScript (`web/`)

**Ideal:** declarative panel registry; every contract leaf forced into an
explicit rendered/ignored decision; no hardcoded backend ids; no dead nav.

**Actual:** the leaf-forcing is *stronger than the typical ideal* —
`contractCoverage.test.ts` fails on any unclassified contract leaf, and
`noHardcodedBackend.test.ts` source-scans for backend-id literals. 2
destinations (Standing, Evidence) in `web/src/shell/nav.ts`; the removed Audit
destination redirects to Evidence, with V&V detail served by `/api/v1/trust`.
95 vitest files, 2 Playwright e2e specs, **zero** TODOs.

**Residual ideal-diff:**
- `analyzed[].multidim` and `analyzed[].globalFit` are carried on the wire but
  classified "ignored: cut" — the engine genuinely fits both showcases (2-D
  native `gaussian2d`, `GlobalFitGraph` joint fit) and no panel renders them.
  The ideal either renders or drops the wire fields. Honest (explicitly
  classified), but the flagship SP-2/SP-3 capabilities are invisible in the UI.
- ProvenanceFooter still shows the pinned-baseline runId next to the masthead
  run date (known confusion, pre-existing).

### 2.4 Cross-cutting

**Ideal:** every hand-maintained mirror is either generated or guard-tested;
CI equals local; docs cannot silently lie.

**Actual:** code-facing guards are excellent — binding audit
(`scripts/audit_bindings.py`, CI `ci.yml:230`), len-pinned exhaustiveness,
wire-string parity, contract coverage, prose-contract drift for LIMITATIONS
prose, S1–S5 structure wires riding in the TrustBlock. GitHub CI now runs
blocking `cargo clippy --workspace --all-targets -- -D warnings` and blocking
`ty` (parity plan executed; several session memories claiming otherwise were
stale and have been corrected).

**The single largest ideal-diff: README/MODELS/CHANGELOG prose is unguarded.**
README carried three false claims for weeks (§3). Nothing red-flags a stale
hand-pinned number in README the way `contractCoverage` red-flags an
unclassified leaf. See §4, class 7.

## 3. Gap matrix (docs-expected vs is)

| # | Claim | Where | Reality | Class | Disposition |
|---|-------|-------|---------|-------|-------------|
| 1 | "The 5 views are Overview / Dashboard / Report / Cockpit / Export" | README (pre-fix) | 2 destinations: Standing, Evidence (`web/src/shell/nav.ts`) | must-fix | **Fixed this audit** |
| 2 | "no inlined fixture, no self-contained HTML" | README (pre-fix) | `poe report_html` builds a self-contained offline bundle — documented 40 lines later in the same README | must-fix | **Fixed this audit** |
| 3 | "139-case catalog spanning 7 categories" | README (pre-fix) | 151 cases / 9 categories (`python/oracles/cases.py` `CATEGORY_REGISTRY`) | must-fix | **Fixed this audit** (rephrased registry-referencing, removing the drift vector) |
| 4 | Model reference table complete | MODELS.md (pre-fix, 16/34) | 34 manifest variants; 18 undocumented (true_voigt … kww, gaussian2d, gaussian_nd) | must-fix | **Fixed this audit** (full 34-variant documentation) |
| 5 | `python -m benchmark.cli` | CHANGELOG 0.1.0b1 entry | F13 renamed to `oracles.cli`; historical entry was accurate at release time | must-fix | **Fixed this audit** (Unreleased note; history untouched) |
| 6 | multidim/global_fit showcases "deferred — no panel renders them" | CLAUDE.md | ACCURATE — confirmed against `web/src/panels/registry.tsx` + `contractCoverage.test.ts` | — | No action (an exploration agent wrongly flagged this as stale; direct read refuted it) |
| 7 | Executed plans presented as a work queue | `docs/superpowers/plans/` (29 files) | All 29 executed/superseded | must-fix | **Deleted this audit** (git history preserves) |
| 8 | Standalone decision docs duplicating DECISIONS.md ADRs | `docs/decisions/` (2 files) | Both absorbed by ADRs (`DECISIONS.md` 2026-06-05 greenfield; 2026-06-09/2026-05-* pre-commit ADRs) | must-fix | **Deleted this audit** |
| 9 | multidim / globalFit rendered showcases | contract carries the fields | No renderer (explicitly classified "ignored: cut") | nice-to-have | Open — registered gap |
| 10 | NIST StRD breadth | LIMITATIONS.md discloses subset | 5 of 27 datasets wired | nice-to-have | Open — disclosed honestly |
| 11 | `docs/examples/*.md` runnable | implied by "runnable examples" | Not executed as tests (no gate) | nice-to-have | Open — registered gap |
| 12 | ProvenanceFooter runId | — | Pinned-baseline runId shown next to masthead date | nice-to-have | Open — registered gap |

## 4. Root-cause mapping (9-class historical taxonomy)

Mined from `DECISIONS.md` (100+ ADRs) and session memories:

| Class | Historical instances | Status |
|-------|---------------------|--------|
| 1. Rust↔Python type/string parity drift | varpro `all_variants` went 4 variants stale; hand-synced `ModelType` | **Structurally fixed** — `model_manifest!` + `ModelTypeStr::ALL` + `model_type_wire_strings()` export + parity tests |
| 2. Multi-crate model-add ripple | adding a model touched ~6 crates / ~12 hand-synced sites | **Reduced, accepted** — macro collapsed string surface; registration surface documented as the cost of registry-over-map |
| 3. Dual-contract 3-mirror resync | SP-3 rename left latent red on main via a stale fixture | **Guarded but wide** — `poe contract_regen` + snapshot vitest + golden watchdog; mirror count unchanged |
| 4. Stale exhaustiveness guards | varpro list silently drifted (no len pin); builder E0004 gate is test-only | **Fixed** — len-pinned; builder gate documented in CLAUDE.md |
| 5. CI local-green / remote-red | scoped clippy missed cross-crate lints; GitHub ci.yml lacked clippy | **Closed** — GitHub ci.yml now runs blocking clippy + ty; `audit_bindings.py` in CI |
| 6. Honesty/framing failures | SP-1 and SP-3 tribunal failures; G5 silent 0.0-coercion | **Structural** — tribunal gates, BPDD framing-integrity invariant, `nonfinite_dr2_case_ids` gate fix |
| 7. **Doc drift** | README 3 false claims; MODELS.md 16/34; stale gaps register entries; 3 stale session memories; **two of this audit's own exploration agents produced wrong staleness verdicts** | **RECURRING, UNGUARDED** — the only class without a structural fix. Follow-up registered: pin or generate README/MODELS numeric claims |
| 8. vitest/e2e flakiness | parallel-contention flakes; e2e wait-target races; HashMap-order covariance flake | **Patched + one structural fix** (`covariance_param_order` field); serial-run workaround documented |
| 9. Packaging debt | spc-bench ImportError'd on clean install; alpha metadata | **Closed at 0.1.0b1** — Option A lean wheel, no console scripts |

**Headline: 8 of 9 historical failure classes now have structural guards or
closed dispositions. The survivor is doc drift** — and it reproduced *inside
this audit*: one exploration agent asserted the showcases were rendered
(wrong), another asserted the parity export didn't exist (wrong), and three
session memories contradicted the code. Every load-bearing conclusion in this
document was therefore verified by direct file reads.

## 5. Standing verdict per language

- **Rust: healthy.** Single-source manifest, guarded parity, one TODO. The
  model-add ripple is a known, documented, accepted cost.
- **Python: healthy.** One engine package post-F13, generated contract,
  mechanical cross-language parity, registry-driven everything. The 3-mirror
  contract resync is the widest remaining seam, and it is guard-tested.
- **TypeScript: healthy, with invisible flagships.** Guard discipline exceeds
  the ideal; the cost of the honest "ignored: cut" classification is that the
  2-D and global-fit capabilities the engine genuinely has are not visible in
  the product.
- **Docs: the weak layer.** Everything code-adjacent that is *generated or
  guard-tested* is accurate; everything hand-written with numbers in it had
  drifted. Fixed where found; the class-level fix (generate/pin prose numbers)
  is registered as a follow-up gap.

## 6. Actions taken this session (branch `code-review-faible`)

**Fixed:**
- README.md — 5-views claim → 2 destinations; self-contained-HTML
  contradiction removed; hand-pinned 139/7 counts → registry-referencing
  phrasing.
- MODELS.md — full 34-variant documentation (formula, canonical param names,
  wire string, Python `ModelType` member per model) + banner naming
  `model_manifest!` as the authoritative source.
- CHANGELOG.md — `[Unreleased]` note recording the F13 CLI rename (historical
  entries untouched).
- DECISIONS.md — dead pointers to deleted standalone docs converted to
  "absorbed / git history" notes (preamble + line ~2887).
- `docs/superpowers/specs/2026-06-18-discovered-gaps.md` — G5 path updated
  post-F13; open rows from the 2026-06-26 outstanding audit migrated in; new
  gaps registered (showcase panels, MODELS.md generation, ProvenanceFooter,
  StRD breadth, README prose guard, examples-as-tests).
- Session memories — 3 stale memories corrected (GitHub CI parity, regression-
  policy test failures, gaps-register state).

**Deleted** (git history preserves all content):
- `docs/superpowers/plans/` — all 29 executed plans.
- `docs/decisions/hybrid-precommit-strategy.md`,
  `docs/decisions/web-greenfield-rebuild.md` (both absorbed by DECISIONS.md
  ADRs; zero inbound references after pointer fixes).
- `docs/audit-2026-06-26-F13-tree-consolidation-plan.md`,
  `docs/audit-2026-06-26-outstanding.md` (completed; open rows migrated to the
  gaps register first).

**Explicitly kept** (load-bearing): `docs/rust_binding_audit.md` (CI-enforced
by `scripts/audit_bindings.py`), `docs/superpowers/ledgers/` (Stop-hook
scanned), `docs/superpowers/specs/` (design records), `docs/methodology.md`,
`DECISIONS.md`, `CLAUDE.md`, `ARCHITECTURE.md`, `LIMITATIONS.md`,
`.claude/instructions/**`.

## 7. Open items (registered, not a work queue here)

All open items live in `docs/superpowers/specs/2026-06-18-discovered-gaps.md`:
showcase panels (multidim/globalFit renderers), MODELS.md generation from the
manifest, README numeric-claim guard, ProvenanceFooter runId, NIST StRD
breadth, docs/examples-as-tests, S3 detector fix, S-wire rung-capping
promotion, stateful-hook oracle, 3 stale-fixture audit-suite failures on main.
