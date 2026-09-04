# Agent-gen reference — sub-agent definitions

Self-contained essentials. Historical content under
`.claude/skills/agent-generator/` is in git history.

## Sub-agent shape

A sub-agent (`.agent.md`) is a bounded role with:

- A focused system prompt — what the agent does, what it doesn't.
- A tool-allow / tool-deny matrix — which tools it may call.
- A handoff criterion — when it returns control.
- A single result type — the agent returns one structured payload, then
  terminates.

## Use cases in this repo

- Subagents spawned by `andon-loop tri-stream` (one per stream).
- The Explore agent invoked by the rung-1 curiosity sub-cycle.
- The Plan agent invoked when designing a feature.

## Convention

Each sub-agent lives in `.claude/agents/<name>.agent.md`. The
`superpowers:dispatching-parallel-agents` skill describes how to invoke
them in parallel without shared state.

## Anti-pattern

A sub-agent is not a skill. Skills carry domain knowledge; agents
execute bounded tasks. If the artifact is "knowledge", it's a skill
reference. If the artifact is "a role you call", it's an agent.

## Stuck-mode entry

An agent that returns wrong results usually has a tool-allow matrix
that includes something it shouldn't, or a handoff criterion that's
ambiguous. Curiosity sub-cycle: re-read the agent's last 3 invocations
and look for tools that fired outside the intended scope.
