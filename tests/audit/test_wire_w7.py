from oracles.audit.wires import ALL_WIRES, wire_w7_inference_validity


def test_w7_passes_seeded_ci_reproduces():
    out = wire_w7_inference_validity()
    assert out[0].wire_id == "W7"
    assert out[0].status == "pass"


def test_w7_is_registered():
    assert wire_w7_inference_validity in ALL_WIRES


def test_w7_reports_skipped_not_vacuous_pass_when_no_inference_cases():
    """A single-backend/self-baseline run has no inference.cases -- W7 must report
    'skipped', not a vacuous 'pass' disconnected from this run's actual data (the
    write-time claim-integrity guard in oracles.audit.runner otherwise expects
    inference.speedup_ci/delta_r2_ci to resolve and crashes when they don't -- see
    DECISIONS.md / the plan's Task 2 finding)."""
    out = wire_w7_inference_validity(has_inference_cases=False)
    assert out[0].wire_id == "W7"
    assert out[0].status == "skipped"


def test_w7_default_and_explicit_true_still_pass_seeded_ci():
    """Backward-compat: the direct-call default (no arg) and has_inference_cases=True
    both still run the real reproducibility self-check, unchanged from
    test_w7_passes_seeded_ci_reproduces's existing expectation."""
    assert wire_w7_inference_validity()[0].status == "pass"
    assert wire_w7_inference_validity(has_inference_cases=True)[0].status == "pass"
