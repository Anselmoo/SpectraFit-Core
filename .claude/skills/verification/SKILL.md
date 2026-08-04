---
name: verification
description: |
  Crosscut verification conductor — closes the oracle gap for scientific
  / numerical software. Owns ground-truth V&V, NIST StRD fixtures,
  benchmark scenarios, and DAG validation across the three streams.
  Absorbs ground-truth, nist-strd-runner, benchmark-scenario-generator,
  and dag-validator. Use when validating against a gold standard,
  closing the oracle gap, auditing benchmark trustworthiness, running
  NIST StRD harnesses, generating realistic benchmark scenarios, or
  checking the Rust crate DAG for cycles. Composes with
  superpowers:verification-before-completion. Serena-first for code.
license: MIT
---

# verification

The crosscut V&V skill. Activates from any stream when the question is
"is the answer right?" — and stops a cycle from closing on the
three-pillar RIGOR axis if the oracle is biased or missing.

## Anchors

**CLAUDE.md sections** (read before acting):
- *Benchmark Backend Comparison Fairness* — spectrafit is the subject;
  lmfit and jax are independent cross-verification oracles.
- *After a benchmark run* — what to read from `manifest.json` and how
  to report regressions / accuracy / speed.

**Hooks that will fire:**
- `protect-nist-fixtures.sh` — **BLOCKING (exit 2)**: guards
  `tests/fixtures/nist_strd/`. Only update via the absorbed nist
  workflow + a fresh `itl.nist.gov` fetch.
- `pre-merge-dag.sh` — pre-merge gate that the crate DAG has no cycles
  and no invalid cross-dependencies.
- `pre-merge-perf-baseline.sh` — pre-merge gate that perf hasn't
  regressed against the recorded baseline.
- `enforce-perf-accuracy.sh` — perf/accuracy contract enforcement when
  present.

## Serena first

For DAG validation and source-scan checks:

```
mcp__serena__find_symbol Cargo.toml       → manifest discovery is path,
                                            not symbol — grep is ok here
mcp__serena__find_referencing_symbols     → for trace-impact of a
                                            removed model
```

For code-touching verification work (writing oracles, harnesses),
serena drives.

## Decision: which sub-document?

| Subject | Reference |
|---------|-----------|
| Manufactured solutions, metamorphic relations, significant-digit checks, differential tests, uncertainty quantification, claim-to-evidence map | `references/ground-truth.md` |
| NIST StRD fixtures, certified-data fitting harness, `tests/fixtures/nist_strd/` | `references/nist.md` |
| Generating realistic benchmark scenarios (YAML), outlier injection, multi-solver comparisons | `references/scenario-gen.md` |
| Rust crate dependency DAG validation, cycle detection, visualization | `references/dag.md` |

## Composes with

1. The stream that owns the code under test (`crates-stream`,
   `python-stream`, or `web-stream`).
2. `superpowers:verification-before-completion` — never claim "done"
   without an oracle reading.
3. `superpowers:systematic-debugging` when a verification failure is
   confusing (the oracle disagrees but the path isn't obvious).
4. If stuck: `andon-loop/references/stuck-mode.md`.

## Three-pillar reporting

Verification owns the RIGOR pillar. On any cycle close that touched
science / numerics, this skill writes a one-line RIGOR statement:

> `RIGOR: <oracle exercised> · max|Δr²| = X · UQ coverage = Y%`

## How verification activates in tri-stream mode

In `andon-loop tri-stream`, the parent loop spawns a `verification`
crosscut subagent **after** the per-stream sub-loops report green but
**before** the cycle is marked converged. The subagent runs:

1. The NIST StRD harness (if any test path under
   `tests/fixtures/nist_strd/` was touched in this cycle).
2. The DAG validator (if any `Cargo.toml` was edited).
3. The benchmark gate (`uv run spc-bench gate`) — geomean speedup +
   max |Δr²| against the baseline solver.
4. The ground-truth claim-to-evidence map if a manuscript-adjacent
   artifact was touched (e.g. `docs/superpowers/*.md`).

Any failure halts the cycle — the andon rule applies across the
crosscut as well.
