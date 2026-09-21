from dataclasses import replace
from pathlib import Path

from engine.governance_api import (
    CoverageStatus,
    GateStatus,
    GovernanceEngine,
    GovernanceMode,
    GovernanceRequest,
    GovernanceStatus,
    ProviderObservation,
)
from engine.governance_api import _digest_path


def _request(tmp_path: Path, **overrides) -> GovernanceRequest:
    source = tmp_path / "source"
    candidate = tmp_path / "candidate"
    source.mkdir()
    candidate.mkdir()
    (source / "SKILL.md").write_text("source", encoding="utf-8")
    (candidate / "SKILL.md").write_text("candidate", encoding="utf-8")
    request = GovernanceRequest(
        request_id="req-1",
        action_type="FIX",
        required_capabilities=("DELIVERABLE_CONTRACT",),
        applicability={"deliverable_contract": "required"},
        validation_status="PASS",
        coverage_status="COMPLETE",
        integrity_status="PASS",
        source_digest=_digest_path(source),
        candidate_digest=_digest_path(candidate),
        source_path=str(source),
        candidate_path=str(candidate),
        providers=(
            ProviderObservation(
                provider_id="provider.contract",
                capability="DELIVERABLE_CONTRACT",
                available=True,
                selected=True,
                executed=True,
                status="PASS",
                evidence_valid=True,
                evidence_refs=("evidence:contract",),
            ),
        ),
        deliverable_contract={"status": "PASS"},
    )
    return replace(request, **overrides)


def test_public_api_authorizes_only_complete_verified_request(tmp_path: Path) -> None:
    request = _request(tmp_path)
    result = GovernanceEngine(engine_version="1.0.3", engine_revision="abc123").evaluate(request)

    assert result.gate_status is GateStatus.PASS
    assert result.publish_authorized is True
    assert result.coverage_status is CoverageStatus.COMPLETE
    assert result.integrity_status is GovernanceStatus.PASS
    assert result.engine_version == "1.0.3"
    assert result.engine_revision == "abc123"


def test_required_provider_not_executed_is_incomplete(tmp_path: Path) -> None:
    request = _request(
        tmp_path,
        providers=(
            ProviderObservation(
                provider_id="provider.contract",
                capability="DELIVERABLE_CONTRACT",
                available=True,
                selected=True,
                executed=False,
            ),
        ),
        deliverable_contract=None,
    )
    result = GovernanceEngine().evaluate(request)

    assert result.gate_status is GateStatus.INCOMPLETE
    assert result.publish_authorized is False
    assert "provider_not_executed" in result.reason_codes


def test_digest_change_blocks_publication(tmp_path: Path) -> None:
    request = _request(tmp_path, source_digest="wrong")
    result = GovernanceEngine().evaluate(request)

    assert result.gate_status is GateStatus.BLOCKED
    assert result.integrity_status is GovernanceStatus.FAIL
    assert "source_digest_mismatch" in result.reason_codes


def test_deliverable_contract_mismatch_blocks_publication(tmp_path: Path) -> None:
    request = _request(tmp_path, deliverable_contract={"status": "INCOMPLETE"})
    result = GovernanceEngine().evaluate(request)

    assert result.gate_status is GateStatus.INCOMPLETE
    assert result.publish_authorized is False
    assert "deliverable_contract_incomplete" in result.reason_codes


def test_shadow_mode_never_authorizes_publish(tmp_path: Path) -> None:
    result = GovernanceEngine(mode=GovernanceMode.SHADOW).evaluate(_request(tmp_path))

    assert result.gate_status is GateStatus.PASS
    assert result.publish_authorized is False
    assert "shadow_mode" in result.reason_codes
