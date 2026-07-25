"""Wire W4 — every /api endpoint response must validate against the contract."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from oracles.api import app
from oracles.bench_contract import BenchReport


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_get_api_report_validates(client: TestClient) -> None:
    """GET /api/report response validates as BenchReport."""
    response = client.get("/api/report")
    # The endpoint may return 404 if no run is on disk — that is acceptable.
    if response.status_code == 404:
        pytest.skip("no benchmark run on disk; /api/report returns 404")
    assert response.status_code == 200
    BenchReport.model_validate(response.json())


def test_get_api_report_by_run_id_validates(client: TestClient) -> None:
    """GET /api/report/{run_id} response validates as BenchReport."""
    # First, get the list of available runs.
    response = client.get("/api/runs")
    assert response.status_code == 200
    runs = response.json()

    if not runs:
        pytest.skip("no benchmark runs on disk; /api/runs is empty")

    # Pick the first run and fetch its report.
    run_id = runs[0]
    response = client.get(f"/api/report/{run_id}")
    assert response.status_code == 200
    BenchReport.model_validate(response.json())


def test_get_api_runs_returns_list(client: TestClient) -> None:
    """GET /api/runs returns a list of run ids."""
    response = client.get("/api/runs")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
