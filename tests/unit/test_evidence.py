import pytest

from engine.evidence import EvidenceCollector, InvalidEvidence
from engine.models import CheckResult, CheckStatus, LifecycleState


def _result(**overrides):
    values = dict(check_id="check", source="internal", subject="demo", required=True,
                  status=CheckStatus.PASS, deterministic=True, reproducible=True,
                  confidence=1.0, evidence=("ok",), remediation_stage=LifecycleState.VALIDATED,
                  artifact_reference=None)
    values.update(overrides)
    return CheckResult(**values)


def test_optional_provider_error_is_not_required() -> None:
    collector = EvidenceCollector()
    collector.add(_result(required=False, status=CheckStatus.ERROR))
    assert collector.required_results() == ()
    assert len(collector.optional_results()) == 1


def test_malformed_result_is_rejected() -> None:
    collector = EvidenceCollector()
    with pytest.raises(InvalidEvidence):
        collector.add(_result(check_id="", evidence=()))


def test_conflicting_duplicate_is_rejected() -> None:
    collector = EvidenceCollector()
    collector.add(_result())
    with pytest.raises(InvalidEvidence):
        collector.add(_result(status=CheckStatus.FAIL, evidence=("bad",)))


def test_skip_without_reason_is_rejected() -> None:
    collector = EvidenceCollector()
    with pytest.raises(InvalidEvidence):
        collector.add(_result(status=CheckStatus.SKIP, evidence=()))


def test_non_enum_status_is_rejected() -> None:
    collector = EvidenceCollector()
    with pytest.raises(InvalidEvidence):
        collector.add(_result(status="PASS"))
