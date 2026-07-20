from oracles.engine import build_report

# import build_catalog and get_backends from the SAME modules engine.py imports them from:
from oracles.cases import build_catalog  # engine.py imports from oracles.cases
from oracles.backends import get_backends  # engine.py imports from oracles.backends


def test_build_report_attaches_inference_block():
    catalog = build_catalog(20260603)[:2]
    backends = [b for b in get_backends() if b.name in {"lmfit", "spectrafit"}]
    report = build_report(n_reps=2, n_mc=4, catalog=catalog, backends=backends)
    assert report.inference is not None
    assert report.inference.config.bootstrap_b > 0
    assert len(report.inference.cases) >= 1
    c = report.inference.cases[0]
    assert c.speedup_ci.lo <= c.speedup_ci.point <= c.speedup_ci.hi
    assert len(report.inference.equivalence) >= 1
