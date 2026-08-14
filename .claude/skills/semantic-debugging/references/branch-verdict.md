# Branch Verdict

Every find that is OFF the trunk gets exactly one verdict, logged in the ledger
BEFORE you act on it. Acting on a branch with no logged verdict IS the tree problem.

## The decision procedure
Ask these in order; take the first that matches (the ordering matters — `re-baseline`
is checked before `defer` so a branch bigger than the trunk is never silently parked).
1. **Does it block the trunk's Definition of Done?**
   - Yes → `fix-now`. (e.g. CI must be green to satisfy "merged to main".)
   - No → go to 2.
2. **Is the branch actually more important / bigger than the current trunk?**
   - Yes → `re-baseline`: STOP, surface to the human, and swap the trunk
     explicitly (park the old ledger as `Status: open`, note the swap). Never let
     the trunk drift silently — that is the failure this skill exists to prevent.
   - No → go to 3.
3. **Is it real and worth doing eventually?**
   - Yes → `defer`: `spawn_task` a chip with enough context to act cold, log the
     chip id in the ledger, and DO NOT follow it now.
   - No → `drop`, with a one-line reason in the ledger.

## Verdicts
| verdict | when | action |
|---------|------|--------|
| `fix-now` | blocks trunk DoD | fix inline, on the trunk |
| `defer` | real, non-blocking | `spawn_task` chip + log id; do not follow |
| `re-baseline` | bigger than the trunk | stop, ask human, swap trunk explicitly |
| `drop` | not worth it | log the reason |

## Worked example (this session)
Trunk = value-provenance. CI fixes BLOCKED "merged to main" → `fix-now`. The plot
methodology was bigger and human-introduced → `re-baseline` (but the old trunk
should have been explicitly parked, not abandoned). The serena-reliability find was
real but non-blocking → `defer` (chip). Cleaning leftover docs → `fix-now` once the
human pulled it onto the trunk.
