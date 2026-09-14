from dataclasses import dataclass

import pytest

from engine.models import ProviderDescriptor, ProviderResult, ProviderStatus
from engine.providers import (
    AUDIT_SKILL,
    CHECK_SKILL_CONFORMANCE,
    CREATE_CANDIDATE,
    GOVERN_AGENT_INSTRUCTIONS,
    ProviderGateway,
    normalize_findings,
    normalize_provider_result,
)


@dataclass
class StubProvider:
    descriptor: ProviderDescriptor
    result: object

    def invoke(self, capability: str, request: dict[str, object]) -> object:
        return self.result


def provider(provider_id: str = "external", *, source_identity: str | None = "test/source", revision: str | None = "r1", status: ProviderStatus = ProviderStatus.AVAILABLE, result: object | None = None) -> StubProvider:
    descriptor = ProviderDescriptor(provider_id, source_identity, revision, AUDIT_SKILL, status, "test", (), None)
    value = result or ProviderResult(provider_id, AUDIT_SKILL, status, ("finding",), (), ("evidence",), (), False)
    return StubProvider(descriptor, value)


def test_gateway_invokes_adapter_without_host_specific_arguments() -> None:
    adapter = provider()
    result = ProviderGateway([adapter]).invoke(AUDIT_SKILL, {"subject": "skill"}, formal_run=False)
    assert result.provider_id == "external"
    assert result.findings == ("finding",)


def test_formal_run_skips_unpinned_provider_and_uses_internal_fallback() -> None:
    adapter = provider(revision=None)
    result = ProviderGateway([adapter]).invoke(AUDIT_SKILL, {}, formal_run=True)
    assert result.provider_id == "internal.audit.v1"
    assert result.fallback_used is True
    assert result.provider_status is ProviderStatus.AVAILABLE


@pytest.mark.parametrize("status", [ProviderStatus.UNAVAILABLE, ProviderStatus.INVALID_OUTPUT, ProviderStatus.TIMEOUT, ProviderStatus.INCOMPATIBLE])
def test_external_failure_uses_internal_fallback(status: ProviderStatus) -> None:
    adapter = provider(status=status)
    result = ProviderGateway([adapter]).invoke(AUDIT_SKILL, {}, formal_run=False)
    assert result.fallback_used is True
    assert result.provider_id == "internal.audit.v1"


def test_provider_result_normalization_rejects_final_authority_fields() -> None:
    with pytest.raises(ValueError):
        normalize_provider_result({
            "provider_id": "external",
            "capability": AUDIT_SKILL,
            "provider_status": "AVAILABLE",
            "findings": [],
            "candidate_changes": [],
            "evidence": [],
            "limitations": [],
            "fallback_used": False,
            "final_gate_verdict": "PASS",
        })


@pytest.mark.parametrize("capability,provider_id", [
    (CREATE_CANDIDATE, "internal.create.v1"),
    (AUDIT_SKILL, "internal.audit.v1"),
    (GOVERN_AGENT_INSTRUCTIONS, "internal.agents-governance.v1"),
    (CHECK_SKILL_CONFORMANCE, "internal.structure-validator.v1"),
])
def test_every_capability_has_internal_fallback(capability: str, provider_id: str) -> None:
    result = ProviderGateway().invoke(capability, {}, formal_run=True)
    assert result.provider_id == provider_id
    assert result.fallback_used is True


def test_identity_does_not_change_normalized_findings() -> None:
    first = ProviderGateway([provider("alpha")]).invoke(AUDIT_SKILL, {}, False)
    second = ProviderGateway([provider("beta")]).invoke(AUDIT_SKILL, {}, False)
    assert normalize_findings(first) == normalize_findings(second)


@pytest.mark.parametrize("revision", ["", "   ", "\t\n"])
def test_formal_run_treats_blank_revision_as_unpinned(revision: str) -> None:
    adapter = provider(revision=revision)
    result = ProviderGateway([adapter]).invoke(AUDIT_SKILL, {}, formal_run=True)
    assert result.provider_id == "internal.audit.v1"


@pytest.mark.parametrize("source_identity", [None, "", "   ", "\t\n"])
def test_formal_run_treats_blank_source_identity_as_unpinned(source_identity: str | None) -> None:
    adapter = provider(source_identity=source_identity)
    result = ProviderGateway([adapter]).invoke(AUDIT_SKILL, {}, formal_run=True)
    assert result.provider_id == "internal.audit.v1"


def test_gateway_marks_fallback_used_even_when_fallback_result_does_not() -> None:
    fallback = provider("custom-fallback", result=ProviderResult(
        "custom-fallback", AUDIT_SKILL, ProviderStatus.AVAILABLE,
        (), (), ("fallback evidence",), (), False,
    ))
    result = ProviderGateway(fallbacks={AUDIT_SKILL: fallback}).invoke(
        AUDIT_SKILL, {}, formal_run=True,
    )
    assert result.provider_id == "custom-fallback"
    assert result.fallback_used is True


def test_gateway_accepts_explicit_empty_fallback_as_optional() -> None:
    result = ProviderGateway(fallbacks={AUDIT_SKILL: None}).invoke(
        AUDIT_SKILL, {}, formal_run=True,
    )
    assert result.provider_status is ProviderStatus.UNAVAILABLE
    assert result.fallback_used is False
    assert result.limitations
