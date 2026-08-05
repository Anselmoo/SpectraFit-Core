#!/bin/bash

################################################################################
# Rust Binding Audit Validator
#
# Purpose: Ensure every PyO3 entrypoint registered in
#          crates/spectrafit-core/src/lib.rs and every Solver:: variant
#          declared in crates/spectrafit-solver/src/dispatch.rs has a
#          one-line description in scripts/binding_audit_notes.toml, and
#          that the notes file has no stale entries left behind by a removed
#          binding. Delegates to scripts/audit_bindings.py — this wrapper
#          exists only to match the .claude/hooks/pre-merge-*.sh convention.
#
# Fix: uv run poe audit_bindings_regen (also refreshes the optional
#      docs/reference/rust/binding-audit.md human-readable rendering).
#
# Exit codes:
#   0 = binding_audit_notes.toml matches the grepped source surface
#   1 = drift detected (missing or stale entry)
#
# Invocation status: same caveat as pre-merge-pyO3.sh — this repo's
# .pre-commit-config.yaml entries are NOT confirmed auto-wired to every
# contributor's local git hooks (depends on `pre-commit install` having been
# run). The actually-enforced gate is CI (.gitlab/30-test.yml,
# .github/workflows/ci.yml both run `python3 scripts/audit_bindings.py`
# directly); this hook is a fast local convenience, not the safety net.
#
################################################################################

REPO_ROOT=$(git rev-parse --show-toplevel)
python3 "$REPO_ROOT/scripts/audit_bindings.py"
