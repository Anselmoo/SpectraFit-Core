# `mode: tri-stream` — parallel sub-loops over the three streams

The spectrafit-core repo splits naturally into three streams:

| Stream | Root      | Manifest        |
|--------|-----------|-----------------|
| crates | `crates/` | `Cargo.toml`    |
| python | `python/` | `pyproject.toml`|
| web    | `web/`    | `package.json`  |

Wires between them (from `.claude/skills/INDEX.yaml § inter_stream_wires`):

| Wire             | Contract                                     | Proof (fast lane) | Slow lane |
|------------------|----------------------------------------------|-------------------|-----------|
| crates → python  | pyo3 ABI (`spectrafit_core::fit`, `::fit_fast`) | import + call + JSON round-trip | — |
| python → web     | `BenchReport` (oracles.contract → openapi.gen.ts) | openapi-typescript regen + `contractCoverage.test.ts` | — |
| python → web     | rendered dashboard surfaces                  | (n/a)             | playwright `dashboard-render-audit` |

## When to use tri-stream mode

Use `tri-stream` when the gap touches **two or more** streams. Typical
triggers:

- Adding a new spectroscopic model (Rust kernel + Python ModelType +
  bench registry + web panel).
- Migrating a `BenchReport` contract field (Python `contract.py` +
  `openapi.gen.ts` + a web panel + maybe a Rust serde struct).
- Recovering performance (Rust solver tuning + Python adapter wiring
  + dashboard pillar update).

A gap that lives in one stream stays in the existing single-stream
sequential loop — tri-stream is for the multi-stream case where
parallel fan-out is the only way to keep wall-clock down.

## How a tri-stream cycle runs

```
                          andon-loop tri-stream
                                 │
                  reads .claude/skills/INDEX.yaml
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
   crates sub-loop          python sub-loop          web sub-loop
   (subagent 1)             (subagent 2)             (subagent 3)
   skill: crates-stream     skill: python-stream     skill: web-stream
   anchors:                 anchors:                 anchors:
     Adding a New             Code Conventions         Running &
     Benchmark Model          (pydantic-first)         previewing the
   hook contracts:          hook contracts:            dashboard
     cargo-check-on-          enforce-pydantic-      hook contracts:
     rust-edit                native                   enforce-render-
     enforce-modeltype-       enforce-match-           boundary
     parity                   dispatch                 frontend-soft-
     pre-merge-pyO3           contract-sync-           freeze
                              reminder
        │                        │                        │
        ▼                        ▼                        ▼
   wire: crates→python      wire: python→web         wire: python→web
   (pyo3 ABI)               (BenchReport)            (rendered surface)
        │                        │                        │
        └────────────────────────┼────────────────────────┘
                                 ▼
                 inter-stream wires green?
                                 │
                                 ▼
                       cycle converged
```

Each sub-loop is a real `andon-loop` invocation in its own subagent, with
the same Phases 1–5. The parent loop:

1. Forks via `superpowers:dispatching-parallel-agents`.
2. Aggregates child ledgers into a parent v3 ledger
   (`cursors: [{stream, stage, pass}, …]`).
3. Refuses to mark the cycle converged until inter-stream wires are 🟢.

## Inter-stream wires are the andon rule, applied across streams

Each inter-stream wire has the same andon-rule status as any intra-stream
wire (`green` / `red` / `unknown`). The wire proofs are real, runnable
checks:

- **crates → python (pyo3 ABI)**: `import spectrafit_core; spectrafit_core.fit(...)`
  with a minimal `BenchReport`-shaped payload; assert the returned object
  round-trips through `BenchReport.model_validate(...)`.
- **python → web (BenchReport contract)**:
  `uv run poe serve` then `cd web && npm run contract` regenerates
  `openapi.gen.ts`; `npm run test contractCoverage.test.ts` confirms every
  contract leaf is rendered or explicitly ignored.
- **python → web (rendered surface, slow lane)**: `uv run poe web_e2e`
  Playwright `dashboard-render-audit`. Slow-lane: runs on cadence or as a
  parallel subagent, never blocks the fast loop.

A red inter-stream wire halts the cycle (andon rule) — the sub-loops can
continue on their own intra-stream wires, but the cycle does not close.

## Failure modes (and what they look like)

| Symptom | Likely cause | Where to look |
|---------|--------------|---------------|
| `crates` stream subagent burns tokens grepping for `fn fit_fast` | `serena_first` not honored | check serena-first hook fired warning; re-run with explicit serena instruction |
| `python → web` wire stays red after every cycle | `contract.py` edited but `npm run contract` not run | the `contract-sync-reminder.sh` hook should have nudged at edit-time |
| `cursors` list out of sync with stream count | parent loop spawned wrong number of subagents | check `INDEX.yaml`'s `streams:` list and `stream_scan.py` output |
| Inter-stream wire stays `unknown` across passes | parent loop forgot to record wire proof | manifest in `.andon/ledger.json`'s `wires` entries; v3 schema requires `lane` and `kind: inter-stream` |

See `references/stuck-mode.md` for the escape ladder when a wire reopens
three times.
