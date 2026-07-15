# Invariant classes — what to CLASSIFY a defect against

When BPDD's CLASSIFY step asks "what invariant does this violate?", check the
defect against this catalog first. If it fits one, you've found the class. If it
fits none, you've found a *new* class — name it and add it here. This file is
the living big-picture map; it grows by SWEEP, not by bug report.

## Invariant 0 — Functionality-before-Presentation (the value-stream ordering law)

The governing invariant: it decides *when the others even apply*. The value
stream is `crates/python (compute) → verification (ground-truth) → contract
(JSON→Pydantic→OpenAPI→TS) → web (render) → cupertino (design)`.

**A metric-bearing plot/panel is legitimate only when its metric is (a) computed
for real at the source (Rust/Python) — NOT a proxy/reconstruction standing in for
an unimplemented quantity; (b) a first-class field in the contract; (c) verified
against ground truth.** Only then (d) render, (e) design-polish.

Violation signature: effort spent on web/CSS/cupertino for a metric whose upstream
stage is a stub or proxy. This is *why a team "struggles with the frontend"* — there
is nothing real to plot, so the struggle is mistaken for a styling problem.

- **Sample:** the "Convergence to ground truth" panel (`registry.tsx:1651`) renders
  a **χ²-floor proxy** — its own caption admits "per-iteration parameters aren't
  stored" (`:1657`). The real functionality (the Rust solver storing per-iteration
  θ so actual θ-distance-to-truth can be computed + ground-truth-tested) does not
  exist. Presenting/polishing it violates Invariant 0.
- **ENFORCE:** (1) the andon-loop blocks the web stage for a metric whose
  python+ground-truth wire is red/absent — the andon rule, applied to the
  value-stream order; (2) the L3 integrity suite forbids an *unflagged* proxy: a
  metric plot must render a real contract field, OR be explicitly declared a proxy
  in `LIMITATIONS.md` with a tracked task to implement the real metric. No silent
  proxy. (3) `solvay-council` defines the correct metric *before* crates implements
  it; `cupertino-council` runs *last*, never on a stub.

## Invariant V — End-to-end Value Provenance (the value-quality spine)

Invariant 0 governs *ordering* (value before presentation); **Invariant V**
governs *provenance* — it makes the value side of that order machine-enforceable
and enumerable. A numerical value a panel renders is legitimate only when it is:

- **V1** produced *for real* at the source (Rust/Python), not a proxy/reconstruction
  (generalizes Invariant 0).
- **V2** a first-class contract field that resolves non-null in the payload
  (generalizes I1 + W).
- **V3** checked against an **independent oracle** within a declared tolerance
  (generalizes F + W2a + NIST W8).
- **V4** **no silent skip** — a skipped check on an audited value wire is *loud*
  (caps the rung / fails), never a silent pass.
- **V5** **no silent proxy** — a proxy is machine-declared (in the spine, with a
  tracked task) + disclosed, or the suite fails (Invariant 0 generalized).

**ENFORCE (structural, best tier):** the `VALUE_PROVENANCE` registry in
[`python/oracles/audit/provenance.py`](../../../../python/oracles/audit/provenance.py)
is the single declarative source — one `ValueProvenance` record per rendered
value (source → contract_field → oracle/tolerance → panel → status). `status:
"proxy"` *cannot be constructed* without a `proxy_task` (V5), and `status:
"real"` *cannot be constructed* without an `oracle` (V3). The claim ledger
(`CLAIM_REGISTRY`), the proxy register, and contract-coverage all *derive* from
it, so claim and evidence can never diverge on two paths (kills I2 by
construction). Adding the next metric is one record, not new gate code — the
anti-Vista-trap. The parity + consistency suite is
[`tests/audit/test_value_provenance.py`](../../../../tests/audit/test_value_provenance.py).

## Invariant T — Trunk convergence (the work-discipline law)

At all times exactly one trunk (the active goal) is on the stack with a *verifiable*
Definition of Done; every discovered branch (side-find) carries a recorded verdict
(`fix-now`/`defer`/`re-baseline`/`drop`); the session is not "done" until every DoD
item is checked AND verified, with no open `fix-now`/`re-baseline` branches.

Enforced by the `semantic-debugging` skill (the committed trunk ledger under
`docs/superpowers/ledgers/`) and the `guard-ledger-freshness.sh` reaper hook.
Generalizes the failure mode where a session fixes real side-bugs (branches) but
loses the trunk and never closes — or merges — its original goal (the "tree
problem"). Classify against T when work sprawls across branches and the goal stalls.

## The presentation/comparison logic contract (web report)

The dashboard makes **claims** (rung, wires, geomean, win-rate, Δr²) backed by
**evidence** (contract fields) **rendered** by panels. The binding invariants:

- **I1 — Claim ⇒ Evidence.** Every *audited* claim's `source_field` resolves to
  a non-null value in the payload AND is rendered by a panel.
  `rung == 5 ⟹ nist_validation` present, all datasets ≥ threshold.
  *No claim without visible evidence.*
- **I2 — Single derivation.** A claim and its displayed evidence derive from the
  **same** object. No parallel recomputation of the same fact on two paths
  (the divergence that hid the NIST bug).
- **I3 — Cross-panel consistency.** A quantity (geomean, rung, win-rate) shows
  one value everywhere: headline = gate = panel.
- **I4 — Enumeration completeness.** A new solver in the roster appears in every
  backend-enumerating panel (`solversOf`, no hardcoded id) and has every derived
  metric computed for it. No `?? PRIMARY` fallback.
- **I5 — No-empty-when-claimed.** A panel must not render its empty-fallback
  while the report asserts the claim that panel visualizes.

## The value-stream / wire class (cross-service)

- **W — Wire integrity.** A service's output contract must be consumable by the
  next service, proven by a wire test (pyo3 ABI, `BenchReport` → `openapi.gen.ts`,
  rendered surfaces). A broken wire halts advance — see [[andon-loop]].

## The comparison-fairness class (benchmark)

- **F — Fairness.** Same data, matched tolerances, timing-isolation across
  backends; a derived metric is computed on the correct case-subset
  (e.g. |Δr²| on LM-family only) and against the correct reference
  (`baseline_solver_id`, not a hardcoded slot). Adding a solver or changing the
  baseline must not silently break a derived number.

## Worked example — the NIST claim⇒evidence defect (BPDD applied)

A human reported: "no NIST values show in the report." The instinct is to
populate `nist_validation`. BPDD instead:

1. **MAP** — `serena` the trust path: `build_report` does NOT set `trust_block`;
   a separate `run_audit(run_dir)` attaches rung + wires + `nist_validation`.
   Inside it, `nist_validation` is built by `run_nist_validation()` in a
   `try/except → None`; W8's status is computed *independently* in `wires.py`.
   → claim (W8/rung) and evidence (`nist_validation`) are **two paths**.
2. **CLASSIFY** — this is **I1** (claim shown, evidence absent) caused by **I2**
   (dual derivation). Not "the NIST panel is empty" — that's the sample.
3. **ENFORCE** — (L1 structural) derive W8/rung FROM the `nist_validation` block
   so a missing block cannot unlock rung 5; (L2) a `model_validator` rejecting
   `rung==5` with no evidence; (L3) a generalized claim-evidence integrity suite
   over `CLAIM_REGISTRY` (pytest data-level + vitest render-level). Write the
   failing test FIRST: a fixture with `rung 5 + null nist_validation` must fail.
4. **SWEEP** — run L3 over every claim in the ledger, not just NIST. Fix every
   audited claim whose `source_field` is null or unrendered in the same pass.
   Also fix the I-adjacent wording defects the MAP surfaced ("representative
   subset" in `LIMITATIONS.md` and `registry.tsx`; retired Eckerle4 in
   `DECISIONS.md`).

Result: the human never has to report the *next* severed claim — L3 fails in CI
and pre-commit, and L1 makes the specific divergence structurally impossible.
