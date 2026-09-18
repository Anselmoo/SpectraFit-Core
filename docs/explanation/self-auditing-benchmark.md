---
icon: lucide/shield-check
description: How the benchmark verifies itself — the fourteen numerical wires (W1, W2a–W2d, W3–W11), the S1–S5 structural wires that check the project's self-description, and how both roll up into one credibility rung.
tags:
  - Validation
  - Benchmarking
---

# The self-auditing benchmark

> "The project rigorously verifies its output and never verifies its
> self-description."
>
> — `oracles.audit.structure_wires` module docstring

Every check described on this page is implemented in `python/oracles/audit/`
and `oracles.trust_ledger`. Rather than re-narrate what those modules already
document — the kind of restatement that is exactly how the drift this page
exists to close first happened — this page renders their own docstrings and
adds only the connective prose needed to read them in order.

## Numerical wires: W1, W2a–W2d, W3–W11

`oracles.audit.wires` verifies that the **numbers** the benchmark reports are
true — synthetic-data invariants, metric identities recomputed from raw
arrays, results round-tripping through the frozen contract, Jacobian
conditioning, and more. Each `wire_w*` function returns one or more
`WireResult` records with a `"pass"` / `"warn"` / `"fail"` / `"skipped"` /
`"gap"` status; a missing input is reported as `"skipped"` or `"gap"`, never
silently upgraded to a pass. The full function-by-function listing (every
`wire_w1`.. `wire_w11`) lives on
[Python: benchmark harness](../reference/python/benchmark-harness.md#verification-wires) —
this page renders only the module's own framing of that discipline:

::: oracles.audit.wires
    options:
      members: false

W8, the external-replication gate, is its own module because it re-runs real
NIST StRD certified-value datasets rather than checking an internal
invariant:

::: oracles.audit.nist
    options:
      members: false

See [NIST StRD Validation](nist-validation.md) for what that dataset-by-dataset
agreement means and [NIST StRD reference](../reference/nist-strd.md) for the
generated agreement table itself.

## Structural wires: the S1–S5 taxonomy

The W-wires above only ever check numbers. A 2026-06-26 audit sweep found a
different, previously-unguarded defect class: claims the repository makes
about *its own structure* — a hook's cited "source of truth" file, an
enforcement anchor's trigger, a doc's ownership claim, an FFI (Foreign
Function Interface) stub's completeness, a hand-maintained model list —
silently drifting from the structure itself. `oracles.audit.structure_wires`
closes that gap with the same idiom as the numerical wires: each
`S`-prefixed wire below returns a
`WireResult`, so a drifted comment or a stale doc now fails a wire exactly
the way a wrong $r^2$ does, and both land in the same `TrustBlock`.

::: oracles.audit.structure_wires
    options:
      show_source: false
      members_order: source
      heading_level: 3
      filters: ["!^_"]

Structure wires are deliberately **non-capping** on the credibility rung in
both directions — see [Credibility-rung derivation](#credibility-rung-derivation)
below for why.

## Claim registry and value provenance

Two smaller registries back the taxonomy above with *what* is being audited,
as opposed to *whether* each check passed:

::: oracles.audit.claims
    options:
      show_source: false
      members_order: source
      heading_level: 3
      filters: ["!^_"]

::: oracles.audit.provenance
    options:
      show_source: false
      members_order: source
      heading_level: 3
      filters: ["!^_"]

## Credibility-rung derivation

`oracles.audit.runner` walks every wire and produces the `TrustBlock` that
gets persisted as `trust.json` and inlined into `results.json`:

::: oracles.audit.runner
    options:
      members: false

The mapping from wire statuses to a `CredibilityRung` — which statuses cap
the rung, which are non-capping, and what unlocks the reserved top rung — is
itself substantial enough to read as primary source rather than summary:

::: oracles.audit.runner._compute_rung
    options:
      show_source: false
      heading_level: 3

## TrustBlock: the provenance contract

`oracles.trust_ledger` defines the typed records every wire above ultimately
produces or feeds — `WireResult`, `NistParam`/`NistDataset`/`NistValidation`
(the W8 evidence block), `TrustBlock`, and the persisted `TrustLedger` — plus
the `CredibilityRung` enum `_compute_rung` returns:

::: oracles.trust_ledger
    options:
      show_source: false
      members_order: source
      heading_level: 3

## See also

- **Related explanation**: [NIST StRD Validation](nist-validation.md) — what
  W8 checks.
- **Reference**: [Python: benchmark harness](../reference/python/benchmark-harness.md) —
  the full internal API surface, including every W-wire signature this page
  only frames. [NIST StRD reference](../reference/nist-strd.md) — its full
  agreement table. [Python: benchmark API](../reference/python/benchmark-api.md) —
  the `/api/v1/trust` endpoint that serves a run's `TrustBlock` to the web UI.
- **Glossary**: [Glossary](../glossary.md) — definitions for this page's
  project-specific terms (`StRD`, `NIST`, `Jacobian`).
