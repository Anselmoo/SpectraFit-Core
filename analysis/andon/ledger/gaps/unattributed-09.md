---
type: gap
title: "[Medium] code-idiom: unreadable-nested-heredoc"
description: "scripts/check_pytest_bg.sh:100 — unreadable-nested-heredoc"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `scripts/check_pytest_bg.sh:100`
- Finding domain: code-idiom
- Suggested fix / explanation: Split the inner PID-lookup into its own named step (assign the PID
  to a shell variable first via a single small heredoc), instead of nesting a `python3 - <<'PYPID'
  ...` heredoc inside a `$(status_for_pid "$(...)")` command-substitution chain that is itself an
  argument to the outer `python3 - <<'PY' ...` heredoc.
- Resolved by: [[evidence/unattributed-shell-ev1]]
- Proposal: Extracted the inner PID lookup to its own statement (`pid=$(python3 - "$meta"
  <<'PYPID' ... PYPID\n)`) immediately before the loop's main step, then `status=$(status_for_pid
  "$pid")` as its own statement, then the outer heredoc's positional-arg list references `"$meta"
  "$status" ...` directly — same 5 positional args in the same order as before, just no longer
  triple-nested on one statement. Verified no variable-name collision (`pid`/`status` unused
  elsewhere at this scope; `status_for_pid`'s own `local pid` is function-scoped, no conflict).
  `bash -n` syntax-clean. Functionally tested by copying both the original (`git show HEAD:...`)
  and fixed script into isolated temp `ROOT_DIR`s (the script derives its root from
  `${BASH_SOURCE[0]}`'s directory, so a real filesystem copy was needed, not just a stashed
  in-place edit) with a synthetic job.json (`pid: $$`, so `kill -0` genuinely resolves to
  "running") — output identical field-for-field (job_id, status, pid, mode, started_at,
  started_at_bern, command); the only diff was the two separate `mktemp -d` paths themselves
  (expected test-setup noise, not a behavior difference). Strategy: a (functional equivalence
  test). Blast radius: local+reversible.
