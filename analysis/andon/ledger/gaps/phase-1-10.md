---
type: gap
title: "[Medium] docs-drift: End-to-end visual | `playwright_mcp` against `report.html` | manual gate (Cycle 7.5+)"
description: "web/playwright.config.ts:36 — End-to-end visual | `playwright_mcp` against `report.html` | manual gate (Cycle 7.5+)"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `web/playwright.config.ts:36`
- Finding domain: docs-drift
- Suggested fix / explanation: The canonical E2E suite CLAUDE.md documents (`uv run poe web_e2e`, dashboard-render-audit) runs against the live Vite dev server, not report.html. A separate spec (web/tests/e2e/report-ux.spec.ts) does open report.html via file:// but only when REPOR
- Resolved by: [[evidence/phase-1-10-ev1]]
- Proposal: Corrected docs/methodology.md:121's E2E row to describe the real target (live Vite dev server via poe web_e2e), not report.html. Strategy: e, Tier 3. Blast radius: local+reversible.
