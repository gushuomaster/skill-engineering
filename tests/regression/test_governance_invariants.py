from pathlib import Path

import pytest

from dataclasses import dataclass
from engine.models import GateOutcome, GateResult, GateVerdict, Intent, ProviderDescriptor, ProviderResult, ProviderStatus
from engine.orchestrator import EngineeringRequest, PipelineBlockedError, PipelineOrchestrator
from engine.workspace import CrossFilesystemPublishError, WorkspaceSession, publish_atomic


FIXTURE = Path(__file__).parents[1] / "fixtures" / "skills" / "minimal-valid"


def _gate(**overrides):
    values = dict(verdict=GateVerdict.PASS, outcome=GateOutcome.READY_TO_PUBLISH,
                  blocking_findings=(), warnings=(), required_checks_summary="ok",
                  evidence_summary="ok", publish_authorized=True, policy_version="v1")
    values.update(overrides)
    return GateResult(**values)


def test_provider_pass_cannot_bypass_gate(tmp_path: Path) -> None:
    @dataclass
    class PassingProvider:
        descriptor: ProviderDescriptor
        def invoke(self, capability: str, request: dict[str, object]) -> ProviderResult:
            return ProviderResult("external.audit", capability, ProviderStatus.AVAILABLE, (), (), ("provider PASS",), (), False)

    from engine.providers import AUDIT_SKILL, ProviderGateway
    provider = PassingProvider(ProviderDescriptor("external.audit", "vendor/audit", "r1", AUDIT_SKILL, ProviderStatus.AVAILABLE, "test", (), None))
    with pytest.raises(PipelineBlockedError):
        PipelineOrchestrator(provider_gateway=ProviderGateway([provider])).run(
            EngineeringRequest("fix", Intent.FIX, FIXTURE, (), True, tmp_path)
        )


def test_audit_only_never_auto_upgrades(tmp_path: Path) -> None:
    result = PipelineOrchestrator().run(EngineeringRequest("audit", Intent.AUDIT_ONLY, FIXTURE, (), False, tmp_path))
    assert result.gate_result.publish_authorized is False
    assert result.artifact_path == FIXTURE


def test_cross_volume_publish_fails(tmp_path: Path, monkeypatch) -> None:
    session = WorkspaceSession.for_existing(Intent.MODIFY, FIXTURE)
    session.prepare(tmp_path)
    monkeypatch.setattr("engine.workspace._same_filesystem", lambda *_: False)
    with pytest.raises(CrossFilesystemPublishError):
        publish_atomic(session, _gate())


def test_missing_required_evidence_never_passes(tmp_path: Path) -> None:
    with pytest.raises(PipelineBlockedError) as caught:
        PipelineOrchestrator().run(EngineeringRequest("fix", Intent.FIX, FIXTURE, (), True, tmp_path))
    assert caught.value.gate_result.verdict is GateVerdict.FAIL
