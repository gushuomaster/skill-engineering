from pathlib import Path

from engine.models import Intent, GateVerdict
from engine.orchestrator import EngineeringRequest, PipelineOrchestrator
from engine.rule_governance import GovernanceAction, GovernanceDecision
from tests.support import codex_decision, confirmation


def test_rule_findings_are_advisory_in_pipeline(tmp_path: Path) -> None:
    source = tmp_path / "skill"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: skill\ndescription: valid skill\n---\n\nMust validate artifacts before publish.\nMust validate artifacts before release.\n",
        encoding="utf-8",
    )
    orchestrator = PipelineOrchestrator()
    inspection = orchestrator.inspect(Intent.AUDIT_ONLY, source)
    actionable = next(item for item in inspection.findings if item.confidence > 0)
    governance = GovernanceDecision(
        actionable.finding_id,
        GovernanceAction.KEEP,
        "Codex reviewed the similar rules and kept their distinct release scope",
        actionable.evidence_refs,
        "SKILL.md",
    )
    validation = orchestrator.validate(
        inspection,
        codex_decision(Intent.AUDIT_ONLY),
        (governance,),
        candidate=None,
        target_parent=tmp_path,
        authorized_to_modify=False,
    )
    outcome = orchestrator.confirm(validation, confirmation(source))
    assert outcome.gate_result.verdict is GateVerdict.PASS
    assert any("rule-signal" in warning for warning in outcome.gate_result.warnings)
