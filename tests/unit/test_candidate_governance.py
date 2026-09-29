from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.candidate_governance import (
    CandidateChangedError,
    finalize_candidate,
    incomplete_candidate_result,
)
from engine.discovery_models import (
    CandidateGovernanceStatus,
    ImmutabilityStatus,
    ResolvedCandidate,
    SelectionRecord,
)
from engine.discovery_serialization import canonical_record_digest
from engine.inventory import digest_tree
from engine.models import (
    CapabilityPreservationStatus,
    CoverageStatus,
    GateOutcome,
    GateResult,
    GateVerdict,
    Intent,
    ManagedCompletionReceipt,
)


NOW = "2026-09-29T00:00:00+00:00"


def fixed_clock() -> datetime:
    return datetime(2026, 9, 29, tzinfo=timezone.utc)


def selection() -> SelectionRecord:
    values = {
        "schema_version": "1.0",
        "selection_id": "selection-1",
        "discovery_bundle_digest": "a" * 64,
        "selected_candidate_id": "openspace-cloud:" + "1" * 64,
        "selection_rationale": "Best match for the requested workflow.",
        "selected_by": "CODEX",
        "selected_at": NOW,
    }
    return SelectionRecord(
        **values,
        selection_record_digest=canonical_record_digest(values),
    )


def resolved(tmp_path: Path, *, proven: bool) -> ResolvedCandidate:
    skill = tmp_path / ("proven" if proven else "unproven")
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo Skill.\n---\n",
        encoding="utf-8",
    )
    current_selection = selection()
    values = {
        "schema_version": "1.0",
        "resolution_id": "resolution-1",
        "discovery_bundle_digest": current_selection.discovery_bundle_digest,
        "selection_record_digest": current_selection.selection_record_digest,
        "candidate_id": current_selection.selected_candidate_id,
        "name": "demo",
        "source_type": "openspace-cloud",
        "source_id": "demo__clo_12345678",
        "source_uri": None,
        "fetch_reference": "demo__clo_12345678",
        "resolved_revision": "immutable-revision-1" if proven else None,
        "immutability_status": (
            ImmutabilityStatus.PROVEN if proven else ImmutabilityStatus.UNPROVEN
        ),
        "immutability_evidence": (
            "origin_revision=immutable-revision-1" if proven
            else "immutable revision unproven",
        ),
        "quarantine_path": skill,
        "candidate_digest": digest_tree(skill),
        "resolver": "openspace-download-skill",
        "resolved_at": NOW,
    }
    return ResolvedCandidate(
        **values,
        resolution_record_digest=canonical_record_digest(values),
    )


def gate(verdict: GateVerdict) -> GateResult:
    outcome = {
        GateVerdict.PASS: GateOutcome.AUDIT_COMPLETE_VALID,
        GateVerdict.FAIL: GateOutcome.AUDIT_COMPLETE_BLOCKING_FINDINGS,
        GateVerdict.INCOMPLETE: GateOutcome.AUDIT_INCOMPLETE,
    }[verdict]
    return GateResult(
        verdict,
        outcome,
        ("B04: candidate failed",) if verdict is GateVerdict.FAIL else (),
        (),
        "required=complete",
        "candidate evidence",
        True,
        False,
        "v1",
        CoverageStatus.FULL,
        CapabilityPreservationStatus.CAPABILITY_PRESERVED,
    )


def receipt(candidate_digest: str) -> ManagedCompletionReceipt:
    return ManagedCompletionReceipt(
        inspection_id="inspection-1",
        operation_mode=Intent.AUDIT,
        source_digest=candidate_digest,
        candidate_digest=candidate_digest,
        baseline_capability_digest="b" * 64,
        candidate_capability_digest="b" * 64,
        validation_bundle_digest="c" * 64,
        semantic_confirmation_digest="d" * 64,
        coverage_status=CoverageStatus.FULL,
        capability_preservation=CapabilityPreservationStatus.CAPABILITY_PRESERVED,
        gate_verdict=GateVerdict.PASS,
        gate_outcome=GateOutcome.AUDIT_COMPLETE_VALID,
        formal_completion=True,
    )


def inspection():
    return SimpleNamespace(inspection_id="inspection-1")


def test_pass_cannot_approve_unproven_revision(tmp_path: Path) -> None:
    current = resolved(tmp_path, proven=False)

    result = finalize_candidate(
        current,
        selection(),
        inspection(),
        gate(GateVerdict.PASS),
        receipt(current.candidate_digest),
        plugin_version="1.1.0+codex.20260929000000",
        clock=fixed_clock,
    )

    assert result.governance_status is CandidateGovernanceStatus.INCOMPLETE
    assert result.receipt is None


def test_pass_receipt_binds_revision_digest_selection_and_inspection(
    tmp_path: Path,
) -> None:
    current = resolved(tmp_path, proven=True)

    result = finalize_candidate(
        current,
        selection(),
        inspection(),
        gate(GateVerdict.PASS),
        receipt(current.candidate_digest),
        plugin_version="1.1.0+codex.20260929000000",
        clock=fixed_clock,
    )

    assert result.governance_status is CandidateGovernanceStatus.APPROVED
    assert result.receipt is not None
    assert result.receipt.resolved_revision == "immutable-revision-1"
    assert result.receipt.candidate_digest == current.candidate_digest
    assert result.receipt.selection_id == selection().selection_id
    assert result.receipt.inspection_id == "inspection-1"


def test_fail_maps_to_blocked_without_receipt(tmp_path: Path) -> None:
    current = resolved(tmp_path, proven=True)

    result = finalize_candidate(
        current,
        selection(),
        inspection(),
        gate(GateVerdict.FAIL),
        None,
        plugin_version="1.1.0+codex.20260929000000",
        clock=fixed_clock,
    )

    assert result.governance_status is CandidateGovernanceStatus.BLOCKED
    assert result.receipt is None
    assert result.blocking_reasons == ("B04: candidate failed",)


def test_candidate_change_invalidates_approval(tmp_path: Path) -> None:
    current = resolved(tmp_path, proven=True)
    (current.quarantine_path / "changed.txt").write_text("changed", encoding="utf-8")

    with pytest.raises(CandidateChangedError):
        finalize_candidate(
            current,
            selection(),
            inspection(),
            gate(GateVerdict.PASS),
            receipt(current.candidate_digest),
            plugin_version="1.1.0+codex.20260929000000",
            clock=fixed_clock,
        )


def test_gate_and_managed_receipt_must_match(tmp_path: Path) -> None:
    current = resolved(tmp_path, proven=True)
    mismatched_gate = replace(gate(GateVerdict.PASS), coverage_status=CoverageStatus.PARTIAL)

    with pytest.raises(ValueError, match="Gate and managed receipt"):
        finalize_candidate(
            current,
            selection(),
            inspection(),
            mismatched_gate,
            receipt(current.candidate_digest),
            plugin_version="1.1.0+codex.20260929000000",
            clock=fixed_clock,
        )


def test_preinspection_incomplete_result_does_not_fabricate_gate_fields() -> None:
    result = incomplete_candidate_result(
        "openspace-cloud:" + "1" * 64,
        ("download failed",),
        candidate_digest=None,
        discovery_bundle_digest="a" * 64,
        selection_record_digest="b" * 64,
        clock=fixed_clock,
    )

    assert result.governance_status is CandidateGovernanceStatus.INCOMPLETE
    assert result.inspection_id is None
    assert result.coverage_status is None
    assert result.gate_verdict is None
    assert result.receipt is None
