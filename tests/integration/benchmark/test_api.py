"""Tests for the benchmark FastAPI app (``oracles.api``).

The app is the single runtime source of truth: it serves the frozen ``BenchReport``
contract (validated against :mod:`oracles.bench_contract`) under both the canonical
``/api/v1/*`` prefix and a one-cycle legacy ``/api/*`` alias. Its OpenAPI schema is
the type source for the web app's ``contract.ts`` — so this also guards that the
schemas the views import are present in ``/openapi.json``.

Every endpoint test is parametrized over both prefixes to enforce the bridge
invariant: byte-identical payloads, identical status codes. Two extra tests pin
the Rosetta semantics — ``test_v1_and_legacy_runs_byte_identical`` (no payload drift)
and ``test_legacy_alias_has_deprecation_headers`` (canonical = clean, legacy = signed).

The tests write a real synthetic report into a temp reports tree and point the app's
``REPORTS_ROOT`` at it (monkeypatched), so no benchmark run or disk fixture is needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from oracles import api
from oracles.bench_contract import BenchReport
from oracles.synth import build_report

# Both prefixes are exercised by every endpoint test so the legacy alias cannot
# silently drift from the canonical surface.
_PREFIXES = ("/api", "/api/v1")


@pytest.fixture
def client_with_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, str]:
    """A TestClient backed by a temp reports tree holding one synthetic run."""
    from oracles import reports as reports_mod

    monkeypatch.setattr(reports_mod, "REPORTS_ROOT", tmp_path)
    monkeypatch.setattr(api, "REPORTS_ROOT", tmp_path)
    run_dir = reports_mod.write_run(build_report(), category="benchmark", root=tmp_path)
    return TestClient(api.app), run_dir.name


@pytest.mark.parametrize("prefix", _PREFIXES)
def test_get_report_returns_valid_bench_report(
    client_with_run: tuple[TestClient, str], prefix: str
) -> None:
    """``GET <prefix>/report`` serves the latest run as a contract-valid BenchReport."""
    client, _ = client_with_run
    resp = client.get(f"{prefix}/report")
    assert resp.status_code == 200
    # Revalidate against the frozen contract (alias-aware): the payload IS a BenchReport.
    report = BenchReport.model_validate(resp.json())
    assert len(report.suite) > 0
    assert {s.id for s in report.solvers}  # non-empty solver legend


@pytest.mark.parametrize("prefix", _PREFIXES)
def test_list_runs_includes_written_run(
    client_with_run: tuple[TestClient, str], prefix: str
) -> None:
    """``GET <prefix>/runs`` lists the run id that was written."""
    client, run_id = client_with_run
    resp = client.get(f"{prefix}/runs")
    assert resp.status_code == 200
    assert run_id in resp.json()


@pytest.mark.parametrize("prefix", _PREFIXES)
def test_get_report_by_run_id(
    client_with_run: tuple[TestClient, str], prefix: str
) -> None:
    """``GET <prefix>/report/{run_id}`` serves that specific run."""
    client, run_id = client_with_run
    resp = client.get(f"{prefix}/report/{run_id}")
    assert resp.status_code == 200
    BenchReport.model_validate(resp.json())


@pytest.mark.parametrize("prefix", _PREFIXES)
def test_unknown_run_id_404(
    client_with_run: tuple[TestClient, str], prefix: str
) -> None:
    """A bad/unknown run id yields 404 (and the id-shape guard blocks traversal)."""
    client, _ = client_with_run
    assert client.get(f"{prefix}/report/2099-01-01_run_999").status_code == 404
    # A traversal-shaped id never matches the run pattern → 404, never a path escape.
    assert client.get(f"{prefix}/report/..%2f..%2fetc").status_code == 404


@pytest.mark.parametrize("prefix", _PREFIXES)
def test_report_404_when_no_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prefix: str
) -> None:
    """With no runs written, ``<prefix>/report`` is 404 and ``<prefix>/runs`` is empty."""
    monkeypatch.setattr(api, "REPORTS_ROOT", tmp_path)
    from oracles import reports as reports_mod

    monkeypatch.setattr(reports_mod, "REPORTS_ROOT", tmp_path)
    client = TestClient(api.app)
    assert client.get(f"{prefix}/report").status_code == 404
    assert client.get(f"{prefix}/runs").json() == []


@pytest.mark.parametrize("prefix", _PREFIXES)
def test_pre_1_3_payload_is_migrated_on_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prefix: str
) -> None:
    """A schemaVersion-1.2 results.json (no ``panels``) is upgraded at serve time.

    The Playwright-verified blank-Case-page bug: an archived pre-Plan-D run went
    to the web raw, with ``panels`` defaulting to ``[]``, so the panel grid had
    nothing to render. ``_load_report`` is the single chokepoint that must
    chain-migrate the payload, so both the ``latest`` and ``by run_id``
    endpoints come out stamped current with a NON-empty panel registry.
    """
    import json as _json

    from oracles import reports as reports_mod
    from oracles.bench_contract import SCHEMA_VERSION

    monkeypatch.setattr(reports_mod, "REPORTS_ROOT", tmp_path)
    monkeypatch.setattr(api, "REPORTS_ROOT", tmp_path)

    legacy = _json.loads(build_report().model_dump_json(by_alias=True))
    legacy.pop("panels", None)
    legacy.pop("schema_version", None)
    legacy["schemaVersion"] = "1.2"
    # Route through write_run so <root>/index.json exists — `latest_results`
    # resolves the latest run via the index, not by walking the tree. Then
    # overwrite the written results.json with the legacy 1.2 payload.
    run_dir = reports_mod.write_run(build_report(), category="benchmark", root=tmp_path)
    (run_dir / "results.json").write_text(_json.dumps(legacy), encoding="utf-8")

    client = TestClient(api.app)
    for path in (f"{prefix}/report", f"{prefix}/report/{run_dir.name}"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        report = BenchReport.model_validate(resp.json())
        assert report.schema_version == SCHEMA_VERSION, path
        assert len(report.panels) >= 20, (
            f"{path}: pre-1.3 payload must be served with a NON-empty panel registry"
        )


def test_v1_and_legacy_runs_byte_identical(
    client_with_run: tuple[TestClient, str],
) -> None:
    """The Rosetta bridge invariant: same handler, byte-identical JSON payloads.

    Comparing ``response.content`` (not ``.json()``) catches any drift in
    serialization — key order, whitespace, float formatting — that would silently
    break a caller treating one prefix as a drop-in for the other.
    """
    client, _ = client_with_run
    legacy = client.get("/api/runs")
    canonical = client.get("/api/v1/runs")
    assert legacy.status_code == 200
    assert canonical.status_code == 200
    assert legacy.content == canonical.content


def test_legacy_alias_has_deprecation_headers(
    client_with_run: tuple[TestClient, str],
) -> None:
    """``Deprecation: true`` + ``Sunset`` ride every ``/api/*`` response; absent on ``/api/v1/*``.

    RFC 8594 (Sunset) + draft-ietf-httpapi-deprecation-header. The headers must
    appear on EVERY legacy endpoint (not just one) and must NEVER leak onto the
    canonical surface.
    """
    client, run_id = client_with_run
    legacy_paths = ["/api/runs", "/api/report", f"/api/report/{run_id}"]
    canonical_paths = [
        "/api/v1/runs",
        "/api/v1/report",
        f"/api/v1/report/{run_id}",
    ]
    for path in legacy_paths:
        resp = client.get(path)
        assert resp.headers.get("deprecation") == "true", (
            f"legacy {path} missing Deprecation header"
        )
        assert "sunset" in {k.lower() for k in resp.headers}, (
            f"legacy {path} missing Sunset header"
        )
    for path in canonical_paths:
        resp = client.get(path)
        assert "deprecation" not in {k.lower() for k in resp.headers}, (
            f"canonical {path} leaked Deprecation header"
        )
        assert "sunset" not in {k.lower() for k in resp.headers}, (
            f"canonical {path} leaked Sunset header"
        )


def test_unrelated_404_does_not_carry_deprecation_headers(
    client_with_run: tuple[TestClient, str],
) -> None:
    """A 404 on a path that only shares the ``/api`` prefix isn't a legacy endpoint.

    Paths like ``/api/v1abc`` or ``/apicruft`` are not registered routes; they must
    not pick up ``Deprecation``/``Sunset`` headers, or migration-metric clients
    would see false positives that drown out real legacy traffic.
    """
    client, _ = client_with_run
    for path in ("/api/v1abc", "/apicruft", "/api/does-not-exist"):
        resp = client.get(path)
        assert resp.status_code == 404, path
        assert "deprecation" not in {k.lower() for k in resp.headers}, path
        assert "sunset" not in {k.lower() for k in resp.headers}, path


def test_openapi_exposes_contract_schemas() -> None:
    """The OpenAPI schema names the contract types the web ``contract.ts`` aliases."""
    client = TestClient(api.app)
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    # The exact set the views import via web/src/contract.ts.
    expected = {
        "BenchReport",
        "Featured",
        "SuiteCase",
        "BackendProfile",
        "SolverMeta",
        "SpreadPt",
        "Point2D",
        "MultiDim",
        "Projection",
        # Plan D (1.3): data-driven panel layout contract.
        "PanelSpec",
        "PanelLayout",
    }
    assert expected <= set(schemas), f"missing from OpenAPI: {expected - set(schemas)}"
