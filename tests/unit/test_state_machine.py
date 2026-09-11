import pytest

from engine.models import Intent, LifecycleState
from engine.state_machine import InvalidTransition, TransitionContext, allowed_targets, transition


DISCOVERED = LifecycleState.DISCOVERED
STAGED = LifecycleState.STAGED
CLASSIFIED = LifecycleState.CLASSIFIED
AUDITED = LifecycleState.AUDITED
MECHANISM_SELECTED = LifecycleState.MECHANISM_SELECTED
VALIDATED = LifecycleState.VALIDATED
GATE_FAILED = LifecycleState.GATE_FAILED
GATE_PASSED = LifecycleState.GATE_PASSED
PUBLISHED = LifecycleState.PUBLISHED
UNCHANGED_VALIDATED = LifecycleState.UNCHANGED_VALIDATED
UNCHANGED_BLOCKED = LifecycleState.UNCHANGED_BLOCKED


def test_fix_can_stage_before_classification() -> None:
    context = TransitionContext(Intent.FIX, True, True, True)
    assert transition(DISCOVERED, STAGED, context) is STAGED
    assert transition(STAGED, CLASSIFIED, context) is CLASSIFIED


def test_create_can_stage_first() -> None:
    context = TransitionContext(Intent.CREATE, True, False, True)
    assert transition(DISCOVERED, STAGED, context) is STAGED


def test_audit_only_cannot_enter_staged() -> None:
    context = TransitionContext(Intent.AUDIT_ONLY, False, True, False)
    with pytest.raises(InvalidTransition):
        transition(DISCOVERED, STAGED, context)


def test_audit_only_defect_returns_to_audit_without_staging() -> None:
    context = TransitionContext(Intent.AUDIT_ONLY, False, True, False)
    assert transition(DISCOVERED, AUDITED, context) is AUDITED
    assert transition(AUDITED, CLASSIFIED, context) is CLASSIFIED
    assert transition(CLASSIFIED, MECHANISM_SELECTED, context) is MECHANISM_SELECTED
    assert transition(MECHANISM_SELECTED, AUDITED, context) is AUDITED


@pytest.mark.parametrize("target", [CLASSIFIED, MECHANISM_SELECTED, STAGED, AUDITED, VALIDATED])
def test_gate_failure_can_return_to_responsible_stage(target: LifecycleState) -> None:
    context = TransitionContext(Intent.FIX, True, True, True)
    assert transition(GATE_FAILED, target, context) is target


def test_remediated_candidate_must_reaudit_before_publish() -> None:
    context = TransitionContext(Intent.FIX, True, True, True)
    with pytest.raises(InvalidTransition):
        transition(STAGED, PUBLISHED, context)


def test_stale_audit_cycle_cannot_reenter_gate() -> None:
    context = TransitionContext(
        Intent.FIX,
        True,
        True,
        True,
        remediation_cycle=2,
        audit_cycle=1,
        validation_cycle=2,
    )
    with pytest.raises(InvalidTransition):
        transition(VALIDATED, GATE_PASSED, context)


def test_fresh_cycles_allow_gate_and_publication() -> None:
    context = TransitionContext(Intent.FIX, True, True, True, 2, 2, 2, 1)
    assert transition(VALIDATED, GATE_PASSED, context) is GATE_PASSED
    assert transition(GATE_PASSED, PUBLISHED, context) is PUBLISHED


def test_gate_failed_can_block_unchanged_audit() -> None:
    context = TransitionContext(Intent.AUDIT_ONLY, False, True, False)
    assert transition(GATE_FAILED, UNCHANGED_BLOCKED, context) is UNCHANGED_BLOCKED


def test_non_audit_cannot_block_as_unchanged() -> None:
    context = TransitionContext(Intent.FIX, True, True, True)
    with pytest.raises(InvalidTransition):
        transition(GATE_FAILED, UNCHANGED_BLOCKED, context)


def test_audit_only_can_finish_unchanged_validated() -> None:
    context = TransitionContext(Intent.AUDIT_ONLY, False, False, False, 0, 0, 0)
    assert transition(VALIDATED, GATE_PASSED, context) is GATE_PASSED
    assert transition(GATE_PASSED, UNCHANGED_VALIDATED, context) is UNCHANGED_VALIDATED


def test_audit_optimize_without_needed_change_can_finish_unchanged() -> None:
    context = TransitionContext(Intent.AUDIT_OPTIMIZE, True, False, False, 0, 0, 0, modification_needed=False)
    assert transition(VALIDATED, GATE_PASSED, context) is GATE_PASSED
    assert transition(GATE_PASSED, UNCHANGED_VALIDATED, context) is UNCHANGED_VALIDATED


def test_audit_optimize_needed_change_cannot_finish_unchanged() -> None:
    context = TransitionContext(Intent.AUDIT_OPTIMIZE, True, False, True, 0, 0, 0, modification_needed=True)
    with pytest.raises(InvalidTransition):
        transition(GATE_PASSED, UNCHANGED_VALIDATED, context)


def test_audit_only_can_classify_before_auditing() -> None:
    context = TransitionContext(Intent.AUDIT_ONLY, False, False, False)
    assert transition(DISCOVERED, CLASSIFIED, context) is CLASSIFIED
    assert transition(CLASSIFIED, MECHANISM_SELECTED, context) is MECHANISM_SELECTED
    assert transition(MECHANISM_SELECTED, AUDITED, context) is AUDITED


@pytest.mark.parametrize("intent", [Intent.CREATE, Intent.MODIFY, Intent.FIX])
def test_mutating_flows_must_stage_before_classification(intent: Intent) -> None:
    context = TransitionContext(intent, True, False, True)
    with pytest.raises(InvalidTransition):
        transition(DISCOVERED, CLASSIFIED, context)


def test_staging_requires_authorization() -> None:
    context = TransitionContext(Intent.AUDIT_OPTIMIZE, False, False, True)
    with pytest.raises(InvalidTransition):
        transition(DISCOVERED, STAGED, context)


def test_same_failed_cycle_cannot_reenter_gate() -> None:
    context = TransitionContext(Intent.FIX, True, True, True, 2, 2, 2, 2)
    with pytest.raises(InvalidTransition):
        transition(VALIDATED, GATE_PASSED, context)


def test_authorized_flow_requires_staging_for_publication() -> None:
    context = TransitionContext(Intent.FIX, True, True, False, 0, 0, 0)
    with pytest.raises(InvalidTransition):
        transition(VALIDATED, GATE_PASSED, context)


def test_allowed_targets_are_guarded_by_context() -> None:
    context = TransitionContext(Intent.AUDIT_ONLY, False, True, False)
    targets = allowed_targets(DISCOVERED, context)
    assert targets == frozenset({AUDITED, CLASSIFIED})
    assert STAGED not in targets
