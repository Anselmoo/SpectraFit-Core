---
type: gap
title: "[High] docs-drift: web/src/contract.ts re-exports the named view types (BenchReport, Featured, SuiteCase, BackendProfile, SolverMeta, Sprea"
description: "web/src/contract/index.ts:1 — web/src/contract.ts re-exports the named view types (BenchReport, Featured, SuiteCase, BackendProfile, SolverMeta, SpreadPt, Point2D, MultiDim, Projection, GlobalFit, GlobalFitSlice, PeakTrace) from i"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: true
- Location: `web/src/contract/index.ts:1`
- Finding domain: docs-drift
- Suggested fix / explanation: There is no file web/src/contract.ts — the module now lives at web/src/contract/index.ts (a directory-style module), confirmed by `ls` returning 'No such file' for contract.ts and finding contract/index.ts instead. Additionally, SolverMeta is NOT amo
- Resolved by: [[evidence/phase-1-01-ev1]]
- Proposal: Corrected CLAUDE.md:294-297 to reference `web/src/contract/index.ts` (not the non-existent `contract.ts`) and to list the file's actual 17 exported type names (dropped `SolverMeta`, added `NdPeak`/`TrustBlock`/`WireResult`/`SuiteMetric`/`CaseInference`/`PeakACS`). Verification strategy: e (structural/connectivity), Tier 3. Blast radius: local+reversible.
