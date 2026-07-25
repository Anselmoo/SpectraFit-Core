---
type: gap
title: "[Medium] docs-drift: .claude/AGENT_SKILL_MAP.md is a pre-consolidation relic"
description: ".claude/AGENT_SKILL_MAP.md — whole file describes 13 agents/skills that no longer exist; the description of it in docs/methodology.md is also stale"
tags: ["kind:bug", "status:closed", "domain:docs-drift", "severity:medium"]
timestamp: "2026-07-24T00:00:00Z"
---

## Gap detail

- Stage: [[stages/unattributed]]
- On constraint: false
- Location: `.claude/AGENT_SKILL_MAP.md` (whole file, generated 2026-05-09, pre-dates the
  skill-catalog consolidation), plus its own validator `.claude/scripts/validate_agent_skill_map.py`
- Finding domain: docs-drift
- Suggested fix / explanation: the file maps 13 pre-consolidation agent names to 13 skill paths,
  none of which exist anymore; the 5 current non-`schema-migration-auditor` agents have no entry
  at all.
- Resolved by: [[evidence/unattributed-methodology-ev1]]
- Proposal: Ran `.claude/scripts/validate_agent_skill_map.py` first (read-only) — confirmed it
  fails hard: 5 current agents missing from the map, all 13 mapped skill paths absent,
  12 mapping entries for agents that no longer exist. Rewrote the file: the only real 1:1
  mapping that survives consolidation is `schema-migration-auditor` → `python-stream` (the
  `spectrafit-schemas` skill it used to map to was absorbed into `python-stream`). The other 5
  current agents (`ci-failure-router`, `cloud-batch-analyzer`, `pipeline-monitor`,
  `universal-explore`, `validation-reviewer`) are genuinely cross-cutting utility agents with no
  single-skill owner — rather than inventing a false mapping to make the table "complete," added
  an explicit `(none)` sentinel value and taught the validator script to treat it as a legitimate
  "no skill" answer (was previously unsupported — the validator would have flagged `(none)` as a
  missing skill directory). Re-ran the validator after the rewrite: passes clean
  (`✓ Agent → Skill mapping is consistent`). Also fixed `docs/methodology.md`'s description of
  this file (§5), which cited a fictional "spectrafit-solver agent"/"spectrafit-solver skill"
  pair — see [[unattributed-16]]. Strategy: a (the validator script itself is the ground-truth
  check — ran it before and after). Blast radius: local+reversible (the validator is a standalone
  manual script, not wired into any hook/CI — confirmed via grep).
