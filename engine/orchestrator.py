"""Phased deterministic support for Codex-led Skill engineering."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from engine.contracts import validate_contract
from engine.diagnostics import validate_classification
from engine.evidence import EvidenceCollector
from engine.inventory import build_artifact_manifest, digest_tree, snapshot_tree
from engine.mechanism_selection import validate_mechanism_selection
from engine.models import (
    ArtifactAssessment, ArtifactManifest, AuditExecution, CheckResult, CheckStatus,
    DecisionRecord, DirectorySnapshot, GateOutcome, GateResult, GateVerdict, Intent,
    LifecycleState, PrimaryIssueClass, ProviderEvidence, ProviderResult, ProviderStatus,
    RegressionDisposition, SemanticConfirmation,
)
from engine.providers import (
    AUDIT_SKILL, CAPABILITIES, CHECK_SKILL_CONFORMANCE, ProviderGateway,
)
from engine.quality_gate import GateContext, adjudicate, load_gate_policy
from engine.rule_bloat import RuleFinding, detect_rule_bloat, extract_rule_units
from engine.rule_governance import (
    GovernanceDecision, governance_evidence, signal_evidence,
    validate_governance_decisions,
)
from engine.workspace import PublishResult, WorkspaceDiff, WorkspaceSession, publish_atomic
from validators.reference_integrity import validate_references
from validators.skill_structure import validate_skill_structure


TOOL_SCHEMA_VERSION = "2.0"


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
    publish_requested: bool = False


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
    created_at: str
    tool_schema_version: str
    lifecycle_state: LifecycleState = LifecycleState.INSPECTED


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
    workspace_diff: WorkspaceDiff
    checks_fingerprint: str
    authorized_to_modify: bool
    publish_requested: bool
    project_policy: Path | None
    pending_semantic_confirmation: bool = True
    gate_result: GateResult | None = None
    audit_execution: AuditExecution | None = None
    artifact_assessment: ArtifactAssessment | None = None
    lifecycle_state: LifecycleState = LifecycleState.VALIDATED_PENDING_CONFIRMATION


@dataclass(frozen=True)
class EngineeringOutcome:
    outcome_type: str
    artifact_path: Path
    gate_result: GateResult
    minimal_blocking_findings: tuple[dict[str, str], ...]
    workspace_diff: WorkspaceDiff
    publication_session: WorkspaceSession | None
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
                 provider_gateway: ProviderGateway | None = None) -> None:
        self.state_history: list[LifecycleState] = []
        self._state_observer = state_observer
        self._provider_gateway = provider_gateway

    def _record(self, state: LifecycleState) -> None:
        self.state_history.append(state)
        if self._state_observer is not None:
            self._state_observer(state)

    def inspect(self, mode: Intent, source: Path | None) -> InspectionBundle:
        if not isinstance(mode, Intent):
            raise ValueError("mode must be explicitly supplied")
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
        providers = _inspect_provider_evidence(
            self._provider_gateway, source.name if source is not None else "new-skill"
        )
        return InspectionBundle(
            str(uuid4()), mode, source, manifest, snapshot, baseline_digest, signals,
            findings, tuple(item.finding_id for item in findings),
            tuple(sorted(CAPABILITIES)), providers, datetime.now(UTC).isoformat(),
            TOOL_SCHEMA_VERSION,
        )

    def validate(self, inspection: InspectionBundle, decision: DecisionRecord,
                 governance_decisions: tuple[GovernanceDecision, ...], *,
                 candidate: Path | None, target_parent: Path,
                 authorized_to_modify: bool,
                 behavioral_runner: Callable[[Path], CheckResult] | None = None,
                 regression_runner: Callable[[Path], CheckResult] | None = None,
                 publish_requested: bool = False,
                 project_policy: Path | None = None) -> ValidationBundle:
        _validate_inspection(inspection)
        _validate_decision(decision, inspection.mode)
        _verify_inspection_fresh(inspection)
        governed = validate_governance_decisions(inspection.findings, governance_decisions)
        actionable = {item.finding_id for item in inspection.findings if item.confidence > 0}
        decided = {item.finding_id for item in governed}
        if missing := sorted(actionable - decided):
            raise ValueError("missing governance decisions: " + ", ".join(missing))

        target_parent = target_parent.resolve(strict=True)
        session = _session_for_inspection(inspection)
        read_only_validation = inspection.mode is Intent.AUDIT_ONLY or (
            inspection.mode is Intent.AUDIT_OPTIMIZE and candidate is None
        )
        if read_only_validation:
            if candidate is not None:
                raise ValueError("Audit Only cannot accept a publishable candidate")
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
        source_checks: list[bool] = []
        try:
            if behavioral_runner is not None:
                commands.append(behavioral_runner(execution_artifact))
                if inspection.mode is Intent.AUDIT_ONLY:
                    source_checks.append(session.verify_source_unchanged())
            elif inspection.mode is Intent.CREATE:
                commands.append(_missing_behavioral_check(execution_artifact.name))
            if decision.regression_disposition is RegressionDisposition.REQUIRED:
                if regression_runner is None:
                    commands.append(_missing_regression_check(execution_artifact.name))
                else:
                    commands.append(regression_runner(execution_artifact))
                    if inspection.mode is Intent.AUDIT_ONLY:
                        source_checks.append(session.verify_source_unchanged())
            if inspection.mode is Intent.AUDIT_ONLY:
                source_checks.append(session.verify_source_unchanged())

            manifest = build_artifact_manifest(artifact, inspection.mode, inspection.baseline_digest)
            evidence = (
                validate_skill_structure(manifest) + validate_references(manifest)
                + tuple(commands) + inspection.signals + governance_evidence(governed)
            )
            if decision.primary_issue_class is PrimaryIssueClass.INSUFFICIENT_EVIDENCE:
                evidence += (_diagnostic_failure(manifest.skill_name),)
            if inspection.mode is Intent.AUDIT_ONLY:
                evidence += (_source_integrity_evidence(session, source_checks),)
            collector = EvidenceCollector()
            for item in evidence:
                collector.add(item)
            deterministic = collector.snapshot()
            advisory = tuple(_provider_evidence_to_check(item, manifest.skill_name)
                             for item in inspection.provider_evidence)
            diff = session.source_diff() if inspection.mode is Intent.AUDIT_ONLY else session.diff(artifact)
            audit_execution = None
            assessment = None
            if inspection.mode is Intent.AUDIT_ONLY:
                audit_execution = (
                    AuditExecution.COMPLETE
                    if all(source_checks) and all(item.status is CheckStatus.PASS for item in commands)
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
            governed, deterministic, advisory, diff,
            _checks_fingerprint(deterministic, advisory), authorized_to_modify,
            publish_requested, project_policy, audit_execution=audit_execution,
            artifact_assessment=assessment,
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
                validation.project_policy, deterministic,
                validation.advisory_evidence,
            )
            lifecycle = _audit_terminal_state(audit_execution, assessment)
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
                    semantic_confirmed, validation.publish_requested,
                ), evidence, policy=load_gate_policy(validation.project_policy),
            )
            if gate.verdict is GateVerdict.FAIL:
                self._record(LifecycleState.GATE_FAILED)
                raise PipelineBlockedError(gate, validation.artifact_path,
                                           validation.workspace_diff, evidence)
            session = (
                _publication_session(validation, confirmation)
                if gate.publish_authorized else None
            )
            lifecycle = (LifecycleState.READY_TO_PUBLISH
                         if gate.outcome is GateOutcome.READY_TO_PUBLISH
                         else LifecycleState.VALIDATED)
            findings = ()
            outcome_type = "Validated Complete Skill"
        self._record(lifecycle)
        return EngineeringOutcome(
            outcome_type, validation.artifact_path, gate, findings,
            _current_source_diff(validation) if validation.intent is Intent.AUDIT_ONLY
            else validation.workspace_diff,
            session if gate.publish_authorized else None, evidence,
            deterministic, validation.advisory_evidence,
            audit_execution, assessment, lifecycle, validation, confirmation,
        )

    def run(self, request: EngineeringRequest) -> EngineeringOutcome:
        _validate_compatibility_request(request)
        inspection = self.inspect(request.intent, request.source)
        validation = self.validate(
            inspection, request.decision, request.governance_decisions,
            candidate=request.candidate, target_parent=request.target_parent,
            authorized_to_modify=request.authorized_to_modify,
            behavioral_runner=request.behavioral_runner,
            regression_runner=request.regression_runner,
            publish_requested=request.publish_requested,
            project_policy=request.project_policy,
        )
        confirmation = request.semantic_confirmation or SemanticConfirmation(
            "missing", "No Codex confirmation was supplied", "MISSING"
        )
        return self.confirm(validation, confirmation)


def publish(outcome: EngineeringOutcome) -> PublishResult:
    if outcome.publication_session is None:
        raise ValueError("outcome has no publication-ready workspace")
    return publish_atomic(outcome.publication_session, outcome.gate_result)


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


def _inspect_provider_evidence(gateway: ProviderGateway | None,
                               subject: str) -> tuple[ProviderEvidence, ...]:
    records: list[ProviderEvidence] = []
    invoked = {AUDIT_SKILL, CHECK_SKILL_CONFORMANCE}
    for capability in sorted(CAPABILITIES):
        if gateway is None or capability not in invoked:
            records.append(ProviderEvidence(
                f"optional.none.{capability.lower()}", capability, "INSPECT",
                CheckStatus.NOT_EXECUTED,
                "optional Provider was not requested or available",
            ))
        else:
            records.append(_provider_record(
                gateway.invoke(capability, {"subject": subject}, formal_run=True),
                "INSPECT",
            ))
    return tuple(records)


def _provider_record(result: ProviderResult, phase: str) -> ProviderEvidence:
    unavailable = {ProviderStatus.UNAVAILABLE, ProviderStatus.INVALID_OUTPUT,
                   ProviderStatus.TIMEOUT, ProviderStatus.INCOMPATIBLE}
    status = (CheckStatus.NOT_EXECUTED if result.provider_status in unavailable
              else CheckStatus.WARN if result.provider_status is ProviderStatus.DEGRADED
              or result.findings else CheckStatus.PASS)
    summary = "; ".join((*result.findings, *result.evidence, *result.limitations))
    return ProviderEvidence(result.provider_id, result.capability, phase, status,
                            summary or "provider returned no details")


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
                deterministic: tuple[CheckResult, ...] = (),
                advisory: tuple[CheckResult, ...] = ()) -> GateResult:
    policy_version = str(load_gate_policy(project_policy)["policy_version"])
    if execution is not AuditExecution.COMPLETE or not semantic_confirmed:
        return GateResult(
            GateVerdict.FAIL, GateOutcome.AUDIT_INCOMPLETE,
            ("B10: Audit execution is incomplete or source integrity is untrusted",
             "B12: Codex semantic confirmation for the validated artifact is absent"),
            (), "Audit execution incomplete.", "Artifact assessment is UNKNOWN.",
            False, False, policy_version,
        )
    outcome = {
        ArtifactAssessment.VALID: GateOutcome.AUDIT_COMPLETE_VALID,
        ArtifactAssessment.FINDINGS: GateOutcome.AUDIT_COMPLETE_FINDINGS,
        ArtifactAssessment.BLOCKING_FINDINGS: GateOutcome.AUDIT_COMPLETE_BLOCKING_FINDINGS,
    }[assessment]
    warnings = tuple(
        detail
        for item in (*deterministic, *advisory)
        if item.status in {CheckStatus.WARN, CheckStatus.FAIL}
        for detail in (f"{item.check_id}: {'; '.join(item.evidence)}",)
    )
    if assessment is not ArtifactAssessment.VALID:
        warnings += (f"artifact_assessment={assessment.value}",)
    return GateResult(GateVerdict.PASS, outcome, (), warnings,
                      "Audit execution complete.",
                      f"Artifact assessment is {assessment.value}.", True, False,
                      policy_version)


def _audit_terminal_state(execution: AuditExecution | None,
                          assessment: ArtifactAssessment | None) -> LifecycleState:
    if execution is not AuditExecution.COMPLETE:
        return LifecycleState.AUDIT_INCOMPLETE
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


def _publication_session(validation: ValidationBundle,
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
