"""Bind resolved candidates to the existing Gate and completion receipt."""

from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Callable, Sequence
from uuid import uuid4

from engine.discovery_models import (
    CandidateGovernanceReceipt,
    CandidateGovernanceResult,
    CandidateGovernanceStatus,
    ImmutabilityStatus,
    ResolvedCandidate,
    SelectionRecord,
)
from engine.discovery_serialization import canonical_record_digest
from engine.inventory import digest_tree
from engine.managed_completion import validate_completion_receipt
from engine.models import GateResult, GateVerdict, ManagedCompletionReceipt
from engine.orchestrator import InspectionBundle
from engine.version import package_version


class CandidateChangedError(ValueError):
    """Raised when quarantine content or its bound records changed."""


def _assert_record_digest(record: object, expected: str, field: str) -> None:
    actual = canonical_record_digest(record, omit=frozenset({field}))
    if not hmac.compare_digest(actual, expected):
        raise CandidateChangedError(f"{field} mismatch")


def _result(
    status: CandidateGovernanceStatus,
    resolved: ResolvedCandidate,
    inspection: InspectionBundle,
    gate: GateResult,
    reasons: Sequence[str],
    receipt: CandidateGovernanceReceipt | None,
    clock: Callable[[], datetime],
) -> CandidateGovernanceResult:
    values = {
        "schema_version": "1.0",
        "result_id": str(uuid4()),
        "governance_status": status,
        "candidate_id": resolved.candidate_id,
        "candidate_digest": resolved.candidate_digest,
        "discovery_bundle_digest": resolved.discovery_bundle_digest,
        "selection_record_digest": resolved.selection_record_digest,
        "inspection_id": inspection.inspection_id,
        "coverage_status": gate.coverage_status,
        "gate_verdict": gate.verdict,
        "blocking_reasons": tuple(reasons),
        "receipt": receipt,
        "finalized_at": clock().astimezone(timezone.utc).isoformat(),
    }
    return CandidateGovernanceResult(
        **values,
        result_digest=canonical_record_digest(values),
    )


def incomplete_candidate_result(
    candidate_id: str,
    reasons: Sequence[str],
    *,
    candidate_digest: str | None,
    discovery_bundle_digest: str | None,
    selection_record_digest: str | None,
    clock: Callable[[], datetime],
) -> CandidateGovernanceResult:
    normalized = tuple(item.strip() for item in reasons if item.strip())
    if not normalized:
        raise ValueError("incomplete candidate result requires a reason")
    values = {
        "schema_version": "1.0",
        "result_id": str(uuid4()),
        "governance_status": CandidateGovernanceStatus.INCOMPLETE,
        "candidate_id": candidate_id,
        "candidate_digest": candidate_digest,
        "discovery_bundle_digest": discovery_bundle_digest,
        "selection_record_digest": selection_record_digest,
        "inspection_id": None,
        "coverage_status": None,
        "gate_verdict": None,
        "blocking_reasons": normalized,
        "receipt": None,
        "finalized_at": clock().astimezone(timezone.utc).isoformat(),
    }
    return CandidateGovernanceResult(
        **values,
        result_digest=canonical_record_digest(values),
    )


def finalize_candidate(
    resolved: ResolvedCandidate,
    selection: SelectionRecord,
    inspection: InspectionBundle,
    gate: GateResult,
    receipt: ManagedCompletionReceipt | None,
    *,
    plugin_version: str,
    clock: Callable[[], datetime],
) -> CandidateGovernanceResult:
    _assert_record_digest(
        selection, selection.selection_record_digest, "selection_record_digest"
    )
    _assert_record_digest(
        resolved, resolved.resolution_record_digest, "resolution_record_digest"
    )
    if digest_tree(resolved.quarantine_path) != resolved.candidate_digest:
        raise CandidateChangedError("quarantine candidate changed after resolution")
    if selection.discovery_bundle_digest != resolved.discovery_bundle_digest:
        raise ValueError("selection and resolved candidate reference different bundles")
    if selection.selected_candidate_id != resolved.candidate_id:
        raise ValueError("selection and resolved candidate IDs do not match")
    if selection.selection_record_digest != resolved.selection_record_digest:
        raise ValueError("selection and resolved record digests do not match")
    if receipt is not None and inspection.inspection_id != receipt.inspection_id:
        raise ValueError("inspection and managed receipt do not match")

    if gate.verdict is GateVerdict.FAIL:
        reasons = gate.blocking_findings or ("existing Quality Gate failed",)
        return _result(
            CandidateGovernanceStatus.BLOCKED,
            resolved,
            inspection,
            gate,
            reasons,
            None,
            clock,
        )
    if resolved.immutability_status is not ImmutabilityStatus.PROVEN:
        return _result(
            CandidateGovernanceStatus.INCOMPLETE,
            resolved,
            inspection,
            gate,
            ("immutable revision unproven",),
            None,
            clock,
        )
    if gate.verdict is not GateVerdict.PASS or receipt is None:
        return _result(
            CandidateGovernanceStatus.INCOMPLETE,
            resolved,
            inspection,
            gate,
            ("formal PASS receipt missing",),
            None,
            clock,
        )

    validate_completion_receipt(receipt)
    if (
        gate.verdict is not receipt.gate_verdict
        or gate.outcome is not receipt.gate_outcome
        or gate.coverage_status is not receipt.coverage_status
    ):
        raise ValueError("Gate and managed receipt do not describe the same decision")
    if receipt.candidate_digest != resolved.candidate_digest:
        raise CandidateChangedError(
            "managed receipt is bound to a different candidate"
        )
    receipt_values = {
        "schema_version": "1.0",
        "receipt_id": str(uuid4()),
        "governance_status": CandidateGovernanceStatus.APPROVED,
        "candidate_id": resolved.candidate_id,
        "source_type": resolved.source_type,
        "source_id": resolved.source_id,
        "source_uri": resolved.source_uri,
        "resolved_revision": resolved.resolved_revision,
        "candidate_digest": resolved.candidate_digest,
        "resolution_record_digest": resolved.resolution_record_digest,
        "discovery_bundle_digest": resolved.discovery_bundle_digest,
        "selection_id": selection.selection_id,
        "selection_rationale": selection.selection_rationale,
        "selection_record_digest": resolved.selection_record_digest,
        "inspection_id": inspection.inspection_id,
        "coverage_status": receipt.coverage_status,
        "gate_verdict": gate.verdict,
        "managed_completion_receipt_digest": canonical_record_digest(receipt),
        "engine_version": package_version(),
        "plugin_version": plugin_version,
        "issued_at": clock().astimezone(timezone.utc).isoformat(),
    }
    candidate_receipt = CandidateGovernanceReceipt(
        **receipt_values,
        receipt_digest=canonical_record_digest(receipt_values),
    )
    return _result(
        CandidateGovernanceStatus.APPROVED,
        resolved,
        inspection,
        gate,
        (),
        candidate_receipt,
        clock,
    )


__all__ = [
    "CandidateChangedError",
    "finalize_candidate",
    "incomplete_candidate_result",
]
