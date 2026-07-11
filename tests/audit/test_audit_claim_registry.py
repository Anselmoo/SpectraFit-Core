from __future__ import annotations

import pytest

from oracles.audit.claims import CLAIM_REGISTRY, Claim, register_claim


def test_register_claim_adds_to_registry():
    @register_claim
    class _Probe(Claim):
        claim_id = "probe.test"
        wire_id = "W1"
        source_field = "fake.path"
        description = "test claim"

    assert "probe.test" in CLAIM_REGISTRY
    del CLAIM_REGISTRY["probe.test"]


def test_register_claim_rejects_duplicate_id():
    @register_claim
    class _A(Claim):
        claim_id = "probe.dup"
        wire_id = "W1"
        source_field = "x"
        description = "x"

    with pytest.raises(ValueError, match="already registered"):
        @register_claim
        class _B(Claim):
            claim_id = "probe.dup"
            wire_id = "W2a"
            source_field = "y"
            description = "y"

    del CLAIM_REGISTRY["probe.dup"]


def test_claim_id_must_be_dotted_namespace():
    with pytest.raises(ValueError, match="dotted namespace"):
        @register_claim
        class _Bad(Claim):
            claim_id = "no_dot_here"
            wire_id = "W1"
            source_field = "x"
            description = "x"
