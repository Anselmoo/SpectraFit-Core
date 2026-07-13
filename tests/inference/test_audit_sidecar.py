import json
from typer.testing import CliRunner
from oracles.cli import app


def test_run_writes_audit_sidecar_with_full_arrays(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = CliRunner().invoke(app, ["run", "--reps", "2", "--mc", "3"])
    assert res.exit_code == 0, res.output
    sidecars = list(tmp_path.rglob("audit.json"))
    assert sidecars, "no audit.json sidecar written"
    records = json.loads(sidecars[0].read_text())
    assert isinstance(records, list) and records
    r = records[0]
    # each record carries the FULL arrays + stored metrics for exact recompute
    for key in ("case", "backend", "y", "fit", "sigma", "dof",
                "storedR2", "storedChi2Red", "storedRmse"):
        assert key in r, f"missing {key}"
    assert len(r["y"]) == len(r["fit"]) and len(r["y"]) > 0
