"""Required Capability planning and fail-closed execution evidence."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import yaml

from engine.models import (
    CapabilityAssessment,
    CapabilityStatus,
    CheckResult,
    CheckStatus,
    DeliverableContractApplicability,
    FallbackEquivalence,
    Intent,
    LifecycleState,
    ProviderEvidence,
    ProviderExecution,
)
from engine.equivalence_contracts import proven_equivalence_levels
from engine.providers import (
    AUDIT_SKILL,
    CHECK_SKILL_CONFORMANCE,
    CREATE_CANDIDATE,
    GOVERN_AGENT_INSTRUCTIONS,
)


SKILL_CREATION_OR_RESTRUCTURE = "skill_creation_or_restructure"
SKILL_STRUCTURE = "skill_structure"
SKILL_TRIGGER_AND_DESCRIPTION = "skill_trigger_and_description"
SKILL_INSTRUCTION_DESIGN = "skill_instruction_design"
SKILL_AUDIT_AND_SIMPLIFICATION = "skill_audit_and_simplification"
SKILL_INSTRUCTION_QUALITY = "skill_instruction_quality"
SKILL_RULE_GOVERNANCE = "skill_rule_governance"
SKILL_DUPLICATION_AND_BLOAT = "skill_duplication_and_bloat"
SKILL_RESOURCE_INTEGRITY = "skill_resource_integrity"
SKILL_SCRIPT_INTEGRITY = "skill_script_integrity"
SKILL_CONFORMANCE = "skill_conformance"
AGENT_INSTRUCTION_GOVERNANCE = "agent_instruction_governance"
REGRESSION_VALIDATION = "regression_validation"
EVIDENCE_COLLECTION = "evidence_collection"
QUALITY_GATE = "quality_gate"
GOAL_AND_RESPONSIBILITY = "goal_and_responsibility"
ACTUAL_IMPLEMENTATION = "actual_implementation"
BEHAVIORAL_VALIDATION = "behavioral_validation"
DELIVERABLE_CONTRACT = "deliverable_contract"

SECURITY_REVIEW = "security_review"
PLUGIN_MANIFEST_VALIDATION = "plugin_manifest_validation"
PDF_VALIDATION = "pdf_validation"
DOCUMENT_VALIDATION = "document_validation"
SPREADSHEET_VALIDATION = "spreadsheet_validation"
PRESENTATION_VALIDATION = "presentation_validation"
FRONTEND_VALIDATION = "frontend_validation"
GITHUB_CI_VALIDATION = "github_ci_validation"
VISUAL_ASSET_VALIDATION = "visual_asset_validation"

CORE_CAPABILITIES = (
    SKILL_STRUCTURE,
    SKILL_TRIGGER_AND_DESCRIPTION,
    SKILL_INSTRUCTION_QUALITY,
    SKILL_RULE_GOVERNANCE,
    SKILL_DUPLICATION_AND_BLOAT,
    SKILL_RESOURCE_INTEGRITY,
    SKILL_SCRIPT_INTEGRITY,
    SKILL_CONFORMANCE,
    AGENT_INSTRUCTION_GOVERNANCE,
    REGRESSION_VALIDATION,
    EVIDENCE_COLLECTION,
    QUALITY_GATE,
    GOAL_AND_RESPONSIBILITY,
    ACTUAL_IMPLEMENTATION,
    BEHAVIORAL_VALIDATION,
)

DOMAIN_CAPABILITIES = (
    SECURITY_REVIEW,
    PLUGIN_MANIFEST_VALIDATION,
    PDF_VALIDATION,
    DOCUMENT_VALIDATION,
    SPREADSHEET_VALIDATION,
    PRESENTATION_VALIDATION,
    FRONTEND_VALIDATION,
    GITHUB_CI_VALIDATION,
    VISUAL_ASSET_VALIDATION,
)


@dataclass(frozen=True)
class CapabilityDefinition:
    capability: str
    preferred_providers: tuple[str, ...]
    provider_capabilities: tuple[str, ...]
    fallback: str | None
    fallback_equivalence: FallbackEquivalence


def _definition(
    capability: str,
    providers: tuple[str, ...],
    ports: tuple[str, ...],
    fallback: str | None,
    equivalence: FallbackEquivalence,
) -> CapabilityDefinition:
    return CapabilityDefinition(capability, providers, ports, fallback, equivalence)


_DEFINITIONS = {
    SKILL_CREATION_OR_RESTRUCTURE: _definition(
        SKILL_CREATION_OR_RESTRUCTURE, (), (CREATE_CANDIDATE,),
        "internal restructuring rubric",
        FallbackEquivalence.FULL,
    ),
    SKILL_STRUCTURE: _definition(
        SKILL_STRUCTURE, (), (CHECK_SKILL_CONFORMANCE,),
        "internal deterministic structure validator", FallbackEquivalence.FULL,
    ),
    SKILL_TRIGGER_AND_DESCRIPTION: _definition(
        SKILL_TRIGGER_AND_DESCRIPTION, (),
        (CREATE_CANDIDATE, CHECK_SKILL_CONFORMANCE),
        "internal frontmatter and trigger-description validator", FallbackEquivalence.FULL,
    ),
    SKILL_INSTRUCTION_DESIGN: _definition(
        SKILL_INSTRUCTION_DESIGN, (), (CREATE_CANDIDATE,),
        "internal instruction-design rubric", FallbackEquivalence.FULL,
    ),
    SKILL_AUDIT_AND_SIMPLIFICATION: _definition(
        SKILL_AUDIT_AND_SIMPLIFICATION, (), (AUDIT_SKILL,),
        "internal evidence-backed audit and simplification rubric", FallbackEquivalence.FULL,
    ),
    SKILL_INSTRUCTION_QUALITY: _definition(
        SKILL_INSTRUCTION_QUALITY, (), (AUDIT_SKILL,),
        "internal executable-instruction audit", FallbackEquivalence.FULL,
    ),
    SKILL_RULE_GOVERNANCE: _definition(
        SKILL_RULE_GOVERNANCE, (), (AUDIT_SKILL,),
        "internal rule-governance coverage validator", FallbackEquivalence.FULL,
    ),
    SKILL_DUPLICATION_AND_BLOAT: _definition(
        SKILL_DUPLICATION_AND_BLOAT, (), (AUDIT_SKILL,),
        "internal duplication, conflict, ownership, overlap, and bloat rubric",
        FallbackEquivalence.FULL,
    ),
    SKILL_RESOURCE_INTEGRITY: _definition(
        SKILL_RESOURCE_INTEGRITY, (), (CHECK_SKILL_CONFORMANCE,),
        "internal deterministic reference-integrity validator", FallbackEquivalence.FULL,
    ),
    SKILL_SCRIPT_INTEGRITY: _definition(
        SKILL_SCRIPT_INTEGRITY, (), (CHECK_SKILL_CONFORMANCE,),
        "internal deterministic declared-script validator", FallbackEquivalence.FULL,
    ),
    SKILL_CONFORMANCE: _definition(
        SKILL_CONFORMANCE, (), (CHECK_SKILL_CONFORMANCE,),
        "internal deterministic conformance suite", FallbackEquivalence.FULL,
    ),
    AGENT_INSTRUCTION_GOVERNANCE: _definition(
        AGENT_INSTRUCTION_GOVERNANCE, (), (GOVERN_AGENT_INSTRUCTIONS,),
        "direct AGENTS.md and CLAUDE.md hierarchy inspection", FallbackEquivalence.FULL,
    ),
    REGRESSION_VALIDATION: _definition(
        REGRESSION_VALIDATION, (), (), "internal regression-disposition enforcement",
        FallbackEquivalence.FULL,
    ),
    EVIDENCE_COLLECTION: _definition(
        EVIDENCE_COLLECTION, (), (), "internal typed evidence collector",
        FallbackEquivalence.FULL,
    ),
    QUALITY_GATE: _definition(
        QUALITY_GATE, (), (), "internal fail-closed Quality Gate", FallbackEquivalence.FULL,
    ),
    GOAL_AND_RESPONSIBILITY: _definition(
        GOAL_AND_RESPONSIBILITY, (), (), "internal responsibility rubric", FallbackEquivalence.NONE,
    ),
    ACTUAL_IMPLEMENTATION: _definition(
        ACTUAL_IMPLEMENTATION, (), (), "internal implementation integrity checks", FallbackEquivalence.NONE,
    ),
    BEHAVIORAL_VALIDATION: _definition(
        BEHAVIORAL_VALIDATION, (), (), "internal and Codex-selected behavior checks", FallbackEquivalence.NONE,
    ),
}

DECLARED_FALLBACK_EQUIVALENCES: Mapping[str, FallbackEquivalence] = {
    name: item.fallback_equivalence for name, item in _DEFINITIONS.items()
}
DEFAULT_FALLBACK_EQUIVALENCES: Mapping[str, FallbackEquivalence] = (
    proven_equivalence_levels(DECLARED_FALLBACK_EQUIVALENCES)
)
DEFAULT_INTERNAL_FALLBACKS = frozenset(
    name for name, level in DEFAULT_FALLBACK_EQUIVALENCES.items()
    if level in {FallbackEquivalence.FULL, FallbackEquivalence.ALTERNATIVE}
)


def _frontmatter(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    skill_path = path / "SKILL.md"
    try:
        lines = skill_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
        value = yaml.safe_load("\n".join(lines[1:end]))
    except (StopIteration, yaml.YAMLError):
        return {}
    return value if isinstance(value, dict) else {}


def declared_required_capabilities(path: Path | None) -> tuple[str, ...]:
    """Read target-declared domain capabilities without assuming a closed whitelist."""
    raw = _frontmatter(path).get("required_capabilities", ())
    if isinstance(raw, str):
        raw = (raw,)
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(sorted({item.strip() for item in raw if isinstance(item, str) and item.strip()}))


def infer_domain_capabilities(path: Path | None) -> frozenset[str]:
    """Compatibility helper: domain needs are declared by Codex, never guessed."""
    return frozenset(declared_required_capabilities(path))


def _provider_for(
    definition: CapabilityDefinition,
    provider_evidence: Iterable[ProviderEvidence],
) -> tuple[ProviderEvidence, bool] | None:
    executed = {CheckStatus.PASS, CheckStatus.FAIL}
    for index, port in enumerate(definition.provider_capabilities):
        match = next(
            (item for item in provider_evidence
             if item.capability == port
             and item.status in executed
             and item.provider_execution is ProviderExecution.EXECUTED
             and item.evidence_valid),
            None,
        )
        if match is not None:
            return match, index > 0
    return None


def _effective_levels(
    internal_fallbacks: frozenset[str] | None,
    fallback_equivalences: Mapping[str, FallbackEquivalence] | None,
) -> dict[str, FallbackEquivalence]:
    levels = dict(DEFAULT_FALLBACK_EQUIVALENCES)
    if internal_fallbacks is not None:
        levels = {
            name: level if name in internal_fallbacks else FallbackEquivalence.NONE
            for name, level in levels.items()
        }
    if fallback_equivalences:
        levels.update({name: FallbackEquivalence(level) for name, level in fallback_equivalences.items()})
    return levels


def build_capability_preflight(
    mode: Intent,
    target: Path | None,
    provider_evidence: tuple[ProviderEvidence, ...],
    *,
    internal_fallbacks: frozenset[str] | None = None,
    fallback_equivalences: Mapping[str, FallbackEquivalence] | None = None,
    deliverable_contract_applicability: DeliverableContractApplicability = DeliverableContractApplicability.COMPATIBILITY,
) -> tuple[CapabilityAssessment, ...]:
    """Infer required checks, then resolve each to executed Provider or equivalent fallback."""
    levels = _effective_levels(internal_fallbacks, fallback_equivalences)
    declared = set(declared_required_capabilities(target))
    ordered = [
        SKILL_CREATION_OR_RESTRUCTURE,
        SKILL_INSTRUCTION_DESIGN,
        SKILL_AUDIT_AND_SIMPLIFICATION,
        *CORE_CAPABILITIES,
    ]
    ordered.extend(sorted(declared - set(ordered)))
    if DELIVERABLE_CONTRACT not in ordered:
        ordered.append(DELIVERABLE_CONTRACT)

    assessments: list[CapabilityAssessment] = []
    for capability in ordered:
        definition = _DEFINITIONS.get(capability)
        if capability == DELIVERABLE_CONTRACT:
            if deliverable_contract_applicability is DeliverableContractApplicability.NOT_REQUIRED:
                assessments.append(CapabilityAssessment(
                    capability, False, CapabilityStatus.NOT_APPLICABLE,
                    (), None, None, FallbackEquivalence.NONE,
                    ("deliverable contract is explicitly not required for this inspection",),
                ))
                continue
            required = (
                deliverable_contract_applicability
                is DeliverableContractApplicability.REQUIRED
            )
            executed = next(
                (item for item in provider_evidence
                 if item.capability == "DELIVERABLE_CONTRACT"
                 and item.provider_execution is ProviderExecution.EXECUTED
                 and item.evidence_valid
                 and item.deliverable_contract is not None),
                None,
            )
            if executed is not None:
                assessments.append(CapabilityAssessment(
                    capability, required, CapabilityStatus.READY,
                    (executed.provider_id,), executed.provider_id, None,
                    FallbackEquivalence.NONE,
                    (f"deliverable contract Provider executed: {executed.provider_id}",),
                ))
                continue
            attempted = next(
                (item for item in provider_evidence
                 if item.capability == "DELIVERABLE_CONTRACT"
                 and (item.provider_available
                      or item.provider_execution is not ProviderExecution.NOT_STARTED)),
                None,
            )
            assessments.append(CapabilityAssessment(
                capability, required, CapabilityStatus.BLOCKED,
                ((attempted.provider_id,) if attempted is not None else ()),
                None, None, FallbackEquivalence.NONE,
                (("selected deliverable contract Provider did not return valid executed evidence",)
                 if attempted is not None else
                 ("no deliverable contract Provider was available for this inspection",)),
            ))
            continue
        not_applicable = (
            capability in {SKILL_CREATION_OR_RESTRUCTURE, SKILL_INSTRUCTION_DESIGN}
            and mode is Intent.AUDIT_ONLY
            and capability not in declared
        ) or (
            capability == SKILL_AUDIT_AND_SIMPLIFICATION
            and mode not in {Intent.AUDIT_ONLY, Intent.AUDIT_OPTIMIZE}
            and capability not in declared
        )
        if not_applicable:
            assessments.append(CapabilityAssessment(
                capability, False, CapabilityStatus.NOT_APPLICABLE,
                definition.preferred_providers if definition else (), None,
                definition.fallback if definition else None,
                levels.get(capability, FallbackEquivalence.NONE),
                ("capability is not applicable to this target and intent",),
            ))
            continue
        if definition is None:
            dynamic = next(
                (item for item in provider_evidence
                 if item.capability.lower() == capability.lower()
                 and item.status in {CheckStatus.PASS, CheckStatus.FAIL}
                 and item.provider_execution is ProviderExecution.EXECUTED
                 and item.evidence_valid),
                None,
            )
            if dynamic is not None:
                assessments.append(CapabilityAssessment(
                    capability, True, CapabilityStatus.READY,
                    (dynamic.provider_id,), dynamic.provider_id, None,
                    FallbackEquivalence.NONE,
                    (f"dynamic Provider executed: {dynamic.provider_id}",),
                ))
                continue
            assessments.append(CapabilityAssessment(
                capability, True, CapabilityStatus.BLOCKED, (), None, None,
                FallbackEquivalence.NONE,
                ("required capability has no executed Provider or equivalent fallback",),
            ))
            continue

        selected = _provider_for(definition, provider_evidence)
        if selected is not None:
            provider, alternative = selected
            equivalence = FallbackEquivalence.ALTERNATIVE if alternative else FallbackEquivalence.NONE
            assessments.append(CapabilityAssessment(
                capability, True,
                CapabilityStatus.FALLBACK if alternative else CapabilityStatus.READY,
                definition.preferred_providers, provider.provider_id,
                f"alternative Provider: {provider.provider_id}" if alternative else None,
                equivalence,
                (f"Provider executed with status {provider.status.value}: {provider.provider_id}",),
            ))
            continue

        failed_provider = next(
            (item for item in provider_evidence
             if item.capability in definition.provider_capabilities
             and item.provider_available
             and item.provider_execution is ProviderExecution.FAILED),
            None,
        )
        if failed_provider is None:
            assessments.append(CapabilityAssessment(
                capability, True, CapabilityStatus.READY, (), "internal.core",
                None, FallbackEquivalence.NONE,
                ("skill-engineer core implementation selected directly",),
            ))
            continue
        level = levels.get(capability, FallbackEquivalence.NONE)
        allowed = level in {FallbackEquivalence.FULL, FallbackEquivalence.ALTERNATIVE}
        status = CapabilityStatus.FALLBACK if allowed and definition.fallback else CapabilityStatus.BLOCKED
        assessments.append(CapabilityAssessment(
            capability, True, status, (), None,
            definition.fallback, level,
            ((f"installed Provider runtime failed: {failed_provider.provider_id}",
              f"equivalent fallback selected: {definition.fallback}")
             if status is CapabilityStatus.FALLBACK else
             (f"installed Provider runtime failed: {failed_provider.provider_id}",
              f"fallback equivalence={level.value}; FULL or ALTERNATIVE is required")),
        ))
    return tuple(assessments)


def capability_preflight_evidence(
    assessments: tuple[CapabilityAssessment, ...], subject: str,
) -> tuple[CheckResult, ...]:
    """Bind resolution status to Gate evidence; execution is proven separately."""
    results: list[CheckResult] = []
    for item in assessments:
        status = CheckStatus.NOT_EXECUTED if item.status is CapabilityStatus.BLOCKED else CheckStatus.PASS
        evidence = (
            f"preflight_status={item.status.value}",
            f"preferred_providers={list(item.preferred_providers)}",
            f"selected_provider={item.selected_provider or 'none'}",
            f"fallback={item.fallback or 'none'}",
            f"fallback_equivalence={item.fallback_equivalence.value}",
            *item.evidence,
        )
        results.append(CheckResult(
            f"capability.{item.capability}.preflight", "internal.capability-preflight",
            subject, item.required, status, True, True, 1.0, tuple(evidence),
            LifecycleState.VALIDATED_PENDING_CONFIRMATION, subject,
        ))
    return tuple(results)


def provider_capability_evidence(
    assessments: tuple[CapabilityAssessment, ...],
    providers: tuple[ProviderEvidence, ...],
    subject: str,
) -> tuple[CheckResult, ...]:
    """Promote an executed selected Provider into required Capability evidence."""
    results: list[CheckResult] = []
    for item in assessments:
        if item.selected_provider is None:
            continue
        if item.capability == DELIVERABLE_CONTRACT:
            # The deterministic contract validator is the canonical execution
            # evidence; do not create a competing CheckResult identity here.
            continue
        provider = next(
            (record for record in providers if record.provider_id == item.selected_provider
             and record.status in {CheckStatus.PASS, CheckStatus.FAIL}
             and record.provider_execution is ProviderExecution.EXECUTED
             and record.evidence_valid),
            None,
        )
        if provider is None:
            continue
        evidence = (
            f"implementation=provider:{provider.provider_id}",
            f"invocation_phase={provider.invocation_phase}",
            f"provider_available={str(provider.provider_available).lower()}",
            f"provider_execution={provider.provider_execution.value}",
            f"fallback_used={str(provider.fallback_used).lower()}",
            f"provider_evidence_valid={str(provider.evidence_valid).lower()}",
            *(f"finding={value}" for value in provider.findings),
            *(f"evidence={value}" for value in provider.evidence),
            *(f"limitation={value}" for value in provider.limitations),
        )
        results.append(CheckResult(
            f"capability.{item.capability}", f"provider:{provider.provider_id}",
            subject, True, provider.status, False, provider.reproducible, 1.0,
            evidence or (provider.summary,), LifecycleState.VALIDATED_PENDING_CONFIRMATION,
            subject,
        ))
    return tuple(results)


def capability_execution_gap_evidence(
    assessments: tuple[CapabilityAssessment, ...],
    executed: tuple[CheckResult, ...],
    subject: str,
) -> tuple[CheckResult, ...]:
    """Fail closed if preflight resolution never produced execution evidence."""
    ids = {item.check_id for item in executed}
    return tuple(
        CheckResult(
            f"capability.{item.capability}.execution", "internal.capability-execution",
            subject, True, CheckStatus.NOT_EXECUTED, True, True, 1.0,
            ("preflight selected an implementation but no execution evidence was produced",
             f"preflight_status={item.status.value}",
             f"fallback_equivalence={item.fallback_equivalence.value}"),
            LifecycleState.VALIDATED_PENDING_CONFIRMATION, subject,
        )
        for item in assessments
        if item.required
        and item.status is not CapabilityStatus.BLOCKED
        and f"capability.{item.capability}" not in ids
    )


def capability_matrix(
    assessments: tuple[CapabilityAssessment, ...],
) -> tuple[Mapping[str, object], ...]:
    """Return a display-safe matrix for CLI/report consumers."""
    return tuple({
        "capability": item.capability,
        "preferred_providers": item.preferred_providers,
        "selected_provider": item.selected_provider,
        "fallback": item.fallback,
        "fallback_equivalence": item.fallback_equivalence.value,
        "status": item.status.value,
    } for item in assessments)
