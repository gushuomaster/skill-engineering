import pytest

from engine.models import ProviderStatus
from engine.providers import (
    AUDIT_SKILL,
    CHECK_SKILL_CONFORMANCE,
    CREATE_CANDIDATE,
    GOVERN_AGENT_INSTRUCTIONS,
    ProviderGateway,
)


@pytest.mark.parametrize("capability", [CREATE_CANDIDATE, AUDIT_SKILL, GOVERN_AGENT_INSTRUCTIONS, CHECK_SKILL_CONFORMANCE])
def test_pipeline_capability_available_when_external_providers_disabled(capability: str) -> None:
    result = ProviderGateway().invoke(capability, {"subject": "demo"}, formal_run=True)
    assert result.fallback_used
    assert result.provider_status is ProviderStatus.AVAILABLE
    assert result.evidence
