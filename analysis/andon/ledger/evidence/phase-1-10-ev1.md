---
type: evidence
title: "methodology.md E2E-target fix (report.html -> live Vite dev server) matches reality"
description: "Independent verification confirms uv run poe web_e2e runs dashboard-render-audit.spec.ts against the live Vite dev server via playwright.config.ts's webServer, not a static report.html."
resource: "web/tests/e2e/dashboard-render-audit.spec.ts"
tags: ["strategy:e", "tier:3"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: docs/methodology.md (docs) -> web/playwright.config.ts + web/tests/e2e/dashboard-render-audit.spec.ts (code)
- Verdict: green
- Strategy detail: Tier 3, independent agent confirmed pyproject.toml's web_e2e poe task, config's
  live-Vite-dev-server webServer branch (only switches to static report.html when REPORT_HTML_PATH
  is set, which web_e2e never sets), and the spec file's own header comment stating it needs the
  FastAPI API + Vite dev server. Minor noted imprecision (not a defect): the doc names one spec file
  but the testDir would pick up other e2e specs too — doesn't affect the corrected claim's accuracy.
- Non-overridable: false
