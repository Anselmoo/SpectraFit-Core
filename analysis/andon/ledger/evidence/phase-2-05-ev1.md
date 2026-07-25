---
type: evidence
title: "LIMITATIONS.md rung-5 all-10-datasets fix matches reality; bonus nist.py docstring fix"
description: "Independent verification confirms W8's pass/fail is a strict all() over all 10 NIST datasets with no production exclusion. Also surfaced (and I fixed) a second, directly-related stale docstring inside nist.py itself making the same false 'excludes Bennett5' claim."
resource: "python/oracles/audit/nist.py"
tags: ["strategy:e", "tier:3"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: LIMITATIONS.md (docs) -> python/oracles/audit/nist.py + wires.py + trust_ledger.py (code, phase-2/oracles)
- Verdict: green
- Strategy detail: Tier 3, independent agent traced the full chain (_RECIPES has all 10, no
  filtering; wire_w8 passes through nist_validation.passed verbatim; RUNG_5 gates on that same
  strict value; _OPTIONAL_DATASETS exists ONLY in the test suite's own separate assertion).
  Bonus finding: nist.py's own module docstring (lines 18-29) independently made the same false
  "guarded to exclude Bennett5" claim LIMITATIONS.md had — fixed in the same pass to accurately
  describe the strict all()-with-no-production-exclusion behavior.
- Non-overridable: false
