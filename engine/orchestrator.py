"""Phased deterministic support for Codex-led Skill engineering."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Mapping
from uuid import uuid4

from engine.contracts import validate_contract
from engine.diagnostics import validate_classification
from engine.evidence import EvidenceCollector
from engine.inventory import build_artifact_manifest, digest_tree, snapshot_tree
from engine.mechanism_selection import validate_mechanism_selection
from engine.models import (
    ArtifactAssessment, ArtifactManifest, ArtifactRole, AuditExecution,
    CapabilityAssessment, CapabilityDiff, CapabilityManifest,
    CapabilityPreservationStatus, CapabilityStatus, CheckResult, CheckStatus,
    CoverageStatus,
    DecisionRecord, DirectorySnapshot, GateOutcome, GateResult, GateVerdict, Intent,
    DeliverableContractApplicability, DeliverableContractProvenance,
    FallbackEquivalence, LifecycleState, PrimaryIssueClass, ProviderEvidence,
    ProviderExecution, ProviderResult, ProviderStatus,
    ManagedCompletionReceipt, RegressionDisposition, SemanticConfirmation,
    StandardDependencyAssessment,
    StandardDependencyStatus, StandardSkillRequirement,
)
from engine.providers import CAPABILITIES, CAPABILITY_CONTRACT, ProviderGateway
from engine.capability_diff import compare_capability_manifests
from engine.capability_decisions import (
    capability_preservation_status,
    validate_capability_change_decision,
)
from engine.capability_manifest import (
    capability_manifest_digest,
    validate_capability_manifest,
)
from engine.applicability import AuditDimension, resolve_deliverable_applicability
from engine.capabilities import (
    build_capability_preflight, capability_execution_gap_evidence,
    capability_preflight_evidence, provider_capability_evidence,
)
from engine.quality_gate import GateContext, adjudicate, load_gate_policy
from engine.rule_bloat import RuleFinding, detect_rule_bloat, extract_rule_units
from engine.rule_governance import (
    GovernanceDecision, governance_evidence, signal_evidence,
    validate_governance_decisions,
)
from engine.workspace import (
    ApplyResult, SemanticWorkspaceDiff, WorkspaceDiff, WorkspaceSession,
    apply_atomic, build_semantic_workspace_diff,
)
from engine.toolchain import (
    MissingStandardDependencyError, assess_standard_dependencies, dependency_evidence,
)
from validators.reference_integrity import validate_references
from validators.skill_structure import validate_skill_structure
from validators.capability_fallbacks import execute_internal_capability_fallbacks
from engine.deliverable_contract import validate_deliverable_contract


TOOL_SCHEMA_VERSION = "4.2"


@dataclass(frozen=True)
class EngineeringRequest:
    """Compatibility request; run() executes all formal phases in order."""
    requirement: str
    intent: Intent
    decision: DecisionRecord
    source: Path | None
    candidate: Path | None
    failure_evidence: tuple[str, ...]
    authorized_to_modify: bool
    target_parent: Path
    semantic_confirmation: SemanticConfirmation | None = None
    governance_decisions: tuple[GovernanceDecision, ...] = ()
    project_policy: Path | None = None
    regression_runner: Callable[[Path], CheckResult] | None = None
    behavioral_runner: Callable[[Path], CheckResult] | None = None
    contract_runner: Callable[[Path], CheckResult] | None = None
    apply_requested: bool = False
    required_standard_skills: tuple[StandardSkillRequirement, ...] = ()
    continue_limited: bool = False
    deliverable_contract_applicability: DeliverableContractApplicability = DeliverableContractApplicability.COMPATIBILITY


@dataclass(frozen=True)
class InspectionBundle:
    inspection_id: str
    mode: Intent
    source_path: Path | None
    baseline_manifest: ArtifactManifest | None
    baseline_snapshot: DirectorySnapshot | None
    baseline_digest: str | None
    signals: tuple[CheckResult, ...]
    findings: tuple[RuleFinding, ...]
    finding_ids: tuple[str, ...]
    provider_capabilities: tuple[str, ...]
    provider_evidence: tuple[ProviderEvidence, ...]
    capability_preflight: tuple[CapabilityAssessment, ...]
    standard_dependencies: tuple[StandardDependencyAssessment, ...]
    created_at: str
    tool_schema_version: str
    lifecycle_state: LifecycleState = LifecycleState.INSPECTED
    inspection_nonce: str = ""
    provenance: tuple[str, ...] = ()
    deliverable_contract_applicability: DeliverableContractApplicability = DeliverableContractApplicability.COMPATIBILITY
    deliverable_contract_provenance: DeliverableContractProvenance | None = None
    baseline_capability_manifest: CapabilityManifest | None = None
    baseline_capability_digest: str | None = None
    capability_provider_id: str | None = None
    capability_provider_revision: str | None = None
    audit_dimensions: tuple[AuditDimension, ...] = ()
    deliverable_not_required_rationale: str | None = None


@dataclass(frozen=True)
class ValidationBundle:
    validation_id: str
    inspection_id: str
    intent: Intent
    source_path: Path | None
    baseline_snapshot: DirectorySnapshot | None
    baseline_digest: str | None
    artifact_path: Path
    staging_path: Path | None
    target_parent: Path
    artifact_manifest: ArtifactManifest
    artifact_digest: str
    decision: DecisionRecord
    governance_decisions: tuple[GovernanceDecision, ...]
    deterministic_evidence: tuple[CheckResult, ...]
    advisory_evidence: tuple[CheckResult, ...]
    capability_preflight: tuple[CapabilityAssessment, ...]
    workspace_diff: WorkspaceDiff
    checks_fingerprint: str
    authorized_to_modify: bool
    apply_requested: bool
    standard_dependencies: tuple[StandardDependencyAssessment, ...]
    limited_audit: bool
    project_policy: Path | None
    pending_semantic_confirmation: bool = True
    gate_result: GateResult | None = None
    audit_execution: AuditExecution | None = None
    artifact_assessment: ArtifactAssessment | None = None
    lifecycle_state: LifecycleState = LifecycleState.VALIDATED_PENDING_CONFIRMATION
    coverage_status: CoverageStatus = CoverageStatus.COMPATIBILITY
    deliverable_contract_provenance: DeliverableContractProvenance | None = None
    baseline_capability_manifest: CapabilityManifest | None = None
    baseline_capability_digest: str | None = None
    candidate_capability_manifest: CapabilityManifest | None = None
    candidate_capability_digest: str | None = None
    capability_diff: CapabilityDiff | None = None
    capability_decision_check: CheckResult | None = None
    candidate_provider_evidence: tuple[ProviderEvidence, ...] = ()
    capability_preservation: CapabilityPreservationStatus | None = None
    semantic_workspace_diff: SemanticWorkspaceDiff | None = None


@dataclass(frozen=True)
class EngineeringOutcome:
    outcome_type: str
    artifact_path: Path
    gate_result: GateResult
    minimal_blocking_findings: tuple[dict[str, str], ...]
    workspace_diff: WorkspaceDiff
    apply_session: WorkspaceSession | None
    evidence: tuple[CheckResult, ...] = ()
    deterministic_evidence: tuple[CheckResult, ...] = ()
    advisory_evidence: tuple[CheckResult, ...] = ()
    audit_execution: AuditExecution | None = None
    artifact_assessment: ArtifactAssessment | None = None
    lifecycle_state: LifecycleState = LifecycleState.VALIDATED
    validation: ValidationBundle | None = None
    semantic_confirmation: SemanticConfirmation | None = None


class PipelineBlockedError(RuntimeError):
    def __init__(self, gate_result: GateResult, artifact_path: Path | None = None,
                 workspace_diff: WorkspaceDiff | None = None,
                 evidence: tuple[CheckResult, ...] = ()) -> None:
        super().__init__("Skill engineering pipeline blocked by the Quality Gate")
        self.gate_result = gate_result
        self.artifact_path = artifact_path
        self.workspace_diff = workspace_diff
        self.evidence = evidence


class PipelineOrchestrator:
    """Expose inspect, validate, and confirm as separate engine phases."""
    def __init__(self, state_observer: Callable[[LifecycleState], None] | None = None,
                 provider_gateway: ProviderGateway | None = None,
                 internal_fallbacks: frozenset[str] | None = None,
                 fallback_equivalences: Mapping[str, FallbackEquivalence] | None = None,
                 required_standard_skills: tuple[StandardSkillRequirement, ...] = (),
                 skill_roots: tuple[Path, ...] | None = None) -> None:
        self.state_history: list[LifecycleState] = []
        self._state_observer = state_observer
        self._provider_gateway = provider_gateway
        self._internal_fallbacks = internal_fallbacks
        self._fallback_equivalences = fallback_equivalences
        self._required_standard_skills = required_standard_skills
        self._skill_roots = skill_roots

    def _record(self, state: LifecycleState) -> None:
        self.state_history.append(state)
        if self._state_observer is not None:
            self._state_observer(state)

    def inspect(
        self, mode: Intent, source: Path | None, *,
        required_standard_skills: tuple[StandardSkillRequirement, ...] | None = None,
        deliverable_contract_applicability: DeliverableContractApplicability = DeliverableContractApplicability.COMPATIBILITY,
        audit_dimensions: tuple[AuditDimension, ...] | None = None,
        deliverable_not_required_rationale: str | None = None,
    ) -> InspectionBundle:
        if not isinstance(mode, Intent):
            raise ValueError("mode must be explicitly supplied")
        if not isinstance(deliverable_contract_applicability, DeliverableContractApplicability):
            raise ValueError("deliverable contract applicability must be explicitly typed")
        if mode is Intent.CREATE:
            if source is not None:
                raise ValueError("Create inspection does not accept a source Skill")
            manifest = None
            snapshot = None
            baseline_digest = None
            findings: tuple[RuleFinding, ...] = ()
            signals: tuple[CheckResult, ...] = ()
        else:
            if source is None:
                raise ValueError(f"{mode.value} inspection requires a source Skill")
            source = source.resolve(strict=True)
            snapshot = snapshot_tree(source)
            manifest = build_artifact_manifest(source, mode, None)
            baseline_digest = manifest.content_digest
            findings = detect_rule_bloat(extract_rule_units(source), history=None)
            signals = signal_evidence(findings)
        self.state_history.clear()
        self._record(LifecycleState.DISCOVERED)
        self._record(LifecycleState.INSPECTED)
        inspection_id = str(uuid4())
        inspection_nonce = uuid4().hex
        capability_providers = (
            ()
            if mode is Intent.CREATE
            else _inspect_provider_evidence(
                self._provider_gateway,
                source.name if source is not None else "new-skill",
                source,
                mode,
                inspection_id=inspection_id,
                inspection_nonce=inspection_nonce,
                target_digest=baseline_digest,
                deliverable_contract_applicability=deliverable_contract_applicability,
                capabilities=(CAPABILITY_CONTRACT,),
            )
        )
        baseline_capability_manifest = None
        baseline_capability_digest = None
        capability_provider_id = None
        capability_provider_revision = None
        capability_record = next(
            (
                item for item in capability_providers
                if item.capability == CAPABILITY_CONTRACT
                and item.capability_manifest is not None
            ),
            None,
        )
        if capability_record is not None and manifest is not None:
            capability_check = validate_capability_manifest(
                capability_record.capability_manifest,
                manifest,
                inspection_id=inspection_id,
                inspection_nonce=inspection_nonce,
                provider_id=capability_record.provider_id,
                provider_execution=capability_record.provider_execution,
                expected_role=ArtifactRole.BASELINE,
            )
            signals = signals + (capability_check,)
            if capability_check.status is CheckStatus.PASS:
                baseline_capability_manifest = capability_record.capability_manifest
                baseline_capability_digest = capability_manifest_digest(
                    baseline_capability_manifest
                )
                capability_provider_id = capability_record.provider_id
        if mode is Intent.CREATE and self._provider_gateway is not None:
            descriptor = self._provider_gateway.descriptor_for(CAPABILITY_CONTRACT)
            if descriptor is not None:
                capability_provider_id = descriptor.provider_id
                capability_provider_revision = descriptor.revision_or_version
        elif capability_provider_id is not None and self._provider_gateway is not None:
            descriptor = self._provider_gateway.descriptor_for(
                CAPABILITY_CONTRACT, capability_provider_id,
            )
            if descriptor is not None:
                capability_provider_revision = descriptor.revision_or_version
        if audit_dimensions is not None:
            public_status = (
                baseline_capability_manifest.public_output_contract_status
                if baseline_capability_manifest is not None else "unknown"
            )
            applicability_decision = resolve_deliverable_applicability(
                mode, audit_dimensions, public_status,
            )
            deliverable_contract_applicability = applicability_decision.applicability
            if (
                deliverable_contract_applicability
                is DeliverableContractApplicability.NOT_REQUIRED
                and deliverable_not_required_rationale is not None
                and not deliverable_not_required_rationale.strip()
            ):
                raise ValueError("deliverable not-required rationale must be nonblank")
        remaining_capabilities = (
            tuple(
                sorted(self._provider_gateway.capabilities - {CAPABILITY_CONTRACT})
            )
            if self._provider_gateway is not None else ()
        )
        providers = capability_providers + _inspect_provider_evidence(
            self._provider_gateway,
            source.name if source is not None else "new-skill",
            source,
            mode,
            inspection_id=inspection_id,
            inspection_nonce=inspection_nonce,
            target_digest=baseline_digest,
            deliverable_contract_applicability=deliverable_contract_applicability,
            capabilities=remaining_capabilities,
        )
        preflight = build_capability_preflight(
            mode, source, providers, internal_fallbacks=self._internal_fallbacks,
            fallback_equivalences=self._fallback_equivalences,
            deliverable_contract_applicability=deliverable_contract_applicability,
        )
        provider_capabilities = (
            () if self._provider_gateway is None
            else self._provider_gateway.capabilities
        )
        dependencies = assess_standard_dependencies(
            self._required_standard_skills
            if required_standard_skills is None else required_standard_skills,
            roots=self._skill_roots,
        )
        deliverable_provenance = _deliverable_contract_provenance(
            deliverable_contract_applicability, providers,
        )
        return InspectionBundle(
            inspection_id, mode, source, manifest, snapshot, baseline_digest, signals,
            findings, tuple(item.finding_id for item in findings),
            tuple(sorted(provider_capabilities)), providers, preflight, dependencies,
            datetime.now(UTC).isoformat(),
            TOOL_SCHEMA_VERSION, inspection_nonce=inspection_nonce,
            provenance=(
                "engine=skill-engineering",
                f"tool_schema_version={TOOL_SCHEMA_VERSION}",
                f"inspection_id={inspection_id}",
                f"inspection_nonce={inspection_nonce}",
                f"target_digest={baseline_digest or 'none'}",
            ),
            deliverable_contract_applicability=deliverable_contract_applicability,
            deliverable_contract_provenance=deliverable_provenance,
            baseline_capability_manifest=baseline_capability_manifest,
            baseline_capability_digest=baseline_capability_digest,
            capability_provider_id=capability_provider_id,
            capability_provider_revision=capability_provider_revision,
            audit_dimensions=audit_dimensions or (),
            deliverable_not_required_rationale=deliverable_not_required_rationale,
        )

    def validate(self, inspection: InspectionBundle, decision: DecisionRecord,
                 governance_decisions: tuple[GovernanceDecision, ...], *,
                 candidate: Path | None, target_parent: Path,
                 authorized_to_modify: bool,
                 behavioral_runner: Callable[[Path], CheckResult] | None = None,
                 contract_runner: Callable[[Path], CheckResult] | None = None,
                 regression_runner: Callable[[Path], CheckResult] | None = None,
                 apply_requested: bool = False,
                 continue_limited: bool = False,
                 project_policy: Path | None = None) -> ValidationBundle:
        _validate_inspection(inspection)
        if inspection.capability_provider_id is not None:
            if self._provider_gateway is None:
                raise ValueError("selected capability Provider is unavailable")
            descriptor = self._provider_gateway.descriptor_for(
                CAPABILITY_CONTRACT, inspection.capability_provider_id,
            )
            if descriptor is None:
                raise ValueError("selected capability Provider is unavailable")
            if descriptor.revision_or_version != inspection.capability_provider_revision:
                raise ValueError("Capability Provider resource changed after inspection")
        _validate_decision(decision, inspection.mode)
        _verify_inspection_fresh(inspection)
        missing_dependencies = tuple(
            item for item in inspection.standard_dependencies
            if item.status is StandardDependencyStatus.MISSING
        )
        if missing_dependencies and not continue_limited:
            raise MissingStandardDependencyError(missing_dependencies)
        governed = validate_governance_decisions(inspection.findings, governance_decisions)
        actionable = {item.finding_id for item in inspection.findings if item.confidence > 0}
        decided = {item.finding_id for item in governed}
        if missing := sorted(actionable - decided):
            raise ValueError("missing governance decisions: " + ", ".join(missing))

        target_parent = target_parent.resolve(strict=True)
        session = _session_for_inspection(inspection)
        read_only_validation = inspection.mode is Intent.AUDIT_ONLY
        if read_only_validation:
            if candidate is not None:
                raise ValueError("Audit cannot accept a repair candidate")
            if inspection.source_path is None:
                raise ValueError("Audit Only requires a source")
            artifact = inspection.source_path
            execution_artifact = (
                session.prepare_audit_snapshot()
                if inspection.mode is Intent.AUDIT_ONLY
                else artifact
            )
        else:
            if candidate is None:
                raise ValueError("Codex must supply a complete candidate")
            if not authorized_to_modify:
                raise ValueError("candidate staging requires modification authorization")
            if inspection.source_path is not None and candidate.resolve() == inspection.source_path.resolve():
                raise ValueError("candidate must be separate from the source Skill")
            candidate_findings = detect_rule_bloat(extract_rule_units(candidate), history=None)
            uninspected = sorted(
                item.finding_id
                for item in candidate_findings
                if item.confidence > 0 and item.finding_id not in inspection.finding_ids
            )
            if uninspected:
                raise ValueError(
                    "candidate introduces uninspected actionable findings: "
                    + ", ".join(uninspected)
                )
            artifact = session.stage_candidate(candidate, target_parent)
            execution_artifact = artifact

        self._record(LifecycleState.CLASSIFIED)
        self._record(LifecycleState.MECHANISM_SELECTED)
        if inspection.mode is not Intent.AUDIT_ONLY:
            self._record(LifecycleState.STAGED)

        commands: list[CheckResult] = []
        framework_errors: list[CheckResult] = []
        source_checks: list[bool] = []
        try:
            if behavioral_runner is not None:
                try:
                    commands.append(behavioral_runner(execution_artifact))
                except Exception as exc:
                    framework_errors.append(_framework_failure(
                        execution_artifact.name, "behavioral runner", exc,
                    ))
                if inspection.mode is Intent.AUDIT_ONLY:
                    source_checks.append(session.verify_source_unchanged())
            elif inspection.mode is Intent.CREATE:
                commands.append(_missing_behavioral_check(execution_artifact.name))
            if decision.regression_disposition is RegressionDisposition.REQUIRED:
                if regression_runner is None:
                    commands.append(_missing_regression_check(execution_artifact.name))
                else:
                    try:
                        commands.append(regression_runner(execution_artifact))
                    except Exception as exc:
                        framework_errors.append(_framework_failure(
                            execution_artifact.name, "regression runner", exc,
                        ))
                    if inspection.mode is Intent.AUDIT_ONLY:
                        source_checks.append(session.verify_source_unchanged())
            if contract_runner is not None:
                try:
                    commands.append(contract_runner(execution_artifact))
                except Exception as exc:
                    framework_errors.append(_framework_failure(
                        execution_artifact.name, "contract runner", exc,
                    ))
                if inspection.mode is Intent.AUDIT_ONLY:
                    source_checks.append(session.verify_source_unchanged())
            if inspection.mode is Intent.AUDIT_ONLY:
                source_checks.append(session.verify_source_unchanged())

            manifest = build_artifact_manifest(artifact, inspection.mode, inspection.baseline_digest)
            candidate_provider_evidence: tuple[ProviderEvidence, ...] = ()
            candidate_capability_manifest = None
            candidate_capability_digest = None
            capability_diff = None
            capability_decision_check = None
            if (
                self._provider_gateway is not None
                and inspection.capability_provider_id is not None
            ):
                candidate_result = self._provider_gateway.invoke(
                    CAPABILITY_CONTRACT,
                    {
                        "subject": manifest.skill_name,
                        "target_path": str(execution_artifact),
                        "mode": inspection.mode.value,
                        "inspection_id": inspection.inspection_id,
                        "inspection_nonce": inspection.inspection_nonce,
                        "target_digest": manifest.content_digest,
                        "artifact_role": ArtifactRole.CANDIDATE.value,
                        "deliverable_contract_applicability": inspection.deliverable_contract_applicability.value,
                    },
                    formal_run=True,
                )
                candidate_record = _provider_record(candidate_result, "VALIDATE")
                candidate_provider_evidence = (candidate_record,)
                if candidate_record.provider_id != inspection.capability_provider_id:
                    capability_decision_check = _capability_provider_identity_failure(
                        manifest.skill_name,
                        inspection.capability_provider_id,
                        candidate_record.provider_id,
                    )
                elif candidate_record.capability_manifest is not None:
                    manifest_check = validate_capability_manifest(
                        candidate_record.capability_manifest,
                        manifest,
                        inspection_id=inspection.inspection_id,
                        inspection_nonce=inspection.inspection_nonce,
                        provider_id=candidate_record.provider_id,
                        provider_execution=candidate_record.provider_execution,
                        expected_role=ArtifactRole.CANDIDATE,
                    )
                    commands.append(manifest_check)
                    if manifest_check.status is CheckStatus.PASS:
                        candidate_capability_manifest = candidate_record.capability_manifest
                        candidate_capability_digest = capability_manifest_digest(
                            candidate_capability_manifest
                        )
                        capability_diff = compare_capability_manifests(
                            inspection.baseline_capability_manifest,
                            candidate_capability_manifest,
                        ) if inspection.baseline_capability_manifest is not None else None
                        capability_decision_check = (
                            validate_capability_change_decision(
                                capability_diff,
                                decision.capability_change_decision,
                            )
                            if capability_diff is not None else None
                        )
                else:
                    capability_decision_check = _missing_capability_manifest(
                        manifest.skill_name
                    )
            try:
                current_findings = detect_rule_bloat(extract_rule_units(artifact), history=None)
            except Exception as exc:
                current_findings = ()
                framework_errors.append(_framework_failure(
                    manifest.skill_name, "rule analysis", exc,
                ))
            try:
                structure = validate_skill_structure(manifest)
            except Exception as exc:
                structure = ()
                framework_errors.append(_framework_failure(
                    manifest.skill_name, "structure validation", exc,
                ))
            try:
                references = validate_references(manifest)
            except Exception as exc:
                references = ()
                framework_errors.append(_framework_failure(
                    manifest.skill_name, "reference validation", exc,
                ))
            preflight = build_capability_preflight(
                inspection.mode, artifact, inspection.provider_evidence,
                internal_fallbacks=self._internal_fallbacks,
                fallback_equivalences=self._fallback_equivalences,
                deliverable_contract_applicability=inspection.deliverable_contract_applicability,
            )
            try:
                capability_results = execute_internal_capability_fallbacks(
                    manifest, structure=structure, references=references,
                    findings=current_findings, governance_decisions=governed,
                    decision=decision, command_results=tuple(commands),
                )
            except Exception as exc:
                capability_results = ()
                framework_errors.append(_framework_failure(
                    manifest.skill_name, "capability fallback execution", exc,
                ))
            internal_capabilities = {
                item.capability for item in preflight
                if (
                    item.status is CapabilityStatus.FALLBACK
                    and item.selected_provider is None
                ) or item.selected_provider == "internal.core"
            }
            internal_results = tuple(
                item for item in capability_results
                if item.check_id.removeprefix("capability.") in internal_capabilities
            )
            provider_results = provider_capability_evidence(
                preflight, inspection.provider_evidence, manifest.skill_name,
            )
            executed_capabilities = internal_results + provider_results
            contract_checks: tuple[CheckResult, ...] = ()
            for provider in inspection.provider_evidence:
                contract = provider.deliverable_contract
                if contract is None:
                    continue
                contract_checks += (validate_deliverable_contract(
                    contract, manifest,
                    inspection_id=inspection.inspection_id,
                    inspection_nonce=inspection.inspection_nonce,
                    provider_id=provider.provider_id,
                    provider_execution=provider.provider_execution,
                    required=(
                        inspection.deliverable_contract_applicability
                        is DeliverableContractApplicability.REQUIRED
                    ),
                ),)
            executed_capabilities = executed_capabilities + contract_checks
            execution_gaps = capability_execution_gap_evidence(
                preflight, executed_capabilities, manifest.skill_name,
            )
            evidence = (
                structure + references + tuple(commands)
                + signal_evidence(current_findings) + governance_evidence(governed)
                + capability_preflight_evidence(preflight, manifest.skill_name)
                + executed_capabilities + execution_gaps
                + dependency_evidence(
                    inspection.standard_dependencies, manifest.skill_name,
                    continue_limited=continue_limited,
                )
                + tuple(framework_errors)
            )
            if capability_decision_check is not None:
                evidence += (capability_decision_check,)
            if decision.primary_issue_class is PrimaryIssueClass.INSUFFICIENT_EVIDENCE:
                evidence += (_diagnostic_failure(manifest.skill_name),)
            if inspection.mode is Intent.AUDIT_ONLY:
                evidence += (_source_integrity_evidence(session, source_checks),)
            collector = EvidenceCollector()
            for item in evidence:
                collector.add(item)
            deterministic = collector.snapshot()
            deliverable_check = next(
                (item for item in deterministic
                 if item.check_id == "capability.deliverable_contract"),
                None,
            )
            deliverable_provenance = _deliverable_contract_provenance(
                inspection.deliverable_contract_applicability,
                inspection.provider_evidence,
                deliverable_check,
            )
            coverage_status = deliverable_provenance.coverage_status
            advisory = tuple(
                _provider_evidence_to_check(item, manifest.skill_name)
                for item in (*inspection.provider_evidence, *candidate_provider_evidence)
            )
            diff = session.source_diff() if inspection.mode is Intent.AUDIT_ONLY else session.diff(artifact)
            preservation = capability_preservation_status(
                capability_diff, capability_decision_check,
            )
            if (
                inspection.mode is Intent.CREATE
                and candidate_capability_manifest is not None
            ):
                preservation = CapabilityPreservationStatus.CAPABILITY_PRESERVED
            semantic_diff = build_semantic_workspace_diff(diff, capability_diff)
            audit_execution = None
            assessment = None
            if inspection.mode is Intent.AUDIT_ONLY:
                audit_execution = (
                    AuditExecution.COMPLETE
                    if all(source_checks)
                    and all(item.status is CheckStatus.PASS for item in commands)
                    and not any(
                        item.required and item.status in {
                            CheckStatus.ERROR, CheckStatus.SKIP, CheckStatus.NOT_EXECUTED
                        }
                        for item in deterministic
                    )
                    else AuditExecution.INCOMPLETE
                )
                assessment = _artifact_assessment(audit_execution, deterministic, advisory)
        finally:
            if inspection.mode is Intent.AUDIT_ONLY:
                session.cleanup_audit_snapshot()

        self._record(LifecycleState.VALIDATED_PENDING_CONFIRMATION)
        return ValidationBundle(
            str(uuid4()), inspection.inspection_id, inspection.mode, inspection.source_path,
            inspection.baseline_snapshot, inspection.baseline_digest, artifact,
            session.staging, target_parent, manifest, manifest.content_digest, decision,
            governed, deterministic, advisory, preflight, diff,
            _checks_fingerprint(deterministic, advisory), authorized_to_modify,
            apply_requested, inspection.standard_dependencies, bool(missing_dependencies),
            project_policy, audit_execution=audit_execution,
            artifact_assessment=assessment,
            coverage_status=coverage_status,
            deliverable_contract_provenance=deliverable_provenance,
            baseline_capability_manifest=inspection.baseline_capability_manifest,
            baseline_capability_digest=inspection.baseline_capability_digest,
            candidate_capability_manifest=candidate_capability_manifest,
            candidate_capability_digest=candidate_capability_digest,
            capability_diff=capability_diff,
            capability_decision_check=capability_decision_check,
            candidate_provider_evidence=candidate_provider_evidence,
            capability_preservation=preservation,
            semantic_workspace_diff=semantic_diff,
        )

    def confirm(self, validation: ValidationBundle,
                confirmation: SemanticConfirmation) -> EngineeringOutcome:
        if validation.lifecycle_state is not LifecycleState.VALIDATED_PENDING_CONFIRMATION:
            raise ValueError("validation is not pending semantic confirmation")
        if _checks_fingerprint(validation.deterministic_evidence,
                               validation.advisory_evidence) != validation.checks_fingerprint:
            raise ValueError("validation checks changed after validation")
        source_unchanged = _source_matches_validation(validation)
        if not source_unchanged and validation.intent not in {Intent.CREATE, Intent.AUDIT_ONLY}:
            raise ValueError("source changed after validation")
        if digest_tree(validation.artifact_path) != validation.artifact_digest:
            if validation.intent is Intent.AUDIT_ONLY:
                source_unchanged = False
            else:
                raise ValueError("candidate changed after validation")
        semantic_confirmed = _semantic_confirmation_matches(confirmation, validation.artifact_digest)
        deterministic = validation.deterministic_evidence
        audit_execution = validation.audit_execution
        assessment = validation.artifact_assessment
        if validation.intent is Intent.AUDIT_ONLY:
            if not source_unchanged:
                audit_execution = AuditExecution.INCOMPLETE
                assessment = ArtifactAssessment.UNKNOWN
                semantic_confirmed = False
                deterministic = tuple(
                    item for item in deterministic if item.check_id != "B10"
                ) + (_validation_source_integrity_failure(validation),)
            evidence = deterministic + validation.advisory_evidence
            gate = _audit_gate(
                audit_execution, assessment, semantic_confirmed,
                validation.project_policy, validation.decision, deterministic,
                validation.advisory_evidence,
                validation.coverage_status,
                (
                    validation.deliverable_contract_provenance is not None
                    and validation.deliverable_contract_provenance.applicability
                    is DeliverableContractApplicability.REQUIRED
                ),
            )
            lifecycle = _audit_terminal_state(
                audit_execution, assessment, validation.coverage_status,
            )
            findings = _minimal_audit_findings(
                validation, assessment, deterministic
            )
            outcome_type = gate.outcome.value
            session = None
        else:
            evidence = deterministic + validation.advisory_evidence
            gate = adjudicate(
                GateContext(
                    validation.intent, LifecycleState.VALIDATED,
                    validation.authorized_to_modify,
                    validation.staging_path is not None,
                    validation.staging_path is not None, validation.decision,
                    semantic_confirmed, validation.apply_requested,
                    validation.coverage_status,
                    (
                        validation.deliverable_contract_provenance is not None
                        and validation.deliverable_contract_provenance.applicability
                        is DeliverableContractApplicability.REQUIRED
                    ),
                    validation.capability_preservation,
                ), evidence, policy=load_gate_policy(validation.project_policy),
            )
            if gate.verdict is not GateVerdict.PASS:
                self._record(LifecycleState.GATE_FAILED)
                raise PipelineBlockedError(gate, validation.artifact_path,
                                           validation.workspace_diff, evidence)
            session = (
                _apply_session(validation, confirmation)
                if gate.apply_authorized else None
            )
            lifecycle = (LifecycleState.READY_TO_APPLY
                         if gate.outcome is GateOutcome.READY_TO_APPLY
                         else LifecycleState.VALIDATED)
            findings = ()
            outcome_type = "Validated Complete Skill"
        self._record(lifecycle)
        return EngineeringOutcome(
            outcome_type, validation.artifact_path, gate, findings,
            _current_source_diff(validation) if validation.intent is Intent.AUDIT_ONLY
            else validation.workspace_diff,
            session if gate.apply_authorized else None, evidence,
            deterministic, validation.advisory_evidence,
            audit_execution, assessment, lifecycle, validation, confirmation,
        )

    def run(self, request: EngineeringRequest) -> EngineeringOutcome:
        _validate_compatibility_request(request)
        inspection = self.inspect(
            request.intent, request.source,
            required_standard_skills=request.required_standard_skills,
            deliverable_contract_applicability=request.deliverable_contract_applicability,
        )
        validation = self.validate(
            inspection, request.decision, request.governance_decisions,
            candidate=request.candidate, target_parent=request.target_parent,
            authorized_to_modify=request.authorized_to_modify,
            behavioral_runner=request.behavioral_runner,
            regression_runner=request.regression_runner,
            contract_runner=request.contract_runner,
            apply_requested=request.apply_requested,
            continue_limited=request.continue_limited,
            project_policy=request.project_policy,
        )
        confirmation = request.semantic_confirmation or SemanticConfirmation(
            "missing", "No Codex confirmation was supplied", "MISSING"
        )
        return self.confirm(validation, confirmation)


def apply(
    outcome: EngineeringOutcome,
    receipt: ManagedCompletionReceipt | None = None,
) -> ApplyResult:
    if outcome.apply_session is None:
        raise ValueError("outcome has no validated safe-apply workspace")
    if receipt is None:
        raise ValueError("formal completion receipt is required for Apply")
    from engine.managed_completion import validate_completion_receipt
    validate_completion_receipt(receipt, outcome)
    return apply_atomic(outcome.apply_session, outcome.gate_result)


# Import compatibility for pre-4.2 callers; user-facing workflow is `apply`.
publish = apply


def _validate_inspection(inspection: InspectionBundle) -> None:
    if not isinstance(inspection, InspectionBundle) or not inspection.inspection_id:
        raise ValueError("a valid InspectionBundle is required")
    if inspection.tool_schema_version != TOOL_SCHEMA_VERSION:
        raise ValueError("inspection schema version is unsupported")
    if tuple(item.finding_id for item in inspection.findings) != inspection.finding_ids:
        raise ValueError("inspection finding IDs do not match findings")


def _validate_decision(decision: DecisionRecord, intent: Intent) -> None:
    if not isinstance(decision, DecisionRecord):
        raise ValueError("Codex DecisionRecord is required")
    if decision.intent is not intent:
        raise ValueError("DecisionRecord intent must match inspection mode")
    validate_classification(decision)
    validate_mechanism_selection(decision)


def _verify_inspection_fresh(inspection: InspectionBundle) -> None:
    if inspection.source_path is None:
        return
    if digest_tree(inspection.source_path) != inspection.baseline_digest:
        raise ValueError("stale inspection: source digest no longer matches baseline")
    if inspection.baseline_snapshot is None or (
        snapshot_tree(inspection.source_path).content_digest
        != inspection.baseline_snapshot.content_digest
    ):
        raise ValueError("stale inspection: source manifest no longer matches baseline")


def _session_for_inspection(inspection: InspectionBundle) -> WorkspaceSession:
    if inspection.mode is Intent.CREATE:
        return WorkspaceSession.for_create()
    if inspection.source_path is None:
        raise ValueError("source is required")
    session = WorkspaceSession.for_existing(inspection.mode, inspection.source_path)
    session.source_snapshot = inspection.baseline_snapshot
    session.source_digest = inspection.baseline_digest
    return session


def _inspect_provider_evidence(
    gateway: ProviderGateway | None,
    subject: str,
    target: Path | None,
    mode: Intent,
    *,
    inspection_id: str,
    inspection_nonce: str,
    target_digest: str | None,
    deliverable_contract_applicability: DeliverableContractApplicability,
    capabilities: tuple[str, ...] | None = None,
) -> tuple[ProviderEvidence, ...]:
    if gateway is None:
        return ()
    records: list[ProviderEvidence] = []
    selected_capabilities = (
        tuple(sorted(gateway.capabilities))
        if capabilities is None else capabilities
    )
    for capability in selected_capabilities:
        if (
            capability == "DELIVERABLE_CONTRACT"
            and deliverable_contract_applicability is DeliverableContractApplicability.NOT_REQUIRED
        ):
            continue
        records.append(_provider_record(
            gateway.invoke(capability, {
                "subject": subject,
                "target_path": str(target) if target is not None else None,
                "mode": mode.value,
                "inspection_id": inspection_id,
                "inspection_nonce": inspection_nonce,
                "target_digest": target_digest,
                "artifact_role": ArtifactRole.BASELINE.value,
                "deliverable_contract_applicability": deliverable_contract_applicability.value,
            }, formal_run=True),
            "INSPECT",
        ))
    return tuple(records)


def _provider_record(result: ProviderResult, phase: str) -> ProviderEvidence:
    unavailable = {ProviderStatus.UNAVAILABLE, ProviderStatus.INVALID_OUTPUT,
                   ProviderStatus.TIMEOUT, ProviderStatus.INCOMPATIBLE}
    status = (
        CheckStatus.FAIL if result.findings
        else CheckStatus.NOT_EXECUTED
        if result.provider_status in unavailable
        or result.provider_status is ProviderStatus.DEGRADED
        or result.limitations
        else CheckStatus.PASS
    )
    summary = "; ".join((*result.findings, *result.evidence, *result.limitations))
    return ProviderEvidence(result.provider_id, result.capability, phase, status,
                            summary or "provider returned no details", False, False,
                            result.findings, result.evidence, result.limitations,
                            result.provider_available, result.provider_execution,
                            result.fallback_used, result.evidence_valid,
                            result.deliverable_contract, result.capability_manifest)


def _capability_provider_identity_failure(
    subject: str,
    expected: str,
    actual: str,
) -> CheckResult:
    return CheckResult(
        "capability.provider_identity",
        "engine.capability-provider",
        subject,
        True,
        CheckStatus.NOT_EXECUTED,
        True,
        True,
        1.0,
        (f"CAPABILITY_PROVIDER_IDENTITY_MISMATCH:{expected}:{actual}",),
        LifecycleState.VALIDATED_PENDING_CONFIRMATION,
        subject,
    )


def _missing_capability_manifest(subject: str) -> CheckResult:
    return CheckResult(
        "capability.capability_contract",
        "engine.capability-provider",
        subject,
        True,
        CheckStatus.NOT_EXECUTED,
        True,
        True,
        1.0,
        ("CAPABILITY_MANIFEST_MISSING",),
        LifecycleState.VALIDATED_PENDING_CONFIRMATION,
        subject,
    )


def _deliverable_contract_provenance(
    applicability: DeliverableContractApplicability,
    providers: tuple[ProviderEvidence, ...],
    contract_check: CheckResult | None = None,
) -> DeliverableContractProvenance:
    records = tuple(
        item for item in providers if item.capability == "DELIVERABLE_CONTRACT"
    )
    provider_discovered = any(item.provider_available for item in records)
    provider_selected = any(
        item.provider_available
        or item.provider_execution is not ProviderExecution.NOT_STARTED
        for item in records
    )
    provider_executed = any(
        item.provider_execution is ProviderExecution.EXECUTED for item in records
    )
    contract_present = any(item.deliverable_contract is not None for item in records)
    contract_validated = (
        contract_check is not None and contract_check.status is CheckStatus.PASS
    )
    provider = next(
        (item for item in records if not item.provider_id.startswith("optional.none.")),
        records[0] if records else None,
    )
    if applicability is DeliverableContractApplicability.NOT_REQUIRED:
        coverage = CoverageStatus.FULL
        reason = "not_required"
    elif applicability is DeliverableContractApplicability.COMPATIBILITY:
        coverage = CoverageStatus.COMPATIBILITY
        reason = "legacy_compatibility"
    elif contract_validated:
        coverage = CoverageStatus.FULL
        reason = "contract_validated"
    else:
        coverage = CoverageStatus.PARTIAL
        evidence = contract_check.evidence if contract_check is not None else ()
        if not provider_discovered:
            reason = "provider_unavailable"
        elif not provider_executed:
            reason = (
                "provider_execution_failed"
                if any(item.provider_execution is ProviderExecution.FAILED for item in records)
                else "provider_not_executed"
            )
        elif not contract_present:
            reason = "contract_missing"
        elif any("STALE" in item or "digest mismatch" in item for item in evidence):
            reason = "contract_stale"
        elif contract_check is None:
            reason = "contract_pending_validation"
        else:
            reason = "contract_invalid"
    execution = (
        provider.provider_execution if provider is not None
        else ProviderExecution.NOT_STARTED
    )
    return DeliverableContractProvenance(
        applicability, provider_discovered, provider_selected, provider_executed,
        contract_present, contract_validated, coverage, reason,
        provider.provider_id if provider is not None else None, execution,
    )


def _provider_evidence_to_check(item: ProviderEvidence, subject: str) -> CheckResult:
    return CheckResult(
        f"provider.{item.capability.lower()}", f"provider:{item.provider_id}",
        subject, False, item.status, False, item.reproducible, 1.0,
        (f"invocation_phase={item.invocation_phase}", item.summary),
        LifecycleState.VALIDATED_PENDING_CONFIRMATION, subject,
    )


def _source_integrity_evidence(session: WorkspaceSession,
                               checks: list[bool]) -> CheckResult:
    changed = not all(checks)
    diff = session.source_diff()
    details = (("source baseline changed during Audit Only; change origin is not attributed",
                f"added={list(diff.added)}", f"modified={list(diff.modified)}",
                f"deleted={list(diff.deleted)}") if changed else
               ("source baseline remained unchanged at every verification point",))
    return CheckResult(
        "B10", "engine.source-integrity", str(session.source), True,
        CheckStatus.FAIL if changed else CheckStatus.PASS, True, True, 1.0,
        details, LifecycleState.VALIDATED_PENDING_CONFIRMATION, str(session.source),
    )


def _artifact_assessment(execution: AuditExecution,
                         deterministic: tuple[CheckResult, ...],
                         advisory: tuple[CheckResult, ...]) -> ArtifactAssessment:
    if execution is AuditExecution.INCOMPLETE:
        return ArtifactAssessment.UNKNOWN
    target = tuple(item for item in deterministic if item.source not in {
        "engine.source-integrity", "cli.command", "behavioral.runner", "regression.runner"
    })
    if any(item.required and item.status in {CheckStatus.FAIL, CheckStatus.ERROR}
           for item in target):
        return ArtifactAssessment.BLOCKING_FINDINGS
    if any(item.status is CheckStatus.WARN for item in (*target, *advisory)):
        return ArtifactAssessment.FINDINGS
    return ArtifactAssessment.VALID


def _checks_fingerprint(deterministic: tuple[CheckResult, ...],
                        advisory: tuple[CheckResult, ...]) -> str:
    payload = {"deterministic": [asdict(item) for item in deterministic],
               "advisory": [asdict(item) for item in advisory]}
    encoded = json.dumps(payload, default=_json_default, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_default(value: object) -> object:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"unsupported value: {type(value)!r}")


def _source_matches_validation(validation: ValidationBundle) -> bool:
    if validation.source_path is None:
        return True
    if validation.baseline_snapshot is None:
        return False
    return (digest_tree(validation.source_path) == validation.baseline_digest
            and snapshot_tree(validation.source_path).content_digest
            == validation.baseline_snapshot.content_digest)


def _semantic_confirmation_matches(confirmation: SemanticConfirmation,
                                   artifact_digest: str) -> bool:
    if confirmation.confirmed_by != "CODEX":
        return False
    try:
        validate_contract("semantic-confirmation", asdict(confirmation))
    except Exception:
        return False
    return confirmation.artifact_digest == artifact_digest


def _audit_gate(execution: AuditExecution | None,
                assessment: ArtifactAssessment | None, semantic_confirmed: bool,
                project_policy: Path | None,
                decision: DecisionRecord,
                deterministic: tuple[CheckResult, ...] = (),
                advisory: tuple[CheckResult, ...] = (),
                coverage_status: CoverageStatus = CoverageStatus.COMPATIBILITY,
                full_coverage_required: bool = False) -> GateResult:
    policy = load_gate_policy(project_policy)
    policy_version = str(policy["policy_version"])
    framework_errors = tuple(
        item for item in deterministic
        if item.status is CheckStatus.ERROR and item.source.startswith("engine.framework")
    )
    if framework_errors:
        return GateResult(
            GateVerdict.ERROR, GateOutcome.ERROR,
            tuple(
                f"B08: {item.check_id} ({item.subject}): {'; '.join(item.evidence)}"
                for item in framework_errors
            ),
            (), "Framework execution failed.", "Artifact assessment is UNKNOWN.",
            semantic_confirmed, False, policy_version, coverage_status,
        )
    if execution is not AuditExecution.COMPLETE:
        reasons = ["B10: Audit execution is incomplete or required capability evidence is unavailable"]
        if not semantic_confirmed:
            reasons.append("B12: Codex semantic confirmation for the validated artifact is absent")
        return GateResult(
            GateVerdict.INCOMPLETE, GateOutcome.AUDIT_INCOMPLETE,
            tuple(reasons),
            (), "Audit execution incomplete.", "Artifact assessment is UNKNOWN.",
            semantic_confirmed, False, policy_version, coverage_status,
        )
    base = adjudicate(
        GateContext(
            Intent.AUDIT_ONLY, LifecycleState.VALIDATED, False, False, False,
            decision, semantic_confirmed, False,
            coverage_status,
            full_coverage_required,
        ),
        deterministic + advisory,
        policy=policy,
    )
    if base.verdict is GateVerdict.INCOMPLETE:
        outcome = GateOutcome.AUDIT_INCOMPLETE
    elif base.verdict is GateVerdict.ERROR:
        outcome = GateOutcome.ERROR
    elif coverage_status is CoverageStatus.FULL:
        outcome = {
            ArtifactAssessment.VALID: GateOutcome.AUDIT_COMPLETE_VALID,
            ArtifactAssessment.FINDINGS: GateOutcome.AUDIT_COMPLETE_FINDINGS,
            ArtifactAssessment.BLOCKING_FINDINGS: GateOutcome.AUDIT_COMPLETE_BLOCKING_FINDINGS,
        }[assessment]
    elif base.verdict is GateVerdict.FAIL:
        outcome = (
            GateOutcome.AUDIT_COMPLETE_BLOCKING_FINDINGS
            if assessment is ArtifactAssessment.BLOCKING_FINDINGS
            else GateOutcome.UNCHANGED_BLOCKED
        )
    else:
        outcome = GateOutcome.UNCHANGED_VALIDATED
    warnings = tuple(
        detail
        for item in (*deterministic, *advisory)
        if item.status in {CheckStatus.WARN, CheckStatus.FAIL}
        for detail in (f"{item.check_id}: {'; '.join(item.evidence)}",)
    )
    if assessment is not ArtifactAssessment.VALID:
        warnings += (f"artifact_assessment={assessment.value}",)
    if coverage_status is not CoverageStatus.FULL:
        warnings += (f"coverage_status={coverage_status.value}",)
    return GateResult(
        base.verdict, outcome, base.blocking_findings,
        tuple(dict.fromkeys((*base.warnings, *warnings))),
        base.required_checks_summary,
        f"Artifact assessment is {assessment.value}. {base.evidence_summary}",
        base.semantic_confirmed, False, policy_version, coverage_status,
    )


def _audit_terminal_state(execution: AuditExecution | None,
                          assessment: ArtifactAssessment | None,
                          coverage_status: CoverageStatus = CoverageStatus.COMPATIBILITY) -> LifecycleState:
    if execution is not AuditExecution.COMPLETE:
        return LifecycleState.AUDIT_INCOMPLETE
    if coverage_status is not CoverageStatus.FULL:
        return (
            LifecycleState.AUDIT_COMPLETE_BLOCKING_FINDINGS
            if assessment is ArtifactAssessment.BLOCKING_FINDINGS
            else LifecycleState.UNCHANGED_VALIDATED
        )
    return {
        ArtifactAssessment.VALID: LifecycleState.AUDIT_COMPLETE_VALID,
        ArtifactAssessment.FINDINGS: LifecycleState.AUDIT_COMPLETE_FINDINGS,
        ArtifactAssessment.BLOCKING_FINDINGS: LifecycleState.AUDIT_COMPLETE_BLOCKING_FINDINGS,
    }.get(assessment, LifecycleState.AUDIT_INCOMPLETE)


def _minimal_audit_findings(validation: ValidationBundle,
                            assessment: ArtifactAssessment | None,
                            deterministic: tuple[CheckResult, ...] | None = None) -> tuple[dict[str, str], ...]:
    if assessment in {None, ArtifactAssessment.VALID}:
        return ()
    results = tuple(item for item in (deterministic or validation.deterministic_evidence)
                    if item.status in {CheckStatus.FAIL, CheckStatus.ERROR, CheckStatus.WARN}
                    and not item.check_id.startswith("rule-signal."))
    return tuple({
        "finding_id": item.check_id,
        "affected_path": item.artifact_reference or str(validation.artifact_path),
        "blocking_reason": "; ".join(item.evidence),
        "required_next_action": "Codex must review the finding before any remediation",
    } for item in results)


def _current_source_diff(validation: ValidationBundle) -> WorkspaceDiff:
    if validation.source_path is None or validation.baseline_snapshot is None:
        return WorkspaceDiff((), (), ())
    from engine.workspace import diff_snapshots
    return diff_snapshots(validation.baseline_snapshot,
                          snapshot_tree(validation.source_path))


def _validation_source_integrity_failure(validation: ValidationBundle) -> CheckResult:
    diff = _current_source_diff(validation)
    return CheckResult(
        "B10", "engine.source-integrity", str(validation.source_path), True,
        CheckStatus.FAIL, True, True, 1.0,
        (
            "source baseline changed after validation; change origin is not attributed",
            f"added={list(diff.added)}",
            f"modified={list(diff.modified)}",
            f"deleted={list(diff.deleted)}",
        ),
        LifecycleState.AUDIT_INCOMPLETE,
        str(validation.source_path),
    )


def _apply_session(validation: ValidationBundle,
                         confirmation: SemanticConfirmation) -> WorkspaceSession:
    session = WorkspaceSession(
        validation.intent, validation.source_path, validation.staging_path,
        validation.baseline_digest, source_snapshot=validation.baseline_snapshot,
    )
    session.bind_confirmed_artifact(validation.artifact_path,
                                    confirmation.artifact_digest)
    return session


def _diagnostic_failure(subject: str) -> CheckResult:
    return CheckResult("diagnostic.evidence", "codex.diagnostics", subject, True,
                       CheckStatus.FAIL, True, True, 1.0,
                       ("Codex recorded insufficient failure evidence",),
                       LifecycleState.VALIDATED_PENDING_CONFIRMATION, subject)


def _framework_failure(subject: str, stage: str, error: Exception) -> CheckResult:
    return CheckResult(
        f"framework.{stage.replace(' ', '-')}", "engine.framework.runtime",
        subject, True, CheckStatus.ERROR, True, True, 1.0,
        (f"{stage} failed: {type(error).__name__}: {error}",),
        LifecycleState.VALIDATED_PENDING_CONFIRMATION, subject,
    )


def _missing_behavioral_check(subject: str) -> CheckResult:
    return CheckResult("behavioral.create", "behavioral.runner", subject, True,
                       CheckStatus.NOT_EXECUTED, True, True, 1.0,
                       ("No Create behavioral test was executed",),
                       LifecycleState.VALIDATED_PENDING_CONFIRMATION, subject)


def _missing_regression_check(subject: str) -> CheckResult:
    return CheckResult("B07", "regression.runner", subject, True,
                       CheckStatus.NOT_EXECUTED, True, True, 1.0,
                       ("Required regression command was not supplied",),
                       LifecycleState.VALIDATED_PENDING_CONFIRMATION, subject)


def _validate_compatibility_request(request: EngineeringRequest) -> None:
    if not request.requirement.strip():
        raise ValueError("requirement must be nonblank")
    if request.intent is Intent.AUDIT_ONLY and request.candidate is not None:
        raise ValueError("Audit Only cannot accept a candidate")
    if request.intent in {Intent.CREATE, Intent.MODIFY, Intent.FIX} and request.candidate is None:
        raise ValueError("Codex must supply a complete candidate for this mode")
    if request.candidate is not None and not request.authorized_to_modify:
        raise ValueError("candidate staging requires modification authorization")
