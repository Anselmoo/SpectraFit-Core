> Applies to: .claude/settings.json|.claude/agents/**|skills/**|.github/instructions/**

# Automation ecosystem validation

This file mandates testing and validation procedures for all hooks, agents, and skills before committing them to the spectrafit-core automation ecosystem.

## Validation protocols for hooks

**Before committing a hook to `.claude/settings.json`:**

1. **Schema validation**: Run `python .github/skills/hook-generator/scripts/validate_hook_output.py .claude/settings.json` — must exit 0
2. **JSON syntax**: Paste the hook JSON into a JSON linter (e.g. jq) — must be valid JSON
3. **Command syntax**: For `command` type hooks, test the shell command standalone (if safe) — verify exit codes and output
4. **No secrets**: Grep the hook for hardcoded tokens, API keys, passwords — must be empty result
5. **Broad matcher test**: If `matcher` is `""` or a tool name without `if` field, reject — add narrowing condition
6. **Output format**: Verify the hook returns valid JSON matching the expected schema (permissionDecision, decision, additionalContext, etc.)
7. **Routing coverage**: For `.claude/settings.json`, ensure at least one narrowed hook reinforces ai-agent-guidelines lane selection (`task-bootstrap`, `issue-debug`, `quality-evaluate`, `agent-orchestrate`) and MCP evidence-source selection (`Serena`, `GitHub MCP`, `Context7`, `fetch_webpage`) before broad exploration.
8. **Renderer boundary coverage**: For benchmark reporting surfaces, ensure at least one narrowed hook enforces this split: frontend React/TSX owns HTML/CSS/theme rendering, Python benchmark modules own data/export orchestration only.

## Validation protocols for agents

**Before committing an agent to `.claude/agents/` or `.github/agents/`:**

1. **Frontmatter validation**: Run `python .github/skills/agent-generator/scripts/validate_agent_output.py <agent.agent.md>` — must exit 0
2. **Tool list**: Verify each tool in `tools:` list has a one-line justification in the markdown body
3. **Description length**: Keep description ≤70 chars (UI truncation limit); if longer, move detail to system prompt
4. **Non-goals**: Explicitly list at least 2 things the agent must NOT do
5. **Termination criteria**: Verify completion condition is concrete (e.g. "exits when output report is complete"), not vague ("when done")
6. **System prompt**: Ensure it's under 400 words and follows the Step 3 template structure
7. **Third-person POV**: Verify description does NOT start with "I" or "You"
8. **Handoff format**: If agent delegates to sub-agents, document the input/output schema

## Validation protocols for skills

**Before committing a skill to `skills/`:**

1. **SKILL.md structure**: Must have `## Workflow`, `## Conventions`, `## Anti-patterns`, `## Output format` sections
2. **Validator test**: Run `python .github/skills/<name>/scripts/validate_<name>_output.py .github/skills/<name>/examples/` — must exit 0
3. **Validator failure test**: Create a deliberately invalid artifact (missing required field) and verify validator catches it — must exit 1
4. **Generator test**: Run `python .github/skills/<name>/scripts/generate_<name>_stub.py --name test --description "test"` — must produce valid artifact
5. **Anti-patterns**: Must list ≥3 real anti-patterns with explanations of why each is harmful
6. **Evals coverage**: `evals/evals.json` must have ≥3 scenarios: happy-path, edge-case, near-miss
7. **Examples**: Must have ≥1 complete, production-quality example artifact
8. **Requirements.txt**: Must declare all dependencies; should include `pyyaml>=6.0`
9. **Agent specs**: Verify `agents/grader.agent.md` has 5 named dimensions with pass/fail criteria

## Do not

- Do not commit a hook without running the validator
- Do not commit an agent with vague termination criteria or missing non-goals
- Do not commit a skill without testing both the validator and generator on real examples
- Do not commit a hook with broad tool approval (e.g. `matcher: "" type: command` + allow on PreToolUse Bash)
- Do not commit skill anti-patterns that are not explained
- Do not merge without checking `.claude/settings.json` is valid JSON (`jq empty .claude/settings.json`)
- Do not allow Python benchmark exporters to reintroduce template engines (`jinja2`, `Template`, inline HTML/CSS) when TSX renderer is the active report frontend.
