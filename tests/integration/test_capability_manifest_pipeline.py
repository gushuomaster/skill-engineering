from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import shutil

import pytest

from engine.capability_manifest import capability_manifest_digest
from engine.contracts import validate_contract
from engine.inventory import build_artifact_manifest
from engine.mechanism_selection import MERGE_INVARIANT
from engine.models import (
    ArtifactRole,
    AuthorizationStatus,
    CapabilityChangeDecision,
    CapabilityDecisionKind,
    CapabilityEvidenceState,
    CapabilityManifest,
    CapabilityPreservationStatus,
    CapabilityRecord,
    DeliverableContractApplicability,
    Intent,
    ProviderDescriptor,
    ProviderResult,
    ProviderStatus,
)
from engine.managed_completion import completion_receipt
from engine.orchestrator import PipelineBlockedError, PipelineOrchestrator, apply
from engine.providers import CAPABILITY_CONTRACT, ProviderGateway
from engine.serialization import inspection_from_data, to_data, validation_from_data
from tests.support import codex_decision, confirmation, copy_candidate


FIXTURE = Path(__file__).parents[1] / "fixtures" / "skills" / "minimal-valid"
DOCUMENTS = ("SRS", "SDD_DETAIL", "STD", "STP", "STR")


def _record(document: str) -> CapabilityRecord:
    return CapabilityRecord(
        document,
        f"{document} document generation",
        "deliverable",
        "implemented",
        "implemented",
        (f"cli:{document}",),
        (),
        (document,),
        (),
        (),
        (f"test:{document}",),
        ("file=SKILL.md;line=1",),
        ("file=SKILL.md;line=1",),
        1.0,
        CapabilityEvidenceState.COMPLETE,
    )


def _manifest(request: dict[str, object]) -> CapabilityManifest:
    target = Path(str(request["target_path"]))
    documents = ("SRS",) if (target / "one-output.txt").is_file() else DOCUMENTS
    return CapabilityManifest(
        "1.0",
        str(request["inspection_id"]),
        str(request["inspection_nonce"]),
        ArtifactRole(str(request["artifact_role"])),
        str(request["target_digest"]),
        "bundled.capability-contract",
        tuple(_record(item) for item in documents),
        "present",
        ("file=SKILL.md;line=1",),
    )


@dataclass
class RecordingCapabilityProvider:
    calls: list[dict[str, object]]
    descriptor: ProviderDescriptor = ProviderDescriptor(
        "bundled.capability-contract",
        "bundled-provider:test",
        "a" * 64,
        CAPABILITY_CONTRACT,
        ProviderStatus.AVAILABLE,
        "test",
        (),
        None,
    )

    def invoke(self, capability: str, request: dict[str, object]) -> ProviderResult:
        self.calls.append(dict(request))
        return ProviderResult(
            self.descriptor.provider_id,
            capability,
            ProviderStatus.AVAILABLE,
            (),
            (),
            ("provider executed",),
            (),
            False,
            capability_manifest=_manifest(request),
        )


def test_modify_runs_capability_provider_for_baseline_and_staged_candidate(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source" / "minimal-valid"
    source.parent.mkdir()
    shutil.copytree(FIXTURE, source)
    candidate_parent = tmp_path / "candidate"
    candidate_parent.mkdir()
    candidate = copy_candidate(source, candidate_parent)
    (candidate / "one-output.txt").write_text("SRS only", encoding="utf-8")
    stage_parent = tmp_path / "stage"
    stage_parent.mkdir()
    provider = RecordingCapabilityProvider([])
    orchestrator = PipelineOrchestrator(
        provider_gateway=ProviderGateway((provider,)),
    )

    inspection = orchestrator.inspect(
        Intent.TARGETED_REPAIR,
        source,
        deliverable_contract_applicability=DeliverableContractApplicability.NOT_REQUIRED,
    )
    candidate_artifact = build_artifact_manifest(
        candidate, Intent.TARGETED_REPAIR, inspection.baseline_digest,
    )
    candidate_manifest = CapabilityManifest(
        "1.0",
        inspection.inspection_id,
        inspection.inspection_nonce,
        ArtifactRole.CANDIDATE,
        candidate_artifact.content_digest,
        "bundled.capability-contract",
        (_record("SRS"),),
        "present",
        ("file=SKILL.md;line=1",),
    )
    capability_decision = CapabilityChangeDecision(
        inspection.baseline_capability_digest,
        capability_manifest_digest(candidate_manifest),
        tuple(
            (item, CapabilityDecisionKind.CAPABILITY_REMOVAL)
            for item in ("SDD_DETAIL", "STD", "STP", "STR")
        ),
        ("SDD_DETAIL", "STD", "STP", "STR"),
        (),
        "The user explicitly requested this breaking reduction.",
        True,
        AuthorizationStatus.AUTHORIZED,
        ("user-message: approved exact removal",),
        "BREAKING",
        "Use SRS output.",
        "Retire the four outputs in the next major version.",
    )

    validation = orchestrator.validate(
        inspection,
        codex_decision(
            Intent.TARGETED_REPAIR,
            selected=(MERGE_INVARIANT,),
            capability_change_decision=capability_decision,
        ),
        (),
        candidate=candidate,
        target_parent=stage_parent,
        authorized_to_modify=True,
        apply_requested=True,
    )

    assert [item["artifact_role"] for item in provider.calls] == ["BASELINE", "CANDIDATE"]
    assert validation.capability_diff.removed_capability_ids == (
        "SDD_DETAIL", "STD", "STP", "STR",
    )
    assert validation.capability_preservation is (
        CapabilityPreservationStatus.CAPABILITY_PRESERVED
    )
    assert validation.semantic_workspace_diff.capability_changes == (
        validation.capability_diff.changes
    )

    inspection_payload = to_data(inspection)
    validate_contract("inspection-bundle", inspection_payload)
    assert inspection_from_data(inspection_payload).baseline_capability_digest == (
        inspection.baseline_capability_digest
    )
    validation_payload = to_data(validation)
    validate_contract("validation-bundle", validation_payload)
    restored = validation_from_data(validation_payload)
    assert restored.capability_diff is not None
    assert restored.capability_diff.removed_capability_ids == (
        "SDD_DETAIL", "STD", "STP", "STR",
    )

    outcome = orchestrator.confirm(validation, confirmation(validation.artifact_path))
    receipt = completion_receipt(outcome)
    with pytest.raises(ValueError, match="does not match"):
        apply(outcome, replace(receipt, candidate_digest="0" * 64))
    result = apply(outcome, receipt)
    assert result.status == "APPLIED"


def test_unapproved_capability_removal_reaches_gate_as_authorization_required(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source" / "minimal-valid"
    source.parent.mkdir()
    shutil.copytree(FIXTURE, source)
    candidate_parent = tmp_path / "candidate"
    candidate_parent.mkdir()
    candidate = copy_candidate(source, candidate_parent)
    (candidate / "one-output.txt").write_text("SRS only", encoding="utf-8")
    stage_parent = tmp_path / "stage"
    stage_parent.mkdir()
    orchestrator = PipelineOrchestrator(
        provider_gateway=ProviderGateway((RecordingCapabilityProvider([]),)),
    )
    inspection = orchestrator.inspect(Intent.TARGETED_REPAIR, source)
    candidate_artifact = build_artifact_manifest(
        candidate, Intent.TARGETED_REPAIR, inspection.baseline_digest,
    )
    candidate_manifest = CapabilityManifest(
        "1.0",
        inspection.inspection_id,
        inspection.inspection_nonce,
        ArtifactRole.CANDIDATE,
        candidate_artifact.content_digest,
        "bundled.capability-contract",
        (_record("SRS"),),
        "present",
        ("file=SKILL.md;line=1",),
    )
    decision = CapabilityChangeDecision(
        inspection.baseline_capability_digest,
        capability_manifest_digest(candidate_manifest),
        tuple(
            (item, CapabilityDecisionKind.CAPABILITY_REMOVAL)
            for item in ("SDD_DETAIL", "STD", "STP", "STR")
        ),
        ("SDD_DETAIL", "STD", "STP", "STR"),
        (),
        "Removal was detected but not authorized.",
        True,
        AuthorizationStatus.MISSING,
        (),
        "BREAKING",
        None,
        None,
    )

    validation = orchestrator.validate(
        inspection,
        codex_decision(
            Intent.TARGETED_REPAIR,
            selected=(MERGE_INVARIANT,),
            capability_change_decision=decision,
        ),
        (),
        candidate=candidate,
        target_parent=stage_parent,
        authorized_to_modify=True,
        apply_requested=True,
    )

    assert validation.capability_preservation is (
        CapabilityPreservationStatus.AUTHORIZATION_REQUIRED
    )
    with pytest.raises(PipelineBlockedError) as blocked:
        orchestrator.confirm(validation, confirmation(validation.artifact_path))
    assert blocked.value.gate_result.verdict.value == "FAIL"
    assert blocked.value.gate_result.apply_authorized is False
    assert blocked.value.gate_result.capability_preservation is (
        CapabilityPreservationStatus.AUTHORIZATION_REQUIRED
    )


def test_create_runs_candidate_capability_provider_without_baseline(
    tmp_path: Path,
) -> None:
    candidate_parent = tmp_path / "candidate"
    candidate_parent.mkdir()
    candidate = copy_candidate(FIXTURE, candidate_parent, "minimal-valid")
    stage_parent = tmp_path / "stage"
    stage_parent.mkdir()
    provider = RecordingCapabilityProvider([])
    orchestrator = PipelineOrchestrator(
        provider_gateway=ProviderGateway((provider,)),
    )

    inspection = orchestrator.inspect(Intent.CREATE, None)
    validation = orchestrator.validate(
        inspection,
        codex_decision(Intent.CREATE, selected=(MERGE_INVARIANT,)),
        (),
        candidate=candidate,
        target_parent=stage_parent,
        authorized_to_modify=True,
    )

    assert [item["artifact_role"] for item in provider.calls] == ["CANDIDATE"]
    assert validation.baseline_capability_manifest is None
    assert validation.candidate_capability_manifest is not None
    assert validation.capability_preservation is (
        CapabilityPreservationStatus.CAPABILITY_PRESERVED
    )


def test_validate_rejects_changed_capability_provider_resource(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source" / "minimal-valid"
    source.parent.mkdir()
    shutil.copytree(FIXTURE, source)
    candidate_parent = tmp_path / "candidate"
    candidate_parent.mkdir()
    candidate = copy_candidate(source, candidate_parent)
    stage_parent = tmp_path / "stage"
    stage_parent.mkdir()
    baseline_provider = RecordingCapabilityProvider([])
    inspection = PipelineOrchestrator(
        provider_gateway=ProviderGateway((baseline_provider,)),
    ).inspect(Intent.TARGETED_REPAIR, source)
    changed_descriptor = ProviderDescriptor(
        baseline_provider.descriptor.provider_id,
        baseline_provider.descriptor.source_identity,
        "e" * 64,
        baseline_provider.descriptor.capability,
        ProviderStatus.AVAILABLE,
        baseline_provider.descriptor.invocation_adapter,
        (),
        None,
    )
    changed_provider = RecordingCapabilityProvider([], descriptor=changed_descriptor)

    with pytest.raises(ValueError, match="Provider resource changed"):
        PipelineOrchestrator(
            provider_gateway=ProviderGateway((changed_provider,)),
        ).validate(
            inspection,
            codex_decision(Intent.TARGETED_REPAIR, selected=(MERGE_INVARIANT,)),
            (),
            candidate=candidate,
            target_parent=stage_parent,
            authorized_to_modify=True,
        )
