from pathlib import Path

import pytest

from engine.inventory import digest_tree
from engine.mechanism_selection import IMPLEMENTATION_FIX, MERGE_INVARIANT, REGRESSION_TEST
from engine.models import (
    CheckResult, CheckStatus, GateVerdict, Intent, LifecycleState,
    PrimaryIssueClass, RegressionDisposition,
)
from engine.orchestrator import EngineeringRequest, PipelineBlockedError, PipelineOrchestrator
from tests.support import codex_decision, confirmation, copy_candidate


FIXTURES = Path(__file__).parents[1] / "fixtures" / "skills"


def audit_request(source: Path, target_parent: Path, *, confirmed: bool = True) -> EngineeringRequest:
    return EngineeringRequest(
        "audit this skill", Intent.AUDIT_ONLY, codex_decision(Intent.AUDIT_ONLY),
        source, None, (), False, target_parent,
        semantic_confirmation=confirmation(source) if confirmed else None,
    )


def test_audit_only_valid_skill_is_read_only(tmp_path: Path) -> None:
    source = FIXTURES / "minimal-valid"
    before = digest_tree(source)
    outcome = PipelineOrchestrator().run(audit_request(source, tmp_path))

    assert outcome.gate_result.verdict is GateVerdict.PASS
    assert outcome.artifact_path == source
    assert outcome.workspace_diff.added == outcome.workspace_diff.modified == outcome.workspace_diff.deleted == ()
    assert digest_tree(source) == before
    assert not list(tmp_path.glob(".skill-engineering-*"))


def test_explicit_mode_is_not_overridden_by_requirement_keywords(tmp_path: Path) -> None:
    source = FIXTURES / "minimal-valid"
    request = audit_request(source, tmp_path)
    request = EngineeringRequest(**{**request.__dict__, "requirement": "fix and modify this skill"})
    outcome = PipelineOrchestrator().run(request)

    assert outcome.artifact_path == source
    assert outcome.gate_result.apply_authorized is False
    assert not list(tmp_path.glob(".skill-engineering-*"))


def test_audit_only_invalid_skill_returns_findings_without_copy(tmp_path: Path) -> None:
    source = tmp_path / "broken"
    source.mkdir()
    (source / "SKILL.md").write_text("# missing frontmatter", encoding="utf-8")
    outcome = PipelineOrchestrator().run(audit_request(source, tmp_path))

    assert outcome.outcome_type == "AUDIT_COMPLETE_BLOCKING_FINDINGS"
    assert outcome.gate_result.verdict is GateVerdict.FAIL
    assert outcome.artifact_assessment.value == "BLOCKING_FINDINGS"
    assert not list(tmp_path.glob(".skill-engineering-*"))


@pytest.mark.parametrize("intent", [Intent.MODIFY, Intent.FIX])
def test_mutating_flows_inspect_and_classify_before_staging_candidate(intent: Intent, tmp_path: Path) -> None:
    source = FIXTURES / "minimal-valid"
    candidate_parent = tmp_path / "codex"
    candidate_parent.mkdir()
    candidate = copy_candidate(source, candidate_parent)
    selected = (MERGE_INVARIANT,) if intent is Intent.MODIFY else (IMPLEMENTATION_FIX, REGRESSION_TEST)
    regression = RegressionDisposition.NOT_APPLICABLE if intent is Intent.MODIFY else RegressionDisposition.REQUIRED
    root = None if intent is Intent.MODIFY else "Codex reproduced an implementation defect"
    runner = None
    if intent is Intent.FIX:
        runner = lambda artifact: CheckResult(
            "B07", "test.regression", str(artifact), True, CheckStatus.PASS,
            True, True, 1.0, ("regression passed",), LifecycleState.VALIDATED, str(artifact),
        )
    trace: list[LifecycleState] = []
    outcome = PipelineOrchestrator(state_observer=trace.append).run(EngineeringRequest(
        "Codex-authored candidate", intent,
        codex_decision(intent, primary=PrimaryIssueClass.IMPLEMENTATION_DEFECT if root else PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE,
                       selected=selected, regression=regression, root_cause=root),
        source, candidate, ("reproduced",) if root else (), True, tmp_path,
        semantic_confirmation=confirmation(candidate), regression_runner=runner,
        apply_requested=True,
    ))

    assert trace.index(LifecycleState.INSPECTED) < trace.index(LifecycleState.CLASSIFIED)
    assert trace.index(LifecycleState.CLASSIFIED) < trace.index(LifecycleState.STAGED)
    assert outcome.artifact_path != source
    assert outcome.apply_session is not None
    assert digest_tree(source) != ""


def test_create_requires_and_preserves_complete_codex_candidate(tmp_path: Path) -> None:
    candidate = tmp_path / "codex" / "release-checklist"
    candidate.mkdir(parents=True)
    content = "---\nname: release-checklist\ndescription: Produce a complete release checklist.\n---\n\n# Release checklist\n\nGather scope, risks, validation, and rollback evidence.\n"
    (candidate / "SKILL.md").write_text(content, encoding="utf-8")
    outcome = PipelineOrchestrator().run(EngineeringRequest(
        "Create a release checklist skill", Intent.CREATE,
        codex_decision(Intent.CREATE, primary=PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE,
                       selected=(MERGE_INVARIANT,)),
        None, candidate, (), True, tmp_path,
        semantic_confirmation=confirmation(candidate),
        behavioral_runner=lambda artifact: CheckResult(
            "behavioral.create", "test.behavior", str(artifact), True,
            CheckStatus.PASS, True, True, 1.0,
            ("candidate produced a scoped release checklist",),
            LifecycleState.VALIDATED, str(artifact),
        ),
    ))

    assert (outcome.artifact_path / "SKILL.md").read_text(encoding="utf-8") == content
    assert outcome.workspace_diff.added == ("SKILL.md",)
    assert not (tmp_path / "release-checklist").exists()


def test_change_mode_without_complete_candidate_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="complete candidate"):
        PipelineOrchestrator().run(EngineeringRequest(
            "modify", Intent.MODIFY,
            codex_decision(Intent.MODIFY, selected=(MERGE_INVARIANT,)),
            FIXTURES / "minimal-valid", None, (), True, tmp_path,
        ))


def test_create_without_behavioral_runner_is_not_reported_as_pass(tmp_path: Path) -> None:
    candidate = tmp_path / "codex" / "demo"
    candidate.mkdir(parents=True)
    (candidate / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo behavior.\n---\n\n# Demo\n",
        encoding="utf-8",
    )
    with pytest.raises(PipelineBlockedError) as caught:
        PipelineOrchestrator().run(EngineeringRequest(
            "create demo", Intent.CREATE,
            codex_decision(Intent.CREATE, selected=(MERGE_INVARIANT,)),
            None, candidate, (), True, tmp_path,
            semantic_confirmation=confirmation(candidate),
        ))
    assert any("behavioral.create" in item for item in caught.value.gate_result.blocking_findings)


def test_passing_checks_without_codex_confirmation_are_blocked(tmp_path: Path) -> None:
    with pytest.raises(PipelineBlockedError) as caught:
        candidate_parent = tmp_path / "codex"
        candidate_parent.mkdir()
        candidate = copy_candidate(FIXTURES / "minimal-valid", candidate_parent)
        PipelineOrchestrator().run(EngineeringRequest(
            "modify", Intent.MODIFY,
            codex_decision(Intent.MODIFY, selected=(MERGE_INVARIANT,)),
            FIXTURES / "minimal-valid", candidate, (), True, tmp_path,
        ))
    assert any(item.startswith("B12") for item in caught.value.gate_result.blocking_findings)
    assert caught.value.artifact_path is not None
    assert caught.value.workspace_diff is not None


def test_fix_without_required_regression_is_blocked(tmp_path: Path) -> None:
    candidate_parent = tmp_path / "codex"
    candidate_parent.mkdir()
    candidate = copy_candidate(FIXTURES / "minimal-valid", candidate_parent)
    with pytest.raises(PipelineBlockedError) as caught:
        PipelineOrchestrator().run(EngineeringRequest(
            "fix", Intent.FIX,
            codex_decision(Intent.FIX, primary=PrimaryIssueClass.IMPLEMENTATION_DEFECT,
                           selected=(IMPLEMENTATION_FIX, REGRESSION_TEST),
                           regression=RegressionDisposition.REQUIRED,
                           root_cause="Codex reproduced the defect"),
            FIXTURES / "minimal-valid", candidate, ("reproduced",), True, tmp_path,
            semantic_confirmation=confirmation(candidate),
        ))
    assert any(item.startswith("B07") for item in caught.value.gate_result.blocking_findings)
