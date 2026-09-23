"""Deterministic validation for Codex-authored capability change decisions."""
from __future__ import annotations

from engine.models import (
    AuthorizationStatus,
    CapabilityChangeDecision,
    CapabilityDiff,
    CapabilityPreservationStatus,
    CheckResult,
    CheckStatus,
    LifecycleState,
)


def _result(status: CheckStatus, evidence: tuple[str, ...]) -> CheckResult:
    return CheckResult(
        "capability.change_decision",
        "codex.capability-decision",
        "capability-diff",
        True,
        status,
        True,
        True,
        1.0,
        evidence,
        LifecycleState.VALIDATED_PENDING_CONFIRMATION,
        None,
    )


def validate_capability_change_decision(
    diff: CapabilityDiff,
    decision: CapabilityChangeDecision | None,
) -> CheckResult:
    if diff.broken_capability_ids:
        return _result(
            CheckStatus.FAIL,
            tuple(f"CAPABILITY_BROKEN:{item}" for item in diff.broken_capability_ids),
        )
    if diff.unverifiable_capability_ids:
        return _result(
            CheckStatus.NOT_EXECUTED,
            tuple(
                f"CAPABILITY_UNVERIFIABLE:{item}"
                for item in diff.unverifiable_capability_ids
            ),
        )

    changed_ids = tuple(sorted((*diff.removed_capability_ids, *diff.narrowed_capability_ids)))
    if not changed_ids:
        return _result(CheckStatus.PASS, ("CAPABILITY_CHANGE_AUTHORIZATION_NOT_REQUIRED",))
    if decision is None:
        return _result(
            CheckStatus.FAIL,
            tuple(f"CAPABILITY_REMOVAL_NOT_AUTHORIZED:{item}" for item in changed_ids),
        )
    if (
        decision.baseline_capability_digest != diff.baseline_manifest_digest
        or decision.candidate_capability_digest != diff.candidate_manifest_digest
    ):
        return _result(CheckStatus.FAIL, ("CAPABILITY_DECISION_DIGEST_MISMATCH",))

    decision_ids = tuple(
        sorted((*decision.removed_capability_ids, *decision.narrowed_capability_ids))
    )
    if decision_ids != changed_ids:
        return _result(CheckStatus.FAIL, ("CAPABILITY_AUTHORIZATION_SCOPE_MISMATCH",))
    if (
        not decision.user_authorization_required
        or decision.user_authorization_status is not AuthorizationStatus.AUTHORIZED
        or not decision.authorization_evidence
    ):
        return _result(
            CheckStatus.FAIL,
            tuple(f"CAPABILITY_REMOVAL_NOT_AUTHORIZED:{item}" for item in changed_ids),
        )
    if not decision.migration_plan or not decision.deprecation_plan:
        return _result(CheckStatus.FAIL, ("CAPABILITY_CHANGE_TRANSITION_PLAN_MISSING",))
    return _result(
        CheckStatus.PASS,
        tuple(f"CAPABILITY_CHANGE_AUTHORIZED:{item}" for item in changed_ids),
    )


def capability_preservation_status(
    diff: CapabilityDiff | None,
    decision_check: CheckResult | None,
) -> CapabilityPreservationStatus | None:
    if diff is None:
        return None
    if diff.broken_capability_ids:
        return CapabilityPreservationStatus.CAPABILITY_REGRESSION
    if diff.unverifiable_capability_ids:
        return CapabilityPreservationStatus.CAPABILITY_UNVERIFIABLE
    if diff.removed_capability_ids or diff.narrowed_capability_ids:
        if decision_check is not None and decision_check.status is CheckStatus.PASS:
            return CapabilityPreservationStatus.CAPABILITY_PRESERVED
        return CapabilityPreservationStatus.AUTHORIZATION_REQUIRED
    return CapabilityPreservationStatus.CAPABILITY_PRESERVED


__all__ = ["capability_preservation_status", "validate_capability_change_decision"]
