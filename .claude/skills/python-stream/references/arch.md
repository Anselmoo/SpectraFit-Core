# Arch reference — Python project structure and architecture proposals

Self-contained essentials for Python architecture proposals. Historical
content lives in git history under
`.claude/skills/python-arch-proposer/`.

## When to use

- A directory shape change is being considered (split / merge / new
  module).
- The user pastes code asking "how should I structure this".
- A registry shape needs a refactor.

## Output shape

- A proposed directory tree.
- Per-module responsibility statement.
- Pseudo-code contracts (signatures only).
- Trade-offs vs current shape.
- Optionally, a one-shot implementation prompt.

## python-stream contract additions

1. Architecture decisions are **rare** in tier 1 (the layout is stable).
   When triggered (a refactor, a new module), the proposer drives.
2. Pydantic-first remains non-negotiable — proposals using @dataclass
   for non-leaf types will be blocked by `enforce-pydantic-only.sh` and
   `enforce-pydantic-native.sh`.
3. Registry-over-map remains non-negotiable — proposals introducing
   per-call dispatch maps will not pass the existing dispatch hook.

## Quick paths

- Top-level structure: `python/{oracles,spectrafit_core,benchmark}`.
- Registry pattern: `oracles.models.MODEL_REGISTRY`.
- Contract pattern: `oracles.contract.BenchReport` (frozen `extra="forbid"`).

## Stuck-mode entry

A re-opening arch decision is a sign of unspoken constraint — rung-2
reframe ("what assumption are we defending?") is usually the right rung.
