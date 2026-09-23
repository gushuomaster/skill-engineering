"""Structured capability comparison without domain-specific inference."""
from __future__ import annotations

from engine.capability_manifest import capability_manifest_digest
from engine.models import (
    CapabilityChange,
    CapabilityChangeKind,
    CapabilityDiff,
    CapabilityEvidenceState,
    CapabilityManifest,
    CapabilityRecord,
)


_PUBLIC_SCOPE_FIELDS = (
    "entrypoints",
    "supported_profiles",
    "supported_deliverables",
    "templates",
    "schemas",
)


def _flatten(record: CapabilityRecord | None) -> tuple[str, ...]:
    if record is None:
        return ()
    values = [
        f"public_name={record.public_name}",
        f"capability_type={record.capability_type}",
        f"declared_status={record.declared_status}",
        f"implementation_status={record.implementation_status}",
    ]
    for field in (*_PUBLIC_SCOPE_FIELDS, "validation_coverage"):
        values.extend(f"{field}={item}" for item in getattr(record, field))
    return tuple(values)


def _changed_fields(before: CapabilityRecord, after: CapabilityRecord) -> tuple[str, ...]:
    fields = (
        "public_name", "capability_type", "declared_status", "implementation_status",
        *_PUBLIC_SCOPE_FIELDS, "validation_coverage",
    )
    return tuple(field for field in fields if getattr(before, field) != getattr(after, field))


def _kind(before: CapabilityRecord, after: CapabilityRecord) -> CapabilityChangeKind:
    if after.evidence_state is CapabilityEvidenceState.UNVERIFIABLE:
        return CapabilityChangeKind.UNVERIFIABLE
    if before.implementation_status == "implemented" and after.implementation_status != "implemented":
        return CapabilityChangeKind.BROKEN
    if any(
        set(getattr(after, field)) < set(getattr(before, field))
        for field in _PUBLIC_SCOPE_FIELDS
    ):
        return CapabilityChangeKind.NARROWED
    if set(after.validation_coverage) < set(before.validation_coverage):
        return CapabilityChangeKind.BROKEN
    if before == after:
        return CapabilityChangeKind.PRESERVED
    return CapabilityChangeKind.MODIFIED


def compare_capability_manifests(
    baseline: CapabilityManifest,
    candidate: CapabilityManifest,
) -> CapabilityDiff:
    before = {item.capability_id: item for item in baseline.capabilities}
    after = {item.capability_id: item for item in candidate.capabilities}
    changes: list[CapabilityChange] = []
    for capability_id in sorted(set(before) | set(after)):
        baseline_record = before.get(capability_id)
        candidate_record = after.get(capability_id)
        if baseline_record is None:
            kind = CapabilityChangeKind.ADDED
            changed_fields = ("capability_id",)
        elif candidate_record is None:
            kind = CapabilityChangeKind.REMOVED
            changed_fields = ("capability_id",)
        else:
            kind = _kind(baseline_record, candidate_record)
            changed_fields = _changed_fields(baseline_record, candidate_record)
        changes.append(CapabilityChange(
            capability_id,
            kind,
            changed_fields,
            _flatten(baseline_record),
            _flatten(candidate_record),
        ))
    return CapabilityDiff(
        capability_manifest_digest(baseline),
        capability_manifest_digest(candidate),
        tuple(changes),
    )


__all__ = ["compare_capability_manifests"]
