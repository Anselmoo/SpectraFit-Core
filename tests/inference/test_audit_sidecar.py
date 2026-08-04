import json

from oracles.cli import app
from typer.testing import CliRunner


def test_run_writes_audit_sidecar_with_full_arrays(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # --backends spectrafit,scipy-ls-lm: this only checks the audit.json
    # sidecar's shape (key names + array-length agreement on one record), not
    # cross-backend behavior, so it doesn't need build_report()'s default full
    # 139-case x 6-backend sweep. Unscoped, this single test took ~58min wall
    # time on its own (measured: 3463s of a 3470s full-suite run) -- pytest-
    # xdist can't split one test across workers, so that was a hard floor no
    # amount of worker/thread-count tuning could reduce. A single spectrafit-
    # only backend dropped it to ~1min but also dropped coverage below the 94%
    # gate: engine.py's backend-failure-handling branches (a non-spectrafit
    # backend being unsupported/failing on some catalog case) and
    # _scipy_ls.py's own internal branches only run when a second, non-
    # spectrafit backend is present. scipy-ls-lm restores that coverage while
    # staying far cheaper than the full 6-backend sweep.
    res = CliRunner().invoke(
        app,
        ["run", "--reps", "2", "--mc", "3", "--backends", "spectrafit,scipy-ls-lm"],
    )
    assert res.exit_code == 0, res.output
    sidecars = list(tmp_path.rglob("audit.json"))
    assert sidecars, "no audit.json sidecar written"
    records = json.loads(sidecars[0].read_text())
    assert isinstance(records, list) and records
    r = records[0]
    # each record carries the FULL arrays + stored metrics for exact recompute
    for key in (
        "case",
        "backend",
        "y",
        "fit",
        "sigma",
        "dof",
        "storedR2",
        "storedChi2Red",
        "storedRmse",
    ):
        assert key in r, f"missing {key}"
    assert len(r["y"]) == len(r["fit"]) and len(r["y"]) > 0
