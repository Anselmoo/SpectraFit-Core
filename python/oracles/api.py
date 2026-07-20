"""FastAPI app serving the frozen ``BenchReport`` contract as the single source of truth.

The benchmark engine emits ``results.json`` (the camelCase ``BenchReport`` payload)
into a run-centric tree under ``.spectrafit_reports/benchmark/``. This app is the
*only* runtime bridge to the ``web/`` React UI: the React app fetches ``/api/v1/report``
at load time instead of inlining a build-time fixture, so there is one data flow:

    benchmark run → results.json → FastAPI → React

The response models ARE the frozen contract (:class:`oracles.bench_contract.BenchReport`),
so the OpenAPI schema this app publishes at ``/openapi.json`` is the type source for
``web/src/contract.ts`` (generated via ``openapi-typescript``). Pydantic, not a
hand-kept JSON Schema, is the contract.

Routing — Rosetta bridge:
    The endpoints live on a single :class:`fastapi.APIRouter` mounted twice:

    - ``/api/v1/*`` — canonical prefix going forward. No deprecation headers.
    - ``/api/*``   — legacy alias for one cycle. Every response carries
      ``Deprecation: true`` and ``Sunset: <date>`` so callers see the migration
      window in HTTP itself (RFC 8594 / draft-ietf-httpapi-deprecation-header).

Run::

    uv run --extra benchmark python -m uvicorn oracles.api:app --port 8000
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from oracles.bench_contract import BenchReport
from oracles.migrate import migrate_payload_to_current
from oracles.reports import REPORTS_ROOT, _RUN_RE, latest_results

_CATEGORY = "benchmark"

# Legacy ``/api/*`` alias kept for one cycle. ``Sunset`` is six months from the
# Rosetta-bridge landing date (2026-06-06 → 2026-12-06), per RFC 8594.
_LEGACY_PREFIX = "/api"
_CANONICAL_PREFIX = "/api/v1"
_SUNSET_DATE = "Sat, 06 Dec 2026 00:00:00 GMT"


app = FastAPI(
    title="SpectraFit Benchmark API",
    version="1.0",
    summary="Serves the frozen BenchReport contract (the report the web UI consumes).",
)

# CORS scoped to the local Vite dev origin: the report payload carries git provenance
# (see _capture_git_provenance() in oracles/engine.py), so a wildcard becomes a real
# exposure the moment this ever binds to a non-localhost interface. Add the production
# origin here when one exists — do not revert to "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class _DeprecatedAliasMiddleware(BaseHTTPMiddleware):
    """Stamp ``Deprecation``/``Sunset`` headers on legacy ``/api/<endpoint>`` responses.

    Only requests whose path resolved against a route registered under the legacy
    prefix (i.e. ``/api/runs``, ``/api/report``, ``/api/report/{run_id}``) are
    stamped. Unrelated 404s such as ``/api/v1abc`` or ``/apicruft`` never inherit
    the deprecation headers, and the canonical ``/api/v1/*`` surface stays clean.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response: Response = await call_next(request)
        # Starlette stamps ``request.scope['route']`` only when a real route matched;
        # this avoids tagging 404 paths that merely share the ``/api`` prefix.
        route = request.scope.get("route")
        if route is None:
            return response
        route_path: str = getattr(route, "path", "")
        if not route_path.startswith(_LEGACY_PREFIX + "/"):
            return response
        if (
            route_path.startswith(_CANONICAL_PREFIX + "/")
            or route_path == _CANONICAL_PREFIX
        ):
            return response
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = _SUNSET_DATE
        # ``Link`` to the canonical successor per RFC 8594 § 3.
        successor = _CANONICAL_PREFIX + request.url.path[len(_LEGACY_PREFIX) :]
        response.headers["Link"] = f'<{successor}>; rel="successor-version"'
        return response


app.add_middleware(_DeprecatedAliasMiddleware)


@app.get("/", include_in_schema=False, summary="Human landing — redirects to /docs.")
def root() -> RedirectResponse:
    """Redirect GET / to /docs (the interactive API explorer).

    Prevents the bare ``{"detail":"Not Found"}`` 404 that confuses developers
    who open http://localhost:8000/ expecting something useful.  The UI lives on
    :5173; /docs is the best landing for a bare API hit on :8000.
    """
    return RedirectResponse(url="/docs")


def _load_report(results: Path) -> BenchReport:
    """Read, migrate, and validate a ``results.json`` as a :class:`BenchReport`.

    The single load chokepoint for both the ``latest`` and ``by run_id``
    endpoints: payloads written by an older engine (``schemaVersion`` < current)
    are chain-upgraded via :func:`oracles.migrate.migrate_payload_to_current`
    before validation, so the web app never receives a pre-1.3 report whose
    missing ``panels`` registry would render a blank Case page.
    """
    raw = json.loads(results.read_text(encoding="utf-8"))
    return BenchReport.model_validate(migrate_payload_to_current(raw))


def _results_for_run(run_id: str) -> Path:
    """Return the ``results.json`` path for *run_id*, validating the id shape.

    ``run_id`` is constrained to the ``YYYY-MM-DD_run_NNN`` pattern so a caller can
    never traverse outside the category tree (no ``..`` / slashes reach the path).
    """
    if not _RUN_RE.match(run_id):
        raise HTTPException(status_code=404, detail=f"unknown run id: {run_id!r}")
    return REPORTS_ROOT / _CATEGORY / run_id / "results.json"


# All endpoints live on a single router; the FastAPI app mounts it twice
# (canonical + legacy) below so there is one source of truth for handlers.
router = APIRouter()


@router.get("/runs", summary="List available benchmark run ids (newest first).")
def list_runs() -> list[str]:
    """Return the run ids under ``<REPORTS_ROOT>/benchmark/`` (newest first)."""
    base = REPORTS_ROOT / _CATEGORY
    if not base.exists():
        return []
    runs = [
        d.name
        for d in base.iterdir()
        if d.is_dir() and _RUN_RE.match(d.name) and (d / "results.json").exists()
    ]
    # Names embed a date + monotonic NNN, so a reverse lexicographic sort is
    # newest-first without parsing.
    return sorted(runs, reverse=True)


@router.get(
    "/report",
    response_model=BenchReport,
    summary="The latest run's report (the BenchReport contract).",
)
def get_latest_report() -> BenchReport:
    """Return the newest run's validated :class:`BenchReport`."""
    results = latest_results(_CATEGORY, root=REPORTS_ROOT)
    if results is None:
        raise HTTPException(
            status_code=404,
            detail=f"no benchmark runs under {REPORTS_ROOT / _CATEGORY}",
        )
    return _load_report(results)


@router.get(
    "/report/{run_id}",
    response_model=BenchReport,
    summary="A specific run's report by id.",
)
def get_report(run_id: str) -> BenchReport:
    """Return the validated :class:`BenchReport` for the given *run_id*."""
    results = _results_for_run(run_id)
    if not results.exists():
        raise HTTPException(status_code=404, detail=f"no results for run {run_id!r}")
    return _load_report(results)


@router.get(
    "/trust",
    summary="The latest run's verification ledger (trust block + inference).",
)
def get_trust() -> dict:
    """Latest run's verification ledger slice (trust block + inference).

    The downloadable 'verification ledger' the UI links to for reviewers. The full
    V&V detail (wires, NIST datasets, nested-adequacy, σ-calibration, speed-significance)
    lives here rather than as a dedicated UI page; the landing carries only a compact,
    externally-anchored trust signal. camelCase wire form, like /report.
    """
    results = latest_results(_CATEGORY, root=REPORTS_ROOT)
    if results is None:
        raise HTTPException(
            status_code=404,
            detail=f"no benchmark runs under {REPORTS_ROOT / _CATEGORY}",
        )
    dumped = _load_report(results).model_dump(by_alias=True)
    keys = ("schemaVersion", "runTimestampUnix", "trustBlock", "inference")
    return {k: dumped.get(k) for k in keys}


# Mount canonical first (so it's the primary in the OpenAPI schema), then the
# legacy alias. Both share the same handlers — no duplicated business logic.
app.include_router(router, prefix=_CANONICAL_PREFIX)
app.include_router(router, prefix=_LEGACY_PREFIX)
