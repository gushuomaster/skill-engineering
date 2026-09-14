"""Invocation-neutral provider ports, normalization, and internal fallbacks."""
from __future__ import annotations

from dataclasses import asdict
from typing import Iterable, Mapping, Protocol, runtime_checkable

from engine.contracts import validate_contract
from engine.models import (
    CheckResult,
    CheckStatus,
    LifecycleState,
    ProviderDescriptor,
    ProviderResult,
    ProviderStatus,
)

CREATE_CANDIDATE = "CREATE_CANDIDATE"
AUDIT_SKILL = "AUDIT_SKILL"
GOVERN_AGENT_INSTRUCTIONS = "GOVERN_AGENT_INSTRUCTIONS"
CHECK_SKILL_CONFORMANCE = "CHECK_SKILL_CONFORMANCE"
CAPABILITIES = frozenset(
    {CREATE_CANDIDATE, AUDIT_SKILL, GOVERN_AGENT_INSTRUCTIONS, CHECK_SKILL_CONFORMANCE}
)

_FAILURE_STATUSES = frozenset(
    {ProviderStatus.UNAVAILABLE, ProviderStatus.INVALID_OUTPUT, ProviderStatus.TIMEOUT, ProviderStatus.INCOMPATIBLE}
)
_FORBIDDEN_FIELDS = frozenset(
    {"final_gate_verdict", "publish_authorization", "replace_original_skill", "pipeline_state_transition"}
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
        payload = asdict(result)
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
    for field in ("findings", "candidate_changes", "evidence", "limitations"):
        if field in payload and isinstance(payload[field], list):
            payload[field] = tuple(payload[field])
    status = payload.get("provider_status")
    if isinstance(status, ProviderStatus):
        payload["provider_status"] = status.value
    try:
        schema_payload = dict(payload)
        for field in ("findings", "candidate_changes", "evidence", "limitations"):
            if isinstance(schema_payload.get(field), tuple):
                schema_payload[field] = list(schema_payload[field])
        validate_contract("provider-result", schema_payload)
    except Exception as exc:
        raise ValueError(f"invalid provider result: {exc}") from exc
    return ProviderResult(
        provider_id=str(payload["provider_id"]),
        capability=str(payload["capability"]),
        provider_status=ProviderStatus(payload["provider_status"]),
        findings=tuple(payload["findings"]),
        candidate_changes=tuple(payload["candidate_changes"]),
        evidence=tuple(payload["evidence"]),
        limitations=tuple(payload["limitations"]),
        fallback_used=bool(payload["fallback_used"]),
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
    status = CheckStatus.PASS
    if (
        normalized.provider_status is not ProviderStatus.AVAILABLE
        or normalized.findings
        or normalized.limitations
    ):
        status = CheckStatus.WARN
    return CheckResult(
        check_id=f"provider.{normalized.capability.lower()}",
        source=f"provider:{normalized.provider_id}",
        subject=subject,
        required=False,
        status=status,
        deterministic=True,
        reproducible=True,
        confidence=1.0,
        evidence=tuple(evidence),
        remediation_stage=LifecycleState.VALIDATED,
        artifact_reference=subject,
    )


class InternalFallbackProvider:
    """Minimal deterministic V1 implementation for one required capability."""

    def __init__(self, capability: str, provider_id: str) -> None:
        if capability not in CAPABILITIES:
            raise ValueError(f"unknown provider capability: {capability}")
        self.descriptor = ProviderDescriptor(
            provider_id,
            "skill-engineering/internal",
            "v1",
            capability,
            ProviderStatus.AVAILABLE,
            "internal",
            (),
            None,
        )

    def invoke(self, capability: str, request: dict[str, object]) -> ProviderResult:
        if capability != self.descriptor.capability:
            raise ValueError("fallback capability does not match request")
        subject = request.get("subject")
        subject_note = f" for {subject}" if isinstance(subject, str) and subject else ""
        if capability == CREATE_CANDIDATE:
            candidate_changes = ("minimal complete Skill candidate structure",)
            evidence = ("internal candidate creator v1",)
            findings: tuple[str, ...] = ()
        elif capability == AUDIT_SKILL:
            candidate_changes = ()
            findings = ()
            evidence = (f"internal structure and governance audit{subject_note}",)
        elif capability == GOVERN_AGENT_INSTRUCTIONS:
            candidate_changes = ()
            findings = ()
            evidence = ("AGENTS/CLAUDE scope and duplicate-source checks",)
        else:
            candidate_changes = ()
            findings = ()
            evidence = ("deterministic Skill structure conformance",)
        return ProviderResult(
            self.descriptor.provider_id,
            capability,
            ProviderStatus.AVAILABLE,
            findings,
            candidate_changes,
            evidence,
            (),
            True,
        )


def internal_fallbacks() -> dict[str, InternalFallbackProvider]:
    return {
        CREATE_CANDIDATE: InternalFallbackProvider(CREATE_CANDIDATE, "internal.create.v1"),
        AUDIT_SKILL: InternalFallbackProvider(AUDIT_SKILL, "internal.audit.v1"),
        GOVERN_AGENT_INSTRUCTIONS: InternalFallbackProvider(
            GOVERN_AGENT_INSTRUCTIONS, "internal.agents-governance.v1"
        ),
        CHECK_SKILL_CONFORMANCE: InternalFallbackProvider(
            CHECK_SKILL_CONFORMANCE, "internal.structure-validator.v1"
        ),
    }


class ProviderGateway:
    """Select, invoke, and normalize replaceable providers for a capability."""

    def __init__(
        self,
        adapters: Iterable[ProviderAdapter] | None = None,
        fallbacks: Mapping[str, ProviderAdapter | None] | None = None,
    ) -> None:
        self._adapters: list[ProviderAdapter] = []
        self._fallbacks: dict[str, ProviderAdapter | None] = (
            dict(internal_fallbacks()) if fallbacks is None else dict(fallbacks)
        )
        for adapter in adapters or ():
            self.register(adapter)

    def register(self, adapter: ProviderAdapter) -> None:
        descriptor = getattr(adapter, "descriptor", None)
        if not isinstance(descriptor, ProviderDescriptor):
            raise TypeError("adapter must expose a ProviderDescriptor")
        if descriptor.capability not in CAPABILITIES:
            raise ValueError(f"unknown provider capability: {descriptor.capability}")
        self._adapters.append(adapter)

    def invoke(self, capability: str, request: dict[str, object], formal_run: bool = False) -> ProviderResult:
        if capability not in CAPABILITIES:
            raise ValueError(f"unknown provider capability: {capability}")
        if not isinstance(request, dict):
            raise TypeError("provider request must be a dict")
        attempted: list[str] = []
        for adapter in self._adapters:
            descriptor = adapter.descriptor
            if descriptor.capability != capability:
                continue
            if descriptor.availability is ProviderStatus.UNAVAILABLE:
                attempted.append(f"{descriptor.provider_id}: unavailable")
                continue
            unpinned = not _is_pinned_descriptor(descriptor)
            degraded = descriptor.availability is ProviderStatus.DEGRADED
            if formal_run and (unpinned or degraded):
                attempted.append(f"{descriptor.provider_id}: unpinned/degraded")
                continue
            try:
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
            return normalized
        fallback = self._fallbacks.get(capability)
        if fallback is None:
            limitations = tuple(attempted) + ("no fallback configured; optional capability",)
            return ProviderResult(
                provider_id=f"optional.none.{capability.lower()}",
                capability=capability,
                provider_status=ProviderStatus.UNAVAILABLE,
                findings=(),
                candidate_changes=(),
                evidence=(),
                limitations=limitations,
                fallback_used=False,
            )
        result = normalize_provider_result(fallback.invoke(capability, request), capability=capability)
        if attempted or not result.fallback_used:
            limitations = result.limitations
            if attempted:
                limitations = limitations + ("; ".join(attempted),)
            result = ProviderResult(
                result.provider_id,
                result.capability,
                result.provider_status,
                result.findings,
                result.candidate_changes,
                result.evidence,
                limitations,
                True,
            )
        return result


__all__ = [
    "AUDIT_SKILL",
    "CAPABILITIES",
    "CHECK_SKILL_CONFORMANCE",
    "CREATE_CANDIDATE",
    "GOVERN_AGENT_INSTRUCTIONS",
    "InternalFallbackProvider",
    "ProviderAdapter",
    "ProviderGateway",
    "internal_fallbacks",
    "normalize_provider_result",
    "normalize_findings",
    "provider_result_to_check_result",
]


def _is_pinned_descriptor(descriptor: ProviderDescriptor) -> bool:
    source_identity = descriptor.source_identity
    revision_or_version = descriptor.revision_or_version
    return (
        isinstance(source_identity, str)
        and bool(source_identity.strip())
        and isinstance(revision_or_version, str)
        and bool(revision_or_version.strip())
    )
