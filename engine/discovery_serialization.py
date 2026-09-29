"""Schema-bound serialization for discovery and candidate governance records."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any, Mapping

from engine.contracts import validate_contract
from engine.discovery_models import (
    CandidateGovernanceReceipt,
    CandidateGovernanceResult,
    CandidateGovernanceStatus,
    DiscoveryBundle,
    ImmutabilityStatus,
    ResolvedCandidate,
    SelectionRecord,
    SourceSearchReport,
    SourceSearchStatus,
)
from engine.models import CoverageStatus, GateVerdict
from engine.serialization import to_data
from engine.skill_sources import CandidateSignal, SkillCandidate, SkillOrigin


def canonical_record_digest(
    value: object,
    *,
    omit: frozenset[str] = frozenset(),
) -> str:
    payload = to_data(value)
    if isinstance(payload, dict):
        payload = {key: item for key, item in payload.items() if key not in omit}
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _assert_digest(
    record: object,
    expected: str,
    field: str,
    label: str,
) -> None:
    actual = canonical_record_digest(record, omit=frozenset({field}))
    if not hmac.compare_digest(actual, expected):
        raise ValueError(f"{label} digest mismatch")


def _signal(payload: Mapping[str, Any]) -> CandidateSignal:
    return CandidateSignal(payload["name"], payload["value"])


def _origin(payload: Mapping[str, Any]) -> SkillOrigin:
    return SkillOrigin(
        source_type=payload["source_type"],
        source_id=payload["source_id"],
        source_url=payload["source_url"],
        fetch_reference=payload["fetch_reference"],
        publisher=payload["publisher"],
        version=payload["version"],
        revision=payload["revision"],
        trust_signals=tuple(_signal(item) for item in payload["trust_signals"]),
        popularity_signals=tuple(
            _signal(item) for item in payload["popularity_signals"]
        ),
        quality_signals=tuple(_signal(item) for item in payload["quality_signals"]),
    )


def skill_candidate_from_data(payload: Mapping[str, Any]) -> SkillCandidate:
    return SkillCandidate(
        candidate_id=payload["candidate_id"],
        name=payload["name"],
        description=payload["description"],
        canonical_repository=payload["canonical_repository"],
        content_digest=payload["content_digest"],
        origins=tuple(_origin(item) for item in payload["origins"]),
        discovered_at=payload["discovered_at"],
    )


def discovery_bundle_from_data(payload: dict[str, Any]) -> DiscoveryBundle:
    validate_contract("discovery-bundle", payload)
    bundle = DiscoveryBundle(
        schema_version=payload["schema_version"],
        discovery_id=payload["discovery_id"],
        query=payload["query"],
        source_reports=tuple(
            SourceSearchReport(
                item["source_type"],
                SourceSearchStatus(item["status"]),
                tuple(item["candidate_ids"]),
                tuple(item["errors"]),
            )
            for item in payload["source_reports"]
        ),
        candidates=tuple(skill_candidate_from_data(item) for item in payload["candidates"]),
        discovered_at=payload["discovered_at"],
        bundle_digest=payload["bundle_digest"],
    )
    _assert_digest(bundle, bundle.bundle_digest, "bundle_digest", "discovery bundle")
    return bundle


def selection_record_from_data(payload: dict[str, Any]) -> SelectionRecord:
    validate_contract("selection-record", payload)
    record = SelectionRecord(**payload)
    _assert_digest(
        record,
        record.selection_record_digest,
        "selection_record_digest",
        "selection record",
    )
    return record


def resolved_candidate_from_data(payload: dict[str, Any]) -> ResolvedCandidate:
    validate_contract("resolved-candidate", payload)
    record = ResolvedCandidate(
        **{
            **payload,
            "immutability_status": ImmutabilityStatus(payload["immutability_status"]),
            "immutability_evidence": tuple(payload["immutability_evidence"]),
            "quarantine_path": Path(payload["quarantine_path"]),
        }
    )
    _assert_digest(
        record,
        record.resolution_record_digest,
        "resolution_record_digest",
        "resolved candidate",
    )
    return record


def candidate_governance_receipt_from_data(
    payload: dict[str, Any],
) -> CandidateGovernanceReceipt:
    validate_contract("candidate-governance-receipt", payload)
    receipt = CandidateGovernanceReceipt(
        **{
            **payload,
            "governance_status": CandidateGovernanceStatus(payload["governance_status"]),
            "coverage_status": CoverageStatus(payload["coverage_status"]),
            "gate_verdict": GateVerdict(payload["gate_verdict"]),
        }
    )
    _assert_digest(receipt, receipt.receipt_digest, "receipt_digest", "candidate receipt")
    return receipt


def candidate_governance_result_from_data(
    payload: dict[str, Any],
) -> CandidateGovernanceResult:
    validate_contract("candidate-governance-result", payload)
    receipt_payload = payload["receipt"]
    result = CandidateGovernanceResult(
        schema_version=payload["schema_version"],
        result_id=payload["result_id"],
        governance_status=CandidateGovernanceStatus(payload["governance_status"]),
        candidate_id=payload["candidate_id"],
        candidate_digest=payload["candidate_digest"],
        discovery_bundle_digest=payload["discovery_bundle_digest"],
        selection_record_digest=payload["selection_record_digest"],
        inspection_id=payload["inspection_id"],
        coverage_status=(
            CoverageStatus(payload["coverage_status"])
            if payload["coverage_status"] is not None
            else None
        ),
        gate_verdict=(
            GateVerdict(payload["gate_verdict"])
            if payload["gate_verdict"] is not None
            else None
        ),
        blocking_reasons=tuple(payload["blocking_reasons"]),
        receipt=(
            candidate_governance_receipt_from_data(receipt_payload)
            if receipt_payload is not None
            else None
        ),
        finalized_at=payload["finalized_at"],
        result_digest=payload["result_digest"],
    )
    _assert_digest(
        result,
        result.result_digest,
        "result_digest",
        "candidate governance result",
    )
    return result


__all__ = [
    "candidate_governance_receipt_from_data",
    "candidate_governance_result_from_data",
    "canonical_record_digest",
    "discovery_bundle_from_data",
    "resolved_candidate_from_data",
    "selection_record_from_data",
    "skill_candidate_from_data",
]
