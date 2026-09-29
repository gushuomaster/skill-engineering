from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from jsonschema import ValidationError

from engine.contracts import validate_contract
from engine.discovery_models import (
    CandidateGovernanceResult,
    CandidateGovernanceStatus,
    DiscoveryBundle,
    ImmutabilityStatus,
    ResolvedCandidate,
    SelectionRecord,
    SourceSearchReport,
    SourceSearchStatus,
)
from engine.discovery_serialization import (
    candidate_governance_result_from_data,
    canonical_record_digest,
    discovery_bundle_from_data,
)
from engine.serialization import to_data
from engine.skill_sources import SkillCandidate, SkillOrigin


NOW = "2026-09-29T00:00:00+00:00"


def _candidate() -> SkillCandidate:
    return SkillCandidate(
        candidate_id="openspace-cloud:" + "1" * 64,
        name="demo",
        description="Demo remote Skill",
        canonical_repository=None,
        content_digest=None,
        origins=(SkillOrigin(
            source_type="openspace-cloud",
            source_id="demo__clo_12345678",
            fetch_reference="demo__clo_12345678",
        ),),
        discovered_at=NOW,
    )


def _bundle() -> DiscoveryBundle:
    values = {
        "schema_version": "1.0",
        "discovery_id": "discovery-1",
        "query": "demo skill",
        "source_reports": (
            SourceSearchReport(
                "openspace-cloud",
                SourceSearchStatus.COMPLETE,
                (_candidate().candidate_id,),
                (),
            ),
        ),
        "candidates": (_candidate(),),
        "discovered_at": NOW,
    }
    return DiscoveryBundle(
        **values,
        bundle_digest=canonical_record_digest(values),
    )


def test_selection_record_requires_codex_rationale() -> None:
    with pytest.raises(ValueError, match="selection rationale must be nonblank"):
        SelectionRecord(
            schema_version="1.0",
            selection_id="selection-1",
            discovery_bundle_digest="a" * 64,
            selected_candidate_id=_candidate().candidate_id,
            selection_rationale=" ",
            selected_by="CODEX",
            selected_at=NOW,
            selection_record_digest="b" * 64,
        )


def test_discovery_bundle_round_trip_rejects_digest_tampering() -> None:
    bundle = _bundle()
    payload = to_data(bundle)

    assert discovery_bundle_from_data(payload) == bundle

    payload["query"] = "different query"
    with pytest.raises(ValueError, match="discovery bundle digest mismatch"):
        discovery_bundle_from_data(payload)


def test_resolved_candidate_rejects_revision_without_proof(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unproven candidate cannot claim a revision"):
        ResolvedCandidate(
            schema_version="1.0",
            resolution_id="resolution-1",
            discovery_bundle_digest="a" * 64,
            selection_record_digest="b" * 64,
            candidate_id=_candidate().candidate_id,
            name="demo",
            source_type="openspace-cloud",
            source_id="demo__clo_12345678",
            source_uri=None,
            fetch_reference="demo__clo_12345678",
            resolved_revision="main",
            immutability_status=ImmutabilityStatus.UNPROVEN,
            immutability_evidence=("no immutable revision",),
            quarantine_path=tmp_path,
            candidate_digest="c" * 64,
            resolver="openspace-download-skill",
            resolved_at=NOW,
            resolution_record_digest="d" * 64,
        )


def test_candidate_receipt_schema_rejects_non_pass_gate() -> None:
    payload = {
        "schema_version": "1.0",
        "receipt_id": "receipt-1",
        "governance_status": "APPROVED",
        "candidate_id": _candidate().candidate_id,
        "source_type": "openspace-cloud",
        "source_id": "demo__clo_12345678",
        "source_uri": None,
        "resolved_revision": "revision-1",
        "candidate_digest": "a" * 64,
        "resolution_record_digest": "b" * 64,
        "discovery_bundle_digest": "c" * 64,
        "selection_id": "selection-1",
        "selection_rationale": "Matches the requested workflow.",
        "selection_record_digest": "d" * 64,
        "inspection_id": "inspection-1",
        "coverage_status": "FULL",
        "gate_verdict": "FAIL",
        "managed_completion_receipt_digest": "e" * 64,
        "engine_version": "1.1.0",
        "plugin_version": "1.1.0+codex.20260929000000",
        "issued_at": NOW,
        "receipt_digest": "f" * 64,
    }

    with pytest.raises(ValidationError):
        validate_contract("candidate-governance-receipt", payload)


def test_incomplete_result_allows_unresolved_candidate_and_detects_tampering() -> None:
    values = {
        "schema_version": "1.0",
        "result_id": "result-1",
        "governance_status": CandidateGovernanceStatus.INCOMPLETE,
        "candidate_id": _candidate().candidate_id,
        "candidate_digest": None,
        "discovery_bundle_digest": "a" * 64,
        "selection_record_digest": "b" * 64,
        "inspection_id": None,
        "coverage_status": None,
        "gate_verdict": None,
        "blocking_reasons": ("download failed",),
        "receipt": None,
        "finalized_at": NOW,
    }
    result = CandidateGovernanceResult(
        **values,
        result_digest=canonical_record_digest(values),
    )
    payload = to_data(result)

    assert candidate_governance_result_from_data(payload) == result

    tampered = replace(result, blocking_reasons=("different",))
    with pytest.raises(ValueError, match="candidate governance result digest mismatch"):
        candidate_governance_result_from_data(to_data(tampered))
