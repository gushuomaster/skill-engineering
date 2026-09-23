from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from engine.capabilities import (
    DEFAULT_INTERNAL_FALLBACKS,
    SKILL_DUPLICATION_AND_BLOAT,
)
from engine.models import (
    CapabilityStatus, FallbackEquivalence, GateVerdict, Intent,
    ProviderDescriptor, ProviderResult, ProviderStatus,
)
from engine.orchestrator import PipelineBlockedError, PipelineOrchestrator
from engine.providers import AUDIT_SKILL, ProviderGateway
from engine.rule_governance import GovernanceAction, GovernanceDecision
from tests.support import codex_decision, confirmation, copy_candidate


def _write_skill(root: Path, body: str = "Use the workflow.\n", extra_frontmatter: str = "") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(
        "---\n"
        f"name: {root.name}\n"
        "description: Execute a test workflow.\n"
        f"{extra_frontmatter}"
        "---\n\n"
        f"{body}",
        encoding="utf-8",
    )


def _governance(inspection) -> tuple[GovernanceDecision, ...]:
    return tuple(
        GovernanceDecision(
            item.finding_id, GovernanceAction.KEEP,
            "Test reviewed this stable finding.", item.evidence_refs,
            "SKILL.md", False, item.signals, item.limitations,
        )
        for item in inspection.findings
        if item.confidence > 0
    )


def _audit(orchestrator: PipelineOrchestrator, source: Path):
    inspection = orchestrator.inspect(Intent.AUDIT_ONLY, source)
    validation = orchestrator.validate(
        inspection, codex_decision(Intent.AUDIT_ONLY), _governance(inspection),
        candidate=None, target_parent=source.parent, authorized_to_modify=False,
    )
    return validation, orchestrator.confirm(validation, confirmation(source))


def test_core_audit_is_direct_and_does_not_fake_missing_standard_providers(
    tmp_path: Path,
) -> None:
    source = tmp_path / "demo"
    _write_skill(source)

    validation, outcome = _audit(PipelineOrchestrator(), source)

    statuses = {item.capability: item.status for item in validation.capability_preflight}
    assert all(
        item.status is CapabilityStatus.READY
        for item in validation.capability_preflight if item.required
    )
    assert statuses["skill_creation_or_restructure"] is CapabilityStatus.NOT_APPLICABLE
    assert outcome.gate_result.verdict is GateVerdict.PASS


def test_missing_agent_skills_creator_does_not_hide_duplicate_or_conflicting_rules(
    tmp_path: Path,
) -> None:
    source = tmp_path / "bloated"
    _write_skill(
        source,
        "Must publish checks.\nMust publish checks.\nNever publish checks.\n",
    )

    validation, outcome = _audit(PipelineOrchestrator(), source)

    check = next(
        item for item in validation.deterministic_evidence
        if item.check_id == "capability.skill_duplication_and_bloat"
    )
    assert check.status.value == "FAIL"
    assert any(
        all(field in evidence for field in (
            "file=", "line=", "finding=", "severity=", "reason=", "remediation=",
        ))
        for evidence in check.evidence
    )
    assert outcome.gate_result.verdict is GateVerdict.FAIL
    assert outcome.gate_result.apply_authorized is False


def test_missing_agents_md_provider_still_detects_instruction_conflict(
    tmp_path: Path,
) -> None:
    (tmp_path / "AGENTS.md").write_text("Must publish checks.\n", encoding="utf-8")
    source = tmp_path / "skills" / "demo"
    _write_skill(source, "Never publish checks.\n")

    validation, outcome = _audit(PipelineOrchestrator(), source)

    check = next(
        item for item in validation.deterministic_evidence
        if item.check_id == "capability.agent_instruction_governance"
    )
    assert check.status.value == "FAIL"
    assert outcome.gate_result.verdict is GateVerdict.FAIL


@pytest.mark.parametrize(
    "frontmatter,body,expected_check",
    [
        ("", "[missing](references/missing.md)\n", "reference.required.exists"),
        ("critical_assets:\n  - ../outside.txt\n", "", "skill.structure.critical_assets"),
        ("required_scripts:\n  - scripts/run.py\n", "", "skill.structure.scripts"),
    ],
)
def test_missing_validate_skills_provider_uses_deterministic_conformance_fallback(
    tmp_path: Path, frontmatter: str, body: str, expected_check: str,
) -> None:
    source = tmp_path / "demo"
    _write_skill(source, body, frontmatter)

    validation, outcome = _audit(PipelineOrchestrator(), source)

    assert any(
        item.check_id == expected_check and item.status.value == "FAIL"
        for item in validation.deterministic_evidence
    )
    assert outcome.gate_result.verdict is GateVerdict.FAIL


def test_broken_frontmatter_is_caught_without_validate_skills(tmp_path: Path) -> None:
    source = tmp_path / "broken"
    source.mkdir()
    (source / "SKILL.md").write_text("---\nname: [broken\n---\n", encoding="utf-8")

    validation, outcome = _audit(PipelineOrchestrator(), source)

    assert any(
        item.check_id == "skill.structure.frontmatter" and item.status.value == "FAIL"
        for item in validation.deterministic_evidence
    )
    assert outcome.gate_result.verdict is GateVerdict.FAIL


def test_unknown_required_domain_capability_is_incomplete_and_cannot_publish(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source" / "demo"
    _write_skill(source, extra_frontmatter="required_capabilities:\n  - domain_x\n")
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
        apply_requested=True,
    )

    with pytest.raises(PipelineBlockedError) as caught:
        orchestrator.confirm(validation, confirmation(validation.artifact_path))

    assert caught.value.gate_result.verdict is GateVerdict.INCOMPLETE
    assert caught.value.gate_result.apply_authorized is False
    assert not (destination / "demo").exists()


@dataclass
class CrashingProvider:
    descriptor: ProviderDescriptor

    def invoke(self, capability: str, request: dict[str, object]):
        raise TimeoutError("provider timed out")


@dataclass
class FindingProvider:
    descriptor: ProviderDescriptor

    def invoke(self, capability: str, request: dict[str, object]):
        return ProviderResult(
            self.descriptor.provider_id, capability, ProviderStatus.AVAILABLE,
            ("blocking provider finding",), (), ("provider audit executed",), (), False,
        )


def test_provider_failure_falls_back_and_can_pass_when_fallback_succeeds(
    tmp_path: Path,
) -> None:
    source = tmp_path / "demo"
    _write_skill(source)
    provider = CrashingProvider(ProviderDescriptor(
        "agent-skills-creator", "vendor/agent-skills", "r1", AUDIT_SKILL,
        ProviderStatus.AVAILABLE, "test", (), None,
    ))

    validation, outcome = _audit(
        PipelineOrchestrator(provider_gateway=ProviderGateway([provider])), source,
    )

    item = next(
        item for item in validation.capability_preflight
        if item.capability == SKILL_DUPLICATION_AND_BLOAT
    )
    assert item.status is CapabilityStatus.FALLBACK
    assert outcome.gate_result.verdict is GateVerdict.PASS


def test_provider_failure_uses_fallback_then_blocks_when_fallback_is_unavailable(
    tmp_path: Path,
) -> None:
    source = tmp_path / "demo"
    _write_skill(source)
    provider = CrashingProvider(ProviderDescriptor(
        "agent-skills-creator", "vendor/agent-skills", "r1", AUDIT_SKILL,
        ProviderStatus.AVAILABLE, "test", (), None,
    ))
    fallbacks = DEFAULT_INTERNAL_FALLBACKS - {SKILL_DUPLICATION_AND_BLOAT}
    orchestrator = PipelineOrchestrator(
        provider_gateway=ProviderGateway([provider]), internal_fallbacks=fallbacks,
    )

    validation, outcome = _audit(orchestrator, source)

    item = next(
        item for item in validation.capability_preflight
        if item.capability == SKILL_DUPLICATION_AND_BLOAT
    )
    assert item.status is CapabilityStatus.BLOCKED
    assert outcome.gate_result.verdict is GateVerdict.INCOMPLETE
    assert outcome.gate_result.apply_authorized is False


def test_fallback_override_does_not_replace_direct_core_implementation(tmp_path: Path) -> None:
    source = tmp_path / "demo"
    _write_skill(source)
    orchestrator = PipelineOrchestrator(fallback_equivalences={
        SKILL_DUPLICATION_AND_BLOAT: FallbackEquivalence.PARTIAL,
    })

    validation, outcome = _audit(orchestrator, source)

    item = next(
        value for value in validation.capability_preflight
        if value.capability == SKILL_DUPLICATION_AND_BLOAT
    )
    assert item.status is CapabilityStatus.READY
    assert item.selected_provider == "internal.core"
    assert item.fallback_equivalence is FallbackEquivalence.NONE
    assert outcome.gate_result.verdict is GateVerdict.PASS


def test_direct_core_implementation_executes_before_capability_can_pass(tmp_path: Path) -> None:
    source = tmp_path / "demo"
    _write_skill(source)

    validation, outcome = _audit(PipelineOrchestrator(), source)

    item = next(
        value for value in validation.capability_preflight
        if value.capability == SKILL_DUPLICATION_AND_BLOAT
    )
    executed = next(
        value for value in validation.deterministic_evidence
        if value.check_id == "capability.skill_duplication_and_bloat"
    )
    assert item.fallback_equivalence is FallbackEquivalence.NONE
    assert item.selected_provider == "internal.core"
    assert executed.status.value == "PASS"
    assert outcome.gate_result.verdict is GateVerdict.PASS


def test_successful_provider_findings_are_required_failures(tmp_path: Path) -> None:
    source = tmp_path / "demo"
    _write_skill(source)
    provider = FindingProvider(ProviderDescriptor(
        "agent-skills-creator", "vendor/agent-skills", "r1", AUDIT_SKILL,
        ProviderStatus.AVAILABLE, "test", (), None,
    ))

    validation, outcome = _audit(
        PipelineOrchestrator(provider_gateway=ProviderGateway([provider])), source,
    )

    provider_checks = tuple(
        item for item in validation.deterministic_evidence
        if item.source == "provider:agent-skills-creator" and item.required
    )
    assert provider_checks
    assert all(item.status.value == "FAIL" for item in provider_checks)
    assert outcome.gate_result.verdict is GateVerdict.FAIL


def test_missing_capability_execution_evidence_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "demo"
    _write_skill(source)
    monkeypatch.setattr(
        "engine.orchestrator.execute_internal_capability_fallbacks", lambda *args, **kwargs: (),
    )

    validation, outcome = _audit(PipelineOrchestrator(), source)

    assert any(
        item.check_id.endswith(".execution") and item.status.value == "NOT_EXECUTED"
        for item in validation.deterministic_evidence
    )
    assert outcome.gate_result.verdict is GateVerdict.INCOMPLETE


def test_internal_validator_crash_reports_framework_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "demo"
    _write_skill(source)

    def crash(_manifest):
        raise RuntimeError("validator crashed")

    monkeypatch.setattr("engine.orchestrator.validate_skill_structure", crash)
    _, outcome = _audit(PipelineOrchestrator(), source)

    assert outcome.gate_result.verdict is GateVerdict.ERROR
    assert outcome.gate_result.apply_authorized is False


def test_dogfood_fixture_exercises_all_required_failure_families() -> None:
    source = Path(__file__).parents[1] / "fixtures" / "skills" / "capability-dogfood"

    validation, outcome = _audit(PipelineOrchestrator(), source)

    checks = {item.check_id: item for item in validation.deterministic_evidence}
    assert checks["capability.skill_duplication_and_bloat"].status.value == "FAIL"
    assert checks["capability.agent_instruction_governance"].status.value == "FAIL"
    assert checks["capability.skill_resource_integrity"].status.value == "FAIL"
    assert checks["capability.skill_script_integrity"].status.value == "FAIL"
    assert outcome.gate_result.verdict is GateVerdict.INCOMPLETE
    assert outcome.gate_result.apply_authorized is False
