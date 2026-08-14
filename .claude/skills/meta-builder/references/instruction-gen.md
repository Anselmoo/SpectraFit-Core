# Instruction-gen reference — workspace & file-level instructions

Self-contained essentials. Historical content under
`.claude/skills/instruction-generator/` is in git history.

## When to write an instruction file

An instruction file is **always-on** for matching files / agents.
Use instructions for:

- Team coding conventions (e.g. "always use Pydantic BaseModel").
- Per-file-pattern style (a TSX-only rule).
- Agent-scope rules (an `AGENTS.md` for a sub-agent).
- Copilot-friendly `copilot-instructions.md`.

If the rule is **enforceable** (binary, deterministic), prefer a hook
(see `hook-gen.md`). If the rule is **guidance** (judgment-based),
the instruction is the right primitive.

## Shape

| File | Scope |
|------|-------|
| `CLAUDE.md` | Repo-wide always-on for Claude Code. |
| `AGENTS.md` | Sub-agent specific, in the agent's directory. |
| `copilot-instructions.md` | GitHub Copilot scope. |
| `*.instructions.md` with `applyTo: <glob>` | File-pattern-scoped. |

The `applyTo` frontmatter restricts the instruction to matching files
(via glob), so e.g. a TSX-only style rule only activates on TSX edits.

## Anti-pattern

Don't put domain knowledge in instructions. Domain knowledge belongs
in a skill (it's invoked when relevant). Instructions are the
*conventions* layer — short, always-on, file-pattern-scoped.

## Stuck-mode entry

An instruction that gets ignored is either too long (gets buried in
context) or in conflict with another instruction. Curiosity sub-cycle:
read every instruction file that applies to the path in question and
look for contradictions.
