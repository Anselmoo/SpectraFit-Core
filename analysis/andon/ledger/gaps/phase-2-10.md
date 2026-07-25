---
type: gap
title: "[Medium] lint-audit: "Prefer a registry over per-call maps. New shapes register once in oracles.models.MODEL_REGISTRY; backends read the regi"
description: "python/oracles/backends/_lmfit.py:31 — "Prefer a registry over per-call maps. New shapes register once in oracles.models.MODEL_REGISTRY; backends read the registry, never a private _MODEL_M"
tags: ["kind:bug", "status:closed", "domain:lint-audit", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-2]]
- On constraint: false
- Location: `python/oracles/backends/_lmfit.py:31`
- Finding domain: lint-audit
- Suggested fix / explanation: Register the duplicated _SHAPE_BOUNDS dict once in oracles.models.MODEL_REGISTRY-adjacent scope instead of two hand-synced backend-private copies.
- Resolved by: [[evidence/phase-2-10-ev1]]
- Proposal: Hoisted SHAPE_BOUNDS into oracles/models.py as a single shared constant; both _lmfit.py and _scipy_ls.py now import it instead of maintaining private copies. Updated 2 dependent test files, strengthening the parity test from value-equality to object-identity. Also fixed 3 now-stale live-doc references (CLAUDE.md, 2 skill reference docs). Strategy: a. Blast radius: local+reversible.
