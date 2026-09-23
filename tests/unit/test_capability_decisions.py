from __future__ import annotations

import importlib

import pytest

import engine.models as models


def _module():
    try:
        return importlib.import_module("engine.capability_decisions")
    except ModuleNotFoundError:
        pytest.fail("engine.capability_decisions must enforce capability authorization")


def _required_types() -> None:
    required = (
        "AuthorizationStatus",
        "CapabilityChangeDecision",
        "CapabilityDecisionKind",
    )
    missing = tuple(name for name in required if not hasattr(models, name))
    assert not missing, f"missing capability decision models: {missing}"


def _diff(kind="REMOVED"):
    change = models.CapabilityChange(
        "documents",
        models.CapabilityChangeKind(kind),
        ("supported_deliverables",),
        ("supported_deliverables=SRS", "supported_deliverables=STD"),
        ("supported_deliverables=SRS",),
    )
    return models.CapabilityDiff("a" * 64, "b" * 64, (change,))


def _decision(*, status="MISSING", removed=("documents",), evidence=(), migration=None, deprecation=None):
    _required_types()
    return models.CapabilityChangeDecision(
        baseline_capability_digest="a" * 64,
        candidate_capability_digest="b" * 64,
        capability_changes=(("documents", models.CapabilityDecisionKind.CAPABILITY_REMOVAL),),
        removed_capability_ids=tuple(removed),
        narrowed_capability_ids=(),
        change_rationale="Remove an incompatible public capability.",
        user_authorization_required=True,
        user_authorization_status=models.AuthorizationStatus(status),
        authorization_evidence=tuple(evidence),
        compatibility_impact="BREAKING",
        migration_plan=migration,
        deprecation_plan=deprecation,
    )


def test_removed_capability_without_authorization_fails() -> None:
    result = _module().validate_capability_change_decision(_diff(), _decision())

    assert result.status.value == "FAIL"
    assert "CAPABILITY_REMOVAL_NOT_AUTHORIZED:documents" in result.evidence


def test_authorization_must_match_exact_removed_ids() -> None:
    result = _module().validate_capability_change_decision(
        _diff(),
        _decision(
            status="AUTHORIZED",
            removed=(),
            evidence=("user-message:approved documents removal",),
            migration="Use SRS.",
            deprecation="Remove in the next major version.",
        ),
    )

    assert result.status.value == "FAIL"
    assert "CAPABILITY_AUTHORIZATION_SCOPE_MISMATCH" in result.evidence


def test_exact_authorization_with_migration_and_deprecation_passes() -> None:
    result = _module().validate_capability_change_decision(
        _diff(),
        _decision(
            status="AUTHORIZED",
            evidence=("user-message:approved documents removal",),
            migration="Use SRS before the next release.",
            deprecation="Retire removed document types in the next major version.",
        ),
    )

    assert result.status.value == "PASS"
    assert "CAPABILITY_CHANGE_AUTHORIZED:documents" in result.evidence


def test_broken_capability_cannot_be_authorized_away() -> None:
    result = _module().validate_capability_change_decision(
        _diff("BROKEN"),
        _decision(
            status="AUTHORIZED",
            evidence=("user-message:approved documents removal",),
            migration="Use SRS.",
            deprecation="Retire old outputs.",
        ),
    )

    assert result.status.value == "FAIL"
    assert "CAPABILITY_BROKEN:documents" in result.evidence
