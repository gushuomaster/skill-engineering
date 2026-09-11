import pytest

from engine.diagnostics import DiagnosticInput, InvalidDecisionRecord, validate_classification
from engine.models import (
    ControlGap,
    DecisionRecord,
    Intent,
    PrimaryIssueClass,
    RegressionDisposition,
)


def decision(
    *,
    intent: Intent = Intent.CREATE,
    primary: PrimaryIssueClass = PrimaryIssueClass.NO_DEFECT,
    control_gaps: tuple[ControlGap, ...] = (ControlGap.NONE,),
    regression: RegressionDisposition = RegressionDisposition.NOT_APPLICABLE,
    root_cause: str | None = None,
    evidence_limitations: tuple[str, ...] = (),
    selected_mechanisms: tuple[str, ...] = (),
    rejected_mechanisms: tuple[str, ...] = (),
    prompt_rule_justification: str | None = None,
) -> DecisionRecord:
    return DecisionRecord(
        intent=intent,
        primary_issue_class=primary,
        control_gaps=control_gaps,
        regression_disposition=regression,
        root_cause=root_cause,
        evidence_limitations=evidence_limitations,
        selected_mechanisms=selected_mechanisms,
        rejected_mechanisms=rejected_mechanisms,
        prompt_rule_justification=prompt_rule_justification,
    )


def test_fix_requires_root_cause() -> None:
    with pytest.raises(InvalidDecisionRecord, match="root cause"):
        validate_classification(decision(intent=Intent.FIX))


def test_diagnostic_input_keeps_requirement_and_failure_evidence() -> None:
    diagnostic_input = DiagnosticInput(
        intent=Intent.FIX,
        requirement="Repair the parser.",
        failure_evidence=("Invalid input was accepted.",),
        defect_found=True,
    )
    assert diagnostic_input.failure_evidence == ("Invalid input was accepted.",)


def test_create_accepts_no_root_cause() -> None:
    validate_classification(decision(intent=Intent.CREATE))


def test_invariant_only_modify_accepts_no_root_cause() -> None:
    validate_classification(
        decision(
            intent=Intent.MODIFY,
            primary=PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE,
        )
    )


def test_modify_defect_requires_root_cause() -> None:
    with pytest.raises(InvalidDecisionRecord, match="root cause"):
        validate_classification(
            decision(
                intent=Intent.MODIFY,
                primary=PrimaryIssueClass.IMPLEMENTATION_DEFECT,
            )
        )


def test_audit_defect_requires_root_cause() -> None:
    with pytest.raises(InvalidDecisionRecord, match="root cause"):
        validate_classification(
            decision(
                intent=Intent.AUDIT_ONLY,
                primary=PrimaryIssueClass.CONTRACT_ENFORCEMENT_GAP,
            )
        )


def test_dimensions_remain_independent() -> None:
    validate_classification(
        decision(
            intent=Intent.FIX,
            primary=PrimaryIssueClass.ENVIRONMENT_COMPATIBILITY,
            control_gaps=(ControlGap.ENV_DETECTION_MISSING, ControlGap.REGRESSION_MISSING),
            regression=RegressionDisposition.REQUIRED,
            root_cause="The tool assumes an unsupported shell encoding.",
        )
    )


def test_insufficient_evidence_requires_a_recorded_limitation() -> None:
    with pytest.raises(InvalidDecisionRecord, match="evidence limitation"):
        validate_classification(
            decision(primary=PrimaryIssueClass.INSUFFICIENT_EVIDENCE)
        )


def test_task_local_preference_cannot_contain_persistent_mechanisms() -> None:
    with pytest.raises(InvalidDecisionRecord, match="TASK_LOCAL_PREFERENCE"):
        validate_classification(
            decision(
                primary=PrimaryIssueClass.TASK_LOCAL_PREFERENCE,
                selected_mechanisms=("implementation_fix",),
            )
        )
