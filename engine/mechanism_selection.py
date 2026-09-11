"""Deterministic mechanism selection for classified diagnostic records."""

from dataclasses import replace

from engine.diagnostics import InvalidDecisionRecord, validate_classification
from engine.models import DecisionRecord, PrimaryIssueClass

IMPLEMENTATION_FIX = "implementation_fix"
REGRESSION_TEST = "regression_test"
SCHEMA_VALIDATOR = "schema_validator"
ENVIRONMENT_TOOLING = "environment_tooling"
WORKFLOW_REFACTOR = "workflow_refactor"
MERGE_INVARIANT = "merge_invariant"
PROMPT_RULE = "prompt_rule"

_MECHANISM_ORDER = (
    IMPLEMENTATION_FIX,
    REGRESSION_TEST,
    SCHEMA_VALIDATOR,
    ENVIRONMENT_TOOLING,
    WORKFLOW_REFACTOR,
    MERGE_INVARIANT,
    PROMPT_RULE,
)
_HIGHER_PRIORITY_MECHANISMS = _MECHANISM_ORDER[:-1]

_DEFAULT_SELECTIONS = {
    PrimaryIssueClass.IMPLEMENTATION_DEFECT: (IMPLEMENTATION_FIX, REGRESSION_TEST),
    PrimaryIssueClass.ENVIRONMENT_COMPATIBILITY: (ENVIRONMENT_TOOLING, REGRESSION_TEST),
    PrimaryIssueClass.WORKFLOW_DESIGN_DEFECT: (WORKFLOW_REFACTOR, REGRESSION_TEST),
    PrimaryIssueClass.CONTRACT_ENFORCEMENT_GAP: (SCHEMA_VALIDATOR, REGRESSION_TEST),
    PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE: (MERGE_INVARIANT,),
    PrimaryIssueClass.TASK_LOCAL_PREFERENCE: (),
    PrimaryIssueClass.DOCUMENTATION_GAP: (),
    PrimaryIssueClass.NO_DEFECT: (),
    PrimaryIssueClass.INSUFFICIENT_EVIDENCE: (),
}


def prompt_rule_allowed(record: DecisionRecord) -> bool:
    """Return whether the record contains the complete Prompt Rule justification."""
    if record.primary_issue_class is not PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE:
        return False
    if not set(_HIGHER_PRIORITY_MECHANISMS).issubset(record.rejected_mechanisms):
        return False
    return _non_empty(record.prompt_rule_justification)


def select_mechanisms(record: DecisionRecord) -> DecisionRecord:
    """Select frozen mechanisms and record every unselected alternative."""
    validate_classification(record)
    requested_prompt_rule = PROMPT_RULE in record.selected_mechanisms
    if requested_prompt_rule:
        if not prompt_rule_allowed(record):
            raise InvalidDecisionRecord("Prompt Rule selection requires complete justification")
        selected = (PROMPT_RULE,)
    else:
        selected = _DEFAULT_SELECTIONS[record.primary_issue_class]
    rejected = tuple(mechanism for mechanism in _MECHANISM_ORDER if mechanism not in selected)
    return replace(
        record,
        selected_mechanisms=selected,
        rejected_mechanisms=rejected,
    )


def _non_empty(value: str | None) -> bool:
    return value is not None and bool(value.strip())
