"""A7 — wire W8: NIST StRD certified-value validation.

W8 passes iff all four NIST StRD datasets (Gauss1/2/3 + Lanczos1) reproduce the
certified values to ≥ the sig-fig threshold. It is the independent external-
replication evidence the honest RUNG_5 is reserved for.
"""

from __future__ import annotations

from oracles.audit.wires import ALL_WIRES, wire_w8_nist_certified_validation


def test_w8_passes_when_all_datasets_reproduce_certified() -> None:
    out = wire_w8_nist_certified_validation()
    assert out[0].wire_id == "W8"
    assert out[0].status == "pass"
    assert "sig fig" in out[0].evidence.lower()
    # The four dataset names are surfaced in the evidence string.
    for token in ("Gauss1", "Gauss2", "Gauss3", "Lanczos1"):
        assert token in out[0].evidence


def test_w8_is_registered() -> None:
    assert wire_w8_nist_certified_validation in ALL_WIRES


def test_w8_records_min_sig_figs_detail() -> None:
    out = wire_w8_nist_certified_validation()
    assert "min_sig_figs" in out[0].details
    min_sig_figs = out[0].details["min_sig_figs"]
    assert isinstance(min_sig_figs, (int, float))
    assert min_sig_figs >= 4.0
