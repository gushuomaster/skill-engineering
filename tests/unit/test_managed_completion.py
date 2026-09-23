from dataclasses import replace
from pathlib import Path

import pytest

from engine.managed_completion import managed_status, validate_completion_receipt
from engine.models import (
    CapabilityPreservationStatus,
    CoverageStatus,
    GateOutcome,
    GateVerdict,
    Intent,
    ManagedCompletionReceipt,
    ManagedOperationStatus,
)


def _receipt(**overrides: object) -> ManagedCompletionReceipt:
    values = {
        "inspection_id": "inspection-1",
        "operation_mode": Intent.TARGETED_REPAIR,
        "source_digest": "a" * 64,
        "candidate_digest": "b" * 64,
        "baseline_capability_digest": "c" * 64,
        "candidate_capability_digest": "d" * 64,
        "validation_bundle_digest": "e" * 64,
        "semantic_confirmation_digest": "f" * 64,
        "coverage_status": CoverageStatus.FULL,
        "capability_preservation": CapabilityPreservationStatus.CAPABILITY_PRESERVED,
        "gate_verdict": GateVerdict.PASS,
        "gate_outcome": GateOutcome.READY_TO_APPLY,
        "formal_completion": True,
    }
    values.update(overrides)
    return ManagedCompletionReceipt(**values)


def test_status_without_inspection_receipt_is_unmanaged_change(tmp_path: Path) -> None:
    target = tmp_path / "skill"
    target.mkdir()
    (target / "SKILL.md").write_text("skill", encoding="utf-8")

    result = managed_status(target, receipt=None)

    assert result.status is ManagedOperationStatus.UNMANAGED_CHANGE
    assert result.formal_completion is False


def test_target_pytest_pass_cannot_replace_gate() -> None:
    receipt = _receipt(
        gate_verdict=GateVerdict.INCOMPLETE,
        gate_outcome=GateOutcome.INCOMPLETE,
        formal_completion=True,
    )

    with pytest.raises(
        ValueError,
        match="formal inspection and Gate evidence are required",
    ):
        validate_completion_receipt(receipt)


def test_completion_receipt_requires_full_coverage_and_preservation() -> None:
    with pytest.raises(ValueError, match="FULL coverage"):
        validate_completion_receipt(
            replace(_receipt(), coverage_status=CoverageStatus.COMPATIBILITY)
        )

    with pytest.raises(ValueError, match="capability preservation"):
        validate_completion_receipt(
            replace(
                _receipt(),
                capability_preservation=CapabilityPreservationStatus.AUTHORIZATION_REQUIRED,
            )
        )
