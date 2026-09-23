"""Deterministic validation and identity for Provider-owned capability manifests."""
from __future__ import annotations

from dataclasses import asdict
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from engine.contracts import validate_contract
from engine.models import (
    ArtifactManifest,
    ArtifactRole,
    CapabilityEvidenceState,
    CapabilityManifest,
    CapabilityRecord,
    CheckResult,
    CheckStatus,
    LifecycleState,
    ProviderExecution,
)


_FILE_REFERENCE = re.compile(r"(?:^|[;\s])file=([^;\s]+)")


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def capability_manifest_from_data(payload: Mapping[str, object]) -> CapabilityManifest:
    raw = dict(payload)
    validate_contract("capability-manifest", raw)
    capabilities = tuple(
        CapabilityRecord(
            capability_id=str(item["capability_id"]),
            public_name=str(item["public_name"]),
            capability_type=str(item["capability_type"]),
            declared_status=str(item["declared_status"]),
            implementation_status=str(item["implementation_status"]),
            entrypoints=tuple(item["entrypoints"]),
            supported_profiles=tuple(item["supported_profiles"]),
            supported_deliverables=tuple(item["supported_deliverables"]),
            templates=tuple(item["templates"]),
            schemas=tuple(item["schemas"]),
            validation_coverage=tuple(item["validation_coverage"]),
            public_claim_sources=tuple(item["public_claim_sources"]),
            implementation_evidence=tuple(item["implementation_evidence"]),
            confidence=float(item["confidence"]),
            evidence_state=CapabilityEvidenceState(item["evidence_state"]),
        )
        for item in raw["capabilities"]
    )
    return CapabilityManifest(
        schema_version=str(raw["schema_version"]),
        inspection_id=str(raw["inspection_id"]),
        inspection_nonce=str(raw["inspection_nonce"]),
        artifact_role=ArtifactRole(raw["artifact_role"]),
        artifact_digest=str(raw["artifact_digest"]),
        provider_identity=str(raw["provider_identity"]),
        capabilities=capabilities,
        public_output_contract_status=str(raw["public_output_contract_status"]),
        public_output_contract_evidence=tuple(raw["public_output_contract_evidence"]),
        evidence_origin=str(raw.get("evidence_origin", "provider")),
    )


def capability_manifest_digest(manifest: CapabilityManifest) -> str:
    payload = _json_value(asdict(manifest))
    payload["capabilities"] = sorted(
        payload["capabilities"], key=lambda item: item["capability_id"]
    )
    for item in payload["capabilities"]:
        for field in (
            "entrypoints", "supported_profiles", "supported_deliverables",
            "templates", "schemas", "validation_coverage",
            "public_claim_sources", "implementation_evidence",
        ):
            item[field] = sorted(item[field])
    payload["public_output_contract_evidence"] = sorted(
        payload["public_output_contract_evidence"]
    )
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _result(status: CheckStatus, subject: str, evidence: tuple[str, ...]) -> CheckResult:
    return CheckResult(
        "capability.capability_contract",
        "internal.capability-manifest",
        subject,
        True,
        status,
        True,
        True,
        1.0,
        evidence,
        LifecycleState.VALIDATED_PENDING_CONFIRMATION,
        subject,
    )


def _evidence_values(manifest: CapabilityManifest) -> tuple[str, ...]:
    values = list(manifest.public_output_contract_evidence)
    for capability in manifest.capabilities:
        values.extend(capability.public_claim_sources)
        values.extend(capability.implementation_evidence)
    return tuple(values)


def _invalid_evidence_paths(
    manifest: CapabilityManifest, artifact: ArtifactManifest,
) -> tuple[str, ...]:
    files = set(artifact.files)
    invalid: list[str] = []
    for value in _evidence_values(manifest):
        match = _FILE_REFERENCE.search(value)
        if not match:
            continue
        raw_path = match.group(1).replace("\\", "/")
        path = Path(raw_path)
        if path.is_absolute() or ".." in path.parts or raw_path.lstrip("./") not in files:
            invalid.append(raw_path)
    return tuple(sorted(set(invalid)))


def validate_capability_manifest(
    manifest: CapabilityManifest,
    artifact: ArtifactManifest,
    *,
    inspection_id: str,
    inspection_nonce: str,
    provider_id: str,
    provider_execution: ProviderExecution,
    expected_role: ArtifactRole,
) -> CheckResult:
    subject = artifact.skill_name
    if provider_execution is not ProviderExecution.EXECUTED:
        return _result(CheckStatus.NOT_EXECUTED, subject, ("CAPABILITY_PROVIDER_NOT_EXECUTED",))
    if manifest.evidence_origin != "provider":
        return _result(CheckStatus.NOT_EXECUTED, subject, ("CAPABILITY_MANIFEST_SELF_REPORTED",))
    if manifest.inspection_id != inspection_id or manifest.inspection_nonce != inspection_nonce:
        return _result(CheckStatus.NOT_EXECUTED, subject, ("CAPABILITY_MANIFEST_STALE",))
    if manifest.provider_identity != provider_id:
        return _result(CheckStatus.NOT_EXECUTED, subject, ("CAPABILITY_MANIFEST_PROVIDER_MISMATCH",))
    if manifest.artifact_digest != artifact.content_digest:
        return _result(CheckStatus.NOT_EXECUTED, subject, ("CAPABILITY_MANIFEST_DIGEST_MISMATCH",))
    if manifest.artifact_role is not expected_role:
        return _result(CheckStatus.NOT_EXECUTED, subject, ("CAPABILITY_MANIFEST_ROLE_MISMATCH",))
    capability_ids = tuple(item.capability_id for item in manifest.capabilities)
    duplicates = tuple(sorted({item for item in capability_ids if capability_ids.count(item) > 1}))
    if duplicates:
        return _result(
            CheckStatus.FAIL,
            subject,
            tuple(f"CAPABILITY_MANIFEST_DUPLICATE_ID:{item}" for item in duplicates),
        )
    invalid_paths = _invalid_evidence_paths(manifest, artifact)
    if invalid_paths:
        return _result(
            CheckStatus.NOT_EXECUTED,
            subject,
            ("CAPABILITY_MANIFEST_EVIDENCE_OUT_OF_SCOPE", *invalid_paths),
        )
    return _result(
        CheckStatus.PASS,
        subject,
        (
            f"capability_manifest_digest={capability_manifest_digest(manifest)}",
            f"capability_count={len(manifest.capabilities)}",
        ),
    )


__all__ = [
    "capability_manifest_digest",
    "capability_manifest_from_data",
    "validate_capability_manifest",
]
