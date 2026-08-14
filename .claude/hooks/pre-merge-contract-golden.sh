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
# Exit codes:
#   0 = golden matches live schema
#   1 = drift detected — contract-visible text changed without regenerating

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT" || exit 1

echo "[Contract Golden Checker] Validating OpenAPI golden snapshot..."

if ! uv run pytest tests/audit/test_audit_openapi_watchdog.py::test_openapi_schema_matches_golden -q; then
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
fi

echo "[Contract Golden Checker] PASS: golden matches live schema."
exit 0
