from pathlib import Path

import pytest

from dataclasses import dataclass
from engine.models import GateOutcome, GateResult, GateVerdict, Intent, ProviderDescriptor, ProviderResult, ProviderStatus, PrimaryIssueClass, RegressionDisposition
from engine.orchestrator import EngineeringRequest, PipelineBlockedError, PipelineOrchestrator
from engine.inventory import digest_tree
from engine.workspace import CrossFilesystemPublishError, WorkspaceSession, publish_atomic
from engine.mechanism_selection import IMPLEMENTATION_FIX, REGRESSION_TEST
from tests.support import codex_decision, confirmation, copy_candidate


FIXTURE = Path(__file__).parents[1] / "fixtures" / "skills" / "minimal-valid"


def _gate(**overrides):
    values = dict(verdict=GateVerdict.PASS, outcome=GateOutcome.READY_TO_PUBLISH,
                  blocking_findings=(), warnings=(), required_checks_summary="ok",
                  evidence_summary="ok", semantic_confirmed=True,
                  publish_authorized=True, policy_version="v1")
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
    candidate_parent = tmp_path / "codex"; candidate_parent.mkdir()
    candidate = copy_candidate(FIXTURE, candidate_parent)
    with pytest.raises(PipelineBlockedError):
        PipelineOrchestrator(provider_gateway=ProviderGateway([provider])).run(
            EngineeringRequest(
                "fix", Intent.FIX,
                codex_decision(Intent.FIX, primary=PrimaryIssueClass.IMPLEMENTATION_DEFECT,
                               selected=(IMPLEMENTATION_FIX, REGRESSION_TEST),
                               regression=RegressionDisposition.REQUIRED,
                               root_cause="Codex reproduced the defect"),
                FIXTURE, candidate, ("reproduced",), True, tmp_path,
                semantic_confirmation=confirmation(candidate),
            )
        )


def test_audit_only_never_auto_upgrades(tmp_path: Path) -> None:
    result = PipelineOrchestrator().run(EngineeringRequest(
        "audit", Intent.AUDIT_ONLY, codex_decision(Intent.AUDIT_ONLY),
        FIXTURE, None, (), False, tmp_path, semantic_confirmation=confirmation(FIXTURE),
    ))
    assert result.gate_result.publish_authorized is False
    assert result.artifact_path == FIXTURE


def test_audit_only_scope_fix_preserves_source_and_ignores_runtime_placeholder(tmp_path: Path) -> None:
    source = tmp_path / "example-skill"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: example-skill\ndescription: Example\n---\n\nComplete.\n",
        encoding="utf-8",
    )
    runtime_file = source / ".venv" / "Lib" / "site-packages" / "third_party.py"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_text("# TODO: vendor note\n", encoding="utf-8")
    before = digest_tree(source)
    result = PipelineOrchestrator().run(
        EngineeringRequest(
            "audit", Intent.AUDIT_ONLY, codex_decision(Intent.AUDIT_ONLY),
            source, None, (), False, tmp_path, semantic_confirmation=confirmation(source),
        )
    )
    assert result.gate_result.verdict is GateVerdict.PASS
    assert result.gate_result.publish_authorized is False
    assert digest_tree(source) == before
    assert not any("skill.structure.placeholders" in finding for finding in result.gate_result.blocking_findings)


def test_cross_volume_publish_fails(tmp_path: Path, monkeypatch) -> None:
    session = WorkspaceSession.for_existing(Intent.MODIFY, FIXTURE)
    session.prepare(tmp_path)
    session.bind_confirmed_artifact(session.staging, digest_tree(session.staging))
    monkeypatch.setattr("engine.workspace._same_filesystem", lambda *_: False)
    with pytest.raises(CrossFilesystemPublishError):
        publish_atomic(session, _gate())


def test_missing_required_evidence_never_passes(tmp_path: Path) -> None:
    candidate_parent = tmp_path / "codex"; candidate_parent.mkdir()
    candidate = copy_candidate(FIXTURE, candidate_parent)
    with pytest.raises(PipelineBlockedError) as caught:
        PipelineOrchestrator().run(EngineeringRequest(
            "fix", Intent.FIX,
            codex_decision(Intent.FIX, primary=PrimaryIssueClass.IMPLEMENTATION_DEFECT,
                           selected=(IMPLEMENTATION_FIX, REGRESSION_TEST),
                           regression=RegressionDisposition.REQUIRED,
                           root_cause="Codex reproduced the defect"),
            FIXTURE, candidate, ("reproduced",), True, tmp_path,
            semantic_confirmation=confirmation(candidate),
        ))
    assert caught.value.gate_result.verdict is GateVerdict.FAIL
