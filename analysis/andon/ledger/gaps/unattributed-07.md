---
type: gap
title: "[Low] code-idiom: silent-except-swallow"
description: ".claude/scripts/cloud_batch_hook.py:87 — silent-except-swallow"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `.claude/scripts/cloud_batch_hook.py:87`
- Finding domain: code-idiom
- Suggested fix / explanation: Log the exception (e.g. `logging.debug`/`warning` with the path
  and exception) before continuing/returning the empty fallback.
- Resolved by: [[evidence/unattributed-shell-ev1]]
- Proposal: `load_job_metadata`'s `except Exception: continue` silently dropped any unreadable/
  malformed `job.json` with zero observability. File has no `logging` import and uses plain
  `print()`/stdout for its JSON hook-protocol output, so added a `print(..., file=sys.stderr)`
  (not `logging`, to match the file's existing minimal-import style — the finding's "e.g." made
  `logging` an example, not a requirement) naming the path and exception. Verified stdout/stderr
  separation matters here since this is a Claude Code hook emitting JSON on stdout — functionally
  tested with a synthetic scenario (one valid job.json + one malformed one): stdout still returns
  only the valid job's data (`['good']`), stderr carries the new diagnostic line
  (`skipping unreadable .../job2/job.json: Expecting value: line 1 column 1 (char 0)`) — confirms
  the hook's stdout contract is untouched while the silent-swallow gap is closed. Strategy: a
  (functional test). Blast radius: local+reversible.
