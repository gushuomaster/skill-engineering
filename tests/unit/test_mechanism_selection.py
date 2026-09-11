import pytest

from engine.diagnostics import InvalidDecisionRecord
from engine.mechanism_selection import (
    ENVIRONMENT_TOOLING,
    IMPLEMENTATION_FIX,
    MERGE_INVARIANT,
    PROMPT_RULE,
    PromptRuleJustification,
    REFERENCE_OR_INSTRUCTION,
    REGRESSION_TEST,
    SCHEMA_VALIDATOR,
    WORKFLOW_REFACTOR,
    prompt_rule_allowed,
    select_mechanisms,
)
from engine.models import (
    ControlGap,
    DecisionRecord,
    Intent,
    PrimaryIssueClass,
    RegressionDisposition,
)


def decision(
    *,
    primary: PrimaryIssueClass = PrimaryIssueClass.NO_DEFECT,
    root_cause: str | None = None,
    evidence_limitations: tuple[str, ...] = (),
    selected_mechanisms: tuple[str, ...] = (),
    rejected_mechanisms: tuple[str, ...] = (),
    prompt_rule_justification: str | None = None,
) -> DecisionRecord:
    return DecisionRecord(
        intent=Intent.FIX if root_cause else Intent.CREATE,
        primary_issue_class=primary,
        control_gaps=(ControlGap.NONE,),
        regression_disposition=RegressionDisposition.NOT_APPLICABLE,
        root_cause=root_cause,
        evidence_limitations=evidence_limitations,
        selected_mechanisms=selected_mechanisms,
        rejected_mechanisms=rejected_mechanisms,
        prompt_rule_justification=prompt_rule_justification,
    )


def test_task_local_preference_selects_no_persistent_mechanism() -> None:
    result = select_mechanisms(
        decision(primary=PrimaryIssueClass.TASK_LOCAL_PREFERENCE)
    )
    assert result.selected_mechanisms == ()


def test_insufficient_evidence_cannot_select_prompt_rule() -> None:
    record = decision(
        primary=PrimaryIssueClass.INSUFFICIENT_EVIDENCE,
        evidence_limitations=("The failure cannot be reproduced.",),
    )
    assert prompt_rule_allowed(record) is False
    result = select_mechanisms(record)
    assert PROMPT_RULE not in result.selected_mechanisms


def test_frozen_primary_class_mapping_is_ordered() -> None:
    assert select_mechanisms(
        decision(
            primary=PrimaryIssueClass.IMPLEMENTATION_DEFECT,
            root_cause="The parser accepts invalid input.",
        )
    ).selected_mechanisms == (IMPLEMENTATION_FIX, REGRESSION_TEST)
    assert select_mechanisms(
        decision(
            primary=PrimaryIssueClass.ENVIRONMENT_COMPATIBILITY,
            root_cause="The runtime locale is unsupported.",
        )
    ).selected_mechanisms == (ENVIRONMENT_TOOLING, REGRESSION_TEST)
    assert select_mechanisms(
        decision(
            primary=PrimaryIssueClass.WORKFLOW_DESIGN_DEFECT,
            root_cause="Validation happens after publication.",
        )
    ).selected_mechanisms == (WORKFLOW_REFACTOR, REGRESSION_TEST)
    assert select_mechanisms(
        decision(
            primary=PrimaryIssueClass.CONTRACT_ENFORCEMENT_GAP,
            root_cause="The contract permits an invalid payload.",
        )
    ).selected_mechanisms == (SCHEMA_VALIDATOR, REGRESSION_TEST)
    assert select_mechanisms(
        decision(primary=PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE)
    ).selected_mechanisms == (MERGE_INVARIANT,)
    assert select_mechanisms(
        decision(primary=PrimaryIssueClass.DOCUMENTATION_GAP)
    ).selected_mechanisms == (REFERENCE_OR_INSTRUCTION,)


def test_selector_records_every_unselected_mechanism_as_rejected() -> None:
    result = select_mechanisms(
        decision(
            primary=PrimaryIssueClass.IMPLEMENTATION_DEFECT,
            root_cause="The parser accepts invalid input.",
        )
    )
    assert result.rejected_mechanisms == (
        SCHEMA_VALIDATOR,
        ENVIRONMENT_TOOLING,
        WORKFLOW_REFACTOR,
        MERGE_INVARIANT,
        REFERENCE_OR_INSTRUCTION,
        PROMPT_RULE,
    )


def test_prompt_rule_requires_complete_justification_and_rejected_precedence() -> None:
    record = decision(
        primary=PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE,
        selected_mechanisms=(PROMPT_RULE,),
        rejected_mechanisms=(
            IMPLEMENTATION_FIX,
            REGRESSION_TEST,
            SCHEMA_VALIDATOR,
            ENVIRONMENT_TOOLING,
            WORKFLOW_REFACTOR,
            MERGE_INVARIANT,
            REFERENCE_OR_INSTRUCTION,
        ),
    )
    assert prompt_rule_allowed(record) is False

    justification = PromptRuleJustification(
        stable_long_term_capability_contract=True,
        material_decision_effect=True,
        mechanical_enforcement_unavailable_or_unreliable=True,
        no_adequate_invariant_merge=True,
        not_task_local_preference=True,
        higher_priority_mechanisms_rejected=True,
    )
    justified = DecisionRecord(
        **{
            **record.__dict__,
            "prompt_rule_justification": justification.serialize(),
        }
    )
    assert prompt_rule_allowed(justified) is True
    assert select_mechanisms(justified).selected_mechanisms == (PROMPT_RULE,)


def test_prompt_rule_selection_rejects_missing_justification() -> None:
    record = decision(
        primary=PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE,
        selected_mechanisms=(PROMPT_RULE,),
        rejected_mechanisms=(IMPLEMENTATION_FIX,),
        prompt_rule_justification=None,
    )
    try:
        select_mechanisms(record)
    except InvalidDecisionRecord:
        pass
    else:
        raise AssertionError("Prompt Rule selection must reject incomplete justification")


@pytest.mark.parametrize(
    "missing_predicate",
    [
        "stable_long_term_capability_contract",
        "material_decision_effect",
        "mechanical_enforcement_unavailable_or_unreliable",
        "no_adequate_invariant_merge",
        "not_task_local_preference",
        "higher_priority_mechanisms_rejected",
    ],
)
def test_prompt_rule_rejects_each_missing_justification_predicate(
    missing_predicate: str,
) -> None:
    predicates = {
        "stable_long_term_capability_contract": True,
        "material_decision_effect": True,
        "mechanical_enforcement_unavailable_or_unreliable": True,
        "no_adequate_invariant_merge": True,
        "not_task_local_preference": True,
        "higher_priority_mechanisms_rejected": True,
    }
    predicates[missing_predicate] = False
    record = decision(
        primary=PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE,
        selected_mechanisms=(PROMPT_RULE,),
        rejected_mechanisms=(
            IMPLEMENTATION_FIX,
            REGRESSION_TEST,
            SCHEMA_VALIDATOR,
            ENVIRONMENT_TOOLING,
            WORKFLOW_REFACTOR,
            MERGE_INVARIANT,
            REFERENCE_OR_INSTRUCTION,
        ),
        prompt_rule_justification=PromptRuleJustification(**predicates).serialize(),
    )
    assert prompt_rule_allowed(record) is False


@pytest.mark.parametrize(
    "selected_mechanisms,rejected_mechanisms",
    [
        (("unknown_mechanism",), ()),
        ((IMPLEMENTATION_FIX,), (IMPLEMENTATION_FIX,)),
    ],
)
def test_selector_rejects_unknown_or_conflicting_mechanisms(
    selected_mechanisms: tuple[str, ...], rejected_mechanisms: tuple[str, ...]
) -> None:
    record = decision(
        selected_mechanisms=selected_mechanisms,
        rejected_mechanisms=rejected_mechanisms,
    )
    with pytest.raises(InvalidDecisionRecord, match="mechanism"):
        select_mechanisms(record)


def test_prompt_rule_guard_rejects_unknown_mechanism_bypass() -> None:
    record = decision(
        primary=PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE,
        rejected_mechanisms=(
            IMPLEMENTATION_FIX,
            REGRESSION_TEST,
            SCHEMA_VALIDATOR,
            ENVIRONMENT_TOOLING,
            WORKFLOW_REFACTOR,
            MERGE_INVARIANT,
            REFERENCE_OR_INSTRUCTION,
            "unknown_mechanism",
        ),
        prompt_rule_justification=PromptRuleJustification(
            stable_long_term_capability_contract=True,
            material_decision_effect=True,
            mechanical_enforcement_unavailable_or_unreliable=True,
            no_adequate_invariant_merge=True,
            not_task_local_preference=True,
            higher_priority_mechanisms_rejected=True,
        ).serialize(),
    )
    assert prompt_rule_allowed(record) is False
