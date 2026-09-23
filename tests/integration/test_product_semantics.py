from pathlib import Path

import pytest

from engine.models import (
    CheckResult, CheckStatus, GateVerdict, Intent, LifecycleState,
    PrimaryIssueClass, RegressionDisposition, StandardDependencyStatus,
    StandardSkillRequirement,
)
from engine.inventory import digest_tree
from engine.mechanism_selection import IMPLEMENTATION_FIX, REGRESSION_TEST
from engine.orchestrator import PipelineOrchestrator, apply
from engine.toolchain import MissingStandardDependencyError
from tests.support import codex_decision, confirmation


REQUIREMENT = StandardSkillRequirement(
    "missing-audit-specialist",
    "independent specialist review",
    "specialist-specific findings are not covered",
)


def _skill(root: Path) -> Path:
    root.mkdir()
    (root / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Run a bounded demo workflow.\n---\n\n"
        "Follow the requested workflow.\n",
        encoding="utf-8",
    )
    return root


def _passing(check_id: str):
    def run(path: Path) -> CheckResult:
        return CheckResult(
            check_id, "dogfood.runner", path.name, True, CheckStatus.PASS,
            True, True, 1.0, ("dogfood command completed",),
            LifecycleState.VALIDATED_PENDING_CONFIRMATION, str(path),
        )
    return run


def _repair_decision(mode: Intent):
    return codex_decision(
        mode,
        primary=PrimaryIssueClass.IMPLEMENTATION_DEFECT,
        selected=(IMPLEMENTATION_FIX, REGRESSION_TEST),
        regression=RegressionDisposition.REQUIRED,
        root_cause="The source instruction encodes the wrong observable behavior.",
    )


def test_audit_reports_real_defect_without_file_change(tmp_path: Path) -> None:
    source = tmp_path / "broken"
    source.mkdir()
    (source / "SKILL.md").write_text("# missing frontmatter\n", encoding="utf-8")
    before = digest_tree(source)
    orchestrator = PipelineOrchestrator()
    inspection = orchestrator.inspect(Intent.AUDIT, source)
    validation = orchestrator.validate(
        inspection, codex_decision(Intent.AUDIT), (), candidate=None,
        target_parent=source.parent, authorized_to_modify=False,
    )
    outcome = orchestrator.confirm(validation, confirmation(source))

    assert outcome.gate_result.verdict is GateVerdict.FAIL
    assert outcome.minimal_blocking_findings
    assert digest_tree(source) == before
    assert outcome.workspace_diff.added == outcome.workspace_diff.modified == outcome.workspace_diff.deleted == ()


@pytest.mark.parametrize("mode", [Intent.AUDIT_REPAIR, Intent.TARGETED_REPAIR])
def test_repair_modes_validate_and_safe_apply_without_unrelated_changes(
    tmp_path: Path, mode: Intent,
) -> None:
    source = _skill(tmp_path / "demo")
    (source / "SKILL.md").write_text(
        (source / "SKILL.md").read_text(encoding="utf-8") + "Use OLD behavior.\n",
        encoding="utf-8",
    )
    (source / "unrelated.txt").write_text("keep", encoding="utf-8")
    candidate_parent = tmp_path / "candidate"
    candidate_parent.mkdir()
    candidate = candidate_parent / source.name
    candidate.mkdir()
    (candidate / "SKILL.md").write_text(
        (source / "SKILL.md").read_text(encoding="utf-8").replace("OLD", "NEW"),
        encoding="utf-8",
    )
    (candidate / "unrelated.txt").write_text("keep", encoding="utf-8")
    orchestrator = PipelineOrchestrator()
    inspection = orchestrator.inspect(mode, source)
    validation = orchestrator.validate(
        inspection, _repair_decision(mode), (), candidate=candidate,
        target_parent=source.parent, authorized_to_modify=True,
        behavioral_runner=_passing("behavioral.repair"),
        regression_runner=_passing("B07"), apply_requested=True,
    )
    outcome = orchestrator.confirm(validation, confirmation(validation.artifact_path))
    assert outcome.gate_result.verdict is GateVerdict.PASS
    with pytest.raises(ValueError, match="formal completion receipt"):
        apply(outcome)
    assert "Use OLD behavior." in (source / "SKILL.md").read_text(encoding="utf-8")
    assert (source / "unrelated.txt").read_text(encoding="utf-8") == "keep"
    assert validation.workspace_diff.modified == ("SKILL.md",)


def test_missing_required_standard_skill_requires_user_choice(tmp_path: Path) -> None:
    source = _skill(tmp_path / "demo")
    empty = tmp_path / "skills"
    empty.mkdir()
    orchestrator = PipelineOrchestrator(
        required_standard_skills=(REQUIREMENT,), skill_roots=(empty,),
    )
    inspection = orchestrator.inspect(Intent.AUDIT, source)

    assert inspection.standard_dependencies[0].status is StandardDependencyStatus.MISSING
    with pytest.raises(MissingStandardDependencyError) as caught:
        orchestrator.validate(
            inspection, codex_decision(Intent.AUDIT), (), candidate=None,
            target_parent=source.parent, authorized_to_modify=False,
        )
    assert "install/connect" in str(caught.value)
    assert REQUIREMENT.coverage_gap in str(caught.value)


def test_declined_dependency_continues_only_as_limited_incomplete_audit(
    tmp_path: Path,
) -> None:
    source = _skill(tmp_path / "demo")
    empty = tmp_path / "skills"
    empty.mkdir()
    orchestrator = PipelineOrchestrator(
        required_standard_skills=(REQUIREMENT,), skill_roots=(empty,),
    )
    inspection = orchestrator.inspect(Intent.AUDIT, source)
    validation = orchestrator.validate(
        inspection, codex_decision(Intent.AUDIT), (), candidate=None,
        target_parent=source.parent, authorized_to_modify=False,
        continue_limited=True,
    )
    outcome = orchestrator.confirm(validation, confirmation(source))

    dependency = next(
        item for item in validation.deterministic_evidence
        if item.check_id == "standard-dependency.missing-audit-specialist"
    )
    assert validation.limited_audit is True
    assert "result_scope=LIMITED_AUDIT" in dependency.evidence
    assert outcome.gate_result.verdict is GateVerdict.INCOMPLETE
    assert outcome.gate_result.apply_authorized is False
