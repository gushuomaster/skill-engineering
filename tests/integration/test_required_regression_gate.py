from dataclasses import replace

import pytest

from engine.models import CheckResult, CheckStatus, DecisionRecord, Intent, LifecycleState, PrimaryIssueClass, ControlGap, RegressionDisposition
from engine.quality_gate import GateContext, adjudicate


def _check(check_id: str) -> CheckResult:
    return CheckResult(check_id, "internal", "demo", True, CheckStatus.PASS, True, True, 1.0, ("verified",), LifecycleState.VALIDATED, None)


def _evidence() -> tuple[CheckResult, ...]:
    ids = ("skill.structure.skill_md", "skill.structure.frontmatter", "skill.structure.name_format", "skill.structure.directory_name", "skill.structure.placeholders", "skill.structure.critical_assets", "skill.structure.schema", "skill.structure.executables", "skill.structure.required_dependencies")
    return tuple(_check(check_id) for check_id in ids)


def _context() -> GateContext:
    decision = DecisionRecord(Intent.FIX, PrimaryIssueClass.IMPLEMENTATION_DEFECT, (ControlGap.IMPLEMENTATION_GAP,), RegressionDisposition.REQUIRED, "known defect", (), (), (), None)
    return GateContext(Intent.FIX, LifecycleState.VALIDATED, True, True, True, decision, True)


def test_required_regression_failure_blocks_gate() -> None:
    regression = _check("B07")
    regression = replace(regression, status=CheckStatus.FAIL, evidence=("regression failed",))
    result = adjudicate(_context(), _evidence() + (regression,))
    assert result.verdict.value == "FAIL"
    assert any(finding.startswith("B07") for finding in result.blocking_findings)


def test_required_regression_untrustworthy_adds_b08() -> None:
    regression = replace(_check("B07"), deterministic=False, evidence=("not reproducible",))
    result = adjudicate(_context(), _evidence() + (regression,))
    assert any(finding.startswith("B08") for finding in result.blocking_findings)


def test_recommended_regression_absence_is_warning_only() -> None:
    decision = replace(_context().decision, regression_disposition=RegressionDisposition.RECOMMENDED)
    context = replace(_context(), decision=decision)
    result = adjudicate(context, _evidence())
    assert result.verdict.value == "PASS"
    assert any("recommended regression" in warning for warning in result.warnings)


@pytest.mark.parametrize("status", [CheckStatus.FAIL, CheckStatus.ERROR, CheckStatus.NOT_EXECUTED])
def test_recommended_regression_nonpassing_is_warning_only(status: CheckStatus) -> None:
    decision = replace(_context().decision, regression_disposition=RegressionDisposition.RECOMMENDED)
    context = replace(_context(), decision=decision)
    regression = replace(_check("B07"), required=True, status=status)

    result = adjudicate(context, _evidence() + (regression,))

    assert result.verdict.value == "PASS"
    assert not any(finding.startswith("B07") for finding in result.blocking_findings)
    assert any("B07" in warning for warning in result.warnings)


def test_required_optional_regression_blocks_with_b07_and_b08() -> None:
    regression = replace(_check("B07"), required=False)

    result = adjudicate(_context(), _evidence() + (regression,))

    assert any(finding.startswith("B07") for finding in result.blocking_findings)
    assert any(finding.startswith("B08") for finding in result.blocking_findings)


def test_required_untrustworthy_passing_regression_blocks_with_b07_and_b08() -> None:
    regression = replace(_check("B07"), deterministic=False)

    result = adjudicate(_context(), _evidence() + (regression,))

    assert any(finding.startswith("B07") for finding in result.blocking_findings)
    assert any(finding.startswith("B08") for finding in result.blocking_findings)


def test_not_applicable_regression_does_not_synthesize_result() -> None:
    decision = replace(_context().decision, regression_disposition=RegressionDisposition.NOT_APPLICABLE)
    context = replace(_context(), decision=decision)

    result = adjudicate(context, _evidence())

    assert result.verdict.value == "PASS"
    assert not any("B07" in finding for finding in result.blocking_findings)
    assert not any("B07" in warning for warning in result.warnings)
    assert result.evidence_summary.startswith("9 valid evidence results")
