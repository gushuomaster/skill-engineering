"""Validation for three-dimensional diagnostic classifications."""

from dataclasses import dataclass

from engine.models import (
    ControlGap,
    DecisionRecord,
    Intent,
    PrimaryIssueClass,
    RegressionDisposition,
)


class InvalidDecisionRecord(ValueError):
    """Raised when a diagnostic record violates a frozen invariant."""


@dataclass(frozen=True)
class DiagnosticInput:
    """Input facts used to form a diagnostic classification."""

    intent: Intent
    requirement: str
    failure_evidence: tuple[str, ...]
    defect_found: bool


_DEFECT_CLASSES = frozenset(
    {
        PrimaryIssueClass.IMPLEMENTATION_DEFECT,
        PrimaryIssueClass.ENVIRONMENT_COMPATIBILITY,
        PrimaryIssueClass.WORKFLOW_DESIGN_DEFECT,
        PrimaryIssueClass.CONTRACT_ENFORCEMENT_GAP,
        PrimaryIssueClass.DOCUMENTATION_GAP,
    }
)


def _requires_root_cause(record: DecisionRecord) -> bool:
    if record.primary_issue_class is PrimaryIssueClass.INSUFFICIENT_EVIDENCE:
        return False
    if record.intent is Intent.FIX:
        return True
    return record.intent in {Intent.MODIFY, Intent.AUDIT_ONLY, Intent.AUDIT_OPTIMIZE} and (
        record.primary_issue_class in _DEFECT_CLASSES
    )


def validate_classification(record: DecisionRecord) -> None:
    """Ensure a diagnostic record retains the frozen classification semantics."""
    if not isinstance(record.intent, Intent):
        raise InvalidDecisionRecord("intent must be an Intent")
    if not isinstance(record.primary_issue_class, PrimaryIssueClass):
        raise InvalidDecisionRecord("primary issue class must be a PrimaryIssueClass")
    if not isinstance(record.regression_disposition, RegressionDisposition):
        raise InvalidDecisionRecord(
            "regression disposition must be a RegressionDisposition"
        )
    if not record.control_gaps:
        raise InvalidDecisionRecord("control gaps must record a classification dimension")
    if any(not isinstance(control_gap, ControlGap) for control_gap in record.control_gaps):
        raise InvalidDecisionRecord("each control gap must be a ControlGap")
    if ControlGap.NONE in record.control_gaps and len(record.control_gaps) != 1:
        raise InvalidDecisionRecord("NONE cannot be combined with another control gap")
    if _requires_root_cause(record) and not _non_empty(record.root_cause):
        raise InvalidDecisionRecord("a root cause is required for this defect flow")
    if record.primary_issue_class is PrimaryIssueClass.INSUFFICIENT_EVIDENCE:
        if not record.evidence_limitations:
            raise InvalidDecisionRecord("INSUFFICIENT_EVIDENCE requires an evidence limitation")
        if any(not _non_empty(limitation) for limitation in record.evidence_limitations):
            raise InvalidDecisionRecord("each evidence limitation must be nonblank")
        if record.root_cause is not None:
            raise InvalidDecisionRecord("INSUFFICIENT_EVIDENCE cannot fabricate a root cause")
    if record.primary_issue_class is PrimaryIssueClass.TASK_LOCAL_PREFERENCE:
        if record.selected_mechanisms or record.prompt_rule_justification is not None:
            raise InvalidDecisionRecord("TASK_LOCAL_PREFERENCE cannot persist a mechanism")


def _non_empty(value: str | None) -> bool:
    return value is not None and bool(value.strip())
