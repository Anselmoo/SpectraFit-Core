---
type: gap
title: "[Low] code-idiom: masked-command-return-value + magic-number-shadowing-named-constant"
description: ".claude/audit/cleanup-old-logs.sh:54,108 — two mechanical fixes in the same file"
tags: ["kind:bug", "status:closed", "domain:code-idiom", "severity:low"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `.claude/audit/cleanup-old-logs.sh:54` and `:108`
- Finding domain: code-idiom (2 findings, same file)
- Suggested fix / explanation: (54) `local FILE_NAME=$(basename "$FILE")` masks the command's
  exit status behind `local`'s own — split into `local FILE_NAME; FILE_NAME=$(basename "$FILE")`.
  (108) `HEAD_LINES=3` is declared but never referenced — the 4 usages (`tail -n +4`, `head -n 3`,
  `tail -n +4`, `- 4`) hardcode the literal instead.
- Resolved by: [[evidence/unattributed-shell-ev1]]
- Proposal: Applied both fixes exactly as suggested. IMPORTANT SAFETY NOTE: while comparing
  before/after behavior, an early test run accidentally executed the ORIGINAL (git-stashed)
  script against the REAL `.claude/audit/` directory instead of an isolated temp dir (cwd wasn't
  actually inside the temp git repo when the script ran, so `git rev-parse --show-toplevel`
  resolved to the real repo) — this archived/rewrote 3 real audit files
  (enforcement-decisions.jsonl, enforcement-errors.jsonl, violations-blocked.txt). Caught
  immediately via `git status`/`git diff --stat`, fully restored via `git checkout --` (all 3
  files are git-tracked, diff-clean after restore, confirmed via a second `git diff --stat` with
  no output), and the accidental `.claude/audit/.backups/` directory was removed. Re-tested
  correctly afterward in a properly isolated `mktemp -d` + `git init` + subshell `cd` sandbox.
  Confirmed via MD5 hash comparison that the fixed script produces BYTE-IDENTICAL output to the
  original (unfixed, git-stashed) script on the same synthetic input
  (`c9aa3c16e3cf1e7dec039e3dde447de8` both times) — including a pre-existing, out-of-scope
  behavior quirk (the date-cutoff `grep` logic archives all synthetic test records regardless of
  date, since it does exact-string cutoff-date matching rather than a real date comparison) that
  was confirmed present in BOTH versions, i.e. not introduced by this fix and not in scope for
  these 2 findings. `bash -n` syntax-clean; `shellcheck` no longer flags SC2155 for the two edited
  lines (only unrelated, pre-existing SC2086/SC2015 info-level notes remain, out of scope).
  Strategy: a (functional equivalence test, MD5-verified). Blast radius: local+reversible (script
  logic only touches its own temp/backup files, never called from any hook path).
