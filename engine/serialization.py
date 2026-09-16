"""JSON-safe serialization for phased workflow bundles."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from engine.models import (
    ArtifactAssessment, ArtifactManifest, AuditExecution, CheckResult, CheckStatus,
    ControlGap, DecisionRecord, DirectorySnapshot, GateOutcome, GateResult,
    GateVerdict, Intent, LifecycleState, PrimaryIssueClass, ProviderEvidence,
    RegressionDisposition, SemanticConfirmation, TreeEntry,
)
from engine.contracts import validate_contract
from engine.orchestrator import (
    EngineeringOutcome, InspectionBundle, ValidationBundle,
)
from engine.rule_bloat import RuleFinding
from engine.rule_governance import GovernanceAction, GovernanceDecision
from engine.workspace import WorkspaceDiff


def to_data(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: to_data(item) for key, item in asdict(value).items()}
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
    return DecisionRecord(
        Intent(payload["intent"]), PrimaryIssueClass(payload["primary_issue_class"]),
        tuple(ControlGap(item) for item in payload["control_gaps"]),
        RegressionDisposition(payload["regression_disposition"]), payload["root_cause"],
        tuple(payload["evidence_limitations"]), tuple(payload["selected_mechanisms"]),
        tuple(payload["rejected_mechanisms"]), payload["prompt_rule_justification"],
        payload.get("decided_by", "CODEX"),
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
    providers = tuple(
        ProviderEvidence(
            item["provider_id"], item["capability"], item["invocation_phase"],
            CheckStatus(item["status"]), item["summary"], item["deterministic"],
            item["reproducible"],
        )
        for item in payload["provider_evidence"]
    )
    return InspectionBundle(
        payload["inspection_id"], Intent(payload["mode"]),
        Path(payload["source_path"]) if payload["source_path"] else None,
        _manifest(payload["baseline_manifest"]), _tree(payload["baseline_snapshot"]),
        payload["baseline_digest"], tuple(_check(item) for item in payload["signals"]),
        findings, tuple(payload["finding_ids"]), tuple(payload["provider_capabilities"]),
        providers, payload["created_at"], payload["tool_schema_version"],
        LifecycleState(payload.get("lifecycle_state", "INSPECTED")),
    )


def validation_from_data(payload: dict[str, Any]) -> ValidationBundle:
    validate_contract("validation-bundle", payload)
    gate_payload = payload.get("gate_result")
    gate = _gate(gate_payload) if gate_payload else None
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
        WorkspaceDiff(**{key: tuple(value) for key, value in payload["workspace_diff"].items()}),
        payload["checks_fingerprint"], payload["authorized_to_modify"],
        payload["publish_requested"],
        Path(payload["project_policy"]) if payload.get("project_policy") else None,
        payload["pending_semantic_confirmation"], gate,
        AuditExecution(payload["audit_execution"]) if payload.get("audit_execution") else None,
        ArtifactAssessment(payload["artifact_assessment"])
        if payload.get("artifact_assessment") else None,
        LifecycleState(payload["lifecycle_state"]),
    )


def _gate(payload: dict[str, Any]) -> GateResult:
    return GateResult(
        GateVerdict(payload["verdict"]), GateOutcome(payload["outcome"]),
        tuple(payload["blocking_findings"]), tuple(payload["warnings"]),
        payload["required_checks_summary"], payload["evidence_summary"],
        payload["semantic_confirmed"], payload["publish_authorized"],
        payload["policy_version"],
    )


def outcome_to_data(outcome: EngineeringOutcome) -> dict[str, Any]:
    payload = to_data(outcome)
    payload["publication_ready"] = outcome.publication_session is not None
    payload["publication_session"] = None
    return payload
