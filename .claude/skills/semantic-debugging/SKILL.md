---
name: semantic-debugging
description: Use FIRST when starting any goal or hitting any bug/failure — holds the trunk (the goal), classifies every find, dispatches instance bugs to systematic-debugging and class bugs to big-picture-driven-development, and forces convergence via a committed trunk ledger. Use before systematic-debugging or BPDD.
---

# Semantic Debugging

## Overview

Good sessions go deep and finish; bad ones stay vague and never reach the core.
The cause is rarely weak analysis — it is the **tree problem**: you start with a
*trunk* (the goal), discover *branches* (side-bugs), fix them (correctly), and end
up deep in the canopy having never closed the trunk.

This skill is the **work conductor**. It runs FIRST. It does not replace the two
debugging techniques — it dispatches them:
- one wrong value/line (an **instance**) → `superpowers:systematic-debugging`
- a symptom of a missing invariant (a **class**) → `big-picture-driven-development`

## The Iron Law

```
NO BRANCH WITHOUT A LOGGED VERDICT. NO "DONE" WITHOUT A CHECKED DEFINITION OF DONE.
```

## Invariant T — Trunk convergence

At all times exactly one trunk is on the stack with a *verifiable* Definition of
Done; every discovered branch carries a recorded verdict; the session is not done
until the trunk DoD is checked AND verified (run it, show evidence).

## The Ledger

A committed markdown ledger at `docs/superpowers/ledgers/<YYYY-MM-DD>-<trunk-slug>.md`
(template: this skill's `templates/ledger.md`). It is ALWAYS written; its size
scales to the work — three lines for a one-DoD trunk, the full table for a
cross-stream trunk. There is no "lite vs full mode". Lifecycle and the reaper hook
are in `references/ledger-lifecycle.md`.

## The Loop

You MUST complete each phase before the next.

### Phase 0 — Plant the trunk
1. Run the stale-ledger sweep (`.claude/hooks/guard-ledger-freshness.sh`); reap any
   it flags before starting.
2. Write (or resume) the ledger from `templates/ledger.md`. Every DoD item must be
   **verifiable** — a command or observable, never "looks good". On resume, send a
   pre-flight subagent to reconcile the ledger against git + CI before any work.

### Phase 1 — Semantic triage (every find)
1. **Name what should be true** — the invariant/contract it violates, not the symptom.
2. **Classify the failure kind** — see `references/failure-taxonomy.md`:
   `infra-flake` · `env-limit` · `instance` · `class` · `stale-contract` · `external`.
3. **Relate to the trunk** — on-trunk (blocks DoD) or branch (off-trunk)?

### Phase 2 — Branch verdict (the tree-discipline gate)
Before acting on any branch, record ONE verdict in the ledger
(`references/branch-verdict.md`):
- `fix-now` — only if it **blocks** the trunk DoD.
- `defer` — real but non-blocking → `spawn_task` chip, logged, NOT followed now.
- `re-baseline` — the branch is bigger than the trunk → STOP, surface to the human,
  swap the trunk explicitly. Never drift silently.
- `drop` — with a reason.

### Phase 3 — Dispatch the technique
- `instance` → `superpowers:systematic-debugging` (root cause before fix).
- `class` → `big-picture-driven-development` (fix the class, enforce, sweep).
- `infra-flake`/`env-limit`/`stale-contract`/`external` → the matching mechanical fix.
Honor serena-first and the repo's hooks.

### Phase 4 — Converge
Return to the trunk after every branch. **Done only when every DoD item is checked
AND verified (run it, show evidence) and no open `fix-now`/`re-baseline` remain.**
Otherwise say so plainly; open branches become logged chips. Then reap the ledger
(delete it) and graduate its conclusion to `DECISIONS.md`.

## Red Flags — STOP, you are back in the canopy

- "I'll just quickly fix this thing I noticed" (a branch with no verdict).
- "Looks fixed / looks good" (a DoD item checked by eye, not verified).
- "Let me also refactor / improve while I'm here" (silent re-baseline).
- Three branches deep with the trunk's DoD untouched.
- Declaring "done" while a DoD checkbox is unchecked.

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "This side-bug is quick, I'll just do it" | Quick or not, log a verdict first. Unlogged branches are the tree problem. |
| "The trunk can wait, this is related" | Related ≠ the trunk. Defer or re-baseline explicitly. |
| "It looks done" | DoD is verified by a command, not by eye. |
| "A ledger is overkill here" | Then it is three lines. Always written; scales to the work. |
| "I'll clean the ledger up later" | Later never comes — that is migration-baseline-h. Reap at convergence. |

## Quick Reference

| Phase | Activity | Exit criterion |
|-------|----------|----------------|
| 0 Plant | sweep + write verifiable DoD | ledger open, DoD verifiable |
| 1 Triage | name invariant, classify kind, locate vs trunk | every find labeled |
| 2 Verdict | fix-now / defer / re-baseline / drop | no branch acted without a verdict |
| 3 Dispatch | instance→systematic-debugging, class→BPDD | right technique applied |
| 4 Converge | verify every DoD item, reap ledger | DoD checked+verified, ledger reaped |

## References
- `references/failure-taxonomy.md` — the six failure kinds + diagnostic signatures.
- `references/branch-verdict.md` — the verdict decision procedure + examples.
- `references/ledger-lifecycle.md` — ledger format, scaling, and the reaper hook.

## Related skills
- `superpowers:systematic-debugging` — instance technique (Phase 3).
- `big-picture-driven-development` — class technique (Phase 3).
- `andon-loop` — halt-on-red; this skill supplies the trunk it walks.
- `superpowers:verification-before-completion` — Phase 4 verification.
