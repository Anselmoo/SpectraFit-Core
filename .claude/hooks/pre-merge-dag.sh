#!/bin/bash
# Invocation status (audit F11, 2026-06-26): MANUAL-ONLY. Not auto-wired to any
# merge gate (absent from .claude/settings.json, .git/hooks/, CI, and poe); runs
# only when invoked by hand via .claude/hooks/run-hook.sh. INDEX.yaml lists it as a
# stream anchor, but enforcement is intentionally manual pending a committed
# pre-push hook or CI job. Do not assume this gate blocks a merge automatically.

################################################################################
# Workspace DAG Validator
#
# Purpose: Validate the crate dependency graph follows the allowed DAG:
#          types → models → graph → {varpro, solver} → core
#
# Exit codes:
#   0 = All crate dependencies valid (DAG respected)
#   1 = DAG violations found (cycles or wrong dependencies)
#
################################################################################

REPO_ROOT=$(git rev-parse --show-toplevel)
VIOLATIONS_FOUND=0

echo "[DAG Validator] Validating workspace crate dependencies..."

# Define allowed dependencies function (returns space-separated list)
get_allowed_deps() {
    local CRATE="$1"
    # Allowed DAG (updated for the per-method solver-crate split): the trust-region
    # framework sits above types; each LM-family method crate (dogleg, newton-cg,
    # levenberg-marquardt) builds on trust-region; spectrafit-solver dispatches to all
    # of them; spectrafit-core is the PyO3 top.
    case "$CRATE" in
        spectrafit-types)
            echo ""
            ;;
        spectrafit-models)
            echo "spectrafit-types"
            ;;
        spectrafit-graph)
            echo "spectrafit-types spectrafit-models"
            ;;
        spectrafit-trust-region)
            echo "spectrafit-types"
            ;;
        spectrafit-dogleg|spectrafit-newton-cg|spectrafit-levenberg-marquardt)
            echo "spectrafit-types spectrafit-trust-region"
            ;;
        spectrafit-varpro)
            echo "spectrafit-types spectrafit-models spectrafit-graph"
            ;;
        spectrafit-solver)
            echo "spectrafit-types spectrafit-models spectrafit-graph spectrafit-varpro spectrafit-dogleg spectrafit-newton-cg spectrafit-levenberg-marquardt"
            ;;
        spectrafit-core)
            echo "spectrafit-types spectrafit-models spectrafit-graph spectrafit-solver"
            ;;
        *)
            echo ""
            ;;
    esac
}

# Check if dependency is in allowed list
dep_is_allowed() {
    local DEP="$1"
    local ALLOWED_LIST="$2"
    
    for ALLOWED_DEP in $ALLOWED_LIST; do
        if [ "$DEP" = "$ALLOWED_DEP" ]; then
            return 0
        fi
    done
    return 1
}

# Check each crate's dependencies
for CRATE_DIR in "$REPO_ROOT/crates"/*; do
    if [ ! -d "$CRATE_DIR" ]; then
        continue
    fi
    
    CRATE_NAME=$(basename "$CRATE_DIR")
    CARGO_TOML="$CRATE_DIR/Cargo.toml"
    
    if [ ! -f "$CARGO_TOML" ]; then
        continue
    fi
    
    # Extract internal dependencies (those with "{ workspace = true }")
    ACTUAL_DEPS=$(grep "spectrafit-" "$CARGO_TOML" | grep "{ workspace = true }" | \
                  sed 's/\s*\(spectrafit-[^ =]*\).*/\1/' | sort | uniq)
    
    ALLOWED=$(get_allowed_deps "$CRATE_NAME")
    
    if [ -z "$ACTUAL_DEPS" ]; then
        # No internal dependencies
        continue
    fi
    
    # Check each actual dependency is allowed
    while IFS= read -r DEP; do
        [ -z "$DEP" ] && continue
        
        if ! dep_is_allowed "$DEP" "$ALLOWED"; then
            echo "VIOLATION: Crate '$CRATE_NAME' depends on '$DEP', which is not allowed."
            echo "  Allowed dependencies: ${ALLOWED:-(none)}"
            ((VIOLATIONS_FOUND++))
        fi
    done <<< "$ACTUAL_DEPS"
    
done

if [ "$VIOLATIONS_FOUND" -gt 0 ]; then
    echo "[DAG Validator] FAIL: Found $VIOLATIONS_FOUND DAG violations."
    exit 1
else
    echo "[DAG Validator] PASS: All crate dependencies follow the allowed DAG."
    exit 0
fi
