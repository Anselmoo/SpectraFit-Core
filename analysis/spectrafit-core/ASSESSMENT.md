# Modernization Assessment — spectrafit-core

*Generated 2026-07-13 by `/modernize-assess`, run in **self-assessment mode** (no
`legacy/` folder exists — this is an actively developed codebase, not an
archaeology target). Tools: `cloc` v2.08 (`scc`/`lizard` unavailable in this
environment — complexity ranked by a decision-keyword proxy, noted below),
`npm audit`, direct-read + `grep` sweeps by two `legacy-analyst` subagents and
one `security-auditor` subagent (parallel, ~4-9 min each), plus a live
GitHub Actions API check. All figures reproducible from those tools/commands.*

## Executive Summary

spectrafit-core is a ~42.2 KSLOC, three-language codebase (Rust workspace,
Python package + benchmark harness, Vite/React dashboard) implementing a
spectral peak-fitting library with a self-auditing cross-backend benchmark.
It is **healthy, not distressed**: near-universal file-level documentation
(91% of Rust files, ~100% of Python files carry a leading doc comment), zero
dead-code/deprecated-API markers, no hardcoded credentials anywhere in scope,
and only two genuine "god-function" hotspots out of ~400 hand-authored source
files. The real risk surface is concentrated in two places that generic
LOC/CWE scanning would otherwise under-weight: (1) a **self-inflicted
contract-drift bug** — one Pydantic model group breaks the project's own
camelCase wire convention, already forcing four `as any` casts on the web
side — and (2) **CI/CD topology and supply-chain hardening gaps** on the
GitHub-mirror side (unpinned third-party Actions, a "pwn request" pattern on
the pre-commit-check workflow, a credential embedded in a git remote URL).
Headline recommendation: **targeted refactor-in-place**, not a rewrite — fix
the ranked findings below as scoped tickets; nothing here rises to a
rearchitect/rebuild case.

## System Inventory

### Line counts (`cloc` v2.08, `crates/` + `python/` + `web/`, build/cache dirs excluded)

| Language | Files | Blank | Comment | Code |
|---|---|---|---|---|
| Rust | 82 | 1,785 | 4,650 | 15,384 |
| TypeScript | 195 | 1,344 | 3,303 | 14,554 |
| Python | 101 | 2,703 | 4,131 | 11,398 |
| JSON (generated, excluded below) | 2 | 0 | 0 | 6,698 |
| JSON (hand-authored: `package.json`, `tsconfig.json`, fixtures) | 4 | 0 | 0 | 324 |
| Markdown | 2 | 30 | 0 | 144 |
| TOML | 11 | 23 | 0 | 142 |
| CSS | 1 | 10 | 35 | 138 |
| JavaScript | 2 | 13 | 31 | 88 |
| HTML | 1 | 0 | 1 | 16 |
| SVG | 1 | 0 | 0 | 1 |
| **Total (raw `cloc`)** | **402** | **5,908** | **12,151** | **48,887** |
| **Hand-authored (excl. `package-lock.json` + `openapi.snapshot.json`)** | **400** | — | — | **42,189** |

`package-lock.json` (4,136 lines) and `web/openapi.snapshot.json` (2,562
lines) are machine-generated lockfile/contract-mirror artifacts with no
hand-written logic — excluded from the complexity index below so it isn't
inflated by generated content.

### Complexity ranking (decision-keyword proxy — `scc`/`lizard` not installed in this environment; note per Step 1 protocol)

Top files by `if`/`match`/`for`/`while`/`catch`/`except` density:

| Rank | Rust | Python | TypeScript |
|---|---|---|---|
| 1 | `crates/spectrafit-graph/src/executor.rs` (108) | `python/oracles/cli.py` (152) | `web/src/openapi.gen.ts` (47, generated) |
| 2 | `crates/spectrafit-solver/src/dispatch.rs` (76) | `python/oracles/engine.py` (124) | `web/src/panels/registry.tsx` (34) |
| 3 | `crates/spectrafit-solver/src/postfit.rs` (71) | `python/oracles/cases.py` (106) | `web/src/shell/EvidencePanel.tsx` (32) |
| 4 | `crates/spectrafit-solver/src/problem.rs` (57) | `python/oracles/backends/_scipy_ls.py` (104) | `web/src/panels/bodies/standing.tsx` (27) |
| 5 | `crates/spectrafit-types/src/types.rs` (56) | `python/oracles/_engine_profile.py` (87) | `web/src/plots/grammar.ts` (23) |

These counts are a raw proxy (keyword density, not true cyclomatic
complexity) — cross-checked against the technical-debt subagent's direct
reads below; two of these files (`dispatch.rs`, `postfit.rs`) are confirmed
genuine god-functions, the rest are large-but-declarative (`cases.py` is
registry data, not branching logic — see Technical Debt non-finding).

### Technology fingerprint

| Aspect | Evidence |
|---|---|
| Rust | Workspace (`Cargo.toml`: `members = ["crates/*"]`, `resolver = "2"`), edition **2021** across all 11 crates (not 2024 — a same-stack uplift candidate, not urgent), `faer`/`nalgebra`/`levenberg-marquardt`/`rayon`/`pyo3` 0.22 |
| Python | `pyproject.toml`: `name = "spectrafit-core"`, `version = "0.1.0b1"` (pre-1.0), `requires-python = ">=3.13"` — already on a current runtime |
| Web | `web/package.json`: `spectrafit-benchmark-web` 0.1.0, Vite + React, TypeScript |
| Build system | `maturin` (PyO3 → wheel), `uv` (Python deps), `npm`/`vite` (web) |
| Data stores | None (no DB layer) — run-centric JSON reports under `.spectrafit_reports/`, served read-only by FastAPI |
| Integrations | PyO3 boundary (`crates/spectrafit-core` cdylib), FastAPI `/api/report` + `/openapi.json`, GitLab CI (primary) + GitHub Actions (public mirror), MCP servers (serena/analyzer/context7/github/rrt) |
| Test presence | 158 `test_*.py` files under `tests/`, 53 Rust files with inline `#[cfg(test)]` + 4 crates with dedicated `tests/` integration dirs, 97 web `*.test.ts(x)` files — this is a well-tested codebase, not a coverage gap |

## Architecture-at-a-Glance

Ten domains, three language layers, one contract boundary each direction
(Rust↔Python via PyO3, Python↔Web via the generated OpenAPI contract). Full
Mermaid diagram: [`ARCHITECTURE.mmd`](ARCHITECTURE.mmd).

| Domain | Key files/crates | Depends on | Responsibility |
|---|---|---|---|
| Rust Data/Type Contract | `crates/spectrafit-types` | — | Canonical wire-format types (`ModelTypeStr`, `FitGraphSpec`, `CoreError`) shared by every Rust crate and, via serde JSON, Python |
| Rust Model Kernels | `crates/spectrafit-models` (30 `Model` impls) | Types | Peak/lineshape `eval` + Jacobian implementations keyed by `ModelTypeStr` |
| Rust Fit-Graph Construction | `crates/spectrafit-graph`, `crates/spectrafit-builder` | Types, Models | Compiles a `FitGraphSpec` into an executable node graph with symbolic-expr constraint edges; `spectrafit-builder` is a test-only exhaustiveness gate, not a runtime dependency (documented intent — see Notable Findings) |
| Rust Solver Stack | `spectrafit-trust-region`, `-levenberg-marquardt`, `-dogleg`, `-newton-cg`, `-varpro`, `-solver` | Types, Models, Graph | `spectrafit-solver::fit()` dispatches by solver choice across LM/dogleg/Newton-CG/VarPro/IRLS |
| PyO3 Bridge | `crates/spectrafit-core` (`#[pymodule] _core`) | all of the above | The only Rust↔Python control-flow boundary; every entry point wrapped in `catch_unwind` so a Rust panic never crosses as an uncatchable Python exception |
| Python Wheel API | `python/spectrafit_core/*` | PyO3 Bridge | Typed public API (`fit`, `fit_fast`, `FitGraph`, `Parameter`, 29 `compose()` shape factories) |
| Benchmark Engine & Backends | `python/oracles/{engine,_engine_*,cases,backends/*}` | Wheel API, Rust Solver Stack (indirect) | Runs spectrafit vs. lmfit/scipy-ls/jax oracles, computes accuracy/timing/stability metrics |
| Contract & Serving Layer | `python/oracles/{bench_contract,contract,api,panels,migrate,reports,cli}` | Benchmark Engine | Frozen `BenchReport` Pydantic contract, FastAPI serving, publishes `/openapi.json` |
| Audit/Verification-Wire Subsystem | `python/oracles/audit/*`, `trust_ledger.py` | Contract Layer, Benchmark Engine | Claim-by-claim W1–W7 verification ledger embedded in every report |
| Web (Contract → Series → Shell) | `web/src/{contract,series,plots,shell,panels,chrome}` | Contract & Serving Layer | Typed ingestion → pure chart-data transforms → declarative panel rendering (3 destinations: Standing/Audit/Evidence) |

**Notable structural findings** (from the structural-map pass, all
confidence-rated):
- `spectrafit-builder` has zero runtime consumers by design — it's a
  Rust-native DSL plus a `cargo test`-only compile-time exhaustiveness gate
  (`builder_roundtrip.rs`) that fails if a new `ModelTypeStr` variant isn't
  wired everywhere. Confirmed intentional via `CLAUDE.md`; flagged only so a
  newcomer doesn't mistake it for dead code.
- No dangling Python `oracles` submodules — every candidate (`panels`,
  `nested`, `inference*`, `synth`, `forensics`, `stability`) has a live
  importer. `forensics`/`stability` are CLI-only (`oracles.cli`), not
  exercised by the FastAPI serving path — if that CLI subcommand were ever
  dropped, these two modules would go dangling.
- `crates/spectrafit-core`'s `rlib` crate-type target (alongside `cdylib`) is
  unused by any workspace crate — standard PyO3 boilerplate for `cargo test
  -p spectrafit-core` to link, not a real gap.
- All two `#[pyfunction]`s checked for pymodule-registration risk
  (`model_type_wire_strings`, `evaluate_components`) are correctly
  registered — no dangling PyO3 export.

## Production Runtime Profile

**No telemetry available.** No observability/APM MCP server or runtime
export was accessible in this session — this step is skipped per protocol.
If production wall-clock data for `/api/report`, the benchmark `run`
command, or CI job durations becomes available, re-run this step to surface
the highest-variance (p99/p50) hotspot as a telemetry-grounded (not
static-analysis) operational-risk signal.

## Technical Debt

Ranked by remediation value (full evidence and file:line citations from the
technical-debt subagent's direct-read pass):

1. **Contract camelCase convention violation in `trust_ledger.py`.**
   `WireResult`/`NistValidation`/`TrustBlock` (`python/oracles/trust_ledger.py:42-130`)
   omit `alias_generator=to_camel` (present on every other contract model via
   `_Base` in `bench_contract.py:116-121`), so `n_claims_audited`,
   `nist_validation`, `wire_id`, `total_available` leak snake_case onto the
   wire while the rest of `BenchReport` is camelCase. Already forces 4
   confirmed `as any` casts (`standing.tsx:273`, `methods.tsx:412,437`).
   **This is the single highest-value fix** — it's the one place the
   contract violates its own documented convention, and every future
   `TrustBlock` field addition will keep leaking.
2. **`spectrafit-solver::dispatch::fit()` is a 456-line god-function**
   (`dispatch.rs:178-634`) mixing solver routing, graph compilation, and
   inline VarPro result-merging that duplicates the shared LM assembly path.
3. **`spectrafit-solver::postfit::assemble_result()` is a ~360-line
   god-function** (`postfit.rs:30-388`) computing χ²/R²/AIC/BIC/covariance/
   condition-number in one body — single choke point for every statistical
   diagnostic.
4. **`gate()` CLI duplicates a pass/warn/fail block 4×** instead of looping
   over axis specs (`cli.py:636-719`) — violates the project's own
   "declare, don't loop" convention; the file's own comment already
   anticipates a 5th axis.
5. **Three `as any` casts erase already-correctly-typed contract fields**
   (`ProvenanceFooter.tsx:26-28` on `gitCommit`/`gitBranch`/
   `runTimestampUnix`, plus a fourth structurally-similar cast on
   `report.suite` in `standing.tsx:37-38`) — defeats the project's own
   `noHardcodedBackend`/OpenAPI-sync drift tests, most likely leftover from
   a pre-contract-regen commit.
6. **Two ~220-line React components mix data derivation, formatting, and
   deeply-nested inline JSX** (`standing.tsx`: `gateVerdictCard` lines
   48-262, `renderTruthCard` lines 263-501) with no shared style-token
   layer (49–67 `style={{` occurrences per file) — highest-traffic panels
   (default `#standing` destination), highest visual-regression risk.
7. **Stale docstring describing a bug in a component that no longer
   exists** (`bench_contract.py:66-72` references a `GateBadge.tsx` that
   `find` confirms doesn't exist under `web/src/`) — a doc-drift instance
   matching the pattern the project's own 2026-07-02 three-language audit
   flagged as "the sole survivor" of prior hardening; cross-referenced
   again in Documentation Gaps below.
8. **Five production (non-test) `unwrap()`/`expect()`/`panic!` calls**, all
   with inline `INVARIANT:` comments (`compiler.rs:254,266`,
   `expr.rs:492`, `global.rs:261`, `builder.rs:572`) — good discipline, but
   each is a live panic-on-request-path if the invariant is ever violated
   by a future refactor.
9. **scipy-ls backend's bound-construction table
   (`_scipy_ls.py:138-566`, `_bounds_for`) is a second per-backend map**
   parallel to `oracles.models.MODEL_REGISTRY` — new long-tail-shape models
   require editing this file by hand instead of registering bounds
   alongside the model, against the project's own "registry over per-call
   maps" convention.
10. **`report.suite as any` re-types an already-correct generated type**
    (`standing.tsx:37-38`) to a hand-rolled shape — third occurrence of the
    same erasure pattern in one review pass, suggesting habit rather than
    one-off haste; cheap fix (a `Pick<>` instead of `as any`).

**Notable non-findings** (checked, refuted — worth recording so they aren't
re-flagged next pass): no `#[allow(dead_code)]`/`@deprecated` markers, only
2 honest forward-looking `TODO`s in the whole tree; all 14 `except
Exception` sites are `# noqa`-annotated with an inline rationale (deliberate,
not sloppy); all Rust `.unwrap()` hits outside the 5 listed above are
confined to `#[cfg(test)]`; `cases.py` (1,528 lines) is declarative
registry data, not a god-module.

## Security Findings

CWE-tagged, ranked by severity. No hardcoded credentials, no unsafe
deserialization, no injection vectors, no SQL layer (none exists), and a
correctly-implemented path-traversal guard on the one filesystem-path-from-
user-input endpoint (`api.py:128-136`) — see full clean-scan notes below the
table.

| CWE | Severity | Location | Finding |
|---|---|---|---|
| CWE-522 (Insufficiently Protected Credentials) | Medium | `.gitlab/70-publish.yml:87`, `scripts/publish_snapshot.sh:34` | `GITHUB_TOKEN` (fine-grained PAT, Contents:R/W) embedded in a `git remote add` URL — persists in plaintext `.git/config` in the job's working tree, re-exposed by any later `git remote -v`/debug step. Fix: credential helper or `-c http.extraHeader`, never a persisted remote URL. |
| CWE-214 (Sensitive Info in Process Args) | Medium | `scripts/publish_snapshot.sh:40`, `scripts/purge_github_actions_runs.py:97` | `GITHUB_TOKEN` passed as a `--token` CLI arg — visible via `ps`/`/proc/<pid>/cmdline` to any co-resident process. Fix: read from env inside the script, not `argparse`. |
| CWE-829 ("Pwn Request") | Medium | `.github/workflows/pre-commit-check.yml:1-122` | Triggers on `pull_request` (incl. forks, no author-association gate), checks out and **executes** PR content: `pre-commit run --all-files` runs hooks the PR's own config defines (multiple `language: system` hooks), plus `cargo clippy`/`cargo check` (executes arbitrary `build.rs`). Holds `pull-requests: write` + `secrets.GITHUB_TOKEN`. Fix: gate execution behind same-repo/maintainer-approval for first-time external contributors. |
| CWE-1426-adjacent (Untrusted Input → Privileged Agent) | Medium | `.github/workflows/claude.yml:3-42`, `claude-code-review.yml:1-45` | Triggers on any public commenter's `@claude` mention or any PR (incl. forks); hands `secrets.CLAUDE_CODE_OAUTH_TOKEN` to an LLM agent whose execution context is driven by attacker-controllable comment/PR text — a realistic prompt-injection vector to attempt token exfiltration, even though granted `GITHUB_TOKEN` scope is currently read-only/limited. Fix: restrict trigger to `write`/`admin` `author_association`; verify the action's sandboxing prevents the agent reading its own OAuth token from env. |
| CWE-1104/CWE-829 (Unpinned Third-Party Actions) | Low | `ci.yml`, `benchmark.yml`, `pre-commit-check.yml` — every `uses: actions/*@v4`, `dtolnay/rust-toolchain@stable`, etc. | Mutable-tag pins, not SHA-pinned — `release.yml` in the same repo correctly SHA-pins everything, confirming this is a gap not a stance. Fix: SHA-pin + enable the already-configured Dependabot `github-actions` ecosystem to keep them current. |
| CWE-1333 (ReDoS, transitive, dev-only) | Low | `web/package-lock.json` (`js-yaml` 4.0.0–4.1.1 via `@redocly/openapi-core` → `openapi-typescript`) | `npm audit`: moderate quadratic-complexity DoS in merge-key handling. Dev-only build-time dependency (`npm run contract`), not shipped to the browser bundle or FastAPI service. Fix: `npm audit fix`. |
| CWE-346/942 (Permissive CORS) | Low | `python/oracles/api.py:61-66` | `allow_origins=["*"]`, `allow_credentials` unset (defaults `False`). Low severity as deployed (localhost, read-only non-sensitive data by design) but the report already embeds git provenance (commit/branch); wildcard becomes a real issue the moment this binds to a non-localhost interface. Fix: scope to the known dev/prod origins before any non-local deployment. |
| CWE-494 (Unverified Code Download) | Low | `.gitlab/docker/Dockerfile.ci:85-98` | `rustup`/`cargo-llvm-cov` fetched via `curl \| sh` / `curl \| tar -xz` with no checksum/signature verification before execution — supply-chain risk if the installer or release asset is ever compromised. Fix: pin + verify a SHA-256 checksum. |

**Clean-scan notes:** no `shell=True`/`os.system`/string-built subprocess
calls anywhere; the one `yaml.` call (`scripts/fast_lane_gate.py:81`) is
`safe_load`; the one `dangerouslySetInnerHTML` sink (`Katex.tsx:23`) renders
KaTeX output with default `trust: false` sanitization on server-generated,
not user-editable, input; the only `unsafe` block in all of `crates/`
(`math_backend.rs:63`, an Accelerate FFI call) is correctly guarded with an
accurate `SAFETY` comment; no auth-bypass findings (the FastAPI app has no
auth by design — appropriate for its read-only-local-reports threat model).

## Documentation Gaps

Given the unusually high file-level doc coverage (91% Rust, ~100% Python),
the real gaps skew toward cross-cutting/process documentation rather than
missing docstrings:

1. **`README.md:27` claims the GitHub mirror "carries...no CI runs
   here"** — contradicted by live evidence gathered this session:
   `.github/workflows/*.yml` + `.github/dependabot.yml` demonstrably
   execute full CI. On 2026-07-13, two Dependabot PRs (`js-yaml`/
   `@redocly/openapi-core` bump, esbuild bump) triggered `Pre-Commit Check`
   and `Claude Code Review`, both of which **failed**, while `main` itself
   stayed green. A contributor trusting the README would not expect this.
2. **Stale docstring describing a nonexistent component**
   (`bench_contract.py:66-72` references a `GateBadge.tsx` bug; that file
   doesn't exist under `web/src/` — see Technical Debt #7). A future reader
   could reintroduce the described bug pattern chasing an outdated warning.
3. **`web/` has no `README.md`** — the only one of the three major
   subsystems (Rust/Python/Web) without a standalone entry doc, despite
   near-universal coverage elsewhere.
4. **Four git remotes configured** (`origin`, `github`, `gitlab`,
   `SpectraFit-Core` — two pointing at the identical GitHub URL under
   different casing) with no doc stating which to use for a local push;
   `CLAUDE.md` documents the GitLab-primary *policy* but not this
   remote-naming redundancy.
5. **The orphan-branch force-push republish mechanism** (`rrt git
   publish-snapshot --yes-i-know-this-overwrites-remote-history`, which
   discards all GitHub-side history on every publish) isn't mentioned in
   `README.md`/`CONTRIBUTING.md` — a contributor opening a PR directly
   against the GitHub mirror (as Dependabot does automatically) has no
   visible warning their work will be silently erased on the next snapshot.

## Relative Scale

**COCOMO-II basic index:** `2.94 × (42.189)^1.10 ≈ 180`

This is a **relative complexity/scale index only**, computed from
hand-authored KSLOC (42.2, excluding the two generated JSON artifacts) —
useful for ranking this system against others in a portfolio, or against
its own state at a future re-assessment. **It is not a modernization
timeline, schedule, or cost.** The COCOMO person-month formula assumes
traditional human-team productivity curves, which agentic transformation
does not follow — no date, duration, or budget figure should be derived
from this number.

## Recommended Modernization Pattern

**Refactor (same-stack, in-place) — not Rehost/Replatform/Rearchitect/
Rebuild/Replace.** The evidence doesn't support anything more drastic: 10
debt findings and 8 security findings across ~42K hand-authored lines, zero
dead code, near-universal documentation, and a codebase whose own author
already runs a hardening discipline (`andon-loop`, MCP-first tooling,
enforced conventions) that most of these findings *fell through the cracks
of* rather than never having existed. This is exactly the shape of the
`/modernize-uplift`-style "same-stack, targeted-diff" pattern already used
successfully on `repo-release-tools` — except, honestly, even that command
is a loose fit: `/modernize-uplift` is built for a *runtime-version* delta
(e.g. .NET Framework → .NET 8), and nothing here needs a language/runtime
version bump (Python is already ≥3.13; the one real version gap is Rust
edition 2021 → 2024, a minor, non-urgent item). The findings above are
better executed as **scoped engineering tickets**, prioritized by the
ranking already given:

- **P0** — Technical Debt #1 (contract camelCase fix) and the three
  Medium-severity Security Findings (credential-in-URL, token-in-argv,
  pwn-request pattern, prompt-injection exposure) — all small, surgical,
  behavior-preserving diffs.
- **P1** — Technical Debt #2/#3 (the two god-functions) with characterization
  tests pinned first, per this repo's own `superpowers:test-driven-development`
  discipline.
- **P2** — the remaining Low-severity security items and Documentation Gaps
  (mostly doc-only fixes).

No `MODERNIZATION_BRIEF.md`-style phased program is warranted at this
system's current debt level — that apparatus is built for a rewrite/uplift
decision this assessment doesn't recommend making.
