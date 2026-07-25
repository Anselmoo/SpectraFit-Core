---
type: evidence
title: "run_pytest_bg.sh long-parameter-list fix is correct and functionally verified"
description: "Independent verification confirms build_job_metadata_json() is a byte-for-byte faithful extraction, both call sites correctly consume the single JSON blob, and a real live run produces the expected job.json/jobs.json/jobs.log artifacts."
resource: "scripts/run_pytest_bg.sh"
tags: ["strategy:a", "tier:1"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: gap phase-3-02 (code, phase-3/scripts)
- Verdict: green
- Strategy detail: a (independent reviewer, Rung 2) — diffed against real HEAD, confirmed
  build_job_metadata_json() produces the identical key set/order/semantics as the old
  write_metadata(), both call sites now pass one JSON blob instead of 16 positional args, the
  jobs.json merge and log-line format are byte-identical. Actually ran the script for real (not
  just read it) and inspected the produced job.json/jobs.json/jobs.log artifacts, then cleaned up
  its own test artifacts (gitignored, no repo-history risk). One trivial, harmless cosmetic note:
  job.json now ends with a trailing newline it previously lacked.
- Non-overridable: false
