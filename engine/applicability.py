"""Explicit deliverable-contract applicability policy."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from engine.models import DeliverableContractApplicability, Intent


class AuditDimension(StrEnum):
    FULL = "FULL"
    STRUCTURE = "STRUCTURE"
    CAPABILITIES = "CAPABILITIES"
    DELIVERABLES = "DELIVERABLES"
    ENTRYPOINTS = "ENTRYPOINTS"
    TEMPLATES = "TEMPLATES"
    PROFILES = "PROFILES"
    OUTPUT_COVERAGE = "OUTPUT_COVERAGE"


@dataclass(frozen=True)
class ApplicabilityDecision:
    applicability: DeliverableContractApplicability
    reason: str


_OUTPUT_DIMENSIONS = frozenset(
    {
        AuditDimension.FULL,
        AuditDimension.CAPABILITIES,
        AuditDimension.DELIVERABLES,
        AuditDimension.ENTRYPOINTS,
        AuditDimension.TEMPLATES,
        AuditDimension.PROFILES,
        AuditDimension.OUTPUT_COVERAGE,
    }
)


def resolve_deliverable_applicability(
    mode: Intent,
    audit_dimensions: tuple[AuditDimension, ...] | None,
    public_output_contract_status: str | None,
) -> ApplicabilityDecision:
    if audit_dimensions is None and public_output_contract_status is None:
        return ApplicabilityDecision(
            DeliverableContractApplicability.COMPATIBILITY,
            "legacy_compatibility",
        )
    if mode is not Intent.AUDIT:
        return ApplicabilityDecision(
            DeliverableContractApplicability.REQUIRED,
            "mutating_mode",
        )
    dimensions = frozenset(audit_dimensions or ())
    if dimensions & _OUTPUT_DIMENSIONS:
        return ApplicabilityDecision(
            DeliverableContractApplicability.REQUIRED,
            "output_dimension_requested",
        )
    if public_output_contract_status == "absent":
        return ApplicabilityDecision(
            DeliverableContractApplicability.NOT_REQUIRED,
            "validated_output_contract_absent",
        )
    return ApplicabilityDecision(
        DeliverableContractApplicability.REQUIRED,
        "output_contract_not_proven_absent",
    )


__all__ = ["ApplicabilityDecision", "AuditDimension", "resolve_deliverable_applicability"]
