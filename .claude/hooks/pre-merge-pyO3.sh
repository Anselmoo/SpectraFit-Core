#!/bin/bash

################################################################################
# PyO3 Boundary Validator
#
# Purpose: Ensure all #[pyfunction] decorators in Rust code only return
#          String or Result<String, PyErr> (i.e., JSON strings).
#
# Exit codes:
#   0 = All pyfunctions valid (correct return types)
#   1 = Violations found (invalid return types or syntax errors)
#
# Invocation status (audit F11, 2026-06-26): MANUAL-ONLY. This check is NOT
# auto-wired to any merge gate — it is absent from .claude/settings.json, from
# .git/hooks/, from CI, and from poe. It runs only when invoked by hand via
# .claude/hooks/run-hook.sh. INDEX.yaml lists pre-merge-*.sh as stream anchors,
# but that wiring is intentionally manual pending a committed pre-push hook or
# CI job. Do not assume this gate blocks a merge automatically.
#
################################################################################

REPO_ROOT=$(git rev-parse --show-toplevel)
VIOLATIONS_FOUND=0

# Find all Rust files with #[pyfunction] decorators
PYFUNCTION_FILES=$(find "$REPO_ROOT/crates" -name "*.rs" -type f | xargs grep -l "#\[pyfunction\]" 2>/dev/null)

if [ -z "$PYFUNCTION_FILES" ]; then
    echo "[PyO3 Validator] No pyfunctions found. PASS."
    exit 0
fi

echo "[PyO3 Validator] Checking $(echo "$PYFUNCTION_FILES" | wc -l) files with #[pyfunction] decorators..."

while IFS= read -r FILE; do
    # Extract all pyfunction declarations and their return types
    # Pattern: matches #[pyfunction] followed by fn name(...) -> ReturnType
    
    grep -B1 -A5 "#\[pyfunction\]" "$FILE" | while IFS= read -r LINE; do
        # Look for function signature lines
        if [[ $LINE =~ ^fn\ [a-zA-Z_][a-zA-Z0-9_]*\(.*\)\ *\-\>\ *(.+) ]]; then
            RETURN_TYPE="${BASH_REMATCH[1]}"
            
            # Remove whitespace and check if it's a valid return type
            RETURN_TYPE=$(echo "$RETURN_TYPE" | sed -e 's/^[[:space:]]*//; s/[[:space:]]*$//')
            
            # Valid return types: String, Result<String, PyErr>, PyResult<String>
            if [[ "$RETURN_TYPE" =~ ^(String|Result\<String,\ PyErr\>|PyResult\<String\>)\ *\{? ]]; then
                : # Valid, continue
            else
                echo "VIOLATION: Invalid return type in $FILE: $RETURN_TYPE"
                ((VIOLATIONS_FOUND++))
            fi
        fi
    done
done <<< "$PYFUNCTION_FILES"

# More precise detection: use grep to find each pyfunction block
while IFS= read -r FILE; do
    # For each file, extract pyfunction blocks and validate them
    awk '
    BEGIN { in_pyfunction = 0; line_num = 0; func_line = "" }
    
    /#\[pyfunction\]/ {
        in_pyfunction = 1
        line_num = NR
        next
    }
    
    in_pyfunction && /^fn/ {
        func_line = $0
        
        # Extract return type (everything after -> and before {)
        if (func_line ~ /->/) {
            match(func_line, /-> *([^ {]+)/)
            return_type = substr(func_line, RSTART + 3)
            gsub(/^[ \t]+/, "", return_type)
            gsub(/[ \t{].*/, "", return_type)
            
            # Check if valid
            if (return_type !~ /^(String|Result<String, PyErr>|PyResult<String>)$/) {
                print "VIOLATION: Invalid return type \"" return_type "\" in " FILENAME ":" line_num
                exit 1
            }
        }
        in_pyfunction = 0
    }
    
    in_pyfunction && /^}/ {
        in_pyfunction = 0
    }
    ' "$FILE" || ((VIOLATIONS_FOUND++))
done <<< "$PYFUNCTION_FILES"

if [ "$VIOLATIONS_FOUND" -gt 0 ]; then
    echo "[PyO3 Validator] FAIL: Found $VIOLATIONS_FOUND violations in pyfunction return types."
    exit 1
else
    echo "[PyO3 Validator] PASS: All pyfunctions have correct return types (String/PyResult<String>)."
    exit 0
fi
