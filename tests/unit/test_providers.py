from dataclasses import dataclass

import pytest

from engine.models import ProviderDescriptor, ProviderResult, ProviderStatus
from engine.providers import (
    AUDIT_SKILL,
    CHECK_SKILL_CONFORMANCE,
    CREATE_CANDIDATE,
    GOVERN_AGENT_INSTRUCTIONS,
    ProviderGateway,
    provider_result_to_check_result,
    normalize_findings,
    normalize_provider_result,
)


@dataclass
class StubProvider:
    descriptor: ProviderDescriptor
    result: object

    def invoke(self, capability: str, request: dict[str, object]) -> object:
        return self.result


@dataclass
class RaisingProvider:
    descriptor: ProviderDescriptor
    error: Exception

    def invoke(self, capability: str, request: dict[str, object]) -> object:
        raise self.error


def provider(provider_id: str = "external", *, source_identity: str | None = "test/source", revision: str | None = "r1", status: ProviderStatus = ProviderStatus.AVAILABLE, result: object | None = None) -> StubProvider:
    descriptor = ProviderDescriptor(provider_id, source_identity, revision, AUDIT_SKILL, status, "test", (), None)
    value = result or ProviderResult(provider_id, AUDIT_SKILL, status, ("finding",), (), ("evidence",), (), False)
    return StubProvider(descriptor, value)


def test_gateway_invokes_adapter_without_host_specific_arguments() -> None:
    adapter = provider()
    result = ProviderGateway([adapter]).invoke(AUDIT_SKILL, {"subject": "skill"}, formal_run=False)
    assert result.provider_id == "external"
    assert result.findings == ("finding",)


def test_formal_run_skips_unpinned_provider_without_fabricating_fallback() -> None:
    adapter = provider(revision=None)
    result = ProviderGateway([adapter]).invoke(AUDIT_SKILL, {}, formal_run=True)
    assert result.provider_status is ProviderStatus.UNAVAILABLE
    assert result.fallback_used is False


@pytest.mark.parametrize("status", [ProviderStatus.UNAVAILABLE, ProviderStatus.INVALID_OUTPUT, ProviderStatus.TIMEOUT, ProviderStatus.INCOMPATIBLE])
def test_external_failure_is_reported_as_optional_unavailable(status: ProviderStatus) -> None:
    adapter = provider(status=status)
    result = ProviderGateway([adapter]).invoke(AUDIT_SKILL, {}, formal_run=False)
    assert result.fallback_used is False
    assert result.provider_status is ProviderStatus.UNAVAILABLE


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


@pytest.mark.parametrize("capability", [
    CREATE_CANDIDATE, AUDIT_SKILL, GOVERN_AGENT_INSTRUCTIONS, CHECK_SKILL_CONFORMANCE,
])
def test_every_provider_capability_is_optional(capability: str) -> None:
    result = ProviderGateway().invoke(capability, {}, formal_run=True)
    assert result.provider_status is ProviderStatus.UNAVAILABLE
    assert result.fallback_used is False


def test_identity_does_not_change_normalized_findings() -> None:
    first = ProviderGateway([provider("alpha")]).invoke(AUDIT_SKILL, {}, False)
    second = ProviderGateway([provider("beta")]).invoke(AUDIT_SKILL, {}, False)
    assert normalize_findings(first) == normalize_findings(second)


@pytest.mark.parametrize("revision", ["", "   ", "\t\n"])
def test_formal_run_treats_blank_revision_as_unpinned(revision: str) -> None:
    adapter = provider(revision=revision)
    result = ProviderGateway([adapter]).invoke(AUDIT_SKILL, {}, formal_run=True)
    assert result.provider_status is ProviderStatus.UNAVAILABLE


@pytest.mark.parametrize("source_identity", [None, "", "   ", "\t\n"])
def test_formal_run_treats_blank_source_identity_as_unpinned(source_identity: str | None) -> None:
    adapter = provider(source_identity=source_identity)
    result = ProviderGateway([adapter]).invoke(AUDIT_SKILL, {}, formal_run=True)
    assert result.provider_status is ProviderStatus.UNAVAILABLE


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


def test_custom_fallback_override_does_not_create_other_fallbacks() -> None:
    custom = provider("custom-fallback")
    result = ProviderGateway(fallbacks={AUDIT_SKILL: custom}).invoke(
        CREATE_CANDIDATE, {}, formal_run=True,
    )
    assert result.provider_status is ProviderStatus.UNAVAILABLE
    assert result.fallback_used is False


def test_provider_evidence_is_never_marked_deterministic() -> None:
    result = ProviderResult(
        "external", AUDIT_SKILL, ProviderStatus.AVAILABLE,
        (), (), ("review ran",), (), False,
    )
    check = provider_result_to_check_result(result, subject="demo")
    assert check.deterministic is False
    assert check.reproducible is False


def test_fallback_invoke_error_returns_optional_unavailable_result() -> None:
    descriptor = ProviderDescriptor(
        "raising-fallback", "test/source", "r1", AUDIT_SKILL,
        ProviderStatus.AVAILABLE, "test", (), None,
    )
    fallback = RaisingProvider(descriptor, RuntimeError("fallback exploded"))
    result = ProviderGateway(fallbacks={AUDIT_SKILL: fallback}).invoke(
        AUDIT_SKILL, {}, formal_run=True,
    )
    assert result.provider_status is ProviderStatus.UNAVAILABLE
    assert result.fallback_used is False
    assert any("fallback exploded" in limitation for limitation in result.limitations)


def test_fallback_normalization_error_returns_optional_unavailable_result() -> None:
    fallback = provider("invalid-fallback", result={"capability": AUDIT_SKILL})
    result = ProviderGateway(fallbacks={AUDIT_SKILL: fallback}).invoke(
        AUDIT_SKILL, {}, formal_run=True,
    )
    assert result.provider_status is ProviderStatus.UNAVAILABLE
    assert result.fallback_used is False
    assert any("invalid provider result" in limitation for limitation in result.limitations)
