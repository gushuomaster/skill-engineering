from __future__ import annotations

from pathlib import Path

import pytest

from engine.models import GateVerdict, Intent
from engine.orchestrator import PipelineBlockedError, PipelineOrchestrator
from engine.rule_governance import GovernanceAction, GovernanceDecision
from tests.support import codex_decision, confirmation, copy_candidate


def _governance(inspection) -> tuple[GovernanceDecision, ...]:
    return tuple(
        GovernanceDecision(
            item.finding_id, GovernanceAction.KEEP,
            "Contract fixture retains the finding so fallback behavior can be observed.",
            item.evidence_refs, "SKILL.md", False, item.signals, item.limitations,
        )
        for item in inspection.findings if item.confidence > 0
    )


def _audit(source: Path):
    orchestrator = PipelineOrchestrator()
    inspection = orchestrator.inspect(Intent.AUDIT_ONLY, source)
    validation = orchestrator.validate(
        inspection, codex_decision(Intent.AUDIT_ONLY), _governance(inspection),
        candidate=None, target_parent=source.parent, authorized_to_modify=False,
    )
    outcome = orchestrator.confirm(validation, confirmation(source))
    return validation, outcome


def test_skill_creator_full_fallback_contract_executes_all_design_layers(tmp_path: Path) -> None:
    source = tmp_path / "source" / "demo"
    (source / "references").mkdir(parents=True)
    (source / "references" / "orphan.md").write_text("Unlinked detail.\n", encoding="utf-8")
    (source / "SKILL.md").write_text(
        "---\nname: Wrong Name\ndescription: TODO\n"
        "required_scripts:\n  - scripts/missing.py\n"
        "critical_assets:\n  - assets/missing.txt\n---\n\n"
        "Must govern the entire repository.\nBe careful.\n",
        encoding="utf-8",
    )
    candidate_parent = tmp_path / "candidate"
    candidate_parent.mkdir()
    candidate = copy_candidate(source, candidate_parent)
    destination = tmp_path / "destination"
    destination.mkdir()
    orchestrator = PipelineOrchestrator()
    inspection = orchestrator.inspect(Intent.MODIFY, source)
    validation = orchestrator.validate(
        inspection, codex_decision(Intent.MODIFY), _governance(inspection),
        candidate=candidate, target_parent=destination, authorized_to_modify=True,
    )

    result = next(
        item for item in validation.deterministic_evidence
        if item.check_id == "capability.skill_creation_or_restructure"
    )
    assert result.status.value == "FAIL"
    joined = "\n".join(result.evidence)
    assert "frontmatter" in joined
    assert "critical_assets" in joined
    assert "scripts" in joined
    assert "progressive_disclosure" in joined
    assert "agent_instruction_governance" in joined


def test_agent_skills_creator_full_fallback_contract_emits_complete_findings(
    tmp_path: Path,
) -> None:
    source = tmp_path / "demo"
    source.mkdir()
    (source / "AGENTS.md").write_text("Must publish checks.\n", encoding="utf-8")
    directives = "\n".join([
        "Must publish checks.",
        "Must publish checks.",
        "Never publish checks.",
        "Must use deprecated workflow.",
        "Must always invoke the provider skill.",
        "Must govern the entire repository.",
        "Must be careful.",
        "Should use validation when applicable.",
        "Must use validation unless explicitly exempted.",
    ])
    (source / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Audit a deliberately defective Skill.\n---\n\n"
        + directives + "\n",
        encoding="utf-8",
    )

    validation, outcome = _audit(source)

    result = next(
        item for item in validation.deterministic_evidence
        if item.check_id == "capability.skill_audit_and_simplification"
    )
    assert result.status.value == "FAIL"
    joined = "\n".join(result.evidence)
    for field in ("file=", "line=", "finding=", "severity=", "reason=", "remediation="):
        assert field in joined
    assert "deprecated" in joined
    assert "Provider orchestration" in joined
    assert "cross-layer" in joined or "ownership" in joined
    assert outcome.gate_result.verdict is GateVerdict.FAIL


def test_agents_md_full_fallback_contract_inspects_inherited_instruction_layers(
    tmp_path: Path,
) -> None:
    (tmp_path / "AGENTS.md").write_text("Must publish checks.\n", encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir()
    (project / "CLAUDE.md").write_text("Must publish checks.\n", encoding="utf-8")
    source = project / "skills" / "demo"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Exercise instruction inheritance.\n---\n\n"
        "Must publish checks.\nNever publish checks.\n"
        "Must govern the entire repository.\n",
        encoding="utf-8",
    )

    validation, outcome = _audit(source)

    result = next(
        item for item in validation.deterministic_evidence
        if item.check_id == "capability.agent_instruction_governance"
    )
    joined = "\n".join(result.evidence)
    assert result.status.value == "FAIL"
    assert "AGENTS.md" in joined
    assert "CLAUDE.md" in joined
    assert "SKILL.md" in joined
    assert "cross-layer conflict" in joined
    assert "misplaced" in joined
    assert outcome.gate_result.verdict is GateVerdict.FAIL


@pytest.mark.parametrize(
    "files,expected",
    [
        ({}, "skill.structure.skill_md"),
        ({"SKILL.md": "---\nname: [broken\n---\n"}, "skill.structure.frontmatter"),
        ({"SKILL.md": "---\nname: Bad Name\ndescription: Valid description.\n---\n"}, "skill.structure.name_format"),
        ({"SKILL.md": "---\nname: demo\ndescription: ''\n---\n"}, "capability.skill_trigger_and_description"),
        ({"SKILL.md": "---\nname: demo\ndescription: Valid description.\n---\n[bad](references/missing.md)\n"}, "reference.required.exists"),
        ({"SKILL.md": "---\nname: demo\ndescription: Valid description.\nrequired_scripts:\n  - scripts/missing.py\n---\n"}, "skill.structure.scripts"),
        ({"SKILL.md": "---\nname: demo\ndescription: Valid description.\ncritical_assets:\n  - ../outside.txt\n---\n"}, "skill.structure.critical_assets"),
        ({"SKILL.md": "---\nname: other\ndescription: Valid description.\n---\n"}, "skill.structure.directory_name"),
    ],
)
def test_validate_skills_full_fallback_contract_is_deterministic(
    tmp_path: Path, files: dict[str, str], expected: str,
) -> None:
    source = tmp_path / "demo"
    source.mkdir()
    for relative, content in files.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    validation, outcome = _audit(source)

    assert any(
        item.check_id == expected and item.status.value == "FAIL"
        for item in validation.deterministic_evidence
    )
    conformance = next(
        item for item in validation.deterministic_evidence
        if item.check_id == "capability.skill_conformance"
    )
    assert conformance.status.value == "FAIL"
    assert outcome.gate_result.verdict is GateVerdict.FAIL
