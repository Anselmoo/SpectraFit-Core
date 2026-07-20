# Cycle close — the ritual that ends an andon cycle

Self-contained essentials. The historical specialist content under
`.claude/skills/cycle-close/` is in git history.

The andon-loop owns the *iteration*; this reference owns the *record*.

## When to run

At the end of a `fix`-mode or `tri-stream`-mode andon cycle, after the
cycle is marked converged. Replaces the 10+ manual close commits that
accumulate without a ritual.

## Args (when invoked as a sub-document)

```
cycle close --cycle N --commits HASH[,HASH...]
            [--bucket Solver|Schema|Web|Benchmark|CI|Governance]
            [--supersedes <prior-adr-anchor>]
```

| Arg | Required | Description |
|-----|----------|-------------|
| `--cycle N` | yes | Cycle number (integer). |
| `--commits HASH[,…]` | yes | Comma-separated commit hashes in this cycle. |
| `--bucket BUCKET` | no | One of 6 DECISIONS.md buckets. Prompt if absent. |
| `--supersedes ANCHOR` | no | Prior ADR anchor this decision supersedes. |

## What gets produced

1. **An ADR entry** in `DECISIONS.md` with the canonical structure:
   - Context (what the cycle was for)
   - Decision (what was chosen)
   - Rationale (why)
   - Trade-offs (what was rejected and why)
   - Verification (the evidence — link to manifest, test names)
   - Files (changed files, deduplicated across commits)
   - Commit (one-line summary)

2. **A topic-index entry** under the right of 6 buckets (Solver,
   Schema, Web, Benchmark, CI, Governance) in `DECISIONS.md`'s
   topic-index section. The `audit-decisions-topic-index.sh` hook
   enforces this.

3. **A ledger append** to `.andon/ledger.json` history:
   ```json
   {
     "type": "cycle_close",
     "cycle": N,
     "commits": ["...", "..."],
     "bucket": "Solver",
     "adr_anchor": "cycle-N-<title-slug>"
   }
   ```

4. **A push-ready commit message** capturing the ADR title and the
   three-pillar status (PERF / RIGOR / PRESENTATION).

## Steps inside the close

1. Gather commit metadata: `git show --stat <hash>`, `git log -1
   --format="%s" <hash>` for each commit.
2. Synthesize ADR title from commit subject lines if not user-supplied.
3. Compute three-pillar status from the latest
   `.spectrafit_reports/.../manifest.json`.
4. Write the ADR to `DECISIONS.md` (top of bucket section).
5. Append to ledger.
6. Generate the commit message in a quoted heredoc.

## Stuck-mode entry

Cycle close shouldn't reopen — it's a write of recorded state. If it
does (e.g. the ADR slot is contested), the answer is to bump the cycle
number and re-record, not to overwrite a prior decision.
