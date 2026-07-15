> Applies to: .claude/validators/*.py

# Pydantic Native Validators Integration

## Overview

The `.claude/validators/` directory now contains **native Python validators with Pydantic**, providing type-safe validation of tool inputs before execution.

### Architecture

```
Pre-Commit Layer (Bash, <1s)
  .claude/hooks/pre-merge-*.sh → Fast git-level checks

CLI Validation Layer (Python+Pydantic, ~500ms)
  .claude/validators/pydantic_*.py → Type-safe input validation
                    ↓
Agent Tool Execution (with audit trail)
  → .claude/audit/validation-decisions.jsonl
```

## Validator Strategy

**Python+Pydantic for:**
- Python file validation (AST parsing, schema sync)
- Rust file validation (PyO3 boundary checks, semantic analysis)

**Bash-only for:**
- General git operations (push, commit, merge)
- Bash command validation
- Workflow and configuration validation
- Any non-language-specific checks

---

## Validators

### 1. pydantic_edit.py (Language-Specific)
**Purpose**: Validate file edits before execution

**Checks**:
- Path traversal detection (`..` or absolute paths blocked)
- PyO3 boundary compliance (`#[pyfunction]` must return `String` or `Result<String>`)
- Cargo.toml DAG validation (dependencies follow: types→models→graph→solver)
- Schema sync (Pydantic v2 compliance, no `Any`/`Dict`/`List` loose typing)

**Usage**:
```bash
# Direct invocation
uv run python .claude/validators/pydantic_edit.py src/types.rs "new content"

# From agent tool registry
.claude/tool-registry.json references this path for "edit" tool pre-validation
```

**Pydantic Models**:
- `EditValidationRequest` — Basic security validation
- `PyO3ReturnType` — PyO3 function signature validation
- `CargoTomlEdit` — DAG dependency validation
- `SchemaSyncValidation` — Schema compliance validation
- `EditValidation` — Orchestrator with context-specific logic

---

### 2. pydantic_create.py (Language-Specific)
**Purpose**: Validate file creation before execution

**Checks**:
- Parent directory existence
- Path traversal detection
- File non-existence (create requires new file)
- Python AST syntax validation (for `.py` files)
- Rust brace/paren balance (for `.rs` files)
- Markdown frontmatter validation (for `.md` files)

**Usage**:
```bash
uv run python .claude/validators/pydantic_create.py path/to/new_file.py "code content"

# Supports different file types with type-specific validation
```

**Pydantic Models**:
- `CreateValidationRequest` — Basic security validation
- `PythonFileValidation` — AST syntax check
- `RustFileValidation` — Brace/paren balance check
- `MarkdownFrontmatterValidation` — Frontmatter YAML structure
- `CreateValidation` — Orchestrator with file-type routing

---

### 3. pydantic_bash.py (General - Candidate for Bash-Only)
**Purpose**: Validate bash commands before execution (General, can stay bash-only)

**Checks**:
- Dangerous patterns denied:
  - `rm -rf` (destructive recursive delete)
  - `git push --force` (force push)
  - `sudo` (privilege escalation)
  - Fork bombs
  - Code injection patterns
- Warnings (allowed but logged):
  - Long-running operations (cargo build, npm install)
  - Network operations (curl, wget)
  - Side effects (git reset, git clean, kill, truncate)

**Status**: Pydantic version provided for type-safe CLI layer, but bash-only version (validate-bash.sh) is sufficient for general use

**Usage**:
```bash
# Python version (type-safe CLI)
uv run python .claude/validators/pydantic_bash.py "cargo build"

# Or keep using fast bash version
./.claude/validators/validate-bash.sh "cargo build"

# Both return decision: "allow" | "ask" | "deny"
```

**Pydantic Models** (if using Python version):
- `BashCommandValidation` — Pattern matching, deny/warn checks
- `BashCommandAnalysis` — Risk severity assessment
- Structured analysis with warnings and info

---

## Integration Points

### Option A: Direct CLI Usage
```bash
# Before running agent tool
if ! uv run python .claude/validators/pydantic_edit.py "$path" "$content"; then
  echo "Edit validation failed"
  exit 1
fi

# Run the tool
edit "$path" "$content"
```

### Option B: Pre-Commit Hook
```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: pydantic-validators
      name: Pydantic validators
      entry: uv run python -m pytest .claude/validators/test_validators.py
      language: system
      stages: [commit]
```

### Option C: Agent Tool Registry Integration
```json
// .claude/tool-registry.json
{
  "validators": {
    "edit": {
      "path_python": "./.claude/validators/pydantic_edit.py",
      "recommended": "python",
      "timeout": "10s"
    }
  }
}
```

Before any agent executes `edit` tool:
1. Tool registry looks up validator for "edit"
2. Calls: `uv run python .claude/validators/pydantic_edit.py <path> <content>`
3. Parses JSON result: `{"decision": "allow|deny", "reason": "...", "violations": [...]}`
4. If deny: block operation, log to audit trail
5. If allow: proceed with tool execution

---

## Output Format

All validators output JSON:
```json
{
  "decision": "allow" | "deny" | "ask",
  "reason": "Human-readable explanation",
  "severity": "safe" | "risky" | "denied",
  "violations": ["violation1", "violation2"],
  "warnings": ["warning1"],
  "info": ["info1"]
}
```

Exit codes:
- `0` — allow (decision=allow)
- `1` — deny (decision=deny)
- `2` — ask (decision=ask, requires confirmation)

---

## Testing

### Test Edit Validator
```bash
# Test PyO3 boundary violation
uv run python .claude/validators/pydantic_edit.py \
  src/types.rs \
  "fn compute() -> Vec<f64> { vec![1.0] }"
# Expected: decision=deny (return type must be String)

# Test valid edit
uv run python .claude/validators/pydantic_edit.py \
  src/types.rs \
  "#[pyfunction] fn compute() -> String { \"ok\".to_string() }"
# Expected: decision=allow
```

### Test Create Validator
```bash
# Test Python syntax error
uv run python .claude/validators/pydantic_create.py \
  new_file.py \
  "def foo(: pass"  # Invalid syntax
# Expected: decision=deny (syntax error)

# Test valid Python
uv run python .claude/validators/pydantic_create.py \
  new_file.py \
  "def foo(): pass"
# Expected: decision=allow
```

### Test Bash Validator
```bash
# Test dangerous pattern
uv run python .claude/validators/pydantic_bash.py \
  "rm -rf /"
# Expected: decision=deny (destructive)

# Test safe command
uv run python .claude/validators/pydantic_bash.py \
  "cargo build"
# Expected: decision=allow (or ask for long-running)
```

---

## Audit Trail Integration

All validation decisions logged to `.claude/audit/validation-decisions.jsonl`:
```json
{"timestamp":"2026-05-06T09:30:00Z","agent":"schema-migration-auditor","tool":"edit","path":"src/types.rs","decision":"allow","reason":"Schema validation passed"}
```

Query audit trail:
```bash
# All denials
jq '.[] | select(.decision=="deny")' .claude/audit/validation-decisions.jsonl

# By tool
jq '.[] | select(.tool=="edit")' .claude/audit/validation-decisions.jsonl

# Group by severity
jq 'group_by(.decision) | map({decision: .[0].decision, count: length})' .claude/audit/validation-decisions.jsonl
```

---

## Error Handling

### Validator Crash
- **Behavior**: Fail-safe (operation blocked)
- **Log**: `.claude/audit/validation-errors.log`
- **Message**: "Validation error: {exception}"

### Validator Timeout (>10s)
- **Behavior**: Blocked (timeout = error)
- **Log**: `.claude/audit/validation-errors.log`
- **Message**: "Validator timeout after 10s"

### Invalid JSON Output
- **Behavior**: Blocked
- **Log**: `.claude/audit/validation-errors.log`
- **Message**: "Validator returned invalid JSON"

---

## Migration from Bash Validators

Strategy: **Use bash for general validation, Python+Pydantic for language-specific**

| Bash | Python | Recommendation |
|------|--------|-----------------|
| validate-edit.sh | pydantic_edit.py | ✅ Use Python (Rust/Python file validation) |
| validate-create.sh | pydantic_create.py | ✅ Use Python (syntax validation, AST) |
| validate-bash.sh | pydantic_bash.py | ⚠️ Keep bash-only (general, no special validation needed) |

**Transition**:
- **Language-specific** (Python/Rust files): Use Python validators (type-safe, semantic)
- **General** (bash commands, git ops, workflows): Use bash validators (fast, simple)
- Current pre-commit hooks use bash (fast, no Python) ✅
- CLI validators have flexibility (can use Python for type safety where it matters)

---

## Design Decisions

### Why Pydantic for Python/Rust validation?
1. **Type Safety**: Field validators, strict mode, error messages
2. **AST Parsing**: Semantic analysis (syntax checking, boundary detection)
3. **Reusable Models**: Share with `python/spectrafit_core/schemas.py`
4. **IDE Support**: Type hints, auto-completion
5. **Testability**: Easy to unit test validators

### Why Bash for general validation?
1. **Speed**: Pre-commit hooks need <100ms
2. **Zero dependencies**: Works everywhere
3. **Simplicity**: Regex patterns sufficient for dangerous detection
4. **Reliability**: No Python startup overhead

### Strategy
- ✅ **Use Python+Pydantic**: Python and Rust file validation (language-specific)
- ✅ **Use Bash-only**: General bash, git, workflow validation (non-language-specific)
- ✅ **Hybrid when needed**: Both bash and Python for complementary checks

### Why NOT Rust?
- Overkill for validation (regex + string matching)
- High integration cost (compilation, binary distribution)
- Python already adequate for CLI layer (<500ms acceptable)

---

## Future Enhancements

1. **Web UI Dashboard**: Visualize validator metrics
2. **Custom Validators**: Plugin system for domain-specific rules
3. **Performance Optimization**: Cache AST parses
4. **Integration with Rust**: Compile Pydantic validators to Rust (optional)

---

Generated: 2026-05-06  
Status: ✅ Production-ready  
Recommended: Use Python validators for CLI layer
