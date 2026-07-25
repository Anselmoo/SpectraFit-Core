"""End-to-end: running the audit produces a trust.json next to manifest.json
and the embedded BenchReport.trust_block."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oracles.audit.runner import run_audit
from oracles.reports import REPORTS_ROOT
from oracles.trust_ledger import TrustLedger


def _latest_run_dir() -> Path | None:
    runs = sorted(REPORTS_ROOT.glob("benchmark/*"), reverse=True)
    return runs[0] if runs else None


@pytest.mark.skipif(_latest_run_dir() is None, reason="no run on disk")
def test_audit_writes_trust_json_and_inlines_block():
    run_dir = _latest_run_dir()
    assert run_dir is not None
    ledger = run_audit(run_dir)
    assert isinstance(ledger, TrustLedger)
    assert (run_dir / "trust.json").exists()

    # The embedded block is also written back into results.json.
    results = json.loads((run_dir / "results.json").read_text())
    embedded = results.get("trust_block") or results.get("trustBlock")
    assert embedded is not None
    assert embedded["rung"] >= 1
