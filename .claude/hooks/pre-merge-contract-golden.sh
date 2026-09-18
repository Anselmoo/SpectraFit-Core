#!/bin/bash
# [GIT PRE-COMMIT/PRE-PUSH] Validate the OpenAPI contract golden snapshot
# (tests/audit/golden/openapi_normalised.json) is in sync with the live
# schema FastAPI derives from python/oracles/bench_contract.py,
# python/oracles/trust_ledger.py, and python/oracles/contract.py.
#
# Why this exists: a Pydantic class docstring or Field(description=...) on any
# model serialized into BenchReport becomes the OpenAPI `description` text —
# editing it IS a contract change, even when the edit reads like a pure
# documentation tidy-up. This repo's Python-docstring convention is REAL
# LaTeX ($\chi^2$, $\pm$, $\kappa(J)$, ...), never a hand-typed unicode/ASCII
# approximation (chi-squared sign, plus-minus sign, kappa) — that rule is
# Python-only for now (Rust/TS doc comments are not covered). Do NOT "fix" a
# failure here by de-LaTeX-ing the source. Regenerate the golden instead.
#
# A non-zero pytest exit is NOT automatically schema drift. pytest also exits
# non-zero when it cannot even collect the test — a missing dependency (e.g.
# `fastapi` pruned from the venv), a broken import, a syntax error. Reporting
# those as "contract drift" sends the developer to `poe contract_regen`, which
# cannot help and, if it somehow ran, would write a golden from a broken tree.
# Exit code 2 (pytest's INTERNALERROR/usage-error, which covers collection
# errors) and a captured "ModuleNotFoundError/ImportError/ERROR collecting"
# signature are therefore reported as an ENVIRONMENT failure instead.
#
# Exit codes:
#   0 = golden matches live schema
#   1 = drift detected — contract-visible text changed without regenerating
#   1 = environment broken — test could not run (different message; do NOT regen)

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT" || exit 1

echo "[Contract Golden Checker] Validating OpenAPI golden snapshot..."

OUTPUT=$(uv run pytest tests/audit/test_audit_openapi_watchdog.py::test_openapi_schema_matches_golden -q 2>&1)
STATUS=$?

if [ "$STATUS" -eq 0 ]; then
    echo "[Contract Golden Checker] PASS: golden matches live schema."
    exit 0
fi

echo "$OUTPUT"

# Distinguish "the test ran and the golden differs" from "the test never ran".
# pytest exit 2 = interrupted/usage error (collection errors land here); exit 3/4
# are internal/usage errors. Any of those, or an import-failure signature in the
# captured output, means the environment is broken — not the contract.
MISSING_MODULE=$(printf '%s\n' "$OUTPUT" | grep -oE "ModuleNotFoundError: No module named '[^']+'" | head -n 1)
IMPORT_BREAK=$(printf '%s\n' "$OUTPUT" \
    | grep -qE "ModuleNotFoundError|ImportError|ERROR collecting|error: Failed to (spawn|prepare)|no tests ran" \
    && echo yes)

if [ "$STATUS" -ge 2 ] || [ "$IMPORT_BREAK" = "yes" ]; then
    echo ""
    echo "[Contract Golden Checker] FAIL: the contract golden test could NOT RUN."
    echo "  This is an ENVIRONMENT failure, not schema drift — the OpenAPI golden was"
    echo "  never compared, so nothing is known about the contract either way."
    if [ -n "$MISSING_MODULE" ]; then
        echo ""
        echo "  Missing dependency: $MISSING_MODULE"
    fi
    echo ""
    echo "  Fix your environment, then re-run this check:"
    echo "    uv sync --all-extras --all-groups"
    echo "    uv run pytest tests/audit/test_audit_openapi_watchdog.py -q"
    echo ""
    echo "  Do NOT run 'uv run poe contract_regen' for this failure. It cannot fix a"
    echo "  broken environment, and regenerating from a tree that does not import"
    echo "  would write a WRONG golden."
    exit 1
fi

echo ""
echo "[Contract Golden Checker] FAIL: OpenAPI schema drifted from the checked-in golden."
echo "  A Pydantic Field(description=...) or class docstring in a contract-visible"
echo "  model (bench_contract.py / trust_ledger.py / contract.py) changed."
echo ""
echo "  Regenerate ALL contract artifacts (Python golden + web TS + web snapshot):"
echo "    uv run poe contract_regen"
echo "  Then stage the regenerated files and commit again."
echo ""
echo "  Do NOT revert the docstring's LaTeX notation to fix this — LaTeX is the"
echo "  intended convention; the golden is what must be regenerated."
exit 1
