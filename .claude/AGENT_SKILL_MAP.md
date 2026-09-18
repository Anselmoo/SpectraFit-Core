# Agent → Skill mapping

Generated: 2026-05-09. Regenerated: 2026-07-24 (the 2026-05-09 table pre-dated the skill-catalog
consolidation from 28 specialists to 9 consolidated skills — every mapped skill path it named had
gone missing; `python3 .claude/scripts/validate_agent_skill_map.py` now passes clean).

This file defines the canonical mapping from in-repo agents (`.claude/agents`) to
the corresponding skill documentation folders under `.claude/skills`, where one exists. Not every
agent shadows a skill — several of the current agents are standalone cross-cutting utilities
(CI/pipeline triage, generic research) with no single-skill owner, and are marked as such below
rather than forced into an inaccurate mapping.

Keep this file updated when adding, renaming, or removing agents or skills. If
an agent maps to an existing skill that covers the same responsibilities, the
canonical skill path is listed below.

| Agent (`.claude/agents`) | Canonical Skill Path (`.claude/skills/`) | Notes |
|---|---:|---|
| schema-migration-auditor | `.claude/skills/python-stream/` | Pydantic↔serde schema drift audit; `python-stream` absorbed the old `spectrafit-schemas` specialist this agent used to map to. |
| ci-failure-router | (none) | Cross-cutting CI-log classifier; routes to whichever specialist ADR/agent matches the failure mode, not owned by one skill. |
| cloud-batch-analyzer | (none) | Background pytest/poe job + `.pytest_logs`/`feedback.json` analysis utility; cross-cutting, not skill-specific. |
| pipeline-monitor | (none) | Polls a named GitLab CI pipeline until terminal and reports; cross-cutting CI utility. |
| universal-explore | (none) | Read-only discovery/research helper for the planning suite; used across all streams, not owned by one. |
| validation-reviewer | (none) | Reviews handoff readiness before approval/delegation; cross-cutting review utility. |

How to maintain
- When you add a new agent under `.claude/agents`, add a corresponding entry in
  this file. If a full skill already exists that covers the agent, point the
  mapping to that skill folder. If the agent is a cross-cutting utility with no
  single-skill owner, mark it `(none)` explicitly rather than omitting it —
  `validate_agent_skill_map.py` treats every agent as required to appear in the
  table (with a skill or an explicit none), and treats every listed skill path
  as required to exist on disk.

Usage by automation
- `.claude/scripts/validate_agent_skill_map.py` parses this table and checks it
  against the real `.claude/agents/*.agent.md` files and `.claude/skills/*/`
  directories, failing (exit 1) if any agent is missing or any mapped skill
  path doesn't exist. Run it after any agent/skill rename or addition.
