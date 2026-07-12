# Ledger Lifecycle

## Format
One ledger per trunk at `docs/superpowers/ledgers/<YYYY-MM-DD>-<trunk-slug>.md`,
from `.claude/skills/semantic-debugging/templates/ledger.md`. It parses two
machine-read fields (on one line):
`**Branch:** <git-branch>   **Status:** open|converged`.

## Scales to complexity (one rule)
Always a ledger; size proportional to the work. A one-DoD trunk is the Trunk + a
single DoD checkbox (~3 lines). A cross-stream trunk gets the full Branch-log table.
No mode switch, no threshold to argue about.

## Lifecycle
- **Born** at Phase 0 (trunk planted), `Status: open`.
- **Lives** committed in `docs/superpowers/ledgers/` for the trunk's life (may span
  sessions — that is why it is a file, not session-only TodoWrite).
- **Reaped** at Phase 4 convergence: delete the file (the deletion is a commit), and
  graduate its one durable sentence (decision + any invariant added) to `DECISIONS.md`.

## The reaper (automation, not memory)
`.claude/hooks/guard-ledger-freshness.sh` runs at SessionStart. For every
`Status: open` ledger whose `Branch:` is merged into main / deleted / absent, it
prints a staleness warning (exit 0). `LEDGER_STRICT=block` makes it exit 2. It also
flags a ledger that marks "merged to main" done while git disagrees (a lying DoD).
This is what prevents the migration-baseline-h class of leftover from accumulating.
