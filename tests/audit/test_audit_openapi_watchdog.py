"""Plan G follow-up — OpenAPI watchdog with FQN-tolerant normalisation.

Plan G renamed ``extras.bench.trust_ledger`` → ``oracles.trust_ledger``. Pydantic
embeds the Python module path into the names it surfaces through FastAPI's OpenAPI
generator, so a bytewise schema diff after that rename was non-zero even though the
contract was semantically unchanged. A naive snapshot test would have failed.

This watchdog snapshots the *normalised* schema instead: any embedded Python FQN
segment in ``$ref`` paths, ``components.schemas`` keys, or ``tags`` strings is
collapsed to its leaf name. Cosmetic module moves stay invisible; real field /
operation drift still trips the diff and prints the first ~20 unified-diff lines so
the regression is obvious.

To regenerate the golden after an intentional contract change::

    uv run pytest tests/audit/test_audit_openapi_watchdog.py --update-golden
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from oracles.api import app

GOLDEN_PATH = Path(__file__).parent / "golden" / "openapi_normalised.json"

# Double-underscore FQN as Pydantic surfaces it in ``$ref`` and schema keys, e.g.
# ``oracles__trust_ledger__TrustLedger`` → leaf ``TrustLedger``. The leaf must
# start with an uppercase letter so we only collapse class-style names and never
# accidentally chew through legitimate identifiers like ``snake_case_param``.
_DUNDER_FQN_RE = re.compile(r"(?:[a-zA-Z][a-zA-Z0-9_]*?__)+([A-Z][A-Za-z0-9_]*)")

# Dot-separated Python FQN as it can appear inside ``tags`` strings, e.g.
# ``extras.bench.trust_ledger`` → leaf ``trust_ledger``. Anchored to the whole
# string so we only collapse when the *entire* tag looks like a module path —
# otherwise prose tags such as ``"v1.0 stable"`` would be mauled.
_DOT_FQN_RE = re.compile(r"^(?:[a-zA-Z_][a-zA-Z0-9_]*\.)+([a-zA-Z_][a-zA-Z0-9_]*)$")


def _collapse_dunder_fqn(value: str) -> str:
    """Collapse any ``a__b__C`` segment inside *value* to its leaf class name."""
    return _DUNDER_FQN_RE.sub(lambda m: m.group(1), value)


def _collapse_dot_fqn_tag(tag: str) -> str:
    """Collapse a tag string of the form ``a.b.c`` to its leaf segment ``c``."""
    match = _DOT_FQN_RE.match(tag)
    if match is None:
        return tag
    return match.group(1)


def _normalise_tags(tags: list[Any]) -> list[Any]:
    """Map FQN-shaped tag strings to their leaf; pass non-strings through."""
    out: list[Any] = []
    for tag in tags:
        match tag:
            case str(text):
                out.append(_collapse_dot_fqn_tag(text))
            case _:
                out.append(tag)
    return out


def normalise_schema(schema: Any) -> Any:
    """Return a copy of *schema* with embedded Python FQNs collapsed to leaves.

    Walks the dict/list tree recursively and rewrites:

    - ``$ref`` string values — the trailing schema name is collapsed.
    - ``components.schemas`` map keys — collapsed to the leaf class name.
    - Any ``tags`` list (paths-level or operation-level) — FQN-shaped tag
      strings are collapsed; other tag values pass through untouched.

    ``operationId`` is **not** rewritten: FastAPI builds it from route + handler
    name, not from a Python module path, so it is already FQN-free and a future
    rename of the handler is a real signal we want the diff to surface.
    """
    match schema:
        case dict():
            out: dict[str, Any] = {}
            for key, value in schema.items():
                match (key, value):
                    case ("$ref", str(ref)):
                        out[key] = _collapse_dunder_fqn(ref)
                    case ("tags", list(tags)):
                        out[key] = _normalise_tags(tags)
                    case ("schemas", dict(schemas)):
                        out[key] = {
                            _collapse_dunder_fqn(k): normalise_schema(v)
                            for k, v in schemas.items()
                        }
                    case _:
                        out[key] = normalise_schema(value)
            return out
        case list():
            return [normalise_schema(item) for item in schema]
        case _:
            return schema


def _live_normalised_schema() -> dict[str, Any]:
    """Fetch ``/openapi.json`` through the in-process TestClient and normalise it."""
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200, (
        f"/openapi.json returned {response.status_code}; expected 200"
    )
    return normalise_schema(response.json())


def _dump(payload: Any) -> str:
    """Stable JSON dump used for both the golden file and diff messages."""
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def test_openapi_schema_matches_golden(request: pytest.FixtureRequest) -> None:
    """The live, FQN-normalised OpenAPI schema must equal the checked-in golden.

    Run with ``--update-golden`` after an intentional contract change to refresh
    the snapshot.
    """
    live = _live_normalised_schema()
    live_text = _dump(live)

    if request.config.getoption("--update-golden"):
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(live_text, encoding="utf-8")
        return

    assert GOLDEN_PATH.exists(), (
        f"golden file missing at {GOLDEN_PATH}; regenerate with "
        "`pytest tests/audit/test_audit_openapi_watchdog.py --update-golden`"
    )
    golden_text = GOLDEN_PATH.read_text(encoding="utf-8")

    if live_text == golden_text:
        return

    diff_lines = list(
        difflib.unified_diff(
            golden_text.splitlines(keepends=True),
            live_text.splitlines(keepends=True),
            fromfile=str(GOLDEN_PATH.name) + " (golden)",
            tofile="live /openapi.json (normalised)",
            n=2,
        )
    )
    preview = "".join(diff_lines[:20])
    raise AssertionError(
        "Normalised OpenAPI schema drifted from the checked-in golden.\n"
        "If this drift is intentional, regenerate with "
        "`pytest tests/audit/test_audit_openapi_watchdog.py --update-golden`.\n"
        "First ~20 lines of unified diff (golden → live):\n" + preview
    )


# --------------------------------------------------------------------------- #
# Unit tests for the normalisation function itself.
# These are inline so the audit gate is self-contained: if a future refactor
# breaks the regex, the watchdog test catches it via these fixtures *before* the
# diff-against-golden assertion (which would otherwise fail confusingly).
# --------------------------------------------------------------------------- #


def test_normalise_collapses_dunder_fqn_in_ref() -> None:
    """A ``$ref`` containing a Pydantic dunder FQN collapses to the leaf class."""
    schema = {
        "paths": {
            "/x": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": (
                                            "#/components/schemas/"
                                            "oracles__trust_ledger__TrustLedger"
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    out = normalise_schema(schema)
    ref = out["paths"]["/x"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    assert ref == "#/components/schemas/TrustLedger"


def test_normalise_passes_through_non_fqn_schema_name() -> None:
    """A clean schema name like ``BenchReport`` survives normalisation unchanged."""
    schema = {
        "components": {
            "schemas": {
                "BenchReport": {"type": "object", "properties": {}},
            }
        },
        "paths": {
            "/r": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/BenchReport"
                                    }
                                }
                            }
                        }
                    }
                }
            },
        },
    }
    out = normalise_schema(schema)
    assert "BenchReport" in out["components"]["schemas"]
    assert (
        out["paths"]["/r"]["get"]["responses"]["200"]["content"]["application/json"][
            "schema"
        ]["$ref"]
        == "#/components/schemas/BenchReport"
    )


def test_normalise_collapses_dot_fqn_tag() -> None:
    """A dotted tag like ``extras.bench.trust_ledger`` collapses to ``trust_ledger``."""
    schema = {
        "paths": {
            "/y": {
                "get": {
                    "tags": ["extras.bench.trust_ledger", "plain-tag"],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        }
    }
    out = normalise_schema(schema)
    tags = out["paths"]["/y"]["get"]["tags"]
    assert tags == ["trust_ledger", "plain-tag"]


def test_normalise_renames_schema_map_key() -> None:
    """A dunder-FQN key inside ``components.schemas`` collapses to the leaf."""
    schema = {
        "components": {
            "schemas": {
                "oracles__trust_ledger__TrustLedger": {"type": "object"},
                "BenchReport": {"type": "object"},
            }
        }
    }
    out = normalise_schema(schema)
    assert set(out["components"]["schemas"].keys()) == {"TrustLedger", "BenchReport"}
