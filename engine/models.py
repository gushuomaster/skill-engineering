"""Immutable records exchanged by the skill-engineering pipeline."""
from dataclasses import dataclass
from enum import StrEnum


class Intent(StrEnum):
    AUDIT = "AUDIT"; AUDIT_REPAIR = "AUDIT_REPAIR"; TARGETED_REPAIR = "TARGETED_REPAIR"
    # Compatibility aliases for persisted pre-4.2 records. They are not user modes.
    AUDIT_ONLY = "AUDIT"; AUDIT_OPTIMIZE = "AUDIT_REPAIR"; FIX = "TARGETED_REPAIR"; MODIFY = "TARGETED_REPAIR"
    CREATE = "CREATE"
class LifecycleState(StrEnum):
    DISCOVERED = "DISCOVERED"; INSPECTED = "INSPECTED"; CLASSIFIED = "CLASSIFIED"; MECHANISM_SELECTED = "MECHANISM_SELECTED"; STAGED = "STAGED"; AUDITED = "AUDITED"; VALIDATED_PENDING_CONFIRMATION = "VALIDATED_PENDING_CONFIRMATION"; VALIDATED = "VALIDATED"; GATE_FAILED = "GATE_FAILED"; GATE_PASSED = "GATE_PASSED"; READY_TO_APPLY = "READY_TO_APPLY"; APPLIED = "APPLIED"; APPLY_FAILED_RECOVERED = "APPLY_FAILED_RECOVERED"; APPLY_FAILED_UNRECOVERABLE = "APPLY_FAILED_UNRECOVERABLE"; AUDIT_COMPLETE_VALID = "AUDIT_COMPLETE_VALID"; AUDIT_COMPLETE_FINDINGS = "AUDIT_COMPLETE_FINDINGS"; AUDIT_COMPLETE_BLOCKING_FINDINGS = "AUDIT_COMPLETE_BLOCKING_FINDINGS"; AUDIT_INCOMPLETE = "AUDIT_INCOMPLETE"; UNCHANGED_VALIDATED = "UNCHANGED_VALIDATED"; UNCHANGED_BLOCKED = "UNCHANGED_BLOCKED"; READY_TO_PUBLISH = "READY_TO_APPLY"; PUBLISHED = "APPLIED"; PUBLISH_FAILED_RECOVERED = "APPLY_FAILED_RECOVERED"; PUBLISH_FAILED_UNRECOVERABLE = "APPLY_FAILED_UNRECOVERABLE"
class PrimaryIssueClass(StrEnum):
    IMPLEMENTATION_DEFECT = "IMPLEMENTATION_DEFECT"; ENVIRONMENT_COMPATIBILITY = "ENVIRONMENT_COMPATIBILITY"; WORKFLOW_DESIGN_DEFECT = "WORKFLOW_DESIGN_DEFECT"; CONTRACT_ENFORCEMENT_GAP = "CONTRACT_ENFORCEMENT_GAP"; CAPABILITY_INVARIANT_CHANGE = "CAPABILITY_INVARIANT_CHANGE"; TASK_LOCAL_PREFERENCE = "TASK_LOCAL_PREFERENCE"; DOCUMENTATION_GAP = "DOCUMENTATION_GAP"; NO_DEFECT = "NO_DEFECT"; INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
class ControlGap(StrEnum):
    IMPLEMENTATION_GAP = "IMPLEMENTATION_GAP"; SCHEMA_MISSING = "SCHEMA_MISSING"; VALIDATOR_MISSING = "VALIDATOR_MISSING"; ENV_DETECTION_MISSING = "ENV_DETECTION_MISSING"; REGRESSION_MISSING = "REGRESSION_MISSING"; WORKFLOW_CONTROL_MISSING = "WORKFLOW_CONTROL_MISSING"; INSTRUCTION_GAP = "INSTRUCTION_GAP"; NONE = "NONE"
class RegressionDisposition(StrEnum): REQUIRED = "REQUIRED"; RECOMMENDED = "RECOMMENDED"; NOT_APPLICABLE = "NOT_APPLICABLE"
class CheckStatus(StrEnum): PASS = "PASS"; WARN = "WARN"; FAIL = "FAIL"; SKIP = "SKIP"; ERROR = "ERROR"; NOT_EXECUTED = "NOT_EXECUTED"
class GateVerdict(StrEnum): PASS = "PASS"; FAIL = "FAIL"; INCOMPLETE = "INCOMPLETE"; ERROR = "ERROR"
class GateOutcome(StrEnum): READY_TO_APPLY = "READY_TO_APPLY"; VALIDATED = "VALIDATED"; UNCHANGED_VALIDATED = "UNCHANGED_VALIDATED"; UNCHANGED_BLOCKED = "UNCHANGED_BLOCKED"; REMEDIATION_REQUIRED = "REMEDIATION_REQUIRED"; INCOMPLETE = "INCOMPLETE"; ERROR = "ERROR"; AUDIT_COMPLETE_VALID = "AUDIT_COMPLETE_VALID"; AUDIT_COMPLETE_FINDINGS = "AUDIT_COMPLETE_FINDINGS"; AUDIT_COMPLETE_BLOCKING_FINDINGS = "AUDIT_COMPLETE_BLOCKING_FINDINGS"; AUDIT_INCOMPLETE = "AUDIT_INCOMPLETE"; READY_TO_PUBLISH = "READY_TO_APPLY"
class ProviderStatus(StrEnum): AVAILABLE = "AVAILABLE"; UNAVAILABLE = "UNAVAILABLE"; INVALID_OUTPUT = "INVALID_OUTPUT"; TIMEOUT = "TIMEOUT"; INCOMPATIBLE = "INCOMPATIBLE"; DEGRADED = "DEGRADED"
class ProviderExecution(StrEnum): NOT_STARTED = "NOT_STARTED"; EXECUTED = "EXECUTED"; FAILED = "FAILED"
class CapabilityStatus(StrEnum): READY = "READY"; FALLBACK = "FALLBACK"; NOT_APPLICABLE = "NOT_APPLICABLE"; BLOCKED = "BLOCKED"
class FallbackEquivalence(StrEnum): FULL = "FULL"; ALTERNATIVE = "ALTERNATIVE"; PARTIAL = "PARTIAL"; NONE = "NONE"
class AuditExecution(StrEnum): COMPLETE = "COMPLETE"; INCOMPLETE = "INCOMPLETE"
class ArtifactAssessment(StrEnum): VALID = "VALID"; FINDINGS = "FINDINGS"; BLOCKING_FINDINGS = "BLOCKING_FINDINGS"; UNKNOWN = "UNKNOWN"
class CoverageStatus(StrEnum): FULL = "FULL"; PARTIAL = "PARTIAL"; COMPATIBILITY = "COMPATIBILITY"
class StandardDependencyStatus(StrEnum): AVAILABLE = "AVAILABLE"; MISSING = "MISSING"; DECLINED = "DECLINED"
class DeliverableEvidenceStatus(StrEnum): PRESENT = "present"; MISSING = "missing"; UNKNOWN = "unknown"; NOT_APPLICABLE = "not_applicable"
class DeliverableContractApplicability(StrEnum): NOT_REQUIRED = "NOT_REQUIRED"; OPTIONAL = "OPTIONAL"; REQUIRED = "REQUIRED"; COMPATIBILITY = "COMPATIBILITY"
class ArtifactRole(StrEnum): BASELINE = "BASELINE"; CANDIDATE = "CANDIDATE"
class CapabilityEvidenceState(StrEnum): COMPLETE = "COMPLETE"; UNVERIFIABLE = "UNVERIFIABLE"
class CapabilityChangeKind(StrEnum): ADDED = "ADDED"; PRESERVED = "PRESERVED"; MODIFIED = "MODIFIED"; REMOVED = "REMOVED"; NARROWED = "NARROWED"; BROKEN = "BROKEN"; UNVERIFIABLE = "UNVERIFIABLE"
class CapabilityPreservationStatus(StrEnum): CAPABILITY_PRESERVED = "CAPABILITY_PRESERVED"; CAPABILITY_REGRESSION = "CAPABILITY_REGRESSION"; AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"; CAPABILITY_UNVERIFIABLE = "CAPABILITY_UNVERIFIABLE"
class ManagedOperationStatus(StrEnum): MANAGED = "MANAGED"; AUDIT_INCOMPLETE = "AUDIT_INCOMPLETE"; UNMANAGED_CHANGE = "UNMANAGED_CHANGE"; APPLY_BLOCKED = "APPLY_BLOCKED"
class CapabilityDecisionKind(StrEnum): BUG_FIX = "BUG_FIX"; IMPLEMENTATION_COMPLETION = "IMPLEMENTATION_COMPLETION"; DECLARATION_CORRECTION = "DECLARATION_CORRECTION"; CAPABILITY_REMOVAL = "CAPABILITY_REMOVAL"; CAPABILITY_NARROWING = "CAPABILITY_NARROWING"; INTENTIONAL_BREAKING_CHANGE = "INTENTIONAL_BREAKING_CHANGE"
class AuthorizationStatus(StrEnum): NOT_REQUIRED = "NOT_REQUIRED"; REQUIRED = "REQUIRED"; AUTHORIZED = "AUTHORIZED"; DENIED = "DENIED"; MISSING = "MISSING"

@dataclass(frozen=True)
class TreeEntry:
    path: str; entry_type: str; size: int; content_hash: str | None; mode: int

@dataclass(frozen=True)
class DirectorySnapshot:
    root: str; entries: tuple[TreeEntry, ...]; content_digest: str

@dataclass(frozen=True)
class ArtifactManifest:
    intent: Intent; artifact_root: str; skill_name: str; source_revision: str | None; source_digest: str | None; files: tuple[str, ...]; executable_assets: tuple[str, ...]; required_references: tuple[str, ...]; test_inventory: tuple[str, ...]; content_digest: str

@dataclass(frozen=True)
class CapabilityRecord:
    capability_id: str
    public_name: str
    capability_type: str
    declared_status: str
    implementation_status: str
    entrypoints: tuple[str, ...]
    supported_profiles: tuple[str, ...]
    supported_deliverables: tuple[str, ...]
    templates: tuple[str, ...]
    schemas: tuple[str, ...]
    validation_coverage: tuple[str, ...]
    public_claim_sources: tuple[str, ...]
    implementation_evidence: tuple[str, ...]
    confidence: float
    evidence_state: CapabilityEvidenceState

@dataclass(frozen=True)
class CapabilityManifest:
    schema_version: str
    inspection_id: str
    inspection_nonce: str
    artifact_role: ArtifactRole
    artifact_digest: str
    provider_identity: str
    capabilities: tuple[CapabilityRecord, ...]
    public_output_contract_status: str
    public_output_contract_evidence: tuple[str, ...]
    evidence_origin: str = "provider"

@dataclass(frozen=True)
class CapabilityChange:
    capability_id: str
    kind: CapabilityChangeKind
    changed_fields: tuple[str, ...]
    baseline_values: tuple[str, ...]
    candidate_values: tuple[str, ...]

@dataclass(frozen=True)
class CapabilityDiff:
    baseline_manifest_digest: str
    candidate_manifest_digest: str
    changes: tuple[CapabilityChange, ...]

    def _ids(self, kind: CapabilityChangeKind) -> tuple[str, ...]:
        return tuple(item.capability_id for item in self.changes if item.kind is kind)

    @property
    def removed_capability_ids(self) -> tuple[str, ...]:
        return self._ids(CapabilityChangeKind.REMOVED)

    @property
    def narrowed_capability_ids(self) -> tuple[str, ...]:
        return self._ids(CapabilityChangeKind.NARROWED)

    @property
    def broken_capability_ids(self) -> tuple[str, ...]:
        return self._ids(CapabilityChangeKind.BROKEN)

    @property
    def unverifiable_capability_ids(self) -> tuple[str, ...]:
        return self._ids(CapabilityChangeKind.UNVERIFIABLE)

@dataclass(frozen=True)
class CapabilityChangeDecision:
    baseline_capability_digest: str
    candidate_capability_digest: str
    capability_changes: tuple[tuple[str, CapabilityDecisionKind], ...]
    removed_capability_ids: tuple[str, ...]
    narrowed_capability_ids: tuple[str, ...]
    change_rationale: str
    user_authorization_required: bool
    user_authorization_status: AuthorizationStatus
    authorization_evidence: tuple[str, ...]
    compatibility_impact: str
    migration_plan: str | None
    deprecation_plan: str | None

@dataclass(frozen=True)
class ManagedCompletionReceipt:
    inspection_id: str
    operation_mode: Intent
    source_digest: str | None
    candidate_digest: str
    baseline_capability_digest: str | None
    candidate_capability_digest: str
    validation_bundle_digest: str
    semantic_confirmation_digest: str
    coverage_status: CoverageStatus
    capability_preservation: CapabilityPreservationStatus
    gate_verdict: GateVerdict
    gate_outcome: GateOutcome
    formal_completion: bool

@dataclass(frozen=True)
class ManagedStatusResult:
    status: ManagedOperationStatus
    formal_completion: bool
    target_digest: str | None
    reason: str

@dataclass(frozen=True)
class DeliverableEvidence:
    deliverable_id: str
    declared_status: str
    declarations: tuple[str, ...]
    exposure_status: DeliverableEvidenceStatus
    exposure_entrypoint: str | None
    exposure_selector: str | None
    exposure_evidence: tuple[str, ...]
    implementation_status: DeliverableEvidenceStatus
    implementation_dispatch_route: str | None
    implementation_artifact_pattern: str | None
    implementation_evidence: tuple[str, ...]
    behavioral_status: DeliverableEvidenceStatus
    behavioral_commands: tuple[str, ...]
    expected_artifacts: tuple[str, ...]
    behavioral_evidence: tuple[str, ...]

@dataclass(frozen=True)
class DeliverableScopeConflict:
    summary: str
    blocking: bool
    evidence_refs: tuple[str, ...]

@dataclass(frozen=True)
class DeliverableContract:
    schema_version: str
    inspection_id: str
    target_digest: str
    inspection_nonce: str
    provider_identity: str
    deliverables: tuple[DeliverableEvidence, ...]
    scope_conflicts: tuple[DeliverableScopeConflict, ...]
    applicability_status: str
    applicability_reason: str
    applicability_evidence: tuple[str, ...]
    evidence_origin: str = "provider"
@dataclass(frozen=True)
class DeliverableContractProvenance:
    applicability: DeliverableContractApplicability
    provider_discovered: bool
    provider_selected: bool
    provider_executed: bool
    contract_present: bool
    contract_validated: bool
    coverage_status: CoverageStatus
    reason: str
    provider_id: str | None = None
    provider_execution: ProviderExecution = ProviderExecution.NOT_STARTED
@dataclass(frozen=True)
class DecisionRecord:
    intent: Intent; primary_issue_class: PrimaryIssueClass; control_gaps: tuple[ControlGap, ...]; regression_disposition: RegressionDisposition; root_cause: str | None; evidence_limitations: tuple[str, ...]; selected_mechanisms: tuple[str, ...]; rejected_mechanisms: tuple[str, ...]; prompt_rule_justification: str | None; decided_by: str = "CODEX"; capability_change_decision: CapabilityChangeDecision | None = None
@dataclass(frozen=True)
class SemanticConfirmation:
    artifact_digest: str; rationale: str; confirmed_by: str = "CODEX"
@dataclass(frozen=True)
class ProviderDescriptor:
    provider_id: str; source_identity: str; revision_or_version: str | None; capability: str; availability: ProviderStatus; invocation_adapter: str; limitations: tuple[str, ...]; fallback_provider: str | None
@dataclass(frozen=True)
class ProviderResult:
    provider_id: str; capability: str; provider_status: ProviderStatus; findings: tuple[str, ...]; candidate_changes: tuple[str, ...]; evidence: tuple[str, ...]; limitations: tuple[str, ...]; fallback_used: bool; provider_available: bool = False; provider_execution: ProviderExecution = ProviderExecution.NOT_STARTED; evidence_valid: bool = False; deliverable_contract: DeliverableContract | None = None; capability_manifest: CapabilityManifest | None = None
@dataclass(frozen=True)
class ProviderEvidence:
    provider_id: str; capability: str; invocation_phase: str; status: CheckStatus; summary: str; deterministic: bool = False; reproducible: bool = False; findings: tuple[str, ...] = (); evidence: tuple[str, ...] = (); limitations: tuple[str, ...] = (); provider_available: bool = False; provider_execution: ProviderExecution = ProviderExecution.NOT_STARTED; fallback_used: bool = False; evidence_valid: bool = False; deliverable_contract: DeliverableContract | None = None; capability_manifest: CapabilityManifest | None = None
@dataclass(frozen=True)
class CapabilityAssessment:
    capability: str; required: bool; status: CapabilityStatus; preferred_providers: tuple[str, ...]; selected_provider: str | None; fallback: str | None; fallback_equivalence: FallbackEquivalence; evidence: tuple[str, ...]
@dataclass(frozen=True)
class StandardSkillRequirement:
    skill_name: str; responsibility: str; coverage_gap: str
@dataclass(frozen=True)
class StandardDependencyAssessment:
    skill_name: str; responsibility: str; coverage_gap: str; status: StandardDependencyStatus; installed_path: str | None
@dataclass(frozen=True)
class CheckResult:
    check_id: str; source: str; subject: str; required: bool; status: CheckStatus; deterministic: bool; reproducible: bool; confidence: float; evidence: tuple[str, ...]; remediation_stage: LifecycleState; artifact_reference: str | None
@dataclass(frozen=True)
class GateResult:
    verdict: GateVerdict; outcome: GateOutcome; blocking_findings: tuple[str, ...]; warnings: tuple[str, ...]; required_checks_summary: str; evidence_summary: str; semantic_confirmed: bool; apply_authorized: bool; policy_version: str; coverage_status: CoverageStatus = CoverageStatus.COMPATIBILITY; capability_preservation: CapabilityPreservationStatus | None = None
