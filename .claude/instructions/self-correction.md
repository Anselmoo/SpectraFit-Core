> Applies to: **

# Instruction self-correction

After completing any task, check whether the session revealed a gap in the
existing workspace instructions. If yes, update instructions before closing.

## Rules

- After completing a task that required a post-fix (correcting previously written
  code or tests), add an imperative rule to the relevant instruction file that
  would have prevented the mistake.
- When a new pattern, workaround, or convention is discovered mid-session, capture
  it in `.github/instructions/<domain>.instructions.md` before the session ends.
- When editing an instruction file, check for contradictions with other rules in
  the same file and with `.github/copilot-instructions.md` before saving.
- Prefer adding to an existing scoped instruction file over adding to
  `copilot-instructions.md` — the scoped file loads only when relevant.

## Do not

- Leave a repeated post-fix pattern undocumented after fixing it.
- Add time-sensitive phrasing to any instruction file ("until date X", "currently
  in beta", "as of version Y").
- Duplicate a rule that already exists in `copilot-instructions.md` or another
  instructions file in scope.

---

# Hook self-correction

When adding or modifying hooks in `.claude/settings.json`, verify correctness before saving.

## Rules for hooks

- Every `PreToolUse` hook with broad matcher must use `if` field to narrow scope. Never auto-approve all Bash commands.
- Every hook `command` type must return valid JSON to stdout (test with `echo '{}' | ./hook.sh`).
- If a hook's scope is project-specific, place it in `.claude/settings.json` (project). If workspace-wide, use `~/.claude/settings.json` (user).
- Every `PostToolUse` hook with `async: true` must document side-effects and timeout expectations.
- Hook timeouts must be set based on operation: 30s for simple commands, 60s for DAG validation, 120s for complex checks.
- For hooks that call external scripts (e.g. `check_crate_dag.sh`), verify the script is executable and error-handling is robust.
- Hook descriptions must be clear, actionable, and document the rule being enforced (not just "validate something").

## Do not for hooks

- Do not hardcode secrets or tokens in hook command strings. Use environment variables.
- Do not create hooks that block all invocations of a tool. Always use conditional logic.
- Do not leave a hook without a clear description of what rule it enforces.
- Do not mix multiple concerns in a single hook. Separate hooks by event and concern.

---

# Agent self-correction

When adding or modifying agents in `.claude/agents/`, verify scope and tool balance.

## Rules for agents

- Every agent's `tools` list must be explicit (no empty lists or defaults). Each tool requires a one-line justification comment in adjacent text.
- Agent descriptions (frontmatter `description` field) must start with a verb (e.g. "Analyzes", "Generates", "Validates") and include a "Use when…" trigger phrase.
- Non-goals must be explicit (at least two per agent). List things the agent must refuse or delegate.
- Agent termination criteria must be concrete and measurable. Avoid "when done" — specify exit conditions (e.g. "exits when JSON report is complete").
- Read-only agents (audit, analysis) must have restricted tools (read_file, grep, bash for queries only). Implementation agents may have edit/write tools.
- Agent descriptions must fit in ~70 characters for UI truncation. If longer, shorten and move detail to the system prompt.
- For delegation agents, document handoff format (what schema/structure is passed to sub-agents).

## Do not for agents

- Do not list 39+ tools in an agent frontmatter. If truly needed, document why and mark as "high-capability agent".
- Do not create agents without explicit non-goals. Prevent scope creep.
- Do not mix implementation and read-only concerns in a single agent. Split into separate agents.
- Do not describe an agent in first-person ("I validate", "I generate"). Use third-person only.

---

# Skill self-correction

When adding or modifying skills in `skills/`, verify template and validator quality.

## Rules for skills

- Every skill's SKILL.md must have a `## Conventions` section (domain-specific quality rules) and `## Anti-patterns` section (at least 3 examples with explanations).
- Skill templates in `templates/` must be fill-in-the-blank ready. No placeholder logic or conditional sections.
- Validator script (`validate_<name>_output.py`) must catch at least one real error. Test it on a deliberately broken example before shipping.
- Skill `evals/evals.json` must include at least one happy-path, one edge-case, and one near-miss (confusing request that belongs to a different skill).
- Skill generator scripts (`generate_<name>_stub.py`) must work from CLI without requiring repo-wide sys.path hacks. Use `_SKILL_ROOT = Path(__file__).resolve().parent.parent`.
- Skill descriptions must list trigger phrases (nouns, verbs, specific keywords) and at least one "DO NOT USE" clause (neighboring skills to avoid confusion).
- Skill agents (analyzer, grader, fingerprint, comparator) must be domain-aware. Update `agents/grader.agent.md` to reflect the specific artifact type being graded.

## Do not for skills

- Do not create a "God skill" that generates multiple unrelated artifact types. Scope to one class.
- Do not ship a validator that has never been tested on a known-bad example.
- Do not duplicate an entire skill directory without updating all references to the old artifact name.
- Do not leave anti-patterns undocumented. The grader uses them to score outputs.
