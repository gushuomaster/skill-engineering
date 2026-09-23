"""Digest-bound managed completion receipts and target status."""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from engine.inventory import digest_tree
from engine.models import (
    CapabilityPreservationStatus,
    CoverageStatus,
    GateOutcome,
    GateVerdict,
    ManagedCompletionReceipt,
    ManagedOperationStatus,
    ManagedStatusResult,
)

if TYPE_CHECKING:
    from engine.orchestrator import EngineeringOutcome


def _canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {field.name: _canonical(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def _digest(value: Any) -> str:
    encoded = json.dumps(
        _canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_completion_receipt(
    receipt: ManagedCompletionReceipt,
    outcome: EngineeringOutcome | None = None,
) -> None:
    if (
        not receipt.formal_completion
        or receipt.gate_verdict is not GateVerdict.PASS
        or receipt.gate_outcome not in {
            GateOutcome.READY_TO_APPLY,
            GateOutcome.AUDIT_COMPLETE_VALID,
        }
    ):
        raise ValueError("formal inspection and Gate evidence are required")
    if receipt.coverage_status is not CoverageStatus.FULL:
        raise ValueError("formal completion requires FULL coverage")
    if receipt.capability_preservation is not CapabilityPreservationStatus.CAPABILITY_PRESERVED:
        raise ValueError("formal completion requires capability preservation")
    if outcome is None:
        return
    expected = completion_receipt(outcome)
    if receipt != expected:
        raise ValueError("completion receipt does not match the validated outcome")


def completion_receipt(outcome: EngineeringOutcome) -> ManagedCompletionReceipt:
    validation = outcome.validation
    confirmation = outcome.semantic_confirmation
    if validation is None or confirmation is None:
        raise ValueError("formal completion requires validation and semantic confirmation")
    if validation.candidate_capability_digest is None:
        raise ValueError("formal completion requires a candidate capability manifest")
    preservation = validation.capability_preservation
    if preservation is None:
        raise ValueError("formal completion requires capability preservation evidence")
    formal = (
        outcome.gate_result.verdict is GateVerdict.PASS
        and outcome.gate_result.outcome in {
            GateOutcome.READY_TO_APPLY,
            GateOutcome.AUDIT_COMPLETE_VALID,
        }
        and validation.coverage_status is CoverageStatus.FULL
        and preservation is CapabilityPreservationStatus.CAPABILITY_PRESERVED
    )
    receipt = ManagedCompletionReceipt(
        validation.inspection_id,
        validation.intent,
        validation.baseline_digest,
        validation.artifact_digest,
        validation.baseline_capability_digest,
        validation.candidate_capability_digest,
        _digest(validation),
        _digest(confirmation),
        validation.coverage_status,
        preservation,
        outcome.gate_result.verdict,
        outcome.gate_result.outcome,
        formal,
    )
    if formal:
        validate_completion_receipt(receipt)
    return receipt


def managed_status(
    target: Path,
    receipt: ManagedCompletionReceipt | None,
) -> ManagedStatusResult:
    resolved = target.resolve(strict=True)
    target_digest = digest_tree(resolved)
    if receipt is None:
        return ManagedStatusResult(
            ManagedOperationStatus.UNMANAGED_CHANGE,
            False,
            target_digest,
            "no managed completion receipt was supplied",
        )
    try:
        validate_completion_receipt(receipt)
    except ValueError as exc:
        return ManagedStatusResult(
            ManagedOperationStatus.AUDIT_INCOMPLETE,
            False,
            target_digest,
            str(exc),
        )
    if receipt.candidate_digest != target_digest:
        return ManagedStatusResult(
            ManagedOperationStatus.UNMANAGED_CHANGE,
            False,
            target_digest,
            "receipt is bound to a different artifact digest",
        )
    return ManagedStatusResult(
        ManagedOperationStatus.MANAGED,
        True,
        target_digest,
        "receipt matches the current artifact",
    )


__all__ = ["completion_receipt", "managed_status", "validate_completion_receipt"]
