"""Immutable records for remote Skill discovery and candidate governance."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from engine.models import CoverageStatus, GateVerdict
from engine.skill_sources import SkillCandidate


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _require_digest(name: str, value: str | None) -> None:
    if value is not None and not _is_sha256(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


class SourceSearchStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class ImmutabilityStatus(StrEnum):
    PROVEN = "PROVEN"
    UNPROVEN = "UNPROVEN"


class CandidateGovernanceStatus(StrEnum):
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class SourceSearchReport:
    source_type: str
    status: SourceSearchStatus
    candidate_ids: tuple[str, ...]
    errors: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.source_type.strip():
            raise ValueError("source type must be nonblank")
        if self.status is SourceSearchStatus.COMPLETE and self.errors:
            raise ValueError("complete source report cannot contain errors")
        if self.status is SourceSearchStatus.INCOMPLETE and not self.errors:
            raise ValueError("incomplete source report requires an error")


@dataclass(frozen=True, slots=True)
class DiscoveryBundle:
    schema_version: str
    discovery_id: str
    query: str
    source_reports: tuple[SourceSearchReport, ...]
    candidates: tuple[SkillCandidate, ...]
    discovered_at: str
    bundle_digest: str

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("discovery query must be nonblank")
        _require_digest("bundle_digest", self.bundle_digest)


@dataclass(frozen=True, slots=True)
class SelectionRecord:
    schema_version: str
    selection_id: str
    discovery_bundle_digest: str
    selected_candidate_id: str
    selection_rationale: str
    selected_by: str
    selected_at: str
    selection_record_digest: str

    def __post_init__(self) -> None:
        if not self.selection_rationale.strip():
            raise ValueError("selection rationale must be nonblank")
        if self.selected_by != "CODEX":
            raise ValueError("candidate selection must be authored by CODEX")
        _require_digest("discovery_bundle_digest", self.discovery_bundle_digest)
        _require_digest("selection_record_digest", self.selection_record_digest)


@dataclass(frozen=True, slots=True)
class ResolvedCandidate:
    schema_version: str
    resolution_id: str
    discovery_bundle_digest: str
    selection_record_digest: str
    candidate_id: str
    name: str
    source_type: str
    source_id: str
    source_uri: str | None
    fetch_reference: str
    resolved_revision: str | None
    immutability_status: ImmutabilityStatus
    immutability_evidence: tuple[str, ...]
    quarantine_path: Path
    candidate_digest: str
    resolver: str
    resolved_at: str
    resolution_record_digest: str

    def __post_init__(self) -> None:
        if self.immutability_status is ImmutabilityStatus.PROVEN:
            if self.resolved_revision is None or not self.resolved_revision.strip():
                raise ValueError("proven candidate requires a resolved revision")
        elif self.resolved_revision is not None:
            raise ValueError("unproven candidate cannot claim a revision")
        if not self.immutability_evidence:
            raise ValueError("immutability assessment requires evidence")
        for name in (
            "discovery_bundle_digest",
            "selection_record_digest",
            "candidate_digest",
            "resolution_record_digest",
        ):
            _require_digest(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class CandidateGovernanceReceipt:
    schema_version: str
    receipt_id: str
    governance_status: CandidateGovernanceStatus
    candidate_id: str
    source_type: str
    source_id: str
    source_uri: str | None
    resolved_revision: str
    candidate_digest: str
    resolution_record_digest: str
    discovery_bundle_digest: str
    selection_id: str
    selection_rationale: str
    selection_record_digest: str
    inspection_id: str
    coverage_status: CoverageStatus
    gate_verdict: GateVerdict
    managed_completion_receipt_digest: str
    engine_version: str
    plugin_version: str
    issued_at: str
    receipt_digest: str

    def __post_init__(self) -> None:
        if self.governance_status is not CandidateGovernanceStatus.APPROVED:
            raise ValueError("candidate receipt is APPROVED-only")
        if self.gate_verdict is not GateVerdict.PASS:
            raise ValueError("candidate receipt requires a PASS Gate")
        if self.coverage_status is not CoverageStatus.FULL:
            raise ValueError("candidate receipt requires FULL coverage")
        if not self.resolved_revision.strip():
            raise ValueError("candidate receipt requires an immutable revision")
        if not self.selection_rationale.strip():
            raise ValueError("candidate receipt requires a selection rationale")
        for name in (
            "candidate_digest",
            "resolution_record_digest",
            "discovery_bundle_digest",
            "selection_record_digest",
            "managed_completion_receipt_digest",
            "receipt_digest",
        ):
            _require_digest(name, getattr(self, name))


@dataclass(frozen=True, slots=True)
class CandidateGovernanceResult:
    schema_version: str
    result_id: str
    governance_status: CandidateGovernanceStatus
    candidate_id: str
    candidate_digest: str | None
    discovery_bundle_digest: str | None
    selection_record_digest: str | None
    inspection_id: str | None
    coverage_status: CoverageStatus | None
    gate_verdict: GateVerdict | None
    blocking_reasons: tuple[str, ...]
    receipt: CandidateGovernanceReceipt | None
    finalized_at: str
    result_digest: str

    def __post_init__(self) -> None:
        if self.governance_status is CandidateGovernanceStatus.APPROVED:
            if self.receipt is None:
                raise ValueError("approved result requires a receipt")
            if self.gate_verdict is not GateVerdict.PASS:
                raise ValueError("approved result requires a PASS Gate")
        else:
            if self.receipt is not None:
                raise ValueError("non-approved result cannot contain a receipt")
            if not self.blocking_reasons:
                raise ValueError("non-approved result requires a reason")
        for name in (
            "candidate_digest",
            "discovery_bundle_digest",
            "selection_record_digest",
            "result_digest",
        ):
            _require_digest(name, getattr(self, name))


__all__ = [
    "CandidateGovernanceReceipt",
    "CandidateGovernanceResult",
    "CandidateGovernanceStatus",
    "DiscoveryBundle",
    "ImmutabilityStatus",
    "ResolvedCandidate",
    "SelectionRecord",
    "SourceSearchReport",
    "SourceSearchStatus",
]
