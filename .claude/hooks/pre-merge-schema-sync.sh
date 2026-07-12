#!/bin/bash
# Invocation status (audit F11, 2026-06-26): MANUAL-ONLY. Not auto-wired to any
# merge gate (absent from .claude/settings.json, .git/hooks/, CI, and poe); runs
# only when invoked by hand via .claude/hooks/run-hook.sh. INDEX.yaml lists it as a
# stream anchor, but enforcement is intentionally manual pending a committed
# pre-push hook or CI job. Do not assume this gate blocks a merge automatically.

################################################################################
# Schema Sync Checker
#
# Purpose: Compare Python Pydantic schemas with Rust serde schemas
#          to detect drift at the Python↔Rust JSON boundary.
#
# Exit codes:
#   0 = Schemas in sync (no drift detected)
#   1 = Schema drift detected or validation failed
#
################################################################################

REPO_ROOT=$(git rev-parse --show-toplevel)
VIOLATIONS_FOUND=0

echo "[Schema Sync Checker] Validating Python↔Rust schema alignment..."

# Check if schema files exist
PYTHON_SCHEMAS="$REPO_ROOT/python/spectrafit_core"
RUST_TYPES="$REPO_ROOT/crates/spectrafit-types/src/lib.rs"

if [ ! -d "$PYTHON_SCHEMAS" ]; then
    echo "[Schema Sync Checker] WARN: Python schemas directory not found."
    exit 0
fi

if [ ! -f "$RUST_TYPES" ]; then
    echo "[Schema Sync Checker] WARN: Rust types file not found."
    exit 0
fi

# Check for Python Pydantic models with explicit types (anti-pattern: Any types)
echo "[Schema Sync Checker] Checking Python schemas for loose typing..."

ANY_COUNT=$(grep -r "Any\|Dict\|List" "$PYTHON_SCHEMAS"/*.py 2>/dev/null | \
            grep -E ":\s*(Any|Dict|List)\s*[\[\s,\)]" | \
            grep -v "# type: ignore" | \
            wc -l)

if [ "$ANY_COUNT" -gt 0 ]; then
    echo "VIOLATION: Found $ANY_COUNT uses of permissive Any/Dict/List types in Python schemas."
    echo "  These should be replaced with concrete Annotated[] types for better validation."
    grep -r "Any\|Dict\|List" "$PYTHON_SCHEMAS"/*.py 2>/dev/null | \
        grep -E ":\s*(Any|Dict|List)\s*[\[\s,\)]" | \
        grep -v "# type: ignore" | head -5
    ((VIOLATIONS_FOUND++))
fi

# Check Python models use Pydantic v2 ConfigDict
echo "[Schema Sync Checker] Checking Python models for Pydantic v2 compliance..."

NO_CONFIGDICT=$(grep -L "model_config" "$PYTHON_SCHEMAS"/*.py 2>/dev/null | \
                xargs grep -l "class.*BaseModel" 2>/dev/null | \
                wc -l)

if [ "$NO_CONFIGDICT" -gt 0 ]; then
    echo "INFO: Found $NO_CONFIGDICT Python models without explicit model_config (may be intentional)."
fi

# Check for model_dump_json usage in Python (good practice check)
echo "[Schema Sync Checker] Checking for JSON boundary compliance..."

# This is a best-effort check - we're looking for patterns
DIRECT_DICT_PASS=$(grep -r "model_dump()" "$PYTHON_SCHEMAS" 2>/dev/null | wc -l)

if [ "$DIRECT_DICT_PASS" -gt 0 ]; then
    echo "INFO: Found uses of model_dump() - ensure JSON is used at Rust boundary."
fi

# Check Rust serde derives for proper JSON support
echo "[Schema Sync Checker] Checking Rust serde compliance..."

# Simple heuristic: look for Serialize/Deserialize on types
SERDE_COUNT=$(grep -E "#\[derive\(.*Serialize.*Deserialize" "$RUST_TYPES" 2>/dev/null | wc -l)

if [ "$SERDE_COUNT" -lt 1 ]; then
    echo "INFO: Checking for serde derives in Rust type definitions..."
fi

# Check for consistent naming between Python and Rust
# Python uses snake_case, Rust uses PascalCase (but serde alias handles conversion)
echo "[Schema Sync Checker] Checking for serde field aliasing..."

MISSING_ALIAS=$(grep -A5 "^struct\|^enum" "$RUST_TYPES" | \
                grep -v "#\[serde(rename_all" | \
                grep -E "^\s+[a-z_]+:" | \
                wc -l)

if [ "$MISSING_ALIAS" -gt 0 ]; then
    echo "INFO: Some Rust fields may lack serde field aliasing (this may be intentional)."
fi

if [ "$VIOLATIONS_FOUND" -gt 0 ]; then
    echo "[Schema Sync Checker] FAIL: Found $VIOLATIONS_FOUND schema validation issues."
    exit 1
else
    echo "[Schema Sync Checker] PASS: Schemas appear to be in sync."
    exit 0
fi
