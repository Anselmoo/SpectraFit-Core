# Agent → Skill mapping

Generated: 2026-05-09

This file defines the canonical mapping from in-repo agents (`.claude/agents`) to
the corresponding skill documentation folders under `.claude/skills`.

Keep this file updated when adding, renaming, or removing agents or skills. If
an agent maps to an existing skill that covers the same responsibilities, the
canonical skill path is listed below. If no skill existed previously, a small
SKILL.md stub was created to improve discoverability.

| Agent (`.claude/agents`) | Canonical Skill Path (`.claude/skills/`) | Notes |
|---|---:|---|
| spectrafit-tdd | `.claude/skills/spectrafit-tdd/` | existing |
| spectrafit-benchmark | `.claude/skills/spectrafit-benchmark/` | existing |
| spectrafit-rust-models | `.claude/skills/rust-model-scaffolder/` | maps to existing rust-model-scaffolder skill |
| spectrafit-dag-engine | `.claude/skills/dag-validator/` | existing |
| spectrafit-tests | `.claude/skills/spectrafit-tests/` | existing |
| spectrafit-performance-recovery | `.claude/skills/spectrafit-benchmark/` | mapped to existing benchmark skill |
| spectrafit-bindings | `.claude/skills/spectrafit-bindings/` | existing (bindings routing & diagnostics) |
| spectrafit-schemas | `.claude/skills/spectrafit-schemas/` | existing (schema/authors audit) |
| spectrafit-scaffold | `.claude/skills/spectrafit-scaffold/` | existing (scaffold & repo tasks) |
| spectrafit-devboard | `.claude/skills/spectrafit-devboard/` | existing (devboard / dashboards) |
| spectrafit-solver | `.claude/skills/spectrafit-solver/` | existing (solver investigations) |
| spectrafit-eval-board | `.claude/skills/spectrafit-benchmark/` | merged into benchmark governance/evidence workflow |
| schema-migration-auditor | `.claude/skills/spectrafit-schemas/` | merged into schemas audit workflow |

How to maintain
- When you add a new agent under `.claude/agents`, add a corresponding entry in
  this file. If a full skill already exists that covers the agent, point the
  mapping to that skill folder. Create a new skill folder only when no existing
  canonical skill can own that responsibility without duplication.

Usage by automation
- CI hooks and routing agents should consult this file (or the canonical SKILL
  frontmatter) when resolving which skill to consult or display for a given
  agent name. If you rename skills or agents, update this file atomically with
  the rename to avoid transient routing failures.
