from oracles.audit.wires import wire_w7_inference_validity, ALL_WIRES


def test_w7_passes_seeded_ci_reproduces():
    out = wire_w7_inference_validity()
    assert out[0].wire_id == "W7"
    assert out[0].status == "pass"


def test_w7_is_registered():
    assert wire_w7_inference_validity in ALL_WIRES
