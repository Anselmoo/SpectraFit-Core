# Hook-gen reference — Claude Code lifecycle hooks

Self-contained essentials. Historical content under
`.claude/skills/hook-generator/` is in git history.

## Hook lifecycles available

- `PreToolUse` — runs before a tool call; exit 2 blocks.
- `PostToolUse` — runs after a tool call; can react to side effects.
- `Stop` — runs when the agent stops.
- `SessionStart` — runs at session start.
- `SubagentStop` — runs when a sub-agent terminates.
- `PreCompact` / `PostCompact` — around context compaction.
- (plus more — 30+ events).

## Shape (this repo's convention)

Each hook is a bash script under `.claude/hooks/<name>.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
_tmpf=$(mktemp); trap 'rm -f "$_tmpf"' EXIT; cat > "$_tmpf"
HOOK_STDIN_FILE="$_tmpf" python3 - <<'PYEOF'
# ... parse $HOOK_STDIN_FILE JSON payload, check, exit 0/2 ...
PYEOF
```

Wired into `.claude/settings.json` under the right lifecycle block with
a `matcher` filter and a `description`.

## Existing examples to learn from

| Hook | Lifecycle | Behavior |
|------|-----------|----------|
| `protect-nist-fixtures.sh` | PreToolUse Edit/Write | BLOCKING; guards verbatim NIST data |
| `enforce-pydantic-native.sh` | PreToolUse Edit/Write | BLOCKING; blocks dict-key contract access |
| `cargo-check-on-rust-edit.sh` | PostToolUse Edit/Write *.rs | runs `cargo check` |
| `enforce-serena-first.sh` | PreToolUse Grep | WARN (tier 1) on symbol-shaped patterns |

## When to add a hook vs a skill instruction

If the rule is **deterministic and binary** — yes/no, allowed/blocked
— it's a hook. The harness runs the hook, not Claude, so the rule
fires every time.

If the rule is **judgment-based** (e.g. "prefer serena over grep
*usually*"), it's a skill body instruction (with optional hook as
safety net).

## Anti-pattern

Don't write a hook that re-implements a skill's judgment. Hooks are
the wall; skills are the path. The wall stops bad moves; the path
guides good ones.

## Stuck-mode entry

A hook that fires falsely is over-specified — its matcher or its body
catches more than intended. Curiosity sub-cycle: dump the last 10
invocations' stdin payload and review.
