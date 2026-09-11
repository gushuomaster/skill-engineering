"""Deterministic mechanism selection for classified diagnostic records."""

import json
from dataclasses import asdict, dataclass, replace

from engine.diagnostics import InvalidDecisionRecord, validate_classification
from engine.models import DecisionRecord, PrimaryIssueClass

IMPLEMENTATION_FIX = "implementation_fix"
REGRESSION_TEST = "regression_test"
SCHEMA_VALIDATOR = "schema_validator"
ENVIRONMENT_TOOLING = "environment_tooling"
WORKFLOW_REFACTOR = "workflow_refactor"
MERGE_INVARIANT = "merge_invariant"
PROMPT_RULE = "prompt_rule"
REFERENCE_OR_INSTRUCTION = "reference_or_instruction"

_MECHANISM_ORDER = (
    IMPLEMENTATION_FIX,
    REGRESSION_TEST,
    SCHEMA_VALIDATOR,
    ENVIRONMENT_TOOLING,
    WORKFLOW_REFACTOR,
    MERGE_INVARIANT,
    REFERENCE_OR_INSTRUCTION,
    PROMPT_RULE,
)
_HIGHER_PRIORITY_MECHANISMS = _MECHANISM_ORDER[:-1]


@dataclass(frozen=True)
class PromptRuleJustification:
    """The six frozen predicates required for a persistent Prompt Rule."""

    stable_long_term_capability_contract: bool
    material_decision_effect: bool
    mechanical_enforcement_unavailable_or_unreliable: bool
    no_adequate_invariant_merge: bool
    not_task_local_preference: bool
    higher_priority_mechanisms_rejected: bool

    def serialize(self) -> str:
        """Return the schema-compatible canonical string representation."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def parse(cls, value: str | None) -> "PromptRuleJustification | None":
        """Parse only the complete, schema-compatible predicate declaration."""
        if value is None:
            return None
        try:
            payload = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return None
        expected_keys = set(cls.__dataclass_fields__)
        if not isinstance(payload, dict) or set(payload) != expected_keys:
            return None
        if any(type(predicate) is not bool for predicate in payload.values()):
            return None
        return cls(**payload)

_DEFAULT_SELECTIONS = {
    PrimaryIssueClass.IMPLEMENTATION_DEFECT: (IMPLEMENTATION_FIX, REGRESSION_TEST),
    PrimaryIssueClass.ENVIRONMENT_COMPATIBILITY: (ENVIRONMENT_TOOLING, REGRESSION_TEST),
    PrimaryIssueClass.WORKFLOW_DESIGN_DEFECT: (WORKFLOW_REFACTOR, REGRESSION_TEST),
    PrimaryIssueClass.CONTRACT_ENFORCEMENT_GAP: (SCHEMA_VALIDATOR, REGRESSION_TEST),
    PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE: (MERGE_INVARIANT,),
    PrimaryIssueClass.TASK_LOCAL_PREFERENCE: (),
    PrimaryIssueClass.DOCUMENTATION_GAP: (REFERENCE_OR_INSTRUCTION,),
    PrimaryIssueClass.NO_DEFECT: (),
    PrimaryIssueClass.INSUFFICIENT_EVIDENCE: (),
}


def prompt_rule_allowed(record: DecisionRecord) -> bool:
    """Return whether the record contains the complete Prompt Rule justification."""
    if not _mechanisms_are_valid(record):
        return False
    if record.primary_issue_class is not PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE:
        return False
    if not set(_HIGHER_PRIORITY_MECHANISMS).issubset(record.rejected_mechanisms):
        return False
    justification = PromptRuleJustification.parse(record.prompt_rule_justification)
    return justification is not None and all(asdict(justification).values())


def select_mechanisms(record: DecisionRecord) -> DecisionRecord:
    """Select frozen mechanisms and record every unselected alternative."""
    validate_classification(record)
    _validate_mechanisms(record)
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


def _validate_mechanisms(record: DecisionRecord) -> None:
    if not _mechanisms_are_valid(record):
        selected = set(record.selected_mechanisms)
        rejected = set(record.rejected_mechanisms)
        if not selected.issubset(_MECHANISM_ORDER) or not rejected.issubset(_MECHANISM_ORDER):
            raise InvalidDecisionRecord("mechanism identifiers must be known")
        raise InvalidDecisionRecord("selected and rejected mechanisms must be mutually exclusive")


def _mechanisms_are_valid(record: DecisionRecord) -> bool:
    selected = set(record.selected_mechanisms)
    rejected = set(record.rejected_mechanisms)
    return (
        selected.issubset(_MECHANISM_ORDER)
        and rejected.issubset(_MECHANISM_ORDER)
        and not selected & rejected
    )
