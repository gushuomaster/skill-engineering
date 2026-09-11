"""Pure lifecycle transition rules for the skill-engineering pipeline."""
from dataclasses import dataclass

from .models import Intent, LifecycleState


@dataclass(frozen=True)
class TransitionContext:
    intent: Intent
    authorized_to_modify: bool
    defect_found: bool
    staging_exists: bool
    remediation_cycle: int = 0
    audit_cycle: int | None = None
    validation_cycle: int | None = None


class InvalidTransition(ValueError):
    """Raised when a lifecycle transition violates pipeline policy."""


BASE_TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.DISCOVERED: frozenset({LifecycleState.STAGED, LifecycleState.AUDITED, LifecycleState.CLASSIFIED}),
    LifecycleState.STAGED: frozenset({LifecycleState.CLASSIFIED, LifecycleState.AUDITED}),
    LifecycleState.AUDITED: frozenset({LifecycleState.STAGED, LifecycleState.CLASSIFIED, LifecycleState.VALIDATED}),
    LifecycleState.CLASSIFIED: frozenset({LifecycleState.MECHANISM_SELECTED}),
    LifecycleState.MECHANISM_SELECTED: frozenset({LifecycleState.STAGED, LifecycleState.AUDITED}),
    LifecycleState.VALIDATED: frozenset({LifecycleState.AUDITED, LifecycleState.GATE_PASSED, LifecycleState.GATE_FAILED}),
    LifecycleState.GATE_PASSED: frozenset({LifecycleState.PUBLISHED, LifecycleState.UNCHANGED_VALIDATED}),
    LifecycleState.GATE_FAILED: frozenset({
        LifecycleState.CLASSIFIED,
        LifecycleState.MECHANISM_SELECTED,
        LifecycleState.STAGED,
        LifecycleState.AUDITED,
        LifecycleState.VALIDATED,
        LifecycleState.UNCHANGED_BLOCKED,
    }),
}


def _base_targets(state: LifecycleState) -> frozenset[LifecycleState]:
    return BASE_TRANSITIONS.get(state, frozenset())


def allowed_targets(state: LifecycleState, context: TransitionContext) -> frozenset[LifecycleState]:
    """Return targets legal under the supplied operation context."""
    targets = set(_base_targets(state))
    read_only = context.intent is Intent.AUDIT_ONLY

    if read_only:
        targets.discard(LifecycleState.STAGED)
        targets.discard(LifecycleState.PUBLISHED)
        if state is LifecycleState.DISCOVERED:
            targets.intersection_update({LifecycleState.AUDITED})
        if state is LifecycleState.GATE_PASSED:
            targets.intersection_update({LifecycleState.UNCHANGED_VALIDATED})
        if state is LifecycleState.GATE_FAILED:
            targets.intersection_update({LifecycleState.AUDITED, LifecycleState.UNCHANGED_BLOCKED,
                                          LifecycleState.CLASSIFIED, LifecycleState.MECHANISM_SELECTED,
                                          LifecycleState.VALIDATED})
    else:
        targets.discard(LifecycleState.UNCHANGED_VALIDATED)
        targets.discard(LifecycleState.UNCHANGED_BLOCKED)

    if state is LifecycleState.DISCOVERED and context.intent is Intent.AUDIT_OPTIMIZE:
        targets.discard(LifecycleState.STAGED)
    if not context.staging_exists:
        targets.discard(LifecycleState.STAGED)

    if state is LifecycleState.VALIDATED:
        cycles_are_fresh = (
            context.audit_cycle is not None
            and context.validation_cycle is not None
            and context.audit_cycle == context.validation_cycle == context.remediation_cycle
        )
        if not cycles_are_fresh:
            targets.discard(LifecycleState.GATE_PASSED)
            targets.discard(LifecycleState.GATE_FAILED)
        if not context.staging_exists and not read_only:
            targets.discard(LifecycleState.GATE_PASSED)
            targets.discard(LifecycleState.GATE_FAILED)
    if state is LifecycleState.GATE_PASSED and (
        not context.authorized_to_modify or not context.staging_exists
    ):
        targets.discard(LifecycleState.PUBLISHED)
    return frozenset(targets)


def transition(state: LifecycleState, target: LifecycleState, context: TransitionContext) -> LifecycleState:
    """Validate and apply one lifecycle transition."""
    if target not in allowed_targets(state, context):
        raise InvalidTransition(f"cannot transition {state} to {target} for {context.intent}")
    return target
