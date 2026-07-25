---
type: gap
title: "[High×5/Medium×2] docs-drift: docs/methodology.md inventory counts, test surfaces, which-skill-when matrix"
description: "docs/methodology.md — skill count (21→9), agent count (13→6), MCP server count/names, lifecycle hook count, Rust/Python/oracles test-surface table, lint-gate mirror description, which-skill-when routing matrix (all citing pre-consolidation names), AGENT_SKILL_MAP.md description"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:high"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: true
- Location: `docs/methodology.md` (multiple sections: intro §, per-layer test-surface table,
  pre-push lint gate description, §4 which-skill-when matrix, §5 agent/skill description)
- Finding domain: docs-drift (9 findings, all concentrated in one file, all traced by a dedicated
  research agent before any fix was applied)
- Suggested fix / explanation: multiple counts/paths/routing-table entries drifted from reality —
  most from the skill-catalog consolidation (28→9 skills) that predates this doc's last edit.
- Resolved by: [[evidence/unattributed-methodology-ev1]]
- Proposal: Dispatched a dedicated read-only research agent first to establish ground truth for
  all 15 unattributed docs-drift items before writing any fix (avoiding guessed numbers). For this
  file specifically: (1) intro paragraph — 21→9 skills, 13→6 agents, corrected the MCP server
  list (5 project-scope in .mcp.json are rrt/analyzer/spectrafit-reports/zen-of-languages/
  ai-agent-guidelines, NOT serena/context7/github — those are user-scope; 8 total), 10→20
  distinct hook scripts across 4 lifecycle events (verified by parsing .claude/settings.json
  live). (2) test-surface table — Rust command corrected (`--tests` was dropped, silently skipped
  52 `#[cfg(test)]` lib blocks), the `spectrafit-core` per-package 75% floor was removed
  2026-06-15 (only `spectrafit-solver`'s remains), Python test paths corrected from stale flat
  `tests/test_fit.py` to the real `tests/unit/spectrafit_core/`, and `python/benchmark`→
  `python/oracles/engine.py` (F13 rename). (3) lint-gate description — added the missing
  `ruff format --check .` step and fixed `python/benchmark`→`python/oracles` path (the actual
  `pyproject.toml` `lint_ci` poe task was already correct; only this doc's paraphrase had drifted).
  (4) which-skill-when matrix — full rewrite: all 14 rows named retired pre-consolidation skill
  names (`rust-model-scaffolder`, `spectrafit-tdd`, `spectrafit-solver`, `spectrafit-bindings`,
  `spectrafit-schemas`, `spectrafit-benchmark`, `benchmark-scenario-generator`,
  `spectrafit-devboard`, `dag-validator`, `cupertino-council`, `boring-to-brilliant`,
  `one-more-thing`, `evolutionary-platform-thinking`, `skill-generator`/`agent-generator`/
  `hook-generator`/`prompt-generator`, `find-docs`/`context7-mcp`) — consolidated into 10 rows
  routing to the 9 current skills (per CLAUDE.md's own absorb table) plus a note that `context7`
  is an MCP tool, not a skill. (5) AGENT_SKILL_MAP.md description — updated to name a real current
  agent (`schema-migration-auditor`) instead of a fictional "spectrafit-solver agent," and to
  note most current agents are cross-cutting utilities with no skill (see [[unattributed-17]]).
  Strategy: e (structural/connectivity — every claim checked against live repo state: parsed
  INDEX.yaml, counted `.mcp.json`/`.claude/agents/`/`.claude/settings.json` directly, read
  `.gitlab/30-test.yml`/`.gitlab/20-lint.yml`/`pyproject.toml`). Blast radius: local+reversible
  (docs-only).
