"""Immutable records exchanged by the skill-engineering pipeline."""
from dataclasses import dataclass
from enum import StrEnum


class Intent(StrEnum):
    CREATE = "CREATE"; MODIFY = "MODIFY"; FIX = "FIX"; AUDIT_ONLY = "AUDIT_ONLY"; AUDIT_OPTIMIZE = "AUDIT_OPTIMIZE"
class LifecycleState(StrEnum):
    DISCOVERED = "DISCOVERED"; CLASSIFIED = "CLASSIFIED"; MECHANISM_SELECTED = "MECHANISM_SELECTED"; STAGED = "STAGED"; AUDITED = "AUDITED"; VALIDATED = "VALIDATED"; GATE_FAILED = "GATE_FAILED"; GATE_PASSED = "GATE_PASSED"; PUBLISHED = "PUBLISHED"; UNCHANGED_VALIDATED = "UNCHANGED_VALIDATED"; UNCHANGED_BLOCKED = "UNCHANGED_BLOCKED"
class PrimaryIssueClass(StrEnum):
    IMPLEMENTATION_DEFECT = "IMPLEMENTATION_DEFECT"; ENVIRONMENT_COMPATIBILITY = "ENVIRONMENT_COMPATIBILITY"; WORKFLOW_DESIGN_DEFECT = "WORKFLOW_DESIGN_DEFECT"; CONTRACT_ENFORCEMENT_GAP = "CONTRACT_ENFORCEMENT_GAP"; CAPABILITY_INVARIANT_CHANGE = "CAPABILITY_INVARIANT_CHANGE"; TASK_LOCAL_PREFERENCE = "TASK_LOCAL_PREFERENCE"; DOCUMENTATION_GAP = "DOCUMENTATION_GAP"; NO_DEFECT = "NO_DEFECT"; INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
class ControlGap(StrEnum):
    IMPLEMENTATION_GAP = "IMPLEMENTATION_GAP"; SCHEMA_MISSING = "SCHEMA_MISSING"; VALIDATOR_MISSING = "VALIDATOR_MISSING"; ENV_DETECTION_MISSING = "ENV_DETECTION_MISSING"; REGRESSION_MISSING = "REGRESSION_MISSING"; WORKFLOW_CONTROL_MISSING = "WORKFLOW_CONTROL_MISSING"; INSTRUCTION_GAP = "INSTRUCTION_GAP"; NONE = "NONE"
class RegressionDisposition(StrEnum): REQUIRED = "REQUIRED"; RECOMMENDED = "RECOMMENDED"; NOT_APPLICABLE = "NOT_APPLICABLE"
class CheckStatus(StrEnum): PASS = "PASS"; WARN = "WARN"; FAIL = "FAIL"; SKIP = "SKIP"; ERROR = "ERROR"; NOT_EXECUTED = "NOT_EXECUTED"
class GateVerdict(StrEnum): PASS = "PASS"; FAIL = "FAIL"
class GateOutcome(StrEnum): READY_TO_PUBLISH = "READY_TO_PUBLISH"; UNCHANGED_VALIDATED = "UNCHANGED_VALIDATED"; UNCHANGED_BLOCKED = "UNCHANGED_BLOCKED"; REMEDIATION_REQUIRED = "REMEDIATION_REQUIRED"
class ProviderStatus(StrEnum): AVAILABLE = "AVAILABLE"; UNAVAILABLE = "UNAVAILABLE"; INVALID_OUTPUT = "INVALID_OUTPUT"; TIMEOUT = "TIMEOUT"; INCOMPATIBLE = "INCOMPATIBLE"; DEGRADED = "DEGRADED"

@dataclass(frozen=True)
class ArtifactManifest:
    intent: Intent; artifact_root: str; skill_name: str; source_revision: str | None; source_digest: str | None; files: tuple[str, ...]; executable_assets: tuple[str, ...]; required_references: tuple[str, ...]; test_inventory: tuple[str, ...]; content_digest: str
@dataclass(frozen=True)
class DecisionRecord:
    intent: Intent; primary_issue_class: PrimaryIssueClass; control_gaps: tuple[ControlGap, ...]; regression_disposition: RegressionDisposition; root_cause: str | None; evidence_limitations: tuple[str, ...]; selected_mechanisms: tuple[str, ...]; rejected_mechanisms: tuple[str, ...]; prompt_rule_justification: str | None; decided_by: str = "CODEX"
@dataclass(frozen=True)
class SemanticConfirmation:
    artifact_digest: str; rationale: str; confirmed_by: str = "CODEX"
@dataclass(frozen=True)
class ProviderDescriptor:
    provider_id: str; source_identity: str; revision_or_version: str | None; capability: str; availability: ProviderStatus; invocation_adapter: str; limitations: tuple[str, ...]; fallback_provider: str | None
@dataclass(frozen=True)
class ProviderResult:
    provider_id: str; capability: str; provider_status: ProviderStatus; findings: tuple[str, ...]; candidate_changes: tuple[str, ...]; evidence: tuple[str, ...]; limitations: tuple[str, ...]; fallback_used: bool
@dataclass(frozen=True)
class CheckResult:
    check_id: str; source: str; subject: str; required: bool; status: CheckStatus; deterministic: bool; reproducible: bool; confidence: float; evidence: tuple[str, ...]; remediation_stage: LifecycleState; artifact_reference: str | None
@dataclass(frozen=True)
class GateResult:
    verdict: GateVerdict; outcome: GateOutcome; blocking_findings: tuple[str, ...]; warnings: tuple[str, ...]; required_checks_summary: str; evidence_summary: str; semantic_confirmed: bool; publish_authorized: bool; policy_version: str
