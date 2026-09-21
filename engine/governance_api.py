"""Neutral public contract for embedding skill-engineering governance."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping


class GovernanceError(RuntimeError):
    """Raised when a governance request cannot be interpreted safely."""


class GovernanceMode(StrEnum):
    OFF = "off"
    SHADOW = "shadow"
    ENFORCED = "enforced"


class GovernanceStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class CoverageStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNKNOWN = "UNKNOWN"


class GateStatus(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class ProviderObservation:
    provider_id: str
    capability: str
    available: bool = False
    selected: bool = False
    executed: bool = False
    status: str = "UNKNOWN"
    evidence_valid: bool = False
    evidence_refs: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CapabilityDecision:
    capability: str
    required: bool
    status: GovernanceStatus
    provider_id: str | None
    evidence_refs: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GovernanceRequest:
    request_id: str
    trigger_job_id: str = ""
    decision_id: str = ""
    admission_id: str = ""
    authoring_id: str = ""
    validation_id: str = ""
    action_type: str = ""
    target_skill_ids: tuple[str, ...] = ()
    parent_revision_ids: tuple[str, ...] = ()
    intent: Mapping[str, Any] = field(default_factory=dict)
    applicability: Mapping[str, str] = field(default_factory=dict)
    required_capabilities: tuple[str, ...] = ()
    optional_capabilities: tuple[str, ...] = ()
    capability_results: Mapping[str, str] = field(default_factory=dict)
    source_digest: str | None = None
    candidate_digest: str | None = None
    source_path: str | None = None
    candidate_path: str | None = None
    evidence_refs: tuple[str, ...] = ()
    staging_descriptor: Mapping[str, Any] = field(default_factory=dict)
    validation_status: str = "UNKNOWN"
    coverage_status: str = "UNKNOWN"
    integrity_status: str = "UNKNOWN"
    validation_reasons: tuple[str, ...] = ()
    providers: tuple[ProviderObservation, ...] = ()
    deliverable_contract: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise GovernanceError("request_id is required")
        if self.action_type and not self.action_type.strip():
            raise GovernanceError("action_type cannot be blank")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["providers"] = [item.to_dict() for item in self.providers]
        return data


@dataclass(frozen=True, slots=True)
class GovernanceResult:
    governance_id: str
    validation_status: GovernanceStatus
    coverage_status: CoverageStatus
    integrity_status: GovernanceStatus
    capabilities: tuple[CapabilityDecision, ...]
    provider_results: tuple[ProviderObservation, ...]
    source_digest: str | None
    candidate_digest: str | None
    publish_authorized: bool
    gate_status: GateStatus
    reason_codes: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    engine_name: str
    engine_version: str
    engine_revision: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["capabilities"] = [item.to_dict() for item in self.capabilities]
        data["provider_results"] = [item.to_dict() for item in self.provider_results]
        return data


class GovernanceEngine:
    """Evaluate a neutral request without owning lifecycle state or mutation."""

    def __init__(
        self,
        *,
        engine_name: str = "skill-engineering",
        engine_version: str | None = None,
        engine_revision: str | None = None,
        mode: GovernanceMode | str = GovernanceMode.ENFORCED,
    ) -> None:
        self.engine_name = engine_name
        self.engine_version = engine_version or _package_version()
        self.engine_revision = engine_revision or os.environ.get(
            "SKILL_ENGINEERING_REVISION", "working-tree"
        )
        try:
            self.mode = GovernanceMode(mode)
        except ValueError as exc:
            raise GovernanceError(f"unsupported governance mode: {mode}") from exc

    @property
    def enabled(self) -> bool:
        return self.mode is not GovernanceMode.OFF

    @staticmethod
    def artifact_digest(path: str | Path) -> str:
        return _digest_path(Path(path))

    def evaluate(self, request: GovernanceRequest) -> GovernanceResult:
        if not isinstance(request, GovernanceRequest):
            raise GovernanceError("request must be a GovernanceRequest")

        reason_codes: list[str] = []
        validation = _status(request.validation_status)
        coverage = _coverage(request.coverage_status)
        integrity = self._integrity(request, reason_codes)
        capabilities = self._capabilities(request, reason_codes)
        self._deliverable_contract(request, reason_codes)

        if validation is GovernanceStatus.FAIL:
            reason_codes.append("validation_failed")
        elif validation is GovernanceStatus.UNKNOWN:
            reason_codes.append("validation_unknown")
        if coverage is not CoverageStatus.COMPLETE:
            reason_codes.append(f"coverage_{coverage.value.lower()}")
        if integrity is GovernanceStatus.FAIL:
            reason_codes.append("integrity_failed")
        elif integrity is GovernanceStatus.UNKNOWN:
            reason_codes.append("integrity_unknown")

        required_capabilities = [item for item in capabilities if item.required]
        failed_capabilities = [
            item for item in required_capabilities if item.status is GovernanceStatus.FAIL
        ]
        incomplete_capabilities = [
            item for item in required_capabilities if item.status is GovernanceStatus.UNKNOWN
        ]
        if failed_capabilities:
            reason_codes.extend(
                f"capability_failed:{item.capability}" for item in failed_capabilities
            )
        if incomplete_capabilities:
            reason_codes.extend(
                f"capability_incomplete:{item.capability}"
                for item in incomplete_capabilities
            )
        reason_codes.extend(
            code
            for item in required_capabilities
            for code in item.reason_codes
            if code not in reason_codes
        )

        if any(
            status is GovernanceStatus.FAIL
            for status in (validation, integrity)
        ) or failed_capabilities or "deliverable_contract_failed" in reason_codes:
            gate = GateStatus.BLOCKED
        elif (
            validation is GovernanceStatus.UNKNOWN
            or coverage is not CoverageStatus.COMPLETE
            or integrity is GovernanceStatus.UNKNOWN
            or incomplete_capabilities
            or "deliverable_contract_incomplete" in reason_codes
            or "deliverable_contract_missing" in reason_codes
        ):
            gate = GateStatus.INCOMPLETE
        else:
            gate = GateStatus.PASS

        publish_authorized = gate is GateStatus.PASS and request.action_type.upper() != "AUDIT_ONLY"
        if request.action_type.upper() == "AUDIT_ONLY":
            reason_codes.append("audit_only_no_mutation")
        if self.mode is GovernanceMode.SHADOW:
            reason_codes.append("shadow_mode")
            publish_authorized = False
        elif self.mode is GovernanceMode.OFF:
            reason_codes.append("governance_mode_off")
            gate = GateStatus.INCOMPLETE
            publish_authorized = False

        return GovernanceResult(
            governance_id=f"gov_{_digest(request.to_dict())[:20]}",
            validation_status=validation,
            coverage_status=coverage,
            integrity_status=integrity,
            capabilities=tuple(capabilities),
            provider_results=request.providers,
            source_digest=request.source_digest,
            candidate_digest=request.candidate_digest,
            publish_authorized=publish_authorized,
            gate_status=gate,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            evidence_refs=tuple(dict.fromkeys(request.evidence_refs)),
            engine_name=self.engine_name,
            engine_version=self.engine_version,
            engine_revision=self.engine_revision,
        )

    def _integrity(
        self, request: GovernanceRequest, reason_codes: list[str]
    ) -> GovernanceStatus:
        statuses: list[GovernanceStatus] = []
        for label, expected, path in (
            ("source", request.source_digest, request.source_path),
            ("candidate", request.candidate_digest, request.candidate_path),
        ):
            if expected is None and path is None:
                continue
            if expected is None or path is None:
                reason_codes.append(f"{label}_digest_or_path_missing")
                statuses.append(GovernanceStatus.UNKNOWN)
                continue
            try:
                actual = _digest_path(Path(path))
            except OSError:
                reason_codes.append(f"{label}_path_unreadable")
                statuses.append(GovernanceStatus.UNKNOWN)
                continue
            if actual != expected:
                reason_codes.append(f"{label}_digest_mismatch")
                statuses.append(GovernanceStatus.FAIL)
            else:
                statuses.append(GovernanceStatus.PASS)
        if request.integrity_status:
            statuses.append(_status(request.integrity_status))
        if GovernanceStatus.FAIL in statuses:
            return GovernanceStatus.FAIL
        if GovernanceStatus.UNKNOWN in statuses:
            return GovernanceStatus.UNKNOWN
        return GovernanceStatus.PASS if statuses else GovernanceStatus.UNKNOWN

    def _capabilities(
        self, request: GovernanceRequest, reason_codes: list[str]
    ) -> list[CapabilityDecision]:
        required: list[str] = []
        for capability in request.required_capabilities:
            canonical = _canonical_capability(capability)
            if canonical not in required:
                required.append(canonical)
        for capability, applicability in request.applicability.items():
            canonical = _canonical_capability(capability)
            if applicability.lower() == "required" and canonical not in required:
                required.append(canonical)
        optional = {
            _canonical_capability(capability)
            for capability in request.optional_capabilities
        }
        result: list[CapabilityDecision] = []
        for capability in (*required, *optional):
            is_required = capability in required
            observations = [
                item
                for item in request.providers
                if _canonical_capability(item.capability) == capability
            ]
            selected = next((item for item in observations if item.selected), None)
            declared = request.capability_results.get(capability)
            if declared is None:
                declared = request.capability_results.get(capability.lower())
            if declared is not None:
                status = _status(declared)
                refs = selected.evidence_refs if selected else ()
                reasons = (f"capability_result={declared}",)
            elif selected is None:
                status = GovernanceStatus.UNKNOWN
                refs = ()
                reasons = ("provider_not_selected",)
            elif not selected.available:
                status = GovernanceStatus.FAIL
                refs = selected.evidence_refs
                reasons = ("provider_not_available",)
            elif not selected.executed:
                status = GovernanceStatus.UNKNOWN
                refs = selected.evidence_refs
                reasons = ("provider_not_executed",)
            elif not selected.evidence_valid:
                status = GovernanceStatus.FAIL
                refs = selected.evidence_refs
                reasons = ("provider_evidence_invalid",)
            else:
                status = _status(selected.status)
                refs = selected.evidence_refs
                reasons = selected.reason_codes or (f"provider_status={selected.status}",)
            result.append(
                CapabilityDecision(
                    capability=capability,
                    required=is_required,
                    status=status,
                    provider_id=selected.provider_id if selected else None,
                    evidence_refs=tuple(refs),
                    reason_codes=tuple(reasons),
                )
            )
        return result

    @staticmethod
    def _deliverable_contract(
        request: GovernanceRequest, reason_codes: list[str]
    ) -> None:
        required = (
            request.applicability.get("deliverable_contract", "").lower() == "required"
            or "DELIVERABLE_CONTRACT" in request.required_capabilities
        )
        if not required:
            return
        contract = request.deliverable_contract
        if not isinstance(contract, Mapping):
            reason_codes.append("deliverable_contract_missing")
            return
        status = str(contract.get("status") or "UNKNOWN").upper()
        if status in {"FAIL", "BLOCKED"}:
            reason_codes.append("deliverable_contract_failed")
        elif status not in {"PASS", "COMPLETE"}:
            reason_codes.append("deliverable_contract_incomplete")


def _status(value: Any) -> GovernanceStatus:
    normalized = str(value or "UNKNOWN").upper()
    if normalized in {"PASS", "READY", "AVAILABLE", "COMPLETE"}:
        return GovernanceStatus.PASS
    if normalized in {"FAIL", "FAILED", "BLOCKED", "INVALID"}:
        return GovernanceStatus.FAIL
    return GovernanceStatus.UNKNOWN


def _coverage(value: Any) -> CoverageStatus:
    normalized = str(value or "UNKNOWN").upper()
    if normalized in {"COMPLETE", "FULL"}:
        return CoverageStatus.COMPLETE
    if normalized in {"INCOMPLETE", "PARTIAL"}:
        return CoverageStatus.INCOMPLETE
    return CoverageStatus.UNKNOWN


def _canonical_capability(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    return "DELIVERABLE_CONTRACT" if normalized == "DELIVERABLE_CONTRACT" else normalized


def _digest_path(path: Path) -> str:
    if not path.is_dir():
        raise OSError(f"governance artifact is not a directory: {path}")
    digest = hashlib.sha256()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = child.relative_to(path).as_posix().encode("utf-8")
        content = child.read_bytes()
        digest.update(relative)
        digest.update(b"\0")
        digest.update(str(len(content)).encode("ascii"))
        digest.update(b"\0")
        digest.update(content)
    return digest.hexdigest()


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _package_version() -> str:
    try:
        return importlib.metadata.version("skill-engineering")
    except importlib.metadata.PackageNotFoundError:
        return "1.0.3"


__all__ = [
    "CapabilityDecision",
    "CoverageStatus",
    "GateStatus",
    "GovernanceEngine",
    "GovernanceError",
    "GovernanceMode",
    "GovernanceRequest",
    "GovernanceResult",
    "GovernanceStatus",
    "ProviderObservation",
]
