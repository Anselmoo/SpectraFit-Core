---
type: stage
title: "Unattributed: files outside the stage graph"
description: "self-assess brief 'Unattributed findings' section — files not in file_stage_index.json (config/doc files outside the stage graph: .gitlab/.github CI configs, top-level docs, .claude/ tooling). 35 findings, 5 advisory notes, 1 business rule, none previously ingested into any andon-loop phase."
tags: ["lane:fast"]
timestamp: "2026-07-24T00:00:00Z"
---

## Stage detail

- Detected via: self-assess-brief ingest (MODERNIZATION_BRIEF.md §3 "Unattributed findings/
  advisory notes/business rules" — never entered any Phase 1-6 ledger scan since ingest mode only
  pulls per-phase items from stages in the graph)
- Member stages: (none — by construction, these files are outside file_stage_index.json)
- Outgoing wires: (none)
- Incoming wires: (none — runs after phase-6 cycle 1 convergence, on user request)
- Behavior contract rules attributed this pass: 1 unattributed rule (dataset_index scoping
  policy, P1/Policy) — contract obligation only, not a gap; honor if any fix here touches
  spectrafit-graph/executor.rs (none do)
- Advisory notes (not auto-fixable, human judgment): 5 (confab:agentic-reliability — excluded
  from gap ingestion by design, same fixability routing as phase ingestion)
