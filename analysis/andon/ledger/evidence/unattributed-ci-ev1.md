---
type: evidence
title: "CI-topology parity fixes + optimistix version fix verified"
description: "Independent verification confirms ci.yml's lint job now mirrors .gitlab/20-lint.yml exactly (ruff format --check, cargo fmt --all -- --check added), the .gitlab-ci.yml header comment correction is accurate against both README.md and the actual publish job rules, and the optimistix version bump is confirmed against live PyPI data. Flagged and corrected one wording imprecision in the fix's own description (scope of a diff-vs-HEAD claim), not a code defect."
resource: ".github/workflows/ci.yml, .gitlab-ci.yml, pyproject.toml, uv.lock"
tags: ["strategy:e", "tier:2"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: gaps unattributed-01, unattributed-02, unattributed-03, unattributed-04
- Verdict: green (all 4)
- Strategy detail: e (structural/connectivity) for the 3 CI-topology gaps, b (oracle-gap —
  external registry ground truth) for the optimistix gap. Independent reviewer confirmed
  `.gitlab/20-lint.yml`'s exact command sequence for both lint:python and lint:rust, confirmed
  the new `ci.yml` lint job runs the identical commands in the identical order, and independently
  ran all 5 gate commands themselves (ruff format --check, ruff check, ty check, cargo fmt --all
  -- --check, full-workspace cargo clippy -D warnings via MEM_GUARD_OFF=1) — all clean, confirming
  a real recompile occurred (not a stale cache hit) by touching a file and re-checking.
  Confirmed `.gitlab-ci.yml`'s corrected header comment against README.md's own independent
  statement (near-verbatim match) and against `.gitlab/70-publish.yml`'s actual job rules
  (publish:github has an automatic `if:` trigger, not `when: manual`; publish:github:fast is the
  actual manual job) — both halves of the old comment were wrong, both halves of the new comment
  check out. Confirmed optimistix's earliest published PyPI release is 0.0.2 (0.0.1 never
  existed) via a live fetch of the PyPI JSON API, and confirmed uv.lock's diff is a single
  constraint-string line, no resolved package changed.
  One correction applied after review: my original gap-2 write-up mischaracterized the
  compiler.rs diff-vs-HEAD as "whitespace-only" when git diff HEAD actually includes the entire
  earlier Phase-3 gap-3-03 refactor (already separately verified) plus this gap's own genuinely
  whitespace-only incremental fmt fix — corrected the gap doc's wording; no code change was
  needed since the verifier's own independent line-for-line trace confirmed the whole diff stays
  logic-preserving either way (50/50 spectrafit-graph tests green).
- Non-overridable: false
