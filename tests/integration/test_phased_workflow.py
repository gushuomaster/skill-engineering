from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from engine.inventory import digest_tree
from engine.mechanism_selection import MERGE_INVARIANT
from engine.models import CheckStatus, GateOutcome, GateVerdict, Intent, LifecycleState
from engine.orchestrator import PipelineOrchestrator, publish
from tests.support import codex_decision, confirmation, copy_candidate


FIXTURE = Path(__file__).parents[1] / "fixtures" / "skills" / "minimal-valid"


def test_inspect_precedes_codex_decisions_and_binds_source_digest(tmp_path: Path) -> None:
    source = tmp_path / "minimal-valid"
    shutil.copytree(FIXTURE, source)

    inspection = PipelineOrchestrator().inspect(Intent.MODIFY, source)

    assert inspection.lifecycle_state is LifecycleState.INSPECTED
    assert inspection.baseline_digest == digest_tree(source)
    assert inspection.finding_ids == tuple(finding.finding_id for finding in inspection.findings)
    assert inspection.signals
    assert inspection.provider_capabilities == (
        "AUDIT_SKILL",
        "CHECK_SKILL_CONFORMANCE",
        "CREATE_CANDIDATE",
        "GOVERN_AGENT_INSTRUCTIONS",
    )
    assert all(item.invocation_phase == "INSPECT" for item in inspection.provider_evidence)


def test_validate_rejects_stale_inspection(tmp_path: Path) -> None:
    source = tmp_path / "minimal-valid"
    shutil.copytree(FIXTURE, source)
    orchestrator = PipelineOrchestrator()
    inspection = orchestrator.inspect(Intent.MODIFY, source)
    (source / "changed.txt").write_text("changed", encoding="utf-8")
    candidate_parent = tmp_path / "candidate"
    candidate_parent.mkdir()
    candidate = copy_candidate(source, candidate_parent)

    with pytest.raises(ValueError, match="stale inspection"):
        orchestrator.validate(
            inspection,
            codex_decision(Intent.MODIFY, selected=(MERGE_INVARIANT,)),
            (),
            candidate=candidate,
            target_parent=tmp_path,
            authorized_to_modify=True,
        )


def test_validate_requires_governance_for_every_actionable_finding(tmp_path: Path) -> None:
    source = tmp_path / "rules"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: rules\ndescription: Test rules.\n---\n\n"
        "- must keep output stable\n- must keep output stable\n",
        encoding="utf-8",
    )
    orchestrator = PipelineOrchestrator()
    inspection = orchestrator.inspect(Intent.MODIFY, source)
    candidate_parent = tmp_path / "candidate"
    candidate_parent.mkdir()
    candidate = copy_candidate(source, candidate_parent)

    with pytest.raises(ValueError, match="missing governance decisions"):
        orchestrator.validate(
            inspection,
            codex_decision(Intent.MODIFY, selected=(MERGE_INVARIANT,)),
            (),
            candidate=candidate,
            target_parent=tmp_path,
            authorized_to_modify=True,
        )


def test_validate_is_pending_until_post_validation_confirmation(tmp_path: Path) -> None:
    source = tmp_path / "source" / "minimal-valid"
    source.parent.mkdir()
    shutil.copytree(FIXTURE, source)
    candidate_parent = tmp_path / "candidate"
    candidate_parent.mkdir()
    candidate = copy_candidate(source, candidate_parent)
    destination = tmp_path / "destination"
    destination.mkdir()
    orchestrator = PipelineOrchestrator()
    inspection = orchestrator.inspect(Intent.MODIFY, source)

    validation = orchestrator.validate(
        inspection,
        codex_decision(Intent.MODIFY, selected=(MERGE_INVARIANT,)),
        (),
        candidate=candidate,
        target_parent=destination,
        authorized_to_modify=True,
        publish_requested=True,
    )

    assert validation.lifecycle_state is LifecycleState.VALIDATED_PENDING_CONFIRMATION
    assert validation.pending_semantic_confirmation is True
    assert validation.gate_result is None
    assert validation.deterministic_evidence
    assert all(item.deterministic for item in validation.deterministic_evidence)
    assert all(not item.deterministic for item in validation.advisory_evidence)

    outcome = orchestrator.confirm(validation, confirmation(validation.artifact_path))
    assert outcome.gate_result.verdict is GateVerdict.PASS
    assert outcome.gate_result.outcome is GateOutcome.READY_TO_PUBLISH
    assert outcome.lifecycle_state is LifecycleState.READY_TO_PUBLISH
    assert not (destination / source.name).exists()

    result = publish(outcome)
    assert result.status == "PUBLISHED"
    assert (destination / source.name).exists()


def test_confirm_rejects_candidate_changed_after_validation(tmp_path: Path) -> None:
    source = tmp_path / "source" / "minimal-valid"
    source.parent.mkdir()
    shutil.copytree(FIXTURE, source)
    candidate_parent = tmp_path / "candidate"
    candidate_parent.mkdir()
    candidate = copy_candidate(source, candidate_parent)
    destination = tmp_path / "destination"
    destination.mkdir()
    orchestrator = PipelineOrchestrator()
    validation = orchestrator.validate(
        orchestrator.inspect(Intent.MODIFY, source),
        codex_decision(Intent.MODIFY, selected=(MERGE_INVARIANT,)),
        (),
        candidate=candidate,
        target_parent=destination,
        authorized_to_modify=True,
    )
    (validation.artifact_path / "changed-after-validation.txt").write_text(
        "changed", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="candidate changed after validation"):
        orchestrator.confirm(validation, confirmation(validation.artifact_path))


def test_confirm_marks_audit_unknown_when_source_changes_after_validation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "minimal-valid"
    shutil.copytree(FIXTURE, source)
    orchestrator = PipelineOrchestrator()
    validation = orchestrator.validate(
        orchestrator.inspect(Intent.AUDIT_ONLY, source),
        codex_decision(Intent.AUDIT_ONLY),
        (),
        candidate=None,
        target_parent=tmp_path,
        authorized_to_modify=False,
    )
    (source / "concurrent.txt").write_text("external", encoding="utf-8")

    outcome = orchestrator.confirm(
        validation,
        confirmation(source),
    )

    assert outcome.audit_execution.value == "INCOMPLETE"
    assert outcome.artifact_assessment.value == "UNKNOWN"
    assert outcome.gate_result.semantic_confirmed is False
    assert outcome.workspace_diff.added == ("concurrent.txt",)
    integrity = next(item for item in outcome.deterministic_evidence if item.check_id == "B10")
    assert integrity.status is CheckStatus.FAIL
