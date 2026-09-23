from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from engine.capability_manifest import capability_manifest_digest
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
    GateOutcome,
    GateVerdict,
    Intent,
    ProviderDescriptor,
    ProviderResult,
    ProviderStatus,
)
from engine.orchestrator import PipelineBlockedError, PipelineOrchestrator
from engine.providers import CAPABILITY_CONTRACT, ProviderGateway
from tests.support import codex_decision, confirmation


FIXTURES = Path(__file__).parents[1] / "fixtures" / "skills"
BASELINE = FIXTURES / "capability-preservation-baseline"
CANDIDATE = FIXTURES / "capability-preservation-candidate"
REMOVED = ("SDD_DETAIL", "STD", "STP", "STR")


def _documents(target: Path) -> tuple[str, ...]:
    completed = subprocess.run(
        [sys.executable, str(target / "scripts" / "run.py"), "--list"],
        cwd=target,
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=True,
    )
    return tuple(json.loads(completed.stdout))


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
        ("file=SKILL.md;line=7",),
        ("file=scripts/run.py;line=8",),
        1.0,
        CapabilityEvidenceState.COMPLETE,
    )


@dataclass
class FixtureCapabilityProvider:
    descriptor: ProviderDescriptor = ProviderDescriptor(
        "bundled.capability-contract",
        "bundled-provider:dogfood",
        "d" * 64,
        CAPABILITY_CONTRACT,
        ProviderStatus.AVAILABLE,
        "dogfood",
        (),
        None,
    )

    def invoke(self, capability: str, request: dict[str, object]) -> ProviderResult:
        target = Path(str(request["target_path"]))
        manifest = CapabilityManifest(
            "1.0",
            str(request["inspection_id"]),
            str(request["inspection_nonce"]),
            ArtifactRole(str(request["artifact_role"])),
            str(request["target_digest"]),
            self.descriptor.provider_id,
            tuple(_record(item) for item in _documents(target)),
            "present",
            ("file=SKILL.md;line=7",),
        )
        return ProviderResult(
            self.descriptor.provider_id,
            capability,
            ProviderStatus.AVAILABLE,
            (),
            (),
            ("dogfood capability inspection executed",),
            (),
            False,
            capability_manifest=manifest,
        )


def _copy_pair(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "source" / "capability-preservation-baseline"
    source.parent.mkdir()
    shutil.copytree(BASELINE, source)
    candidate = tmp_path / "candidate" / "capability-preservation-candidate"
    candidate.parent.mkdir()
    shutil.copytree(CANDIDATE, candidate)
    stage = tmp_path / "stage"
    stage.mkdir()
    return source, candidate, stage


def _decision(
    inspection,
    candidate: Path,
    *,
    authorized: bool,
) -> CapabilityChangeDecision:
    artifact = build_artifact_manifest(
        candidate, Intent.TARGETED_REPAIR, inspection.baseline_digest,
    )
    candidate_manifest = CapabilityManifest(
        "1.0",
        inspection.inspection_id,
        inspection.inspection_nonce,
        ArtifactRole.CANDIDATE,
        artifact.content_digest,
        "bundled.capability-contract",
        (_record("SRS"),),
        "present",
        ("file=SKILL.md;line=7",),
    )
    return CapabilityChangeDecision(
        inspection.baseline_capability_digest,
        capability_manifest_digest(candidate_manifest),
        tuple((item, CapabilityDecisionKind.CAPABILITY_REMOVAL) for item in REMOVED),
        REMOVED,
        (),
        "Reduce the public output contract to SRS.",
        True,
        AuthorizationStatus.AUTHORIZED if authorized else AuthorizationStatus.MISSING,
        ("user-message: exact four-output removal approved",) if authorized else (),
        "BREAKING",
        "Migrate consumers to SRS.",
        "Retire the four outputs in the next major version.",
    )


def _validate(tmp_path: Path, *, authorized: bool):
    source, candidate, stage = _copy_pair(tmp_path)
    target_tests = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/outputs_check.py", "-q"],
        cwd=candidate,
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert target_tests.returncode == 0, target_tests.stdout + target_tests.stderr
    orchestrator = PipelineOrchestrator(
        provider_gateway=ProviderGateway((FixtureCapabilityProvider(),)),
    )
    inspection = orchestrator.inspect(
        Intent.TARGETED_REPAIR,
        source,
        deliverable_contract_applicability=DeliverableContractApplicability.NOT_REQUIRED,
    )
    validation = orchestrator.validate(
        inspection,
        codex_decision(
            Intent.TARGETED_REPAIR,
            selected=(MERGE_INVARIANT,),
            capability_change_decision=_decision(
                inspection, candidate, authorized=authorized,
            ),
        ),
        (),
        candidate=candidate,
        target_parent=stage,
        authorized_to_modify=True,
        apply_requested=True,
    )
    return orchestrator, validation


def test_self_consistent_five_to_one_repair_is_blocked_without_authorization(
    tmp_path: Path,
) -> None:
    orchestrator, validation = _validate(tmp_path, authorized=False)

    assert validation.capability_diff.removed_capability_ids == REMOVED
    assert validation.capability_preservation is (
        CapabilityPreservationStatus.AUTHORIZATION_REQUIRED
    )
    with pytest.raises(PipelineBlockedError) as blocked:
        orchestrator.confirm(validation, confirmation(validation.artifact_path))
    assert blocked.value.gate_result.verdict is GateVerdict.FAIL
    assert blocked.value.gate_result.apply_authorized is False


def test_exact_authorization_allows_otherwise_valid_five_to_one_candidate(
    tmp_path: Path,
) -> None:
    orchestrator, validation = _validate(tmp_path, authorized=True)

    outcome = orchestrator.confirm(validation, confirmation(validation.artifact_path))

    assert validation.capability_diff.removed_capability_ids == REMOVED
    assert validation.capability_preservation is (
        CapabilityPreservationStatus.CAPABILITY_PRESERVED
    )
    assert outcome.gate_result.verdict is GateVerdict.PASS
    assert outcome.gate_result.outcome is GateOutcome.READY_TO_APPLY
    assert outcome.gate_result.apply_authorized is True
