---
icon: lucide/gauge
description: Reference for python/oracles/ — the benchmark and cross-verification harness that compares spectrafit against a six-backend oracle roster and audits its own output.
tags:
  - Benchmarking
  - Python
---

# Python: benchmark harness

!!! note
    This page documents `python/oracles/` — the benchmark, verification, and
    trust-ledger internals used to develop and audit spectrafit-core. It is
    **not** part of the stable public API described in
    [Python: core API](core-api.md); it may change without notice between
    releases. For the narrative tour of this package (what a contributor
    touches to add a case or a model), see
    [Benchmark engine](../../contributor-guide/benchmark-engine.md). For the
    project's central methodological claim — that it verifies its numbers but
    had never verified its own self-description — see
    [The self-auditing benchmark](../../explanation/self-auditing-benchmark.md).

`python/oracles/` is 107 modules and roughly 358 public symbols — an order of
magnitude larger than the `spectrafit_core` surface on the previous page. It
is grouped below by concern, not dumped as one flat symbol list, and each
group carries a short note on what the code actually does before the
generated API. `show_source` is disabled throughout: read the linked files
directly on GitLab/GitHub for implementation detail; this page is for
signatures and docstrings.

## Verification wires

The numerical trust ledger. Each `wire_w*` function in `oracles.audit.wires`
computes one independently-checkable property of a benchmark run (W1–W11) and
returns a list of `WireResult` records — `"pass"`, `"warn"`, `"fail"`,
`"skipped"`, or `"gap"`, never a silent pass-by-absence. `oracles.audit.nist`
is wire W8's evidence emitter: it re-runs 22 of NIST's 27 StRD nonlinear
regression datasets against spectrafit and returns a structured
`NistValidation`. See
[The self-auditing benchmark](../../explanation/self-auditing-benchmark.md)
for how these wires roll up into a credibility rung, and
[NIST StRD Validation](../../explanation/nist-validation.md) /
[NIST StRD reference](../nist-strd.md) for what W8 means and the full
per-dataset agreement table.

::: oracles.audit.wires
    options:
      show_source: false
      members_order: source
      heading_level: 3
      filters: ["!^_"]

::: oracles.audit.nist
    options:
      show_source: false
      members_order: source
      heading_level: 3
      filters: ["!^_"]

## Contract and trust ledger

`oracles.bench_contract` is the frozen `BenchReport` Pydantic contract — the
single source of truth for the JSON the benchmark engine emits and the
`web/` React app consumes, camelCase on the wire. `oracles.trust_ledger`
defines the `TrustBlock`/`WireResult`/`CredibilityRung` types that carry wire
outcomes and NIST validation as an optional, additive slice of that contract.

::: oracles.bench_contract
    options:
      show_source: false
      members_order: source
      heading_level: 3
      filters: ["!^_"]

::: oracles.trust_ledger
    options:
      show_source: false
      members_order: source
      heading_level: 3

## Statistics

Four modules that turn raw fit outcomes into the report's statistical claims.
`oracles.metrics` computes the frozen contract's distributional sub-objects
(timing, accuracy) from real repetitions and Monte-Carlo realizations —
nothing fabricated. `oracles.inference` holds the pure inferential-statistics
functions (confidence intervals, equivalence tests, stability scores) so
every comparison in the report carries its own uncertainty. `oracles.nested`
covers nested-model selection statistics for model-adequacy verification and
validation. `oracles.stability` aggregates a reps-ladder of benchmark runs
into per-backend convergence data — at which timing-repetition budget the
headline numbers stop moving.

::: oracles.metrics
    options:
      show_source: false
      members_order: source
      heading_level: 3
      filters: ["!^_"]

::: oracles.inference
    options:
      show_source: false
      members_order: source
      heading_level: 3
      filters: ["!^_"]

::: oracles.nested
    options:
      show_source: false
      members_order: source
      heading_level: 3
      filters: ["!^_"]

::: oracles.stability
    options:
      show_source: false
      members_order: source
      heading_level: 3
      filters: ["!^_"]

## Model kernels

`oracles.jax_kernels` is a deliberately separate module: the numpy `evaluate`
bodies in `oracles.models` sit inside the timed fit loop of the lmfit and
scipy-ls benchmark backends and must never grow a jax branch or import cost,
so every peak-shape formula is re-expressed here in `jax.numpy` and pinned
against its numpy twin by a dedicated parity test.

::: oracles.jax_kernels
    options:
      show_source: false
      members_order: source
      heading_level: 3
      filters: ["!^_"]

## Case catalog and model registry

`oracles.cases` is the declarative, pydantic-first benchmark catalog: a case
is a typed graph of components (Gaussian, Lorentzian, Voigt, Fano,
background, edge, decay — a discriminated union keyed by `model`), organized
into categories such as `easy`, `complex`, `scaling`, `lineshapes`, and
`optfn`. `oracles.models` is the model registry itself — one `PeakModel`
record per shape bundling the numpy formula, the lmfit oracle callable, the
spectrafit `ModelType` name, canonical parameter names, and the jax twin from
`oracles.jax_kernels`. See
[Adding a new benchmark model](../../contributor-guide/benchmark-engine.md#adding-a-new-benchmark-model)
for the registration workflow these two modules drive.

::: oracles.cases
    options:
      show_source: false
      members_order: source
      heading_level: 3
      filters: ["!^_"]

::: oracles.models
    options:
      show_source: false
      members_order: source
      heading_level: 3
      filters: ["!^_"]
