---
type: gap
title: "[Low] confab:dependency-audit: optimistix lower bound pins a non-existent version"
description: "pyproject.toml:50 — optimistix>=0.0.1"
tags: ["kind:bug", "status:closed", "domain:confab:dependency-audit", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `pyproject.toml:50`
- Finding domain: confab:dependency-audit (fixability: fixable)
- Suggested fix / explanation: `optimistix` (legitimate package, Patrick Kidger's JAX/Equinox
  nonlinear-optimisation library) exists on PyPI, but the pinned lower bound `0.0.1` was never
  actually published — the earliest real release is `0.0.2`. Harmless in practice (every real
  release satisfies `>=0.0.1` too) but the exact pin doesn't correspond to a real version.
- Resolved by: [[evidence/unattributed-ci-ev1]]
- Proposal: Re-verified independently against the LIVE PyPI JSON API (not just trusting the
  original confab audit finding, which could itself be stale) — confirmed earliest published
  version is `0.0.2` (2023-08-08), latest is `0.1.0` (2026-02-16), `0.0.1` was never published.
  Bumped `optimistix>=0.0.1` → `>=0.0.2` in `pyproject.toml`, then ran `uv lock` to regenerate
  `uv.lock` (a 1-line constraint-metadata diff only — confirmed via `git diff uv.lock` — no
  actual resolved package version changed, since every already-resolved version already satisfied
  `>=0.0.2`). NOTE: this is the exact fix that was applied and then reverted earlier in this
  session, before the andon-loop gate was set up (the user's process correction: "i was
  interrupting you because we are not following anymore the self-asses workflow" —
  `git checkout -- pyproject.toml`). This time it goes through the proper gated propose→verify
  flow. Strategy: b (oracle-gap — external registry ground truth). Blast radius: local+reversible.
