#!/usr/bin/env bash
set -euo pipefail

# suggest-ai-agent-guidelines
# ---------------------------
# PreToolUse hook on Agent / EnterPlanMode / TaskCreate. Designed as a
# *thinking warning*, not a soft nudge: when a planning surface opens with
# real strategic weight, it routes the agent to the matching
# `mcp__ai-agent-guidelines__<tool>` sub-tool BEFORE the planning subagent
# spawns or plan mode commits — because lazy planning is paid back later
# in review-cycle cost.
#
# Hybrid enforcement (AAG_FIRST_MODE):
#   warn  (default) — stderr only, never blocks.
#   block           — exit 2 only when the matched lane is one of the
#                     high-leverage ones (enterprise-strategy, system-design,
#                     physics-analysis, policy-govern). Other lanes still
#                     warn. The idea is to hard-stop the cases where
#                     skipping AAG is most expensive, without hampering
#                     narrow refactors.
#   off             — silent.
#
# Anti-over-engineering: the hook intentionally does NOT fire when scope
# looks narrow — single-file mechanical edit, short prompt, rename/typo/
# lint/format/bump keywords. The principle (from CLAUDE.md): enforcing
# AAG on a clear, narrow road map is over-engineering; enforcing it on
# vague multi-track planning prevents lazy thinking from compounding.

_tmpf=$(mktemp)
trap 'rm -f "$_tmpf"' EXIT
cat > "$_tmpf"

HOOK_STDIN_FILE="$_tmpf" python3 - <<'PYEOF'
from __future__ import annotations

import json
import os
import re
import sys

MODE = os.environ.get("AAG_FIRST_MODE", "warn")
if MODE == "off":
    raise SystemExit(0)

# ---------------------------------------------------------------------------
# Intent → ai-agent-guidelines tool routing table.
# Keys: list of keywords (lower-case, whole-word). Value: (tool, lane,
# blocking?). Lanes marked blocking=True will exit 2 when MODE=="block".
# Ordering matters: the first match wins, so put higher-priority lanes
# first.
# ---------------------------------------------------------------------------
_ROUTES: list[tuple[list[str], str, str, bool]] = [
    # lane                                          tool                          blocking
    (["enterprise", "transformation", "executive", "roadmap-enterprise",
      "c-suite", "staff-engineering"],              "enterprise-strategy",        "strategy",     True),
    (["governance", "policy", "compliance", "audit-trail", "regulated"],
                                                     "policy-govern",              "governance",   True),
    (["architecture", "system-design", "topology", "trust-boundary",
      "layered", "operating-model"],                 "system-design",              "architecture", True),
    # Physics-ANALYSIS lane: keyed on analysis INTENT, not bare model
    # vocabulary. In a fitting codebase "gaussian"/"kernel"/"jacobian"/
    # "varpro"/"voigt" are everyday code nouns that show up in narrow edits;
    # keying a *blocking* lane on them hard-stopped every model-touching
    # subagent/task (observed: SP-2 forced all model work inline). Require an
    # analysis phrase instead — genuinely strategic physics work carries
    # design/strategy verbs and routes via the architecture/strategy lanes.
    (["physics-analysis", "lineshape-derivation", "solver-math",
      "numerical-stability", "convergence-study", "ill-conditioned",
      "closed-form-jacobian", "faddeeva"],           "physics-analysis",           "physics",      True),
    (["strategy", "scope", "phases", "milestone", "bet", "tradeoff",
      "roadmap"],                                    "strategy-plan",              "strategy",     False),
    (["resilience", "reliability", "failure-mode", "slo", "rollback",
      "circuit-breaker", "dead-letter"],             "fault-resilience",           "reliability",  False),
    (["prompt-engineering", "rewrite-prompt", "instruction-rewrite"],
                                                     "prompt-engineering",         "prompts",      False),
    (["docs-generate", "readme", "changelog-draft", "documentation-draft"],
                                                     "docs-generate",              "docs",         False),
    (["research", "evidence", "literature", "sources", "survey"],
                                                     "evidence-research",          "research",     False),
    (["refactor", "simplify", "cleanup"],            "code-refactor",              "refactor",     False),
    (["review", "audit", "second-opinion", "distinguished-engineer"],
                                                     "code-review",                "review",       False),
    (["debug", "incident", "regression", "issue-triage"],
                                                     "issue-debug",                "debug",        False),
    (["orchestrate", "agent-topology", "dispatch", "meta-routing"],
                                                     "agent-orchestrate",          "orchestration", False),
    (["onboard", "scaffold", "bootstrap"],           "project-onboard",            "onboarding",   False),
    (["evaluate", "benchmark", "eval-suite", "quality-gate",
      "regression-gate"],                            "quality-evaluate",           "evaluation",   False),
    (["test-verify", "verify-parity", "parity-test"],
                                                     "test-verify",                "verification", False),
    (["visualize", "diagram", "graph-render"],       "graph-visualize",            "visualization", False),
    (["feature-implement", "build-feature"],         "feature-implement",          "feature-build", False),
    (["model-discover", "version-pin", "model-registry"],
                                                     "model-discover",             "model-ops",    False),
]

# Narrow-scope signals: when these dominate the input, the hook stays
# silent — enforcing AAG would be over-engineering for clearly bounded
# work.
_NARROW_KEYWORDS = re.compile(
    r"\b(rename|typo|lint|format|bump|pin\s+version|edit\s+line|"
    r"single[- ]file|delete\s+file|move\s+file|copy\s+file|"
    r"fix\s+import|fix\s+lint|fix\s+typo|add\s+test\s+for|"
    r"update\s+changelog|update\s+readme|update\s+comment)\b",
    re.IGNORECASE,
)

# Strategic-weight signals: when these appear, even if the prompt is
# short, the hook still fires (these are non-negotiable high-leverage
# planning surfaces).
# NOTE: bare model-domain nouns ("physics", "kernel", "solver-math") are
# deliberately NOT here — they over-suppressed narrowness, forcing every
# model-touching narrow edit to be treated as high-leverage and (with the
# physics lane) blocked. Strategic weight is signalled by planning verbs
# (architect, roadmap, migration, cross-crate), not domain vocabulary.
_HIGH_LEVERAGE_KEYWORDS = re.compile(
    r"\b(architect|architecture|enterprise|governance|policy|"
    r"roadmap|migration|cross-crate|"
    r"multi-track|value\s+stream|end-to-end)\b",
    re.IGNORECASE,
)


def _score(text: str, keywords: list[str]) -> int:
    score = 0
    lower = text.lower()
    for kw in keywords:
        # whole-word match, allowing -/_ inside the keyword
        pat = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
        score += len(pat.findall(lower))
    return score


def _classify(text: str) -> tuple[str, str, bool, list[str]] | None:
    """Return (tool_name, lane, blocking, matched_keywords) or None."""
    best: tuple[int, str, str, bool, list[str]] | None = None
    for keywords, tool, lane, blocking in _ROUTES:
        s = _score(text, keywords)
        if s == 0:
            continue
        matched = [kw for kw in keywords if re.search(
            r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE)]
        if best is None or s > best[0]:
            best = (s, tool, lane, blocking, matched)
    if best is None:
        return None
    _, tool, lane, blocking, matched = best
    return tool, lane, blocking, matched


def _is_narrow(text: str) -> bool:
    """Suppress hook when scope is clearly narrow AND no strategic-weight
    keywords override that judgement."""
    if _HIGH_LEVERAGE_KEYWORDS.search(text):
        return False
    if len(text.strip()) < 100:
        # short prompt + no strategic keywords → narrow
        return True
    if _NARROW_KEYWORDS.search(text):
        # if the prompt names a mechanical action, treat as narrow even if
        # it's also long
        narrow_hits = len(_NARROW_KEYWORDS.findall(text))
        strategic_hits = len(_HIGH_LEVERAGE_KEYWORDS.findall(text))
        return narrow_hits > strategic_hits
    return False


# ---------------------------------------------------------------------------
# Read the tool call payload.
# ---------------------------------------------------------------------------
with open(os.environ["HOOK_STDIN_FILE"], encoding="utf-8") as fh:
    raw = fh.read().strip()
if not raw:
    raise SystemExit(0)

try:
    payload = json.loads(raw)
except json.JSONDecodeError:
    raise SystemExit(0)

if not isinstance(payload, dict):
    raise SystemExit(0)

tool_name = payload.get("tool_name", "")
tool_input = payload.get("tool_input", {}) if isinstance(
    payload.get("tool_input", {}), dict) else {}

# Build the searchable text per surface.
text = ""
surface = ""
extra: str = ""

if tool_name == "Agent":
    surface = "Agent dispatch"
    subagent_type = str(tool_input.get("subagent_type", ""))
    prompt = str(tool_input.get("prompt", ""))
    description = str(tool_input.get("description", ""))
    text = " ".join([subagent_type, description, prompt])
    extra = f"subagent_type={subagent_type or '(default)'}"
    # Planning-lane subagents always count as strategic-weight, even if
    # the prompt is terse.
    _PLAN_SUBAGENTS = {
        "Plan", "universal-plan", "feature-dev:code-architect",
        "prompt-strategist", "primitive-selector", "validation-reviewer",
        "universal-explore", "schema-migration-auditor",
    }
    if subagent_type in _PLAN_SUBAGENTS:
        # force strategic classification: prepend a strong keyword
        text = "architecture strategy " + text

elif tool_name == "EnterPlanMode":
    surface = "EnterPlanMode"
    plan = str(tool_input.get("plan", ""))
    text = "architecture strategy " + plan  # plan mode = always strategic
    extra = "plan mode opening"

elif tool_name == "TaskCreate":
    surface = "TaskCreate"
    subject = str(tool_input.get("subject", ""))
    description = str(tool_input.get("description", ""))
    text = subject + "\n" + description
    extra = f"subject={subject[:60]!r}"
    # We can only see one task here. The "≥4 items" guard from the design
    # is left to the conductor / caller; this hook fires on the single
    # task content. Anti-over-engineering still applies via _is_narrow.

else:
    raise SystemExit(0)  # not a surface we monitor

# ---------------------------------------------------------------------------
# Decide whether to fire.
# ---------------------------------------------------------------------------
if _is_narrow(text):
    # Suppressed: the road map is clearly narrow; enforcing AAG would be
    # over-engineering.
    raise SystemExit(0)

classification = _classify(text)
if classification is None:
    # No keyword match → no clear lane; treat as narrow and exit silently
    # (avoids spamming on generic prose).
    raise SystemExit(0)

tool, lane, blocking, matched = classification

# ---------------------------------------------------------------------------
# Compose the *thinking warning*.
# ---------------------------------------------------------------------------
matched_str = ", ".join(matched[:5])
preview = text.strip().splitlines()[0][:140] if text.strip() else "(empty)"

msg = (
    f"[ai-agent-first] {surface} on lane '{lane}' ({extra}).\n"
    f"  preview: {preview!r}\n"
    f"  matched keywords: {matched_str}\n"
    f"\n"
    f"PAUSE & THINK before continuing:\n"
    f"  • Is the road map already clear and the scope narrow? Then this\n"
    f"    hook is over-engineering — proceed and don't call AAG.\n"
    f"  • Is the scope open-ended, multi-track, or strategy-shaped? Then\n"
    f"    skipping AAG now costs MORE later in review/redo cycles than the\n"
    f"    one MCP call costs now. Route the planning through AAG FIRST.\n"
    f"\n"
    f"Suggested tool for this lane:\n"
    f"  mcp__ai-agent-guidelines__{tool}\n"
    f"\n"
    f"Anti-pattern this hook prevents: launching a planning subagent / plan\n"
    f"mode / multi-step task list without first using the structured\n"
    f"workflow (vision → capability → strategy → architecture → governance\n"
    f"→ executive brief) that ai-agent-guidelines provides. The cost of\n"
    f"that omission is paid in later review cycles.\n"
    f"\n"
    f"AAG_FIRST_MODE=warn (default) | block (hard-stop on strategic lanes) "
    f"| off (silent)."
)

if MODE == "block" and blocking:
    print(msg, file=sys.stderr)
    raise SystemExit(2)

print(msg, file=sys.stderr)
raise SystemExit(0)
PYEOF
