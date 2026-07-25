---
type: evidence
title: "docs/methodology.md batch + related docs-drift fixes verified (9/9 areas)"
description: "Independent verification confirms all inventory counts (9 skills, 6 agents, 8 MCP servers, 20 hook scripts/4 events), the Rust/Python/oracles test-surface table, the lint-gate description, the which-skill-when matrix rewrite, AGENT_SKILL_MAP.md's full rewrite (validator passes clean), the .toFixed() location fix, the alpha->beta correction, and the spc-bench date correction (found and fixed one additional missed instance)."
resource: "docs/methodology.md, .claude/AGENT_SKILL_MAP.md, .claude/scripts/validate_agent_skill_map.py, CLAUDE.md, .claude/skills/web-stream/references/devboard.md, LIMITATIONS.md, CONTRIBUTING.md, tests/meta/test_console_scripts.py, tests/meta/test_wheel_scope.py, docs/whitepaper_methodology.md"
tags: ["strategy:e", "tier:2"]
timestamp: "2026-07-24T00:00:00Z"
---

## Evidence detail

- Wire: gaps unattributed-16, 17, 18, 19, 20, 21, 22
- Verdict: green (all 9 verification areas)
- Strategy detail: e (structural/connectivity) — independent reviewer re-derived every count and
  claim from scratch: counted skill directories (9, matching INDEX.yaml), agent files (6), .mcp.json
  keys (5 project-scope, cross-checked against CLAUDE.md's own accurate statement), parsed
  settings.json's hooks block programmatically (20 distinct scripts, 4 lifecycle events). Read
  .gitlab/30-test.yml directly to confirm the --tests-drop rationale and the 2026-06-15
  per-package-floor-removal claim. Read .gitlab/20-lint.yml and pyproject.toml's lint_ci task to
  confirm the lint-gate description. Confirmed every retired skill name in the old which-skill-when
  matrix is absent as a directory and every replacement name is present, cross-checked against
  CLAUDE.md's absorb table. Ran validate_agent_skill_map.py live (exit 0) and sandbox-tested that
  the (none) sentinel doesn't weaken the check for a genuinely-wrong path. Confirmed
  registry.tsx has no .toFixed() and format.ts/fmtP()+tickLabels are real. Confirmed
  pyproject.toml/CHANGELOG.md agree on beta status. Ran git log --grep="spc-bench" --all
  independently to confirm the true commit date (2026-06-23) and confirmed the correction didn't
  introduce a different wrong date. Found ONE gap in my own fix pass — tests/meta/
  test_wheel_scope.py:26 also had the stale date, missed because it wasn't swept alongside its
  sibling test_console_scripts.py — fixed and re-verified after the report landed (1 test passed).
  Confirmed the whitepaper_methodology.md caveat note is honest (the still-unverified
  `_MODEL_MAP` claim it flags is genuinely still present, untouched, exactly as disclosed).
- Non-overridable: false
