from dataclasses import replace

from engine.capabilities import (
    DECLARED_FALLBACK_EQUIVALENCES, DOMAIN_CAPABILITIES,
)
from engine.equivalence_contracts import (
    EQUIVALENCE_CONTRACTS, FALLBACK_COVERAGE, FallbackCoverage,
    assess_equivalence, equivalence_matrix, proven_equivalence_levels,
    validate_equivalence_contracts,
)
from engine.models import FallbackEquivalence


def test_every_declared_full_fallback_has_a_complete_equivalence_contract() -> None:
    assessments = validate_equivalence_contracts()

    assert assessments
    assert all(item.complete for item in assessments)
    for capability, level in DECLARED_FALLBACK_EQUIVALENCES.items():
        if level is FallbackEquivalence.FULL:
            assert capability in EQUIVALENCE_CONTRACTS
            assert capability in FALLBACK_COVERAGE


def test_removing_required_dimension_breaks_full_contract() -> None:
    contract = EQUIVALENCE_CONTRACTS["skill_duplication_and_bloat"]
    coverage = FALLBACK_COVERAGE[contract.capability]
    reduced = replace(
        coverage,
        covered_dimensions=coverage.covered_dimensions - {"obsolete_rule"}
        if "obsolete_rule" in coverage.covered_dimensions
        else coverage.covered_dimensions - {"contradictory_rule"},
    )

    assessment = assess_equivalence(contract, reduced)

    assert assessment.complete is False
    assert assessment.missing_dimensions


def test_new_contract_dimension_without_implementation_downgrades_full() -> None:
    capability = "skill_conformance"
    extended = replace(
        EQUIVALENCE_CONTRACTS[capability],
        required_dimensions=(
            EQUIVALENCE_CONTRACTS[capability].required_dimensions
            | {"new_required_dimension"}
        ),
    )
    contracts = dict(EQUIVALENCE_CONTRACTS)
    contracts[capability] = extended

    levels = proven_equivalence_levels(
        DECLARED_FALLBACK_EQUIVALENCES,
        contracts=contracts,
        coverage=FALLBACK_COVERAGE,
    )

    assert levels[capability] is FallbackEquivalence.PARTIAL


def test_equivalence_matrix_contains_dimensions_evidence_and_failure_semantics() -> None:
    rows = {item["capability"]: item for item in equivalence_matrix()}

    row = rows["skill_audit_and_simplification"]
    assert row["equivalence"] == "FULL"
    assert "obsolete_rule" in row["required_dimensions"]
    assert {"file", "line", "finding", "severity", "reason", "remediation"}.issubset(
        row["evidence_contract"]
    )
    assert "defect_is_fail" in row["required_failure_semantics"]


def test_dynamic_domain_capabilities_keep_none_without_fake_contracts() -> None:
    for capability in DOMAIN_CAPABILITIES:
        assert capability not in DECLARED_FALLBACK_EQUIVALENCES
        assert capability not in EQUIVALENCE_CONTRACTS
