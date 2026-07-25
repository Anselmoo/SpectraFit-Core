---
type: gap
title: "[High] docs-drift: ModelType (Python str-enum) and ModelTypeStr (Rust snake_case enum) share the same 11 wire values: gaussian, lorentzian,"
description: "crates/spectrafit-types/src/types.rs:142 — ModelType (Python str-enum) and ModelTypeStr (Rust snake_case enum) share the same 11 wire values: gaussian, lorentzian, voigt, constant, linear, arctan_step, tanh_step, erfc_step, pseudo_voigt, fano,"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/phase-1]]
- On constraint: false
- Location: `crates/spectrafit-types/src/types.rs:142`
- Finding domain: docs-drift
- Suggested fix / explanation: The Rust ModelTypeStr enum and Python ModelType enum now each have 34 variants (gaussian, gaussian2d, gaussian_nd, ..., true_voigt, skewed_gaussian, exp_gaussian, doniach_sunjic, log_normal, pearson7, split_gaussian, moffat, students_t, split_pearson
- Resolved by: [[evidence/phase-1-03-ev1]]
- Proposal: Corrected docs/PARITY.md:53-55's stale 11-value list to 34, pointing to ModelTypeStr::as_str() as canonical instead of re-enumerating (prevents this exact drift recurring). Strategy: e, Tier 3. Blast radius: local+reversible.
