"""Invocation-neutral ports for replaceable Provider implementations and advice."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Iterable, Mapping, Protocol, runtime_checkable

from engine.contracts import validate_contract
from engine.capability_manifest import capability_manifest_from_data
from engine.models import (
    CheckResult,
    CheckStatus,
    DeliverableContract,
    DeliverableEvidence,
    DeliverableEvidenceStatus,
    DeliverableScopeConflict,
    LifecycleState,
    ProviderDescriptor,
    ProviderExecution,
    ProviderResult,
    ProviderStatus,
)

CREATE_CANDIDATE = "CREATE_CANDIDATE"
AUDIT_SKILL = "AUDIT_SKILL"
GOVERN_AGENT_INSTRUCTIONS = "GOVERN_AGENT_INSTRUCTIONS"
CHECK_SKILL_CONFORMANCE = "CHECK_SKILL_CONFORMANCE"
CAPABILITY_CONTRACT = "CAPABILITY_CONTRACT"
CAPABILITIES = frozenset(
    {CREATE_CANDIDATE, AUDIT_SKILL, GOVERN_AGENT_INSTRUCTIONS, CHECK_SKILL_CONFORMANCE,
     CAPABILITY_CONTRACT, "DELIVERABLE_CONTRACT"}
)

_FAILURE_STATUSES = frozenset(
    {ProviderStatus.UNAVAILABLE, ProviderStatus.INVALID_OUTPUT, ProviderStatus.TIMEOUT, ProviderStatus.INCOMPATIBLE}
)
_FORBIDDEN_FIELDS = frozenset(
    {"final_gate_verdict", "apply_authorization", "replace_original_skill", "pipeline_state_transition"}
)


@runtime_checkable
class ProviderAdapter(Protocol):
    descriptor: ProviderDescriptor

    def invoke(self, capability: str, request: dict[str, object]) -> ProviderResult | dict[str, object]:
        """Invoke a capability using the host-specific mechanism owned by the adapter."""


def normalize_provider_result(
    result: ProviderResult | Mapping[str, object],
    *,
    capability: str | None = None,
    provider_id: str | None = None,
) -> ProviderResult:
    """Validate and normalize adapter output into the provider contract."""
    if isinstance(result, ProviderResult):
        payload = _jsonable(asdict(result))
    elif isinstance(result, Mapping):
        if _FORBIDDEN_FIELDS.intersection(result):
            raise ValueError("provider output contains forbidden authority fields")
        payload = dict(result)
    else:
        raise ValueError("provider output must be a ProviderResult or mapping")
    if capability is not None and payload.get("capability") != capability:
        raise ValueError("provider capability does not match requested capability")
    if provider_id is not None and payload.get("provider_id") != provider_id:
        raise ValueError("provider identity does not match descriptor")
    provider_available = bool(payload.pop("provider_available", False))
    provider_execution = ProviderExecution(
        payload.pop("provider_execution", ProviderExecution.NOT_STARTED)
    )
    evidence_valid = bool(payload.pop("evidence_valid", False))
    contract_payload = payload.pop("deliverable_contract", None)
    manifest_payload = payload.pop("capability_manifest", None)
    for field in ("findings", "candidate_changes", "evidence", "limitations"):
        if field in payload and isinstance(payload[field], list):
            payload[field] = tuple(payload[field])
    status = payload.get("provider_status")
    if isinstance(status, ProviderStatus):
        payload["provider_status"] = status.value
    try:
        schema_payload = dict(payload)
        schema_payload["deliverable_contract"] = contract_payload
        schema_payload["capability_manifest"] = manifest_payload
        for field in ("findings", "candidate_changes", "evidence", "limitations"):
            if isinstance(schema_payload.get(field), tuple):
                schema_payload[field] = list(schema_payload[field])
        validate_contract("provider-result", schema_payload)
    except Exception as exc:
        raise ValueError(f"invalid provider result: {exc}") from exc
    contract = None
    if contract_payload is not None:
        if not isinstance(contract_payload, Mapping):
            raise ValueError("deliverable_contract must be an object")
        contract = deliverable_contract_from_data(contract_payload)
    manifest = None
    if manifest_payload is not None:
        if not isinstance(manifest_payload, Mapping):
            raise ValueError("capability_manifest must be an object")
        manifest = capability_manifest_from_data(manifest_payload)
    return ProviderResult(
        provider_id=str(payload["provider_id"]),
        capability=str(payload["capability"]),
        provider_status=ProviderStatus(payload["provider_status"]),
        findings=tuple(payload["findings"]),
        candidate_changes=tuple(payload["candidate_changes"]),
        evidence=tuple(payload["evidence"]),
        limitations=tuple(payload["limitations"]),
        fallback_used=bool(payload["fallback_used"]),
        provider_available=provider_available,
        provider_execution=provider_execution,
        evidence_valid=evidence_valid,
        deliverable_contract=contract,
        capability_manifest=manifest,
    )


def deliverable_contract_from_data(payload: Mapping[str, object]) -> DeliverableContract:
    """Validate and deserialize the Provider-owned deliverable contract."""
    raw = dict(payload)
    validate_contract("deliverable-contract", raw)
    deliverables = tuple(
        DeliverableEvidence(
            item["deliverable_id"], item["declared_status"], tuple(item["declarations"]),
            DeliverableEvidenceStatus(item["exposure_status"]), item["exposure_entrypoint"],
            item["exposure_selector"], tuple(item["exposure_evidence"]),
            DeliverableEvidenceStatus(item["implementation_status"]),
            item["implementation_dispatch_route"], item["implementation_artifact_pattern"],
            tuple(item["implementation_evidence"]),
            DeliverableEvidenceStatus(item["behavioral_status"]),
            tuple(item["behavioral_commands"]), tuple(item["expected_artifacts"]),
            tuple(item["behavioral_evidence"]),
        )
        for item in raw["deliverables"]
    )
    return DeliverableContract(
        raw["schema_version"], raw["inspection_id"], raw["target_digest"],
        raw["inspection_nonce"], raw["provider_identity"], deliverables,
        tuple(
            DeliverableScopeConflict(
                summary=item["summary"],
                blocking=item["blocking"],
                evidence_refs=tuple(item["evidence_refs"]),
            )
            for item in raw["scope_conflicts"]
        ),
        raw["applicability_status"],
        raw["applicability_reason"], tuple(raw["applicability_evidence"]),
        raw["evidence_origin"],
    )


def normalize_findings(result: ProviderResult | Mapping[str, object]) -> tuple[str, ...]:
    """Return canonical findings independent of provider identity."""
    normalized = normalize_provider_result(result)
    return tuple(sorted(item.strip() for item in normalized.findings))


def provider_result_to_check_result(
    result: ProviderResult | Mapping[str, object],
    *,
    subject: str,
) -> CheckResult:
    """Adapt normalized Provider evidence into an optional Gate check."""
    normalized = normalize_provider_result(result)
    evidence = list(normalized.evidence)
    evidence.extend(f"finding: {finding}" for finding in normalized.findings)
    evidence.extend(f"limitation: {limitation}" for limitation in normalized.limitations)
    if normalized.fallback_used:
        evidence.append(f"fallback used: {normalized.provider_id}")
    if not evidence:
        evidence.append("provider returned no evidence")
    if normalized.provider_status in _FAILURE_STATUSES:
        status = CheckStatus.NOT_EXECUTED
    elif normalized.provider_status is ProviderStatus.DEGRADED or normalized.findings or normalized.limitations:
        status = CheckStatus.WARN
    else:
        status = CheckStatus.PASS
    return CheckResult(
        check_id=f"provider.{normalized.capability.lower()}",
        source=f"provider:{normalized.provider_id}",
        subject=subject,
        required=False,
        status=status,
        deterministic=False,
        reproducible=False,
        confidence=1.0,
        evidence=tuple(evidence),
        remediation_stage=LifecycleState.VALIDATED,
        artifact_reference=subject,
    )


class ProviderGateway:
    """Select, invoke, and normalize replaceable providers for a capability."""

    def __init__(
        self,
        adapters: Iterable[ProviderAdapter] | None = None,
        fallbacks: Mapping[str, ProviderAdapter | None] | None = None,
    ) -> None:
        self._adapters: list[ProviderAdapter] = []
        self._fallbacks: dict[str, ProviderAdapter | None] = dict.fromkeys(CAPABILITIES)
        if fallbacks is not None:
            self._fallbacks.update(fallbacks)
        for adapter in adapters or ():
            self.register(adapter)

    def register(self, adapter: ProviderAdapter) -> None:
        descriptor = getattr(adapter, "descriptor", None)
        if not isinstance(descriptor, ProviderDescriptor):
            raise TypeError("adapter must expose a ProviderDescriptor")
        if not isinstance(descriptor.capability, str) or not descriptor.capability.strip():
            raise ValueError("provider capability must be nonblank")
        self._adapters.append(adapter)

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset(
            (*CAPABILITIES, *(item.descriptor.capability for item in self._adapters),
             *self._fallbacks.keys())
        )

    def descriptor_for(
        self,
        capability: str,
        provider_id: str | None = None,
    ) -> ProviderDescriptor | None:
        return next(
            (
                item.descriptor
                for item in self._adapters
                if item.descriptor.capability == capability
                and (provider_id is None or item.descriptor.provider_id == provider_id)
                and item.descriptor.availability is not ProviderStatus.UNAVAILABLE
            ),
            None,
        )

    def invoke(self, capability: str, request: dict[str, object], formal_run: bool = False) -> ProviderResult:
        if not isinstance(capability, str) or not capability.strip():
            raise ValueError("provider capability must be nonblank")
        if not isinstance(request, dict):
            raise TypeError("provider request must be a dict")
        attempted: list[str] = []
        provider_available = False
        invocation_started = False
        for adapter in self._adapters:
            descriptor = adapter.descriptor
            if descriptor.capability != capability:
                continue
            if descriptor.availability is ProviderStatus.UNAVAILABLE:
                detail = "; ".join(descriptor.limitations)
                attempted.append(
                    f"{descriptor.provider_id}: unavailable"
                    + (f" ({detail})" if detail else "")
                )
                continue
            provider_available = True
            unpinned = not _is_pinned_descriptor(descriptor)
            degraded = descriptor.availability is ProviderStatus.DEGRADED
            if formal_run and (unpinned or degraded):
                attempted.append(f"{descriptor.provider_id}: unpinned/degraded")
                continue
            try:
                invocation_started = True
                normalized = normalize_provider_result(
                    adapter.invoke(capability, request),
                    capability=capability,
                    provider_id=descriptor.provider_id,
                )
            except TimeoutError as exc:
                attempted.append(f"{descriptor.provider_id}: timeout ({exc})")
                continue
            except Exception as exc:
                attempted.append(f"{descriptor.provider_id}: invalid output ({exc})")
                continue
            if normalized.provider_status in _FAILURE_STATUSES:
                attempted.append(f"{descriptor.provider_id}: {normalized.provider_status.value.lower()}")
                continue
            if formal_run and normalized.provider_status is ProviderStatus.DEGRADED:
                attempted.append(f"{descriptor.provider_id}: degraded result")
                continue
            successful = normalized.provider_status not in _FAILURE_STATUSES
            return ProviderResult(
                normalized.provider_id, normalized.capability,
                normalized.provider_status, normalized.findings,
                normalized.candidate_changes, normalized.evidence,
                normalized.limitations, normalized.fallback_used,
                True,
                ProviderExecution.EXECUTED if successful else ProviderExecution.FAILED,
                True,
                normalized.deliverable_contract,
                normalized.capability_manifest,
            )
        fallback = self._fallbacks.get(capability)
        if fallback is None:
            limitations = tuple(attempted) + (
                "no Provider fallback configured; Required Capability resolution remains external",
            )
            return ProviderResult(
                provider_id=f"optional.none.{capability.lower()}",
                capability=capability,
                provider_status=ProviderStatus.UNAVAILABLE,
                findings=(),
                candidate_changes=(),
                evidence=(),
                limitations=limitations,
                fallback_used=False,
                provider_available=provider_available,
                provider_execution=(
                    ProviderExecution.FAILED if invocation_started
                    else ProviderExecution.NOT_STARTED
                ),
                evidence_valid=False,
                deliverable_contract=None,
                capability_manifest=None,
            )
        try:
            fallback_result = fallback.invoke(capability, request)
            result = normalize_provider_result(fallback_result, capability=capability)
        except Exception as exc:
            fallback_id = getattr(getattr(fallback, "descriptor", None), "provider_id", "configured")
            limitations = tuple(attempted) + (f"fallback {fallback_id} failed: {exc}",)
            return ProviderResult(
                provider_id=f"optional.none.{capability.lower()}",
                capability=capability,
                provider_status=ProviderStatus.UNAVAILABLE,
                findings=(),
                candidate_changes=(),
                evidence=(),
                limitations=limitations,
                fallback_used=False,
                provider_available=True,
                provider_execution=ProviderExecution.FAILED,
                evidence_valid=False,
                deliverable_contract=None,
                capability_manifest=None,
            )
        limitations = result.limitations
        if attempted:
            limitations = limitations + ("; ".join(attempted),)
        return ProviderResult(
            result.provider_id,
            result.capability,
            result.provider_status,
            result.findings,
            result.candidate_changes,
            result.evidence,
            limitations,
            True,
            True,
            (ProviderExecution.EXECUTED
             if result.provider_status not in _FAILURE_STATUSES
             else ProviderExecution.FAILED),
            True,
            result.deliverable_contract,
            result.capability_manifest,
        )


__all__ = [
    "AUDIT_SKILL",
    "CAPABILITY_CONTRACT",
    "CAPABILITIES",
    "CHECK_SKILL_CONFORMANCE",
    "CREATE_CANDIDATE",
    "GOVERN_AGENT_INSTRUCTIONS",
    "ProviderAdapter",
    "ProviderGateway",
    "normalize_provider_result",
    "deliverable_contract_from_data",
    "normalize_findings",
    "provider_result_to_check_result",
]


def _jsonable(value: object) -> object:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


def _is_pinned_descriptor(descriptor: ProviderDescriptor) -> bool:
    source_identity = descriptor.source_identity
    revision_or_version = descriptor.revision_or_version
    return (
        isinstance(source_identity, str)
        and bool(source_identity.strip())
        and isinstance(revision_or_version, str)
        and bool(revision_or_version.strip())
    )
