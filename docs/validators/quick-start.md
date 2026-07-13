# CLI Validators — Quick Start Guide

## What Are CLI Validators?

Three bash scripts that validate tool inputs **before** execution:
- `validate-edit.sh` — For file edits
- `validate-create.sh` — For file creation
- `validate-bash.sh` — For bash commands

## Quick Test

```bash
# Test a safe edit
./.claude/validators/validate-edit.sh README.md "new content"
# Output: {"decision": "allow", ...}

# Test a dangerous bash command
./.claude/validators/validate-bash.sh "rm -rf /"
# Output: {"decision": "deny", "reason": "Destructive rm -rf detected", ...}

# Test an invalid file creation
./.claude/validators/validate-create.sh "existing_file.txt" "content"
# Output: {"decision": "deny", "reason": "File already exists", ...}
```

## Integration Points

Validators are meant to be called **before** tool execution by the agent/CLI layer:

```bash
# Pseudo-code
VALIDATOR=$(jq -r ".validators[\"$TOOL\"].path" .claude/tool-registry.json)
DECISION=$("$VALIDATOR" "$ARG1" "$ARG2")
DECISION_JSON=$(echo "$DECISION" | jq -r '.decision')
if [[ "$DECISION_JSON" != "allow" ]]; then
  exit 1  # Block operation
fi
```

## Audit Trail

All validation decisions are logged to:
- **Decisions**: `.claude/audit/validation-decisions.jsonl` (JSONL format)
- **Errors**: `.claude/audit/validation-errors.log` (plain text)

Query examples:
```bash
# View all denials
jq 'select(.decision=="deny")' < .claude/audit/validation-decisions.jsonl

# View violations by tool
jq 'group_by(.tool) | map({tool: .[0].tool, count: length})' < .claude/audit/validation-decisions.jsonl
```

## Directory Structure

```
.claude/
├── validators/           # ← Validator scripts
│   ├── validate-edit.sh
│   ├── validate-create.sh
│   └── validate-bash.sh
├── audit/               # ← Audit logs
│   ├── validation-decisions.jsonl
│   ├── validation-errors.log
│   └── README.md
├── tool-registry.json   # ← Validator mappings
├── INTEGRATION.md       # ← Full integration guide
└── VALIDATORS-QUICK-START.md  # ← This file
```

## Validator Checks

### validate-edit.sh
- Path traversal (blocks `..`)
- File existence
- PyO3 boundary checks
- Cargo.toml circular deps
- Schema Pydantic v2 compliance

### validate-create.sh
- Parent dir exists
- Path traversal
- File doesn't exist (new files only)
- Python AST syntax
- Rust brace matching
- Markdown frontmatter

### validate-bash.sh
**Dangerous (denied)**:
- `rm -rf` / `rm -fr`
- `git push --force`
- `sudo`
- Fork bombs
- Code injection

**Warnings (allowed)**:
- Long-running ops (cargo build, npm install)
- Network ops (curl, wget, git clone)
- Side effects (git reset, git clean)

## Exit Codes

```
0 = allow (or allow with warnings)
1 = deny (violations detected)
```

## Timeout

All validators run with 10-second timeout. If timeout occurs, operation is blocked (fail-safe).

## Next Steps

1. **Integration**: Implement in agent/CLI tool execution layer (see `.claude/INTEGRATION.md`)
2. **Monitoring**: Regularly check `.claude/audit/validation-decisions.jsonl` for patterns
3. **Adjustment**: Update validators if new violation patterns emerge

---
For detailed info: See `.claude/INTEGRATION.md`
