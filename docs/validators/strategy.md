# Validator Strategy Quick Reference

## Decision Rule

| Validation Type | Use | Why |
|-----------------|-----|-----|
| **Python file validation** | Python+Pydantic | AST parsing, type checking, schema validation |
| **Rust file validation** | Python+Pydantic | Semantic analysis, PyO3 boundary checks, DAG validation |
| **Bash commands** | Bash-only | Pattern matching is sufficient, speed critical |
| **Git operations** | Bash-only | Simple pattern detection, pre-commit layer |
| **Workflows** | Bash-only | Configuration validation, no semantics needed |
| **Both for extra safety** | Bash + Python | Complementary checks (fast bash + precise Python) |

---

## Files & Recommendations

### Python+Pydantic Validators (Language-Specific)
```
.claude/validators/pydantic_edit.py
  → For editing Python and Rust files
  → Checks: PyO3 boundaries, DAG deps, schema sync
  → Recommended: ✅ Use Python version

.claude/validators/pydantic_create.py
  → For creating Python and Rust files
  → Checks: AST syntax, boundary balance, frontmatter
  → Recommended: ✅ Use Python version
```

### Bash-Only Validators (General)
```
.claude/validators/validate-bash.sh
  → For bash command validation
  → Checks: Dangerous patterns (rm -rf, sudo, git push --force)
  → Recommended: ✅ Keep bash version (sufficient for patterns)

.claude/validators/validate-edit.sh
.claude/validators/validate-create.sh
  → Backup bash validators (optional if Python not available)
  → Recommended: Optional (Python versions preferred for edit/create)
```

---

## Usage Examples

### Edit Python Schema File
```bash
# Use Python validator (type-safe)
uv run python .claude/validators/pydantic_edit.py \
  python/spectrafit_core/schemas.py \
  "class FitResult(BaseModel): ..."
```

### Edit Rust Model File
```bash
# Use Python validator (PyO3 boundary check)
uv run python .claude/validators/pydantic_edit.py \
  src/models/gaussian.rs \
  "#[pyfunction] fn compute() -> String { ... }"
```

### Validate Bash Command
```bash
# Use bash validator (fast pattern matching)
./.claude/validators/validate-bash.sh "rm -rf /"
# OR Python version for more detailed analysis
uv run python .claude/validators/pydantic_bash.py "rm -rf /"
```

### Create New Python Test File
```bash
# Use Python validator (AST checking)
uv run python .claude/validators/pydantic_create.py \
  tests/test_fit.py \
  "def test_gaussian(): assert True"
```

---

## Pre-Commit vs CLI Layer

### Pre-Commit Layer (Must be fast <100ms)
✅ Use bash validators (4 hooks already configured)
- `.claude/hooks/pre-merge-pyO3.sh`
- `.claude/hooks/pre-merge-dag.sh`
- `.claude/hooks/pre-merge-schema-sync.sh`
- `.claude/hooks/pre-merge-perf-baseline.sh`

### CLI Layer (Can be ~500ms)
✅ Use Python+Pydantic for language-specific (edit, create Python/Rust files)
✅ Use Bash for general (bash commands, patterns)

---

## Decision Flowchart

```
Need to validate something?
  ↓
Is it Python or Rust file validation?
  ├─ YES → Use Python+Pydantic
  │   └─ pydantic_edit.py or pydantic_create.py
  │       (type-safe, semantic analysis)
  │
  └─ NO → Use Bash
      └─ validate-bash.sh or validate-edit.sh/validate-create.sh
          (fast pattern matching)

Speed critical (<100ms)?
  ├─ YES → Use Bash
  └─ NO → Python OK (if semantics matter)
```

---

## Maintenance

### When to Add Python+Pydantic Validator
- Language-specific validation needed (Python AST, Rust types)
- Semantic analysis required (not just patterns)
- Performance acceptable (~500ms OK)

### When to Keep Bash-Only
- Pattern matching sufficient
- Pre-commit layer (speed critical)
- No special language knowledge needed

### When to Use Both
- Extra safety needed (belt + suspenders)
- Bash for speed gate, Python for precision
- Example: Bash catches obvious `rm -rf`, Python validates edge cases

---

## References

- **HOOK-ARCHITECTURE-DECISION.md** — Full architecture analysis
- **.claude/PYDANTIC-VALIDATORS.md** — Integration guide with examples
- **.claude/tool-registry.json** — Validator mappings
- **.pre-commit-config.yaml** — Pre-commit hook configuration

---

Status: ✅ Pragmatic hybrid strategy deployed  
Updated: 2026-05-06
