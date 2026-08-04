---
name: meta-builder
description: |
  Generator of skills, agents, hooks, prompts, and instructions for the
  universal-creator framework. Used when the catalog needs to grow.
  Absorbs skill-generator, agent-generator, hook-generator,
  prompt-generator, and instruction-generator — their specialist
  content lives in references/. Use when the user asks to scaffold a
  new skill, write a sub-agent definition, design a hook configuration,
  draft a one-shot prompt, or create workspace instruction files.
  Composes with superpowers:writing-skills and superpowers:writing-plans.
license: MIT
---

# meta-builder

The catalog's own catalog-builder. Builds new artifacts under
`.claude/skills/`, `.claude/agents/`, `.claude/hooks/`, prompts, and
instruction files.

## Anchors

**CLAUDE.md sections** (read before acting):
- *Tooling: use MCP servers for discovery* — the framework the new
  artifact must compose with.

**Hooks**: none directly fire on this skill's work (artifact generation
is outside the spectrafit code surface).

## Serena first?

`serena_first: false` — meta-builder writes new files; it doesn't
usually edit symbols. (When it edits a SKILL.md or hook to extend, it
DOES use serena.)

## Decision: which sub-document?

| Subject | Reference |
|---------|-----------|
| New skill directory (SKILL.md + references + scripts) | `references/skill-gen.md` |
| New sub-agent definition (.agent.md, tool-allow/deny matrix) | `references/agent-gen.md` |
| New hook (PreToolUse / PostToolUse / Stop / etc.) | `references/hook-gen.md` |
| One-shot prompt or .prompt.md file | `references/prompt-gen.md` |
| Workspace / file-level instruction (copilot-instructions.md, AGENTS.md, *.instructions.md) | `references/instruction-gen.md` |

## Composes with

1. `superpowers:writing-skills` — the canonical framework for skill
   shape, evaluation, and verification.
2. `superpowers:writing-plans` — for any multi-step generation task
   (new skill scaffolds typically benefit).
3. `superpowers:brainstorming` — when the artifact's purpose isn't yet
   clear.

## Anti-pattern: don't grow the catalog

Every meta-builder use should ask: **could this be a hook or a
reference instead of a new skill?** Hooks are deterministic; references
live inside an existing skill. New skills cost catalog selection time
(the original problem driving this consolidation). The bar to add a
*new top-level skill* is high — the artifact must have a distinct
trigger language no existing skill claims.

The to_hooks list in `INDEX.yaml` (currently `docstring-enforcer`)
shows the right primitive choice when behavior is deterministic.

## Three-pillar reporting

The pillars don't directly apply — meta-builder writes catalog code,
not science code. The closest analog: keep the catalog small (anti-
PERF-bloat), keep the schema validatable (RIGOR), keep the catalog
discoverable (PRESENTATION).
