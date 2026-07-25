# Code-idiom + style/nesting audit — web / crates / python (main)

Scope: `crates/` (Rust, edition 2021), `python/` (Python, `>=3.13`), `web/src`
(TypeScript, target ES2022, React 18.3.1) on `main`. Answers two questions:
(1) where does coding style visibly differ, within a language and across the
three; (2) is the code "zen of the language," or fighting it / overly nested.

**Methodology.** Three independent, complementary signals per language, then
synthesis:
1. **`self-assess-code-idiom`** — one finder per language, then an adversarial
   Verify pass (a refuter tries to kill each finding) plus a second
   re-confirmation pass for any High-severity survivor. Findings below marked
   **CONFIRMED** went through this; the workflow's own stats show a 0%
   false-positive rate across all 20 findings that reached this pass.
2. **`self-assess-complexity-score`** — SLOC / file count / mean+max cyclomatic
   complexity (CCN) per language, computed by one formula for all three so the
   numbers are comparable.
3. **`zen-of-languages` MCP** — an independent architectural/idiom scanner, run
   separately per language with full pagination (no file silently dropped
   *within what it scanned* — see coverage caveats per language below). This
   tool has **no adversarial verify pass of its own**; every finding from it is
   marked **PLAUSIBLE (unverified)** below, and its raw violation records carry
   no line numbers for Rust/TypeScript (`location: null`) — file-level
   attribution only for those two languages.

**I personally spot-checked 8 of the highest-severity findings across all
three languages by reading the cited code directly**, plus did a **full,
mechanical follow-up investigation of the Rust `panic!`/`.unwrap()` claim**
(§ below) that materially overturns the original severity-9 verdict. Two of
the original 8 spot-checks also refuted a zen-of-languages claim outright.

---

## ⚠ Corrections to the zen-of-languages output (read before the per-language sections)

**1. Rust "Fail Fast" (66 severity-9 `.unwrap()`/`.expect()`/`panic!` hits, 28
files, "production numerical-core code") is a near-total false positive — see
the dedicated follow-up section below.** The short version: of the 140 raw
regex hits across all 82 `.rs` files, only **4 are genuinely reachable at
runtime outside test code**, and every one of those 4 carries an explicit,
specific, human-written invariant proof directly above it.

**2. Python: the "3 empty `except` blocks" claim is a false positive.**
zen-of-languages flagged `python/oracles/backends/__init__.py:19,25,36` as
severity-9 "errors should never pass silently." Direct read shows these are
three `try: from oracles.backends._X import Y; except ImportError: pass`
blocks — the standard, universally-used Python idiom for making an optional
dependency optional (the file's own comment above the third block explains
exactly this: "the roster grows from 3 → 6" as backends become available).
Not error-swallowing that could hide a bug — **refuted**.

**3. Rust: the "`unsafe` block with no `// SAFETY:` comment" claim is a false
positive.** `crates/spectrafit-models/src/math_backend.rs:59-62` has a
`// SAFETY:` comment immediately above the `unsafe { vvexp(...) }` call at
line 63, correctly explaining the non-overlap/length/non-empty invariants.
**Refuted.**

Six other spot-checks (the Rust magic-number finding, the `solve_varpro`
function boundaries, Python's `ModelType(str, Enum)` finding, the
`migrate.py` 7-level-nesting claim, and TypeScript's `tsconfig.json strict`
setting and `AnyCase` alias) all **confirmed exactly as reported**.

**Pattern across all three refutations:** in every case, the zen-of-languages
tool's methodology gap (not excluding test code; not distinguishing a
custom same-named method from the stdlib one it's pattern-matching; a naive
severity assignment with no adversarial check) is what produced the false
positive, not a misread of any individual line. This is exactly why the
report treats every zen-of-languages finding as a lead requiring direct
verification, never a fact on its own.

---

## Follow-up: the Rust `panic!`/`.unwrap()` claim, fully investigated

The original report flagged this as the one Rust finding "squarely fighting
Rust's own idiom" — but also explicitly noted it was the *weakest-evidenced*
claim (unlocated, no adversarial pass). Investigated properly below.

### Method

Regex-scanned all 82 `.rs` files under `crates/` for `.unwrap()`, `.expect(`,
`panic!(`, `unreachable!(`, `todo!(`, `unimplemented!(`, then used Python
brace-matching to determine, for every hit, whether it falls inside a
`#[cfg(test)]` module (inline `mod tests { ... }` blocks *and* separate
`tests.rs` files declared via `#[cfg(test)] mod tests;` in the parent module —
both checked). Files under `crates/*/tests/` (integration tests) and
`build.rs` scripts were out of scope from the start (never part of the
compiled library/binary runtime).

### Result: the claim collapses from "66 hits, 28 files" to "4 hits, 3 files"

| | Count |
|---|---|
| Raw regex hits, whole `crates/` tree | 140 |
| ...inside `#[cfg(test)]` modules (inline or separate `tests.rs`) | 133 |
| ...matching a **custom, non-panicking** `.expect()` parser method (see below) | 2 |
| **Genuinely reachable at runtime, in production library code** | **4** |

The 4 real sites, every one with an explicit written invariant proof:

| File:Line | Call | Justification (verbatim from the code) |
|---|---|---|
| `spectrafit-graph/src/compiler.rs:254` | `key.find('.').unwrap()` | `// INVARIANT: every key in free_keys was produced by format!("{}.{}", nid, pname) two lines above, so it always contains exactly one '.' separator — find is infallible here.` |
| `spectrafit-graph/src/compiler.rs:266` | `.position(...).unwrap()` | Two more `// INVARIANT:` comments immediately above (re: `node_idx_by_id` and `param_name` provenance from earlier compile steps) |
| `spectrafit-graph/src/expr.rs:492` | `stack.last_mut().unwrap()` | `// INVARIANT: this branch is only reachable from within the while let Some(&(node, dep_cursor)) = stack.last() loop, which already confirmed stack is non-empty.` |
| `spectrafit-solver/src/global.rs:261` | `.partial_cmp(b).expect("INVARIANT: both values are finite")` | Iterator is pre-filtered by `.filter(\|(_, c)\| c.is_finite())`; the invariant is embedded directly in the panic message |
| `spectrafit-builder/src/lib.rs:499` | `panic!("...add the kernel registration...")` inside `.unwrap_or_else(...)` | `// Unreachable by construction — every variant is wired into model_from_str, and the available_models_matches_model_from_str test pins this — but explicit panic beats silent UB if a future contributor adds a variant without registering the kernel.` |

**Two of the seven original "production" hits were themselves false-positive
regex matches**, not real panics: `expr.rs:318` and `:324`
(`self.expect(&Token::RParen)?` / `self.expect(&Token::Dot)?`) call a
**custom, fallible `expect(&mut self, tok: &Token) -> Result<(), CoreError>`
method** on the parser struct — it returns a `Result` and is propagated with
`?`, and has nothing to do with the panicking `Option`/`Result::expect()` the
zen-of-languages tool's regex was matching against.

**And the specific named files in the tool's severity-9 table turned out
wrong on direct check:** `spectrafit-graph/src/executor.rs` ("the runtime
graph executor hot path") — **0 production hits**, all 42 raw hits are in its
`#[cfg(test)]` module. Both crates' `error.rs` files ("panicking inside the
error-handling module itself") — **0 production hits each**. `spectrafit-types/src/types.rs`
("the shared types crate") — **0 production hits**. `spectrafit-solver/src/dispatch.rs`,
`spectrafit-varpro/src/solver.rs`, `spectrafit-solver/src/irls.rs`,
`spectrafit-solver/src/postfit.rs` — **0 production hits**, all in test code.

### Revised verdict

**This finding does not hold up.** What looked like a severity-9,
28-file, "fighting Rust's fallibility idiom" problem is, on full investigation,
a measurement artifact: the tool's regex scan didn't exclude test code (95%
of its hits) and conflated a custom same-named method with the stdlib
panicking one (2 of the remaining 7). The small number of genuine
runtime-reachable panic-capable calls that do exist — 4, not 66 — are not
careless error-swallowing; they are **proven-safe invariant assertions**, each
with a specific, falsifiable, human-written proof directly above it. This is
the same defensive-assertion discipline already confirmed correct for this
codebase's one `unsafe` block (see correction #3 above) — not language-fighting,
but a consistent, disciplined pattern of "prove it in a comment, then assert
it, so a future bug fails loudly instead of corrupting state silently."

**This replaces the original report's Rust zen verdict's closing line**
("flag Control Flow as the priority follow-up... genuinely fighting Rust's
own idiom") — that follow-up is now done, and the answer is: there is no
real Control Flow problem in this codebase. The Rust zen verdict should read:
**idiomatic in both function-shape *and* error-handling discipline** — the
long-function debt documented in the idiom-workflow's CONFIRMED findings
(§1 below) is this codebase's only real Rust idiom debt.

---

## Follow-up: the stringly-typed-API claim, fully investigated

The original report flagged this as the one remaining open lead — unlike the
Fail-Fast claim, never independently checked. Investigated properly below,
same standard: mechanical re-scan first, then direct read of survivors.

### The raw count doesn't reproduce, and can't

The claim was **"176 hits / 65 files"** across `spectrafit-graph`,
`spectrafit-solver`, `spectrafit-types`, `spectrafit-varpro`,
`spectrafit-builder`. `find crates/{those 5 crates} -name "*.rs"` returns
**23 files total** — src + tests, no exceptions. 65 files is not a
measurement error, it's not possible: there are fewer than a third that many
`.rs` files in the named crates, full stop.

A fresh, comparable re-run of the same MCP tool (`analyze_repository`,
`language=rust`, same 82-file `crates/` tree the original scan covered)
returns, across every String-related detector combined (`rust-002`
"Stringly-typed APIs", `rust-002` "Using primitive types when newtype would
be safer", and the raw `'String'` anti-pattern regex) — **28 hits across 23
distinct files, repo-wide**, before even narrowing to the 5 named crates.
The tool's own current output is ~6× smaller than the number the report
cites for a narrower scope. Whatever produced "176/65" was not this tool run
under comparable settings — most plausibly a raw per-occurrence text count
(e.g. every literal `String` token in a file, summed) misreported as
"files" and "hits" in the structured sense the rest of the report uses.

### Independent count: mechanical grep, same discipline as the Fail-Fast follow-up

`grep -rn '\bString\b'` across the 5 crates' `src/` (23 files but only 15
contain the token at all): **136 hits in 15 files** (140/17 including
`tests/`). Closer in order of magnitude to the tool's low end, still well
short of 176 — and the file count (17 at most) is barely a quarter of the
claimed 65, for the same reason as above: there is no room for 65 files.

Classifying all ~140 real hits by hand:

| Category | Count | Verdict |
|---|---|---|
| `HashMap<String, f64\|ParameterSpec\|ParameterResultSpec\|Vec<f64>>` — the "flat parameter map" keyed by a dynamically-composed `"{node_id}.{param_name}"` string, threaded through compiler → executor → solver → varpro → builder | 65 (48%) | **Not a smell.** The key space is inherently open (arbitrary user-chosen node/param names) — no closed enum could represent it. A `ParamKey(String)` newtype is a defensible minor nicety, not a bug-preventing fix. |
| Free-form identifiers/text: node/edge `id`/`target`, `Parameter.expr`/`ExprEdge.expression` (the symbolic-formula strings behind [[sp1-parameter-expr-merged]]), `label`, error `message` | ~40+ | **Not a smell.** All genuinely unbounded — correct as `String`. |
| `FitOptionsSpec.solver: String` (`spectrafit-types/src/types.rs:342`) | 1 field, 1 real consequence | **Genuine finding — see below.** |

### The one real finding

`FitOptionsSpec.solver` **is** a closed set — its own doc comment
(`types.rs:338-341`) enumerates exactly 10 values: `"lm"`, `"lm-legacy"`,
`"trf"`, `"geodesic"`, `"varpro"`, `"auto"`, `"irls"`, `"irls:bisquare"`,
`"irls:cauchy"`, `"global"`. `Solver::parse` (`spectrafit-solver/src/dispatch.rs:99-115`)
already parses this string into a proper internal `Solver` enum before
`fit()`'s dispatch `match` (`dispatch.rs:197`) — so the fix pattern this
codebase already applies to `ModelType`/`ModelTypeStr` (a typed wire value
with a canonical parse) was never extended to the solver selector.

**Mechanically confirmed consequence:** the parser is lenient, not
fail-fast — `_ => Solver::Lm` (`dispatch.rs:113`) silently routes any
unrecognised string to the LM default rather than erroring. A typo
(`"lmm"`, wrong-case `"Trf"`) is silently misrouted to a different solver,
not rejected. The same pattern repeats one level down: `WeightFn::from_str`
(`spectrafit-solver/src/irls.rs:81-87`) silently defaults an unrecognised
`"irls:<name>"` suffix to Huber — and the code's own comment
(`irls.rs:78-80`) states this leniency is deliberate ("not the fallible
`std::str::FromStr` contract, so the trait is deliberately not
implemented"), i.e. an acknowledged design choice, not an oversight.

### Revised verdict

**The 176/65 claim is refuted on file-count alone and overstated on hit-count
even generously re-measured.** But — unlike the Fail-Fast and Python
empty-`except` claims, which collapsed to nothing — this cluster is not a
pure false positive either: exactly **one** real, traced instance survives,
with a real (if intentionally-tolerated) consequence. `FitOptionsSpec.solver`
and the nested `"irls:<weight>"` sub-parse are stringly-typed at the public
API boundary in the way the report's principle describes — a closed,
enumerable set of ~10 known values, currently unvalidated at the boundary,
where a typo silently changes solver/weight-function choice instead of
erroring. Severity: **Low-Medium** — documented and long-standing (not
silent data corruption), but a real gap relative to this codebase's own
`ModelTypeStr` precedent for exactly this class of problem. Everything else
originally swept into "176 hits" — the flat-parameter `HashMap<String, _>`
keys and the various node/param/expr/label/message fields — is genuinely
open-ended text with no enum candidate and needs no fix.

---

## 1. Rust (`crates/`, edition 2021)

**Coverage:** 82/82 `.rs` files (independently cross-checked with `find`).

### Style-consistency findings

| # | File:Line | Finding | Status |
|---|---|---|---|
| 1 | `crates/spectrafit-solver/src/dispatch.rs:199` | Bare literal `20` (IRLS outer-iteration cap) at the call site; explained only in a doc comment on the callee (`irls.rs:106`), not locally. Inconsistent with the same crate's own convention — `postfit.rs:616`/`:646` already uses named `const`s (`OFF_DOMAIN_R2_FLOOR`, `SOFT_SUCCESS_R2_FLOOR`) for comparable tunables. | **CONFIRMED** (Low — single call site, documented, no bug-hiding risk) — personally re-verified |
| 2 | `spectrafit-types/src/types.rs:342` | `FitOptionsSpec.solver: String` — a closed ~10-value set (doc comment enumerates them), parsed by `Solver::parse` (`spectrafit-solver/src/dispatch.rs:99-115`) with a silent `_ => Solver::Lm` fallback on unrecognised strings (typos misroute to a different solver instead of erroring); same leniency one level down in `WeightFn::from_str` (`irls.rs:81-87`, deliberately not `FromStr`). The original zen-of-languages "176 hits / 65 files" framing is refuted (only 23 `.rs` files exist across these 5 crates; a fresh tool run + independent grep both land far below 176) — see the dedicated follow-up above — but this one instance is real. | **CONFIRMED (Low-Medium)** — fully investigated, see follow-up above; the other ~135 grep hits (flat-parameter `HashMap<String,_>` keys, node/param/expr/label/message fields) are refuted as findings — genuinely unbounded text, no enum candidate |

### Idiom / nesting findings

| # | File:Line | Function | Size | Severity | Status |
|---|---|---|---|---|---|
| 1 | `spectrafit-varpro/src/solver.rs:27-383` | `solve_varpro` | ~357 ln, 8 distinct concerns in one scope | Medium | **CONFIRMED** — personally re-verified function boundaries |
| 2 | `spectrafit-solver/src/dispatch.rs:178-513` | `fit` (public entrypoint) | ~336 ln | Medium | **CONFIRMED** |
| 3 | `spectrafit-trust-region/src/driver.rs:61-283` | `minimize_tr` | ~223 ln, nested Δ-radius accept/reject subloop at 184-276 | Medium | **CONFIRMED** |
| 4 | `spectrafit-levenberg-marquardt/src/driver.rs:161-478` | `minimize` | ~318 ln, outer + inner λ-search loop | Low | **CONFIRMED** (deliberately tempered — domain-typical MINPACK-style numerical kernel) |
| 5 | `spectrafit-solver/src/global.rs:76-304` | `solve_global` (DE driver) | ~229 ln, 6 concerns | Low | **CONFIRMED** |

All five long-function findings survived verification with 0 refutations (0%
false-positive rate on this batch). Two structural notes: the VarPro stderr
block duplicates sigma-weighted-vs-not branching already present in its own
solve block; the LM and trust-region drivers are structurally similar
siblings — a repeated pattern across the solver-crate family, not a one-off.

**The "production `.unwrap()`/`panic!`" cluster zen-of-languages flagged here
has been fully investigated and does not hold up — see the dedicated section
above.**

### Complexity numbers

SLOC 15,806 / 94 files. **`meanCcn`/`maxCcn`: -1 — not measurable** (`scc`/
`lizard` unavailable and not installable read-only in this environment; a
crude decision-keyword grep, 13.9/file, was used only as a sanity check, never
reported as CCN). `complexityIndex` (COCOMO-II relative scale, not
CCN-grounded): 61.2.

### Zen verdict (revised)

**Idiomatic in both function-shape and error-handling discipline.** The five
CONFIRMED long functions sit exactly where you'd expect in a numerical-solver
crate family (VarPro, LM, trust-region, DE, dispatch) — tightly-coupled mutable
iteration state, already discounted by the workflow's own severity grading (2
capped Medium, 2 graded Low with an explicit domain-typical rationale). That's
a "solver code looks like this in most languages" pattern, not language-fighting.
The one finding that originally looked like real language-fighting — pervasive
production `panic!`/`.unwrap()` — does not survive direct investigation (see
above): the real count is 4 sites, not 66, and all 4 are proven-safe,
explicitly-justified invariant assertions. The stringly-typed-API cluster
(finding #2 above) has now also been fully investigated: the "176 hits / 65
files" framing is refuted (impossible on file-count alone), but one real,
low-medium-severity instance (`FitOptionsSpec.solver` + its nested
`"irls:<weight>"` sub-parse, both leniently defaulting instead of erroring on
an unrecognised string) survives direct read. Both zen-of-languages leads for
Rust are now closed out — no open leads remain in this pass.

---

## 2. Python (`python/`, `>=3.13`)

**Coverage:** 76/76 files (idiom workflow + zen-of-languages both confirm).

### Style-consistency findings

| # | File:Line | Finding | Severity | Status |
|---|---|---|---|
| 1 | `python/spectrafit_core/models.py:12` | `class ModelType(str, Enum)` uses the pre-3.11 str-mixin idiom instead of `enum.StrEnum` (available since 3.11; repo targets `>=3.13`). Only such mixin in the codebase. | Low | **CONFIRMED** — personally re-verified |
| 2 | `oracles/engine.py:433,565`, `_engine_profile.py:180` | `raw_sink=None` is the one unannotated parameter on 3 otherwise fully-typed functions; the real type (`dict[tuple[str,str], dict] | None`) is already declared for the same parameter elsewhere in the same call chain. | Low | **CONFIRMED** |
| 3 | `oracles/backends/_base.py:93` | Unnamed `0.05` shrink factor for a synthetic display-only convergence trace, no name/comment. Scope is narrow — display trace only, no effect on χ²/r²/gating. | Low | **CONFIRMED** |

zen-of-languages independently adds (PLAUSIBLE, unverified): magic numbers
across ~30 `lineshapes/*.py`/`opt_func/*.py` model-formula files (severity 7),
and missing docstrings on 20+ claim-record classes in `oracles/audit/claims.py`.

### Idiom / nesting findings

| # | File:Line | Function | Size | Severity | Status |
|---|---|---|---|
| 1 | `oracles/cli.py:450` | `gate()` | ~317 ln (parsing + evaluation + reporting mixed) | Medium | **CONFIRMED** |
| 2 | `oracles/audit/runner.py:198` | `run_audit()` | ~179 ln | Medium | **CONFIRMED** |
| 3 | `oracles/cli.py:257` | `_gate_evaluate()` | ~161 ln, 3 near-duplicate axis blocks | Medium | **CONFIRMED** (explicitly a documented "Plan C2 refactor 2/4" in progress) |
| 4 | `oracles/inference_report.py:41` | `compute_inference()` | ~140 ln, 5 distinct stats computations | Medium | **CONFIRMED** |
| 5 | `oracles/engine.py:425` | `run_featured()` | ~95 ln, inconsistent with the file's own phase-extraction convention | Medium | **CONFIRMED** |
| 6 | `oracles/migrate.py:146-181` | `_upgrade_1_5_to_1_6()` | **7 real nesting levels** (for→if→pop→if→if→if(slices)→for→if) | Medium | **CONFIRMED** — personally re-verified, nesting depth accurate |

zen-of-languages independently corroborates several of the above by CCN/nesting
and adds (PLAUSIBLE, unverified): `oracles/audit/structure_wires.py` (nesting
depth 9), `oracles/reports.py` (nesting depth 9), `oracles/migrate.py` (depth
8 — directly corroborates #6), `oracles/inference_report.py` flagged as the
single worst average-complexity file in the repo (34.0 CCN, matching the
`maxCcn: 34` measured number below).

**Refuted (see corrections above):** the "3 empty `except` blocks" in
`oracles/backends/__init__.py` is not a real finding — it's the standard
optional-dependency-import idiom, not error-swallowing.

### Complexity numbers

SLOC 12,130 / 102 files. **Mean CCN 3.6** (genuinely low, simple-by-default for
most of the tree) but **max CCN 34** — concentrated, not diffuse. The
concentration matches the findings above almost exactly: `inference_report.py`
(34.0 avg — the single worst file), `audit/runner.py` (20.0 avg), and the
nesting-depth outliers all cluster in two subsystems — the benchmark
inference/report machinery and the audit/wire-validation DAG — plus the
schema migrator. `complexityIndex`: 45.8.

### Zen verdict

**Bimodal, not systemically anti-idiomatic.** Outside the benchmark-inference/
audit-wire/migrator hotspots, the code reads as idiomatic 3.13 Python (PEP 604
unions, `from __future__ import annotations`, Pydantic-first modeling) with
only cosmetic gaps (one un-migrated enum mixin, one repeated untyped param,
one unnamed constant). Inside those hotspots, 5-7 level nesting and 150-300
line functions genuinely fight Python's control-flow model — and, tellingly,
it's the same pattern the codebase's own history shows it already recognizes
and fixes (the prior `engine.py` 1480→674 LOC god-module split). Net: a small
number of well-known, already-acknowledged hotspots, not a language-fighting
posture across the tree — and no genuine silent-error-swallowing problem once
the false positive above is removed.

---

## 3. TypeScript (`web/src`, target ES2022)

**Coverage caveat — read this first:** zen-of-languages' `language="typescript"`
filter only matched `.ts` files (134 of 190) and **silently excluded all 56
`.tsx` files — the entire React component/panel layer** (`Shell.tsx`,
`panels/registry.tsx`, `plots/PlotMount.tsx`, every `panels/bodies/*.tsx`,
`EvidencePanel.tsx`). The idiom-audit workflow's own finder did cover `.tsx`
directly (its findings below include `.tsx` files) — only the zen-of-languages
pass has this gap.

**Direct contradiction, resolved:** zen-of-languages claims `tsconfig.json` has
`strict: false` (severity 9, its single highest-volume finding, claimed across
134/134 files). **I read `web/tsconfig.json:14` directly: `"strict": true`.**
The idiom-audit workflow's own citation of `strict: true` is correct;
zen-of-languages' claim is wrong. Since that one claim cascades into ~91 files
of downstream `any`/type-assertion findings, **treat all of zen-of-languages'
TypeScript output as unreliable** — it's listed for completeness but should
not be trusted the way the idiom-audit's CONFIRMED findings can be.

### Style-consistency findings

| # | File:Line | Finding | Severity | Status |
|---|---|---|---|
| 1 | `web/src/panels/bodies/shared.tsx:20` | `export type AnyCase = any;` (eslint-suppressed) used as `selectedCase()`'s return type, even though its only data source (`analyzedById()`, `contract/index.ts:54`) is already properly typed `Featured \| undefined`. Propagates via `as AnyCase` casts through ~20 sites in `evidenceCase.tsx`/`evidenceOverview.tsx`, and is why ~16 `series/*.ts` functions take bare `any` instead of `Featured`/`BenchReport`. A sibling function (`profOf`, `contract/index.ts:94`) accesses the identical field shape with the real type, proving no structural mismatch forces the escape hatch. | Medium | **CONFIRMED** — personally re-verified |
| 2 | `web/src/plots/scaling.ts:6` (+17 more) | An `(p: any): SVGSVGElement` SVG-unwrap helper duplicated near-verbatim across 18 `plots/*.ts` files. `@observablehq/plot`'s own types don't return `any`, and a sibling file (`plots/globalFit.ts:29`, `toSvg`) already implements the correctly-typed version. | Medium | **CONFIRMED** |
| 3 | `web/src/panels/bodies/evidenceOverview.tsx:122` | Two stacked non-null assertions (`report.manifest!.saturatedCategories!.map(...)`) after a guard (line 101) that TypeScript can't use to narrow — currently safe only by coupling to that guard, would silently break on refactor. | Low | **CONFIRMED** |

### Idiom / nesting findings

| # | File:Line | Finding | Size | Severity | Status |
|---|---|---|---|
| 1 | `web/src/shell/EvidencePanel.tsx:21-272` | `EvidencePanel` — one component owning view-mode state, 2 hash-routing effects, an Escape-key effect, derived data, and two large inline-styled JSX trees. No sub-extraction. | ~250 ln | Medium | **CONFIRMED**, no documented exception |
| 2 | `web/src/panels/bodies/standing.tsx:528-785` | `factsLandingCard` — formatting + derivation + one large JSX return. Mitigated by 2 sibling functions in the same file sharing the identical shape, and the file's own header comment framing these as intentionally-bare "hero cards." | ~257 ln | Low (downgraded for in-file precedent) | **CONFIRMED** |

zen-of-languages' TypeScript output (unreliable per the strict-mode
contradiction above, and only covering 134/190 files) is not reproduced in
detail here beyond noting it exists.

### Complexity numbers

SLOC 14,590 / 192 files. **`meanCcn`/`maxCcn`: -1 — not measurable** (same
tooling gap as Rust). `complexityIndex`: 56.1.

### Zen verdict

**A strictly-typed, contract-driven codebase with a handful of self-inflicted
holes, not a codebase fighting TypeScript's model.** `tsconfig.json` really
does have `strict: true` (verified directly), and the contract layer
(`web/src/contract/`) is fully typed. The real debt is localized: one
`AnyCase`/`any` escape hatch propagating through ~20+36 sites, one 18-way
duplicated `any`-typed helper a sibling file already shows how to fix
correctly, one narrowing gap, and two long components/functions (one of which
is established file convention, not a one-off). None of these are ES2022
version-idiom issues — they're hygiene/consistency debt in one specific
pattern (`AnyCase`) plus two files.

---

## 4. Cross-language style consistency

| Problem class | Rust | Python | TypeScript | Divergence type |
|---|---|---|---|---|
| Registry vs. map | `ModelTypeStr::as_str()` | `MODEL_REGISTRY` | `panels/registry.tsx` | **Convergent, justified** — all three follow the same documented house rule |
| Discriminator dispatch | native `match` (idiom, not policy) | hook-enforced `match/case`, confirmed compliant (`audit/runner.py:198`) | no rule, no evidence either way | **Convergent where evidenced; TS uncovered**, not "TS is fine" |
| Error handling | ~~66 "Fail Fast" hits~~ **REFUTED — 4 real sites, all proven-safe invariant asserts** (see dedicated follow-up) | ~~silent empty `except`~~ **REFUTED** + broad `except Exception` in `cli.py:450` (CONFIRMED, Medium) | no findings (uncovered) | **Not a real divergence once both severity-9 claims are corrected out** |
| Magic numbers | bare `20` vs. crate's own named consts (CONFIRMED, Low) | unnamed `0.05` (CONFIRMED, Low) | none found | **Same accidental smell, independently confirmed twice**, no house rule catches this class |
| Type-escape hatches | `FitOptionsSpec.solver` + nested weight-fn sub-parse, silent-default-on-typo (CONFIRMED, Low-Medium; the claimed 176-hit/65-file scale is refuted) | one untyped param ×3 (CONFIRMED, Low) | `AnyCase`/`any` (CONFIRMED, Medium, no documented exception) | **Convergent once corrected — all three languages now independently verified, none at the originally-claimed scale for Rust** |
| Long-function debt | domain-typical discount (CONFIRMED, capped Low/Medium) | no discount, self-acknowledged debt (CONFIRMED, Medium) | in-file-precedent discount only (CONFIRMED, mixed) | **Same smell, three different excusing standards** |

**Net (revised):** the repo is consistent about the thing it explicitly
documents (registry-over-map), and each language's long-function tolerance
follows a locally coherent — but different — standard (domain-typical for
Rust solvers, zero-tolerance for Python, in-file-precedent for TypeScript).
**The originally-flagged cross-language error-handling divergence does not
hold up** — both the Rust "loud panics" and the Python "silent excepts"
severity-9 claims were false positives from the same unverified tool, and
correcting them removes what looked like this audit's most serious
cross-language finding. The Rust stringly-typed-API cluster is now also
closed out: refuted at the claimed scale (176 hits / 65 files — impossible,
only 23 `.rs` files exist across the named crates), but not a pure false
positive either — one real, low-medium-severity instance survives
(`FitOptionsSpec.solver`, see the dedicated follow-up above). Every
zen-of-languages lead raised in this report has now been independently
investigated to a final verdict; none remain open.

---

## 5. Complexity summary (all three, same formula)

| Language | SLOC | Files | Mean CCN | Max CCN | Complexity Index* |
|---|---|---|---|---|---|
| Rust | 15,806 | 94 | not measurable (tooling unavailable) | not measurable | 61.2 |
| TypeScript | 14,590 | 192 | not measurable (tooling unavailable) | not measurable | 56.1 |
| Python | 12,130 | 102 | 3.6 | 34 | 45.8 |

\* COCOMO-II relative scale index (`2.94 × KSLOC^1.10`) — for ranking, **not**
a duration/cost estimate. Only Python's CCN is real (via `lizard`); Rust's and
TypeScript's `scc`/`lizard` were unavailable in this environment and were
**not** approximated with a fabricated number — this is a real tooling gap,
not a "these languages have no complexity," and should be re-run with `lizard`
installed if a precise Rust/TS CCN number is needed later.
