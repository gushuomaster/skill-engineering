from __future__ import annotations

import engine.candidate_contract as candidate_contract
from engine.inventory import digest_tree
from engine.managed_completion import (
    completion_receipt,
    managed_status,
    validate_completion_receipt,
)
from engine.models import (
    CapabilityPreservationStatus,
    CoverageStatus,
    GateOutcome,
    GateVerdict,
    ManagedCompletionReceipt,
)
from engine.orchestrator import PipelineOrchestrator
from engine.serialization import (
    completion_receipt_from_data,
    confirmation_from_data,
    to_data,
    validation_from_data,
)


EXPECTED_EXPORTS = (
    "digest_tree",
    "completion_receipt",
    "managed_status",
    "validate_completion_receipt",
    "CapabilityPreservationStatus",
    "CoverageStatus",
    "GateOutcome",
    "GateVerdict",
    "ManagedCompletionReceipt",
    "PipelineOrchestrator",
    "completion_receipt_from_data",
    "confirmation_from_data",
    "to_data",
    "validation_from_data",
)


def test_candidate_contract_exports_only_the_host_candidate_boundary() -> None:
    assert candidate_contract.__all__ == EXPECTED_EXPORTS


def test_candidate_contract_preserves_original_object_identity() -> None:
    expected = {
        "digest_tree": digest_tree,
        "completion_receipt": completion_receipt,
        "managed_status": managed_status,
        "validate_completion_receipt": validate_completion_receipt,
        "CapabilityPreservationStatus": CapabilityPreservationStatus,
        "CoverageStatus": CoverageStatus,
        "GateOutcome": GateOutcome,
        "GateVerdict": GateVerdict,
        "ManagedCompletionReceipt": ManagedCompletionReceipt,
        "PipelineOrchestrator": PipelineOrchestrator,
        "completion_receipt_from_data": completion_receipt_from_data,
        "confirmation_from_data": confirmation_from_data,
        "to_data": to_data,
        "validation_from_data": validation_from_data,
    }

    assert {
        name: getattr(candidate_contract, name)
        for name in candidate_contract.__all__
    } == expected
