# Migration: `.github` → `.claude`

This document records the consolidation of repository automation that previously
lived under `.github/` into `.claude/`, and the introduction of a new blocking
performance/accuracy enforcement hook agent.

> Scope note: GitHub Actions **workflows** (`.github/workflows/*.yml`) are **not**
> moved — GitHub requires them to live under `.github/workflows/`. Only the
> Copilot custom instructions, the agent/skill map, the cloud-batch hook
> scripts, and the hook registration move.

## Why

All agentic automation in this repo is driven through Claude (sub-agents, skills,
hooks, instruction files). Keeping a parallel copy of the same automation under
`.github/` (originally for GitHub Copilot custom instructions and VS Code-native
hook discovery) caused **two sources of truth** for the same conventions and
**double-registration** of the cloud-batch hook. Consolidating everything under
`.claude/` gives a single, discoverable home for instructions, agents, skills,
hooks, and the agent↔skill map, and lets the Claude hook runner
(`.claude/hooks/run-hook.sh`) own execution end to end.

## What moved

| Old `.github` path | New `.claude` path | Notes |
| --- | --- | --- |
| `.github/instructions/*.instructions.md` (Copilot custom-instruction files) | `.claude/instructions/*.md` | Originals **deleted**. Disables GitHub Copilot custom instructions (see consequence below). |
| `.github/AGENT_SKILL_MAP.md` | `.claude/AGENT_SKILL_MAP.md` | Agent↔skill routing map. |
| `.github/scripts/cloud_batch_hook.py` | `.claude/scripts/cloud_batch_hook.py` | Cloud-batch policy/summary hook logic. |
| `.github/scripts/validate_agent_skill_map.py` | `.claude/scripts/validate_agent_skill_map.py` | Validates `AGENT_SKILL_MAP.md` against the agents on disk. |
| `.github/hooks/cloud-batch-observer.json` | `.claude/hooks/cloud-batch-observer.json` | Hook registration (`SessionStart` / `PreToolUse` / `PostToolUse`). |

`.github/workflows/*.yml` stays in place (GitHub requirement).

## Consequence: GitHub Copilot custom instructions are disabled

Deleting `.github/instructions/*.instructions.md` removes the files GitHub Copilot
reads for custom instructions. After this migration, **Copilot no longer applies
the repo's custom instructions** — only Claude consumes the equivalent files at
`.claude/instructions/*.md`. This trade-off was accepted: the repo's automation is
Claude-driven, and a duplicated instruction set under `.github/` was a maintenance
liability.

### How to restore Copilot custom instructions (if needed)

Copilot reads from `.github/`, so to re-enable it without losing the Claude copies:

1. Recreate the directory: `mkdir -p .github/instructions`.
2. Copy the migrated files back, restoring the Copilot naming convention:
   for each `.claude/instructions/<name>.md`, write
   `.github/instructions/<name>.instructions.md` (Copilot expects the
   `.instructions.md` suffix and an `applyTo:` front-matter glob).
3. Keep both copies in sync going forward, or treat `.claude/instructions/` as the
   source of truth and regenerate the `.github/` copies on change.

There is no need to restore `.github/workflows/` — it never moved.

## Repointed references

The following files were updated to point at the new `.claude/` locations:

| File | Old reference | New reference |
| --- | --- | --- |
| `.github/workflows/docstring-check.yml` (CI) | `python .github/skills/.../validate_*.py` validator invocations | `python .claude/skills/.../validate_*.py` validator invocations |
| `.claude/hooks/cloud-batch-observer.sh` | `python3 .github/scripts/cloud_batch_hook.py` | `python3 .claude/scripts/cloud_batch_hook.py` |
| `docs/validators/integration.md` | `.github/hooks/cloud-batch-observer.json`, `.github/scripts/cloud_batch_hook.py` | `.claude/hooks/cloud-batch-observer.json`, `.claude/scripts/cloud_batch_hook.py` |

The hook registration (`.claude/hooks/cloud-batch-observer.json`) already routes
execution through `.claude/hooks/run-hook.sh` → `.claude/hooks/cloud-batch-observer.sh`,
so only the script path inside the observer needed repointing.

## New perf/accuracy enforcement hook agent

A new pre-merge hook, `.claude/hooks/enforce-perf-accuracy.sh`, is added as a
"hook agent" that **blocks** merges when spectrafit regresses against lmfit. It is
motivated by `six_peaks_nls` measuring **2.53× slower** than lmfit (52.3 ms vs
20.7 ms) — a regression the existing baseline checker
(`.claude/hooks/pre-merge-perf-baseline.sh`) did not catch as a hard block.

A companion `hook-orchestrator` agent coordinates which enforcement hooks run for a
given change set.

### The 2× rule

The hook reads the latest benchmark `results.json` and blocks if **either** of the
following holds for any case:

- **Performance**: spectrafit `median_ms` > **2×** lmfit `median_ms`.
- **Accuracy**: spectrafit fit accuracy (e.g. chi² / r²) regresses relative to the
  recorded baseline.

### Exit-2 contract

The hook follows the repo's PreToolUse/pre-merge exit-code convention (see the
[2026-06-01] ADR in `DECISIONS.md` on guard-hook exit codes):

- **exit 0** — no regression; the change proceeds.
- **exit 2** — a perf or accuracy regression was detected; the hook prints the
  offending case(s) and the measured ratio to **stderr** and **blocks** the call.

(Exit 1 is reserved for the hook failing to run, e.g. missing benchmark evidence.)

### How to run it manually

```bash
bash .claude/hooks/enforce-perf-accuracy.sh
echo "exit code: $?"   # 0 = pass, 2 = blocked
```

Run a fresh benchmark first so the hook has current evidence to compare, then
inspect the printed case/ratio on a block.

### Which agent to invoke on a block

When `enforce-perf-accuracy.sh` exits 2 on a **performance** regression, hand the
case off to the **`spectrafit-performance-recovery`** agent
(`.claude/agents/spectrafit-performance-recovery.agent.md`), which recovers
benchmark performance when spectrafit trails lmfit. For an **accuracy** regression,
route through the TDD dispatcher (`spectrafit-tdd`) to the appropriate solver/model
specialist.
