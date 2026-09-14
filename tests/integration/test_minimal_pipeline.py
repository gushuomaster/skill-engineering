from pathlib import Path

import pytest

from engine.models import GateVerdict, Intent, LifecycleState
from engine.orchestrator import (
    EngineeringRequest,
    PipelineBlockedError,
    PipelineOrchestrator,
)


FIXTURES = Path(__file__).parents[1] / "fixtures" / "skills"


def request(source: Path, *, intent: Intent = Intent.AUDIT_ONLY, **overrides: object) -> EngineeringRequest:
    values = {
        "requirement": "audit this skill",
        "intent": intent,
        "source": source,
        "failure_evidence": (),
        "authorized_to_modify": False,
        "target_parent": source.parent,
    }
    values.update(overrides)
    return EngineeringRequest(**values)


def test_audit_only_valid_skill_returns_unchanged_validated() -> None:
    source = FIXTURES / "minimal-valid"
    outcome = PipelineOrchestrator().run(request(source))

    assert outcome.outcome_type == "Validated Complete Skill"
    assert outcome.artifact_path == source
    assert outcome.gate_result.verdict is GateVerdict.PASS
    assert outcome.gate_result.publish_authorized is False


def test_audit_only_invalid_skill_returns_minimal_findings(tmp_path: Path) -> None:
    source = tmp_path / "broken"
    source.mkdir()
    (source / "SKILL.md").write_text("# missing frontmatter", encoding="utf-8")

    outcome = PipelineOrchestrator().run(request(source))

    assert outcome.outcome_type == "Unchanged Skill + Minimal Blocking Findings"
    assert outcome.gate_result.verdict is GateVerdict.FAIL
    assert set(outcome.minimal_blocking_findings[0]) == {
        "finding_id", "affected_path", "blocking_reason", "required_next_action"
    }
    assert not list(source.parent.glob(".skill-engineering-*"))


@pytest.mark.parametrize("intent", [Intent.MODIFY, Intent.FIX])
def test_mutating_flows_stage_before_classification(intent: Intent, tmp_path: Path) -> None:
    source = FIXTURES / "minimal-valid"
    trace: list[LifecycleState] = []
    orchestrator = PipelineOrchestrator(state_observer=trace.append)
    try:
        outcome = orchestrator.run(
            request(
                source,
                intent=intent,
                requirement="repair the skill",
                failure_evidence=("the behavior is reproducibly wrong",) if intent is Intent.FIX else (),
                authorized_to_modify=True,
                target_parent=tmp_path,
            )
        )
        assert outcome.outcome_type == "Validated Complete Skill"
    except PipelineBlockedError:
        assert intent is Intent.FIX
    assert trace.index(LifecycleState.STAGED) < trace.index(LifecycleState.CLASSIFIED)


def test_create_stages_before_candidate_generation(tmp_path: Path) -> None:
    trace: list[LifecycleState] = []
    outcome = PipelineOrchestrator(state_observer=trace.append).run(
        EngineeringRequest(
            requirement="Create a release checklist skill",
            intent=Intent.CREATE,
            source=None,
            failure_evidence=(),
            authorized_to_modify=True,
            target_parent=tmp_path,
        )
    )

    assert outcome.outcome_type == "Validated Complete Skill"
    assert trace.index(LifecycleState.STAGED) < trace.index(LifecycleState.CLASSIFIED)


def test_non_audit_blocked_flow_has_no_artifact(tmp_path: Path) -> None:
    with pytest.raises(PipelineBlockedError) as caught:
        PipelineOrchestrator().run(
            EngineeringRequest(
                requirement="repair with no evidence",
                intent=Intent.FIX,
                source=FIXTURES / "minimal-valid",
                failure_evidence=(),
                authorized_to_modify=True,
                target_parent=tmp_path,
            )
        )
    assert caught.value.gate_result.verdict is GateVerdict.FAIL


def test_audit_optimize_needed_change_stages_and_can_publish(tmp_path: Path) -> None:
    source = FIXTURES / "minimal-valid"
    trace: list[LifecycleState] = []
    outcome = PipelineOrchestrator(state_observer=trace.append).run(
        request(
            source,
            intent=Intent.AUDIT_OPTIMIZE,
            requirement="audit and optimize this capability",
            authorized_to_modify=True,
            target_parent=tmp_path,
        )
    )

    assert LifecycleState.STAGED in trace
    assert outcome.gate_result.publish_authorized is True
    assert outcome.artifact_path != source


def test_fix_defect_without_regression_runner_is_blocked(tmp_path: Path) -> None:
    source = FIXTURES / "minimal-valid"
    with pytest.raises(PipelineBlockedError) as caught:
        PipelineOrchestrator().run(
            request(
                source,
                intent=Intent.FIX,
                requirement="fix this skill",
                failure_evidence=("reproducible defect",),
                authorized_to_modify=True,
                target_parent=tmp_path,
            )
        )

    assert caught.value.gate_result.verdict is GateVerdict.FAIL
    assert any(finding.startswith("B07") for finding in caught.value.gate_result.blocking_findings)
