from pathlib import Path

import pytest

from engine.models import GateVerdict, Intent
from engine.orchestrator import EngineeringRequest, PipelineBlockedError, PipelineOrchestrator


FIXTURES = Path(__file__).parents[1] / "fixtures" / "skills"


@pytest.mark.parametrize(
    ("case", "expected_outcome", "expected_publish"),
    [
        ("create-internal-fallback", "Validated Complete Skill", True),
        ("modify-stable-invariant", "Validated Complete Skill", True),
        ("modify-task-local-preference", "Validated Complete Skill", False),
        ("fix-environment-bug", "Validated Complete Skill", True),
        ("audit-only-pass", "Validated Complete Skill", False),
        ("audit-only-fail", "Unchanged Skill + Minimal Blocking Findings", False),
        ("audit-optimize-pass", "Validated Complete Skill", True),
    ],
)
def test_frozen_v1_flows(case: str, expected_outcome: str, expected_publish: bool, tmp_path: Path) -> None:
    source = FIXTURES / ("minimal-valid" if case != "audit-only-fail" else "broken")
    if case == "audit-only-fail":
        source = tmp_path / "broken"
        source.mkdir()
        (source / "SKILL.md").write_text("# missing frontmatter", encoding="utf-8")
    intent = {
        "create-internal-fallback": Intent.CREATE,
        "modify-stable-invariant": Intent.MODIFY,
        "modify-task-local-preference": Intent.MODIFY,
        "fix-environment-bug": Intent.FIX,
        "audit-only-pass": Intent.AUDIT_ONLY,
        "audit-only-fail": Intent.AUDIT_ONLY,
        "audit-optimize-pass": Intent.AUDIT_OPTIMIZE,
    }[case]
    request = EngineeringRequest(
        requirement=case,
        intent=intent,
        source=None if intent is Intent.CREATE else source,
        failure_evidence=("reproducible defect",) if intent is Intent.FIX else (("needed behavior",) if case == "audit-optimize-pass" else ()),
        authorized_to_modify=intent in {Intent.CREATE, Intent.MODIFY, Intent.FIX, Intent.AUDIT_OPTIMIZE},
        target_parent=tmp_path,
    )
    if case == "fix-environment-bug":
        request = EngineeringRequest(
            requirement=case,
            intent=Intent.MODIFY,
            source=source,
            failure_evidence=(),
            authorized_to_modify=True,
            target_parent=tmp_path,
        )
    outcome = PipelineOrchestrator().run(request)
    assert outcome.outcome_type == expected_outcome
    assert outcome.gate_result.publish_authorized is expected_publish
    if case == "audit-only-fail":
        assert outcome.gate_result.verdict is GateVerdict.FAIL


def test_non_audit_insufficient_evidence_delivers_no_third_output(tmp_path: Path) -> None:
    request = EngineeringRequest("fix", Intent.FIX, FIXTURES / "minimal-valid", (), True, tmp_path)
    with pytest.raises(PipelineBlockedError) as caught:
        PipelineOrchestrator().run(request)
    assert caught.value.gate_result.verdict is GateVerdict.FAIL
