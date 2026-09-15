import pytest

from engine.diagnostics import InvalidDecisionRecord
from engine.mechanism_selection import (
    ENVIRONMENT_TOOLING, IMPLEMENTATION_FIX, MERGE_INVARIANT, PROMPT_RULE,
    PromptRuleJustification, REFERENCE_OR_INSTRUCTION, REGRESSION_TEST,
    SCHEMA_VALIDATOR, WORKFLOW_REFACTOR, prompt_rule_allowed,
    validate_mechanism_selection,
)
from engine.models import ControlGap, DecisionRecord, Intent, PrimaryIssueClass, RegressionDisposition


ALL = (
    IMPLEMENTATION_FIX, REGRESSION_TEST, SCHEMA_VALIDATOR, ENVIRONMENT_TOOLING,
    WORKFLOW_REFACTOR, MERGE_INVARIANT, REFERENCE_OR_INSTRUCTION, PROMPT_RULE,
)


def decision(*, selected: tuple[str, ...], primary: PrimaryIssueClass = PrimaryIssueClass.NO_DEFECT,
             justification: str | None = None) -> DecisionRecord:
    return DecisionRecord(
        Intent.CREATE, primary, (ControlGap.NONE,), RegressionDisposition.NOT_APPLICABLE,
        None, (), selected, tuple(item for item in ALL if item not in selected), justification,
    )


def test_validator_preserves_codex_mechanism_choice() -> None:
    record = decision(selected=(WORKFLOW_REFACTOR, REGRESSION_TEST))
    assert validate_mechanism_selection(record) is record


def test_validator_does_not_infer_defaults_from_issue_class() -> None:
    record = decision(selected=(REFERENCE_OR_INSTRUCTION,), primary=PrimaryIssueClass.DOCUMENTATION_GAP)
    assert validate_mechanism_selection(record).selected_mechanisms == (REFERENCE_OR_INSTRUCTION,)


def test_codex_must_explicitly_dispose_every_known_mechanism() -> None:
    record = DecisionRecord(
        Intent.CREATE, PrimaryIssueClass.NO_DEFECT, (ControlGap.NONE,),
        RegressionDisposition.NOT_APPLICABLE, None, (), (), (), None,
    )
    with pytest.raises(InvalidDecisionRecord, match="explicitly select or reject"):
        validate_mechanism_selection(record)


def test_prompt_rule_requires_complete_codex_justification() -> None:
    unjustified = decision(selected=(PROMPT_RULE,), primary=PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE)
    assert prompt_rule_allowed(unjustified) is False
    with pytest.raises(InvalidDecisionRecord):
        validate_mechanism_selection(unjustified)

    justification = PromptRuleJustification(True, True, True, True, True, True).serialize()
    justified = decision(
        selected=(PROMPT_RULE,),
        primary=PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE,
        justification=justification,
    )
    assert prompt_rule_allowed(justified) is True
    assert validate_mechanism_selection(justified) is justified


@pytest.mark.parametrize(
    "selected,rejected",
    [(('unknown',), ALL), ((IMPLEMENTATION_FIX,), ALL)],
)
def test_validator_rejects_unknown_or_overlapping_mechanisms(selected, rejected) -> None:
    record = DecisionRecord(
        Intent.CREATE, PrimaryIssueClass.NO_DEFECT, (ControlGap.NONE,),
        RegressionDisposition.NOT_APPLICABLE, None, (), selected, rejected, None,
    )
    with pytest.raises(InvalidDecisionRecord, match="mechanism"):
        validate_mechanism_selection(record)
