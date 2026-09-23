"""JSON-safe serialization for phased workflow bundles."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from engine.models import (
    ArtifactAssessment, ArtifactManifest, AuditExecution, AuthorizationStatus,
    CapabilityAssessment, CapabilityChange, CapabilityChangeDecision,
    CapabilityChangeKind, CapabilityDecisionKind, CapabilityDiff,
    CapabilityPreservationStatus, CapabilityStatus, CheckResult, CheckStatus,
    CoverageStatus,
    ControlGap, DecisionRecord, DirectorySnapshot, GateOutcome, GateResult,
    FallbackEquivalence, GateVerdict, Intent, LifecycleState,
    ManagedCompletionReceipt, PrimaryIssueClass,
    ProviderEvidence, ProviderExecution,
    DeliverableContract, DeliverableContractApplicability,
    DeliverableContractProvenance, DeliverableEvidence, DeliverableEvidenceStatus,
    RegressionDisposition, SemanticConfirmation, TreeEntry,
    StandardDependencyAssessment, StandardDependencyStatus,
)
from engine.contracts import validate_contract
from engine.orchestrator import (
    EngineeringOutcome, InspectionBundle, ValidationBundle,
)
from engine.rule_bloat import RuleFinding
from engine.rule_governance import GovernanceAction, GovernanceDecision
from engine.workspace import SemanticWorkspaceDiff, WorkspaceDiff
from engine.capability_manifest import capability_manifest_from_data
from engine.applicability import AuditDimension
from engine.providers import deliverable_contract_from_data


def to_data(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, CapabilityChangeDecision):
        return {
            "baseline_capability_digest": value.baseline_capability_digest,
            "candidate_capability_digest": value.candidate_capability_digest,
            "capability_changes": [
                {"capability_id": capability_id, "decision": decision.value}
                for capability_id, decision in value.capability_changes
            ],
            "removed_capability_ids": list(value.removed_capability_ids),
            "narrowed_capability_ids": list(value.narrowed_capability_ids),
            "change_rationale": value.change_rationale,
            "user_authorization_required": value.user_authorization_required,
            "user_authorization_status": value.user_authorization_status.value,
            "authorization_evidence": list(value.authorization_evidence),
            "compatibility_impact": value.compatibility_impact,
            "migration_plan": value.migration_plan,
            "deprecation_plan": value.deprecation_plan,
        }
    if is_dataclass(value):
        return {
            key: to_data(getattr(value, key))
            for key in value.__dataclass_fields__
        }
    if isinstance(value, dict):
        return {str(key): to_data(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_data(item) for item in value]
    return value


def _tree(payload: dict[str, Any] | None) -> DirectorySnapshot | None:
    if payload is None:
        return None
    return DirectorySnapshot(
        payload["root"],
        tuple(TreeEntry(**entry) for entry in payload["entries"]),
        payload["content_digest"],
    )


def _manifest(payload: dict[str, Any] | None) -> ArtifactManifest | None:
    if payload is None:
        return None
    return ArtifactManifest(
        Intent(payload["intent"]), payload["artifact_root"], payload["skill_name"],
        payload["source_revision"], payload["source_digest"], tuple(payload["files"]),
        tuple(payload["executable_assets"]), tuple(payload["required_references"]),
        tuple(payload["test_inventory"]), payload["content_digest"],
    )


def _check(payload: dict[str, Any]) -> CheckResult:
    return CheckResult(
        payload["check_id"], payload["source"], payload["subject"],
        payload["required"], CheckStatus(payload["status"]), payload["deterministic"],
        payload["reproducible"], payload["confidence"], tuple(payload["evidence"]),
        LifecycleState(payload["remediation_stage"]), payload["artifact_reference"],
    )


def decision_from_data(payload: dict[str, Any]) -> DecisionRecord:
    raw_capability_decision = payload.get("capability_change_decision")
    capability_decision = None
    if isinstance(raw_capability_decision, dict):
        capability_decision = CapabilityChangeDecision(
            raw_capability_decision["baseline_capability_digest"],
            raw_capability_decision["candidate_capability_digest"],
            tuple(
                (item["capability_id"], CapabilityDecisionKind(item["decision"]))
                for item in raw_capability_decision["capability_changes"]
            ),
            tuple(raw_capability_decision["removed_capability_ids"]),
            tuple(raw_capability_decision["narrowed_capability_ids"]),
            raw_capability_decision["change_rationale"],
            raw_capability_decision["user_authorization_required"],
            AuthorizationStatus(raw_capability_decision["user_authorization_status"]),
            tuple(raw_capability_decision["authorization_evidence"]),
            raw_capability_decision["compatibility_impact"],
            raw_capability_decision["migration_plan"],
            raw_capability_decision["deprecation_plan"],
        )
    return DecisionRecord(
        Intent(payload["intent"]), PrimaryIssueClass(payload["primary_issue_class"]),
        tuple(ControlGap(item) for item in payload["control_gaps"]),
        RegressionDisposition(payload["regression_disposition"]), payload["root_cause"],
        tuple(payload["evidence_limitations"]), tuple(payload["selected_mechanisms"]),
        tuple(payload["rejected_mechanisms"]), payload["prompt_rule_justification"],
        payload.get("decided_by", "CODEX"), capability_decision,
    )


def governance_from_data(payload: list[dict[str, Any]]) -> tuple[GovernanceDecision, ...]:
    return tuple(
        GovernanceDecision(
            item["finding_id"], GovernanceAction(item["action"]), item["rationale"],
            tuple(item["evidence_refs"]), item.get("target_layer"),
            item.get("blocking", False), tuple(item.get("signals", ())),
            tuple(item.get("limitations", ())), item.get("decided_by", "CODEX"),
        )
        for item in payload
    )


def confirmation_from_data(payload: dict[str, Any]) -> SemanticConfirmation:
    return SemanticConfirmation(
        payload["artifact_digest"], payload["rationale"],
        payload.get("confirmed_by", "CODEX"),
    )


def completion_receipt_from_data(payload: dict[str, Any]) -> ManagedCompletionReceipt:
    validate_contract("managed-completion-receipt", payload)
    return ManagedCompletionReceipt(
        payload["inspection_id"],
        Intent(payload["operation_mode"]),
        payload["source_digest"],
        payload["candidate_digest"],
        payload["baseline_capability_digest"],
        payload["candidate_capability_digest"],
        payload["validation_bundle_digest"],
        payload["semantic_confirmation_digest"],
        CoverageStatus(payload["coverage_status"]),
        CapabilityPreservationStatus(payload["capability_preservation"]),
        GateVerdict(payload["gate_verdict"]),
        GateOutcome(payload["gate_outcome"]),
        payload["formal_completion"],
    )


def _capability(payload: dict[str, Any]) -> CapabilityAssessment:
    return CapabilityAssessment(
        payload["capability"], payload["required"],
        CapabilityStatus(payload["status"]), tuple(payload["preferred_providers"]),
        payload["selected_provider"], payload["fallback"],
        FallbackEquivalence(payload["fallback_equivalence"]), tuple(payload["evidence"]),
    )


def _deliverable_provenance(
    payload: dict[str, Any] | None,
    applicability: DeliverableContractApplicability,
) -> DeliverableContractProvenance:
    if payload is None:
        coverage = (
            CoverageStatus.FULL
            if applicability is DeliverableContractApplicability.NOT_REQUIRED
            else CoverageStatus.COMPATIBILITY
            if applicability is DeliverableContractApplicability.COMPATIBILITY
            else CoverageStatus.PARTIAL
        )
        reason = (
            "not_required"
            if applicability is DeliverableContractApplicability.NOT_REQUIRED
            else "legacy_compatibility"
            if applicability is DeliverableContractApplicability.COMPATIBILITY
            else "provider_unavailable"
        )
        return DeliverableContractProvenance(
            applicability, False, False, False, False, False,
            coverage, reason,
        )
    return DeliverableContractProvenance(
        DeliverableContractApplicability(payload["applicability"]),
        payload["provider_discovered"], payload["provider_selected"],
        payload["provider_executed"], payload["contract_present"],
        payload["contract_validated"], CoverageStatus(payload["coverage_status"]),
        payload["reason"], payload.get("provider_id"),
        ProviderExecution(payload.get("provider_execution", "NOT_STARTED")),
    )


def _provider_evidence(payload: dict[str, Any]) -> ProviderEvidence:
    return ProviderEvidence(
        payload["provider_id"], payload["capability"], payload["invocation_phase"],
        CheckStatus(payload["status"]), payload["summary"], payload["deterministic"],
        payload["reproducible"], tuple(payload.get("findings", ())),
        tuple(payload.get("evidence", ())), tuple(payload.get("limitations", ())),
        payload.get("provider_available", False),
        ProviderExecution(payload.get("provider_execution", "NOT_STARTED")),
        payload.get("fallback_used", False), payload.get("evidence_valid", False),
        deliverable_contract_from_data(payload["deliverable_contract"])
        if payload.get("deliverable_contract") is not None else None,
        capability_manifest_from_data(payload["capability_manifest"])
        if payload.get("capability_manifest") is not None else None,
    )


def _capability_diff(payload: dict[str, Any] | None) -> CapabilityDiff | None:
    if payload is None:
        return None
    return CapabilityDiff(
        payload["baseline_manifest_digest"],
        payload["candidate_manifest_digest"],
        _capability_changes(payload["changes"]),
    )


def _capability_changes(
    payload: list[dict[str, Any]],
) -> tuple[CapabilityChange, ...]:
    return tuple(
        CapabilityChange(
            item["capability_id"],
            CapabilityChangeKind(item["kind"]),
            tuple(item["changed_fields"]),
            tuple(item["baseline_values"]),
            tuple(item["candidate_values"]),
        )
        for item in payload
    )


def _semantic_workspace_diff(
    payload: dict[str, Any] | None,
) -> SemanticWorkspaceDiff | None:
    if payload is None:
        return None
    return SemanticWorkspaceDiff(
        WorkspaceDiff(**{
            key: tuple(value)
            for key, value in payload["file_changes"].items()
        }),
        tuple(payload["declaration_changes"]),
        tuple(payload["entrypoint_changes"]),
        tuple(payload["schema_changes"]),
        tuple(payload["template_changes"]),
        tuple(payload["test_coverage_changes"]),
        _capability_changes(payload["capability_changes"]),
    )


def inspection_from_data(payload: dict[str, Any]) -> InspectionBundle:
    validate_contract("inspection-bundle", payload)
    findings = tuple(
        RuleFinding(
            item["finding_id"], tuple(item["affected_rule_units"]),
            tuple(item["signals"]), item["confidence"], item["risk"],
            item["rationale"], tuple(item.get("evidence_refs", ())),
            tuple(item.get("limitations", ())),
        )
        for item in payload["findings"]
    )
    providers = tuple(_provider_evidence(item) for item in payload["provider_evidence"])
    dependencies = tuple(
        StandardDependencyAssessment(
            item["skill_name"], item["responsibility"], item["coverage_gap"],
            StandardDependencyStatus(item["status"]), item["installed_path"],
        )
        for item in payload.get("standard_dependencies", ())
    )
    applicability = DeliverableContractApplicability(
        payload.get("deliverable_contract_applicability", "COMPATIBILITY")
    )
    return InspectionBundle(
        payload["inspection_id"], Intent(payload["mode"]),
        Path(payload["source_path"]) if payload["source_path"] else None,
        _manifest(payload["baseline_manifest"]), _tree(payload["baseline_snapshot"]),
        payload["baseline_digest"], tuple(_check(item) for item in payload["signals"]),
        findings, tuple(payload["finding_ids"]), tuple(payload["provider_capabilities"]),
        providers, tuple(_capability(item) for item in payload["capability_preflight"]),
        dependencies,
        payload["created_at"], payload["tool_schema_version"],
        LifecycleState(payload.get("lifecycle_state", "INSPECTED")),
        payload.get("inspection_nonce", ""),
        tuple(payload.get("provenance", ())),
        applicability,
        _deliverable_provenance(
            payload.get("deliverable_contract_provenance"), applicability,
        ),
        capability_manifest_from_data(payload["baseline_capability_manifest"])
        if payload.get("baseline_capability_manifest") is not None else None,
        payload.get("baseline_capability_digest"),
        payload.get("capability_provider_id"),
        payload.get("capability_provider_revision"),
        tuple(AuditDimension(item) for item in payload.get("audit_dimensions", ())),
        payload.get("deliverable_not_required_rationale"),
    )


def validation_from_data(payload: dict[str, Any]) -> ValidationBundle:
    validate_contract("validation-bundle", payload)
    gate_payload = payload.get("gate_result")
    gate = _gate(gate_payload) if gate_payload else None
    deliverable_payload = payload.get("deliverable_contract_provenance")
    applicability = DeliverableContractApplicability(
        deliverable_payload.get("applicability", "COMPATIBILITY")
        if isinstance(deliverable_payload, dict) else "COMPATIBILITY"
    )
    return ValidationBundle(
        payload["validation_id"], payload["inspection_id"], Intent(payload["intent"]),
        Path(payload["source_path"]) if payload["source_path"] else None,
        _tree(payload["baseline_snapshot"]), payload["baseline_digest"],
        Path(payload["artifact_path"]),
        Path(payload["staging_path"]) if payload["staging_path"] else None,
        Path(payload["target_parent"]), _manifest(payload["artifact_manifest"]),
        payload["artifact_digest"], decision_from_data(payload["decision"]),
        governance_from_data(payload["governance_decisions"]),
        tuple(_check(item) for item in payload["deterministic_evidence"]),
        tuple(_check(item) for item in payload["advisory_evidence"]),
        tuple(_capability(item) for item in payload["capability_preflight"]),
        WorkspaceDiff(**{key: tuple(value) for key, value in payload["workspace_diff"].items()}),
        payload["checks_fingerprint"], payload["authorized_to_modify"],
        payload["apply_requested"],
        tuple(
            StandardDependencyAssessment(
                item["skill_name"], item["responsibility"], item["coverage_gap"],
                StandardDependencyStatus(item["status"]), item["installed_path"],
            )
            for item in payload.get("standard_dependencies", ())
        ),
        payload.get("limited_audit", False),
        Path(payload["project_policy"]) if payload.get("project_policy") else None,
        payload["pending_semantic_confirmation"], gate,
        AuditExecution(payload["audit_execution"]) if payload.get("audit_execution") else None,
        ArtifactAssessment(payload["artifact_assessment"])
        if payload.get("artifact_assessment") else None,
        LifecycleState(payload["lifecycle_state"]),
        CoverageStatus(payload.get("coverage_status", "COMPATIBILITY")),
        _deliverable_provenance(deliverable_payload, applicability),
        capability_manifest_from_data(payload["baseline_capability_manifest"])
        if payload.get("baseline_capability_manifest") is not None else None,
        payload.get("baseline_capability_digest"),
        capability_manifest_from_data(payload["candidate_capability_manifest"])
        if payload.get("candidate_capability_manifest") is not None else None,
        payload.get("candidate_capability_digest"),
        _capability_diff(payload.get("capability_diff")),
        _check(payload["capability_decision_check"])
        if payload.get("capability_decision_check") is not None else None,
        tuple(
            _provider_evidence(item)
            for item in payload.get("candidate_provider_evidence", ())
        ),
        CapabilityPreservationStatus(payload["capability_preservation"])
        if payload.get("capability_preservation") is not None else None,
        _semantic_workspace_diff(payload.get("semantic_workspace_diff")),
    )


def _gate(payload: dict[str, Any]) -> GateResult:
    return GateResult(
        GateVerdict(payload["verdict"]), GateOutcome(payload["outcome"]),
        tuple(payload["blocking_findings"]), tuple(payload["warnings"]),
        payload["required_checks_summary"], payload["evidence_summary"],
        payload["semantic_confirmed"], payload["apply_authorized"],
        payload["policy_version"],
        CoverageStatus(payload.get("coverage_status", "COMPATIBILITY")),
        CapabilityPreservationStatus(payload["capability_preservation"])
        if payload.get("capability_preservation") is not None else None,
    )


def outcome_to_data(outcome: EngineeringOutcome) -> dict[str, Any]:
    payload = to_data(outcome)
    payload["apply_ready"] = outcome.apply_session is not None
    payload["apply_session"] = None
    from engine.managed_completion import completion_receipt
    try:
        payload["completion_receipt"] = to_data(completion_receipt(outcome))
    except ValueError:
        payload["completion_receipt"] = None
    return payload
