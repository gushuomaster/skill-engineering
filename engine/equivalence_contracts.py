"""Executable contracts proving when an internal fallback may remain FULL."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from engine.models import FallbackEquivalence


TYPED_CHECK_EVIDENCE = frozenset({
    "check_id", "source", "subject", "required", "status", "deterministic",
    "reproducible", "confidence", "evidence", "remediation_stage",
    "artifact_reference",
})
FINDING_EVIDENCE = frozenset({
    "file", "line", "finding", "severity", "reason", "remediation",
})


@dataclass(frozen=True)
class EquivalenceContract:
    capability: str
    preferred_provider: str
    fallback_implementation: str
    required_dimensions: frozenset[str]
    required_evidence: frozenset[str]
    required_failure_semantics: frozenset[str]
    equivalence: FallbackEquivalence = FallbackEquivalence.FULL


@dataclass(frozen=True)
class FallbackCoverage:
    capability: str
    implementation: str
    covered_dimensions: frozenset[str]
    evidence_fields: frozenset[str]
    failure_semantics: frozenset[str]


@dataclass(frozen=True)
class EquivalenceAssessment:
    capability: str
    complete: bool
    missing_dimensions: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    missing_failure_semantics: tuple[str, ...]


def _contract(
    capability: str,
    provider: str,
    implementation: str,
    dimensions: set[str],
    *,
    evidence: frozenset[str] = TYPED_CHECK_EVIDENCE,
    failure_semantics: set[str] | None = None,
) -> EquivalenceContract:
    return EquivalenceContract(
        capability, provider, implementation, frozenset(dimensions), evidence,
        frozenset(failure_semantics or {
            "defect_is_fail", "unavailable_is_not_executed", "engine_exception_is_error",
        }),
    )


EQUIVALENCE_CONTRACTS: Mapping[str, EquivalenceContract] = {
    "skill_creation_or_restructure": _contract(
        "skill_creation_or_restructure", "external.professional-skill", "internal.restructuring-flow",
        {"skill_md_structure", "frontmatter", "name", "description", "trigger_design",
         "instruction_design", "directory_layout", "references", "scripts", "resources",
         "responsibility_boundary", "progressive_disclosure"},
    ),
    "skill_structure": _contract(
        "skill_structure", "external.professional-skill", "internal.structure-validator",
        {"skill_md_structure", "frontmatter", "name", "directory_layout", "resources",
         "scripts", "dependencies"},
    ),
    "skill_trigger_and_description": _contract(
        "skill_trigger_and_description", "external.professional-skill", "internal.trigger-description-validator",
        {"description", "trigger_design"},
    ),
    "skill_instruction_design": _contract(
        "skill_instruction_design", "external.professional-skill", "internal.instruction-design-rubric",
        {"instruction_design", "responsibility_boundary", "progressive_disclosure"},
    ),
    "skill_audit_and_simplification": _contract(
        "skill_audit_and_simplification", "external.professional-skill", "internal.audit-simplification-rubric",
        {"duplicate_rule", "contradictory_rule", "obsolete_rule", "unenforceable_rule",
         "misplaced_rule", "responsibility_overlap", "unconditional_provider_orchestration",
         "rule_bloat", "repeated_constraint", "instruction_quality_defect"},
        evidence=FINDING_EVIDENCE,
    ),
    "skill_instruction_quality": _contract(
        "skill_instruction_quality", "external.professional-skill", "internal.instruction-quality-rubric",
        {"obsolete_rule", "unenforceable_rule", "unconditional_provider_orchestration",
         "instruction_quality_defect"},
        evidence=FINDING_EVIDENCE,
    ),
    "skill_rule_governance": _contract(
        "skill_rule_governance", "external.professional-skill", "internal.rule-governance-validator",
        {"finding_disposition", "ownership_decision", "remediation_decision"},
    ),
    "skill_duplication_and_bloat": _contract(
        "skill_duplication_and_bloat", "external.professional-skill", "internal.duplication-bloat-rubric",
        {"duplicate_rule", "contradictory_rule", "misplaced_rule", "responsibility_overlap",
         "unnecessary_repetition", "excessive_explanation",
         "unconditional_provider_orchestration", "rule_bloat", "repeated_constraint"},
        evidence=FINDING_EVIDENCE,
    ),
    "skill_resource_integrity": _contract(
        "skill_resource_integrity", "external.professional-skill", "internal.reference-validator",
        {"broken_reference", "invalid_relative_path", "missing_resource", "broken_path_link"},
    ),
    "skill_script_integrity": _contract(
        "skill_script_integrity", "external.professional-skill", "internal.script-validator",
        {"missing_script", "invalid_relative_path", "entrypoint_mismatch"},
    ),
    "skill_conformance": _contract(
        "skill_conformance", "external.professional-skill", "internal.conformance-suite",
        {"missing_skill_md", "broken_frontmatter", "invalid_name", "invalid_description",
         "broken_reference", "missing_script", "invalid_relative_path", "missing_resource",
         "manifest_mismatch", "metadata_mismatch", "entrypoint_mismatch", "broken_path_link"},
    ),
    "agent_instruction_governance": _contract(
        "agent_instruction_governance", "external.professional-skill", "internal.instruction-hierarchy-inspection",
        {"agents_md", "claude_md", "skill_md", "project_instructions",
         "directory_instructions", "inheritance", "scope", "precedence", "duplication",
         "conflict", "misplaced_governance_rule"},
        evidence=FINDING_EVIDENCE,
    ),
    "regression_validation": _contract(
        "regression_validation", "internal", "internal.regression-enforcement",
        {"disposition", "required_runner", "runner_result"},
    ),
    "evidence_collection": _contract(
        "evidence_collection", "internal", "internal.typed-evidence-collector",
        {"schema_validation", "deduplication", "artifact_binding"},
    ),
    "quality_gate": _contract(
        "quality_gate", "internal", "internal.fail-closed-gate",
        {"required_coverage", "semantic_confirmation", "verdict_precedence",
         "safe_apply_authorization"},
    ),
    "deliverable_contract": _contract(
        "deliverable_contract", "provider.deliverable-contract",
        "internal.deliverable-contract",
        {"declaration", "exposure", "dispatch", "generation", "behavior",
         "scope_conflict", "provider_provenance", "inspection_binding"},
        evidence=TYPED_CHECK_EVIDENCE,
        failure_semantics={
            "defect_is_fail", "unavailable_is_not_executed",
            "stale_evidence_is_not_executed", "engine_exception_is_error",
        },
    ),
}


def _coverage(
    capability: str,
    implementation: str,
    dimensions: set[str],
    *,
    evidence: frozenset[str] = TYPED_CHECK_EVIDENCE,
    failure_semantics: set[str] | None = None,
) -> FallbackCoverage:
    return FallbackCoverage(
        capability, implementation, frozenset(dimensions), evidence,
        frozenset(failure_semantics or {
            "defect_is_fail", "unavailable_is_not_executed", "engine_exception_is_error",
        }),
    )


# Deliberately independent from EQUIVALENCE_CONTRACTS. A new contract dimension
# is unproven until the implementation coverage and its behavioral tests are both
# updated, so production preflight downgrades the declared FULL level to PARTIAL.
FALLBACK_COVERAGE: Mapping[str, FallbackCoverage] = {
    "skill_creation_or_restructure": _coverage(
        "skill_creation_or_restructure", "internal.restructuring-flow",
        {"skill_md_structure", "frontmatter", "name", "description", "trigger_design",
         "instruction_design", "directory_layout", "references", "scripts", "resources",
         "responsibility_boundary", "progressive_disclosure"},
    ),
    "skill_structure": _coverage(
        "skill_structure", "internal.structure-validator",
        {"skill_md_structure", "frontmatter", "name", "directory_layout", "resources",
         "scripts", "dependencies"},
    ),
    "skill_trigger_and_description": _coverage(
        "skill_trigger_and_description", "internal.trigger-description-validator",
        {"description", "trigger_design"},
    ),
    "skill_instruction_design": _coverage(
        "skill_instruction_design", "internal.instruction-design-rubric",
        {"instruction_design", "responsibility_boundary", "progressive_disclosure"},
    ),
    "skill_audit_and_simplification": _coverage(
        "skill_audit_and_simplification", "internal.audit-simplification-rubric",
        {"duplicate_rule", "contradictory_rule", "obsolete_rule", "unenforceable_rule",
         "misplaced_rule", "responsibility_overlap", "unconditional_provider_orchestration",
         "rule_bloat", "repeated_constraint", "instruction_quality_defect"},
        evidence=FINDING_EVIDENCE,
    ),
    "skill_instruction_quality": _coverage(
        "skill_instruction_quality", "internal.instruction-quality-rubric",
        {"obsolete_rule", "unenforceable_rule", "unconditional_provider_orchestration",
         "instruction_quality_defect"},
        evidence=FINDING_EVIDENCE,
    ),
    "skill_rule_governance": _coverage(
        "skill_rule_governance", "internal.rule-governance-validator",
        {"finding_disposition", "ownership_decision", "remediation_decision"},
    ),
    "skill_duplication_and_bloat": _coverage(
        "skill_duplication_and_bloat", "internal.duplication-bloat-rubric",
        {"duplicate_rule", "contradictory_rule", "misplaced_rule", "responsibility_overlap",
         "unnecessary_repetition", "excessive_explanation",
         "unconditional_provider_orchestration", "rule_bloat", "repeated_constraint"},
        evidence=FINDING_EVIDENCE,
    ),
    "skill_resource_integrity": _coverage(
        "skill_resource_integrity", "internal.reference-validator",
        {"broken_reference", "invalid_relative_path", "missing_resource", "broken_path_link"},
    ),
    "skill_script_integrity": _coverage(
        "skill_script_integrity", "internal.script-validator",
        {"missing_script", "invalid_relative_path", "entrypoint_mismatch"},
    ),
    "skill_conformance": _coverage(
        "skill_conformance", "internal.conformance-suite",
        {"missing_skill_md", "broken_frontmatter", "invalid_name", "invalid_description",
         "broken_reference", "missing_script", "invalid_relative_path", "missing_resource",
         "manifest_mismatch", "metadata_mismatch", "entrypoint_mismatch", "broken_path_link"},
    ),
    "agent_instruction_governance": _coverage(
        "agent_instruction_governance", "internal.instruction-hierarchy-inspection",
        {"agents_md", "claude_md", "skill_md", "project_instructions",
         "directory_instructions", "inheritance", "scope", "precedence", "duplication",
         "conflict", "misplaced_governance_rule"},
        evidence=FINDING_EVIDENCE,
    ),
    "regression_validation": _coverage(
        "regression_validation", "internal.regression-enforcement",
        {"disposition", "required_runner", "runner_result"},
    ),
    "evidence_collection": _coverage(
        "evidence_collection", "internal.typed-evidence-collector",
        {"schema_validation", "deduplication", "artifact_binding"},
    ),
    "quality_gate": _coverage(
        "quality_gate", "internal.fail-closed-gate",
        {"required_coverage", "semantic_confirmation", "verdict_precedence",
         "safe_apply_authorization"},
    ),
    "deliverable_contract": _coverage(
        "deliverable_contract", "internal.deliverable-contract",
        {"declaration", "exposure", "dispatch", "generation", "behavior",
         "scope_conflict", "provider_provenance", "inspection_binding"},
        failure_semantics={
            "defect_is_fail", "unavailable_is_not_executed",
            "stale_evidence_is_not_executed", "engine_exception_is_error",
        },
    ),
}


def assess_equivalence(
    contract: EquivalenceContract,
    coverage: FallbackCoverage | None,
) -> EquivalenceAssessment:
    if coverage is None or coverage.implementation != contract.fallback_implementation:
        return EquivalenceAssessment(
            contract.capability, False, tuple(sorted(contract.required_dimensions)),
            tuple(sorted(contract.required_evidence)),
            tuple(sorted(contract.required_failure_semantics)),
        )
    missing_dimensions = tuple(sorted(contract.required_dimensions - coverage.covered_dimensions))
    missing_evidence = tuple(sorted(contract.required_evidence - coverage.evidence_fields))
    missing_semantics = tuple(sorted(
        contract.required_failure_semantics - coverage.failure_semantics
    ))
    return EquivalenceAssessment(
        contract.capability,
        not (missing_dimensions or missing_evidence or missing_semantics),
        missing_dimensions, missing_evidence, missing_semantics,
    )


def validate_equivalence_contracts(
    contracts: Mapping[str, EquivalenceContract] = EQUIVALENCE_CONTRACTS,
    coverage: Mapping[str, FallbackCoverage] = FALLBACK_COVERAGE,
) -> tuple[EquivalenceAssessment, ...]:
    return tuple(
        assess_equivalence(contract, coverage.get(name))
        for name, contract in sorted(contracts.items())
    )


def proven_equivalence_levels(
    declared: Mapping[str, FallbackEquivalence],
    *,
    contracts: Mapping[str, EquivalenceContract] = EQUIVALENCE_CONTRACTS,
    coverage: Mapping[str, FallbackCoverage] = FALLBACK_COVERAGE,
) -> dict[str, FallbackEquivalence]:
    """Downgrade an unproven FULL declaration to PARTIAL at runtime."""
    assessments = {
        item.capability: item
        for item in validate_equivalence_contracts(contracts, coverage)
    }
    levels: dict[str, FallbackEquivalence] = {}
    for capability, level in declared.items():
        if level is FallbackEquivalence.FULL:
            proof = assessments.get(capability)
            levels[capability] = (
                FallbackEquivalence.FULL
                if proof is not None and proof.complete
                else FallbackEquivalence.PARTIAL
            )
        else:
            levels[capability] = level
    return levels


def equivalence_matrix() -> tuple[dict[str, object], ...]:
    assessments = {
        item.capability: item for item in validate_equivalence_contracts()
    }
    return tuple({
        "capability": contract.capability,
        "preferred_provider": contract.preferred_provider,
        "fallback": contract.fallback_implementation,
        "required_dimensions": tuple(sorted(contract.required_dimensions)),
        "equivalence": (
            FallbackEquivalence.FULL.value
            if assessments[name].complete else FallbackEquivalence.PARTIAL.value
        ),
        "evidence_contract": tuple(sorted(contract.required_evidence)),
        "required_failure_semantics": tuple(sorted(contract.required_failure_semantics)),
    } for name, contract in sorted(EQUIVALENCE_CONTRACTS.items()))
