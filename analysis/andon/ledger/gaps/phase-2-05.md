---
type: gap
title: "[High] docs-drift: The rung-5 external-validation unlock rests on the 8 non-optional converging datasets; broader coverage is planned (see "
description: "python/oracles/audit/nist.py:533 — The rung-5 external-validation unlock rests on the 8 non-optional converging datasets; broader coverage is planned (see roadmap)."
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-2]]
- On constraint: false
- Location: `python/oracles/audit/nist.py:533`
- Finding domain: docs-drift
- Suggested fix / explanation: wire_w8's pass/fail (which gates RUNG_5) is derived from nist_validation.passed, which is an `all()` over ALL 10 recipe datasets including Bennett5 and MGH09 — not just the 8 the doc calls 'non-optional'. A live run confirms all 10 currently report p
- Resolved by: [[evidence/phase-2-05-ev1]]
- Proposal: Corrected LIMITATIONS.md's rung-5 dataset count (8 non-optional -> all 10). Bonus: also fixed nist.py's own docstring making the same false exclusion claim. Strategy: e, Tier 3. Blast radius: local+reversible.
