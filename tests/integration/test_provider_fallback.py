from dataclasses import dataclass
from pathlib import Path

import pytest

from engine.models import (
    Intent,
    ProviderDescriptor,
    ProviderResult,
    ProviderStatus,
)
from engine.orchestrator import EngineeringRequest, PipelineOrchestrator
from engine.providers import (
    AUDIT_SKILL,
    CHECK_SKILL_CONFORMANCE,
    CREATE_CANDIDATE,
    GOVERN_AGENT_INSTRUCTIONS,
    ProviderGateway,
)
from tests.support import codex_decision, confirmation


@dataclass
class StubProvider:
    descriptor: ProviderDescriptor
    result: ProviderResult

    def invoke(self, capability: str, request: dict[str, object]) -> ProviderResult:
        return self.result


@pytest.mark.parametrize("capability", [CREATE_CANDIDATE, AUDIT_SKILL, GOVERN_AGENT_INSTRUCTIONS, CHECK_SKILL_CONFORMANCE])
def test_provider_capability_unavailable_is_explicit_when_disabled(capability: str) -> None:
    result = ProviderGateway().invoke(capability, {"subject": "demo"}, formal_run=True)
    assert result.fallback_used is False
    assert result.provider_status is ProviderStatus.UNAVAILABLE
    assert result.limitations


def test_selected_provider_finding_becomes_required_gate_failure(tmp_path: Path) -> None:
    source = Path(__file__).parents[1] / "fixtures" / "skills" / "minimal-valid"
    descriptor = ProviderDescriptor(
        "external.audit",
        "vendor/audit",
        "r1",
        AUDIT_SKILL,
        ProviderStatus.AVAILABLE,
        "test",
        (),
        None,
    )
    provider = StubProvider(
        descriptor,
        ProviderResult(
            "external.audit",
            AUDIT_SKILL,
            ProviderStatus.AVAILABLE,
            ("advisory finding",),
            (),
            ("provider report",),
            ("provider limitation",),
            False,
        ),
    )
    from engine.providers import ProviderGateway

    request = EngineeringRequest(
        requirement="audit this skill",
        intent=Intent.AUDIT_ONLY,
        decision=codex_decision(Intent.AUDIT_ONLY),
        source=source,
        candidate=None,
        failure_evidence=(),
        authorized_to_modify=False,
        target_parent=tmp_path,
        semantic_confirmation=confirmation(source),
    )
    outcome = PipelineOrchestrator(provider_gateway=ProviderGateway([provider])).run(request)

    assert outcome.gate_result.verdict.value == "FAIL"
    assert outcome.gate_result.apply_authorized is False
    assert any(
        item.source == "provider:external.audit" and item.required
        and item.status.value == "FAIL"
        for item in outcome.deterministic_evidence
    )
    assert any("advisory finding" in warning for warning in outcome.gate_result.warnings)
    assert any("provider limitation" in warning for warning in outcome.gate_result.warnings)
