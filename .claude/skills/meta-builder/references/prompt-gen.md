# Prompt-gen reference — one-shot prompts and .prompt.md files

Self-contained essentials. Historical content under
`.claude/skills/prompt-generator/` is in git history.

## When to write a prompt

A prompt is **one-shot** — it carries enough context to be self-
contained and is invoked once. Use prompts for:

- A sub-agent's brief in `andon-loop tri-stream`.
- A council convening (handed to `quality-council`).
- A reframe+spike instruction (rung 2 of stuck-mode).
- A custom slash command's body.

If the artifact is **always-on** — the agent should respect this every
time — it's an instruction file, not a prompt (see
`instruction-gen.md`).

## Technique catalog (top picks for this repo)

- **Chain-of-thought** — for solver math debugging.
- **ReAct** — for multi-step verification with intermediate tool calls.
- **Self-consistency** — for a critique-then-synthesis flow (council).
- **Generate-knowledge** — for "what could be wrong" exploration.

The full catalog is in `obra/superpowers` and other prompting
literature; pick the technique that matches the task structure.

## Convention

`.prompt.md` files live in `.claude/prompts/<name>.prompt.md` with
frontmatter `name`, `description`, and a body that is the prompt
itself.

## Stuck-mode entry

A prompt that produces drifting outputs is usually missing a
self-containment check — the prompt assumes context the invoked
sub-agent doesn't have.
