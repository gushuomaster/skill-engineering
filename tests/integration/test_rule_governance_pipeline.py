from pathlib import Path

from engine.models import Intent, GateVerdict
from engine.orchestrator import EngineeringRequest, PipelineOrchestrator
from tests.support import codex_decision, confirmation


def test_rule_findings_are_advisory_in_pipeline(tmp_path: Path) -> None:
    source = tmp_path / "skill"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: skill\ndescription: valid skill\n---\n\nMust validate artifacts before publish.\nMust validate artifacts before release.\n",
        encoding="utf-8",
    )
    outcome = PipelineOrchestrator().run(EngineeringRequest(
        requirement="audit", intent=Intent.AUDIT_ONLY,
        decision=codex_decision(Intent.AUDIT_ONLY), source=source, candidate=None,
        failure_evidence=(), authorized_to_modify=False, target_parent=tmp_path,
        semantic_confirmation=confirmation(source),
    ))
    assert outcome.gate_result.verdict is GateVerdict.PASS
    assert any("rule-signal" in warning for warning in outcome.gate_result.warnings)
