---
type: gap
title: "[Medium] code-idiom: long-parameter-list"
description: "scripts/run_pytest_bg.sh:77 — long-parameter-list"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-3]]
- On constraint: false
- Location: `scripts/run_pytest_bg.sh:77`
- Finding domain: code-idiom
- Suggested fix / explanation: Pass an associative array or a single JSON blob (already built via a helper) instead of 16 positional scalars, or at minimum add a leading comment enumerating the parameter order at both the definition and each call site.
- Resolved by: [[evidence/phase-3-02-ev1]]
- Proposal: Added build_job_metadata_json() to build the JSON blob once from named fields; write_metadata() and the jobs.json updater (the second, previously-duplicated 16-arg call site) now both consume the single blob instead of independently re-unpacking 16 positional args. Strategy: a. Blast radius: local+reversible.
