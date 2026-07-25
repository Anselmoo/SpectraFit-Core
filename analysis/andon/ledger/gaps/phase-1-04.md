---
type: gap
title: "[High] docs-drift: All 19 FitResult fields ... match the Rust structs one-for-one (verified by test_fit_result_field_set_matches_rust ...)."
description: "python/spectrafit_core/result.py:83 — All 19 FitResult fields ... match the Rust structs one-for-one (verified by test_fit_result_field_set_matches_rust ...)."
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `python/spectrafit_core/result.py:83`
- Finding domain: docs-drift
- Suggested fix / explanation: Both FitResult (Python) and FitResultSpec (Rust) currently carry 25 fields each (schema_version, parameters, covariance, covariance_param_order, chi2, reduced_chi2, r_squared, dof, aic, bic, n_iter, n_func_evals, n_jac_evals, success, message, best_f
- Resolved by: [[evidence/phase-1-04-ev1]]
- Proposal: Corrected docs/PARITY.md:78's stale FitResult field count (19 -> 25). Strategy: e, Tier 3. Blast radius: local+reversible.
