"""Deterministic workspace, evidence, and release support for Codex Skill work."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from engine.diagnostics import validate_classification
from engine.contracts import validate_contract
from engine.evidence import EvidenceCollector
from engine.inventory import build_artifact_manifest
from engine.mechanism_selection import validate_mechanism_selection
from engine.models import (
    CheckResult,
    CheckStatus,
    DecisionRecord,
    GateResult,
    Intent,
    LifecycleState,
    PrimaryIssueClass,
    RegressionDisposition,
    SemanticConfirmation,
)
from engine.providers import AUDIT_SKILL, ProviderGateway, provider_result_to_check_result
from engine.quality_gate import GateContext, adjudicate, load_gate_policy
from engine.rule_bloat import detect_rule_bloat, extract_rule_units
from engine.rule_governance import (
    GovernanceDecision,
    governance_evidence,
    signal_evidence,
    validate_governance_decisions,
)
from engine.state_machine import TransitionContext, transition
from engine.workspace import PublishResult, WorkspaceDiff, WorkspaceSession, publish_atomic
from validators.reference_integrity import validate_references
from validators.skill_structure import validate_skill_structure


@dataclass(frozen=True)
class EngineeringRequest:
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
class EngineeringOutcome:
    outcome_type: str
    artifact_path: Path
    gate_result: GateResult
    minimal_blocking_findings: tuple[dict[str, str], ...]
    workspace_diff: WorkspaceDiff
    publication_session: WorkspaceSession | None
    evidence: tuple[CheckResult, ...] = ()


class PipelineBlockedError(RuntimeError):
    def __init__(
        self,
        gate_result: GateResult,
        artifact_path: Path | None = None,
        workspace_diff: WorkspaceDiff | None = None,
        evidence: tuple[CheckResult, ...] = (),
    ) -> None:
        super().__init__("Skill engineering pipeline blocked by the Quality Gate")
        self.gate_result = gate_result
        self.artifact_path = artifact_path
        self.workspace_diff = workspace_diff
        self.evidence = evidence


class PipelineOrchestrator:
    """Run deterministic stages around decisions and candidate content supplied by Codex."""

    def __init__(
        self,
        state_observer: Callable[[LifecycleState], None] | None = None,
        provider_gateway: ProviderGateway | None = None,
    ) -> None:
        self.state_history: list[LifecycleState] = []
        self._state_observer = state_observer
        self._provider_gateway = provider_gateway

    def _record(self, state: LifecycleState) -> None:
        self.state_history.append(state)
        if self._state_observer is not None:
            self._state_observer(state)

    def _move(
        self,
        state: LifecycleState,
        target: LifecycleState,
        request: EngineeringRequest,
        session: WorkspaceSession,
        *,
        modification_needed: bool = False,
    ) -> LifecycleState:
        state = transition(
            state,
            target,
            _context(request, session, modification_needed=modification_needed),
        )
        self._record(state)
        return state

    def run(self, request: EngineeringRequest) -> EngineeringOutcome:
        _validate_request(request)
        decision = validate_mechanism_selection(request.decision)
        self.state_history.clear()
        self._record(LifecycleState.DISCOVERED)
        session = _session_for(request)
        state = LifecycleState.DISCOVERED

        if request.intent is Intent.AUDIT_ONLY:
            artifact = request.source
            state = self._move(state, LifecycleState.AUDITED, request, session)
            state = self._move(state, LifecycleState.CLASSIFIED, request, session)
            state = self._move(state, LifecycleState.MECHANISM_SELECTED, request, session)
            state = self._move(state, LifecycleState.AUDITED, request, session)
        elif request.intent is Intent.AUDIT_OPTIMIZE:
            artifact = request.source
            state = self._move(state, LifecycleState.AUDITED, request, session)
            state = self._move(state, LifecycleState.CLASSIFIED, request, session)
            state = self._move(state, LifecycleState.MECHANISM_SELECTED, request, session)
            if request.candidate is not None:
                artifact = session.stage_candidate(request.candidate, request.target_parent)
                state = self._move(state, LifecycleState.STAGED, request, session, modification_needed=True)
                state = self._move(state, LifecycleState.AUDITED, request, session, modification_needed=True)
            else:
                state = self._move(state, LifecycleState.AUDITED, request, session)
        else:
            artifact = session.stage_candidate(request.candidate, request.target_parent)
            state = self._move(state, LifecycleState.STAGED, request, session, modification_needed=True)
            state = self._move(state, LifecycleState.CLASSIFIED, request, session, modification_needed=True)
            state = self._move(state, LifecycleState.MECHANISM_SELECTED, request, session, modification_needed=True)
            state = self._move(state, LifecycleState.AUDITED, request, session, modification_needed=True)

        if artifact is None:
            raise ValueError("artifact is required")
        manifest = build_artifact_manifest(artifact, request.intent, session.source_digest)
        evidence = validate_skill_structure(manifest) + validate_references(manifest)
        if request.behavioral_runner is not None:
            evidence += (request.behavioral_runner(artifact),)
        elif request.intent is Intent.CREATE:
            evidence += (_missing_behavioral_check(manifest.skill_name),)
        if decision.regression_disposition is RegressionDisposition.REQUIRED and request.regression_runner is not None:
            evidence += (request.regression_runner(artifact),)
        elif decision.regression_disposition is RegressionDisposition.REQUIRED:
            evidence += (_missing_regression_check(manifest.skill_name),)
        rule_findings = detect_rule_bloat(extract_rule_units(artifact), history=None)
        evidence += signal_evidence(rule_findings)
        validated_governance = validate_governance_decisions(rule_findings, request.governance_decisions)
        evidence += governance_evidence(validated_governance)
        if request.candidate is not None:
            evidence += (_governance_coverage(rule_findings, validated_governance, manifest.skill_name),)
        if decision.primary_issue_class is PrimaryIssueClass.INSUFFICIENT_EVIDENCE:
            evidence += (_diagnostic_failure(manifest.skill_name),)

        collector = EvidenceCollector()
        for result in evidence:
            collector.add(result)
        if self._provider_gateway is not None:
            provider_result = self._provider_gateway.invoke(
                AUDIT_SKILL, {"subject": manifest.skill_name}, formal_run=True
            )
            collector.add(provider_result_to_check_result(provider_result, subject=manifest.skill_name))
        evidence = collector.snapshot()
        state = self._move(
            state,
            LifecycleState.VALIDATED,
            request,
            session,
            modification_needed=request.candidate is not None,
        )
        semantic_confirmed = _semantic_confirmation_matches(
            request.semantic_confirmation, manifest.content_digest
        )
        candidate_requires_publish = request.candidate is not None
        gate = adjudicate(
            GateContext(
                intent=request.intent,
                state=LifecycleState.VALIDATED,
                authorized_to_modify=request.authorized_to_modify,
                candidate_requires_publish=candidate_requires_publish,
                workspace_publishable=session.staging is not None,
                decision=decision,
                semantic_confirmed=semantic_confirmed,
                publish_requested=request.publish_requested,
            ),
            evidence,
            policy=load_gate_policy(request.project_policy),
        )
        target = LifecycleState.GATE_PASSED if gate.verdict.value == "PASS" else LifecycleState.GATE_FAILED
        self._move(state, target, request, session, modification_needed=candidate_requires_publish)
        workspace_diff = session.diff(artifact)

        if gate.verdict.value == "FAIL":
            if request.intent is Intent.AUDIT_ONLY:
                return _audit_failure(request.source, gate, workspace_diff, evidence)
            raise PipelineBlockedError(gate, artifact, workspace_diff, evidence)
        if session.staging is not None:
            session.bind_confirmed_artifact(artifact, manifest.content_digest)
        return EngineeringOutcome(
            "Validated Complete Skill",
            artifact,
            gate,
            (),
            workspace_diff,
            session if gate.publish_authorized else None,
            evidence,
        )


def publish(outcome: EngineeringOutcome) -> PublishResult:
    """Perform the separately requested atomic publication of a ready outcome."""
    if outcome.publication_session is None:
        raise ValueError("outcome has no publication-ready workspace")
    return publish_atomic(outcome.publication_session, outcome.gate_result)


def _validate_request(request: EngineeringRequest) -> None:
    if not isinstance(request.intent, Intent):
        raise ValueError("intent must be explicitly supplied by Codex")
    if request.decision.intent is not request.intent:
        raise ValueError("DecisionRecord intent must match the explicit request intent")
    validate_classification(request.decision)
    if not request.requirement.strip():
        raise ValueError("requirement must be nonblank")
    if request.intent is Intent.CREATE:
        if request.source is not None:
            raise ValueError("Create does not accept a source Skill")
    elif request.source is None:
        raise ValueError(f"{request.intent.value} requires a source Skill")
    if request.intent is Intent.AUDIT_ONLY and request.candidate is not None:
        raise ValueError("Audit Only cannot accept a candidate")
    if request.intent in {Intent.CREATE, Intent.MODIFY, Intent.FIX}:
        if request.candidate is None:
            raise ValueError("Codex must supply a complete candidate for this mode")
        if not request.authorized_to_modify:
            raise ValueError("candidate staging requires modification authorization")
    if request.intent is Intent.AUDIT_OPTIMIZE and request.candidate is not None and not request.authorized_to_modify:
        raise ValueError("Audit + Optimize candidate staging requires modification authorization")
    if not request.target_parent.exists() or not request.target_parent.is_dir():
        raise ValueError("target parent must be an existing directory")
    if request.candidate is not None:
        published_name = (
            request.candidate.name if request.intent is Intent.CREATE else request.source.name
        )
        publish_target = request.target_parent.resolve(strict=False) / published_name
        if request.candidate.resolve(strict=False) == publish_target:
            raise ValueError("candidate must be outside its publication destination")


def _session_for(request: EngineeringRequest) -> WorkspaceSession:
    if request.intent is Intent.CREATE:
        return WorkspaceSession.for_create()
    return WorkspaceSession.for_existing(request.intent, request.source)


def _context(
    request: EngineeringRequest,
    session: WorkspaceSession,
    *,
    modification_needed: bool = False,
) -> TransitionContext:
    return TransitionContext(
        intent=request.intent,
        authorized_to_modify=request.authorized_to_modify,
        defect_found=bool(request.failure_evidence),
        staging_exists=session.staging is not None,
        audit_cycle=0,
        validation_cycle=0,
        modification_needed=modification_needed,
    )


def _semantic_confirmation_matches(
    confirmation: SemanticConfirmation | None, artifact_digest: str
) -> bool:
    if confirmation is None:
        return False
    try:
        validate_contract("semantic-confirmation", asdict(confirmation))
    except Exception:
        return False
    return confirmation.artifact_digest == artifact_digest


def _governance_coverage(
    findings: tuple[object, ...],
    decisions: tuple[GovernanceDecision, ...],
    subject: str,
) -> CheckResult:
    actionable = {finding.finding_id for finding in findings if finding.confidence > 0}
    decided = {decision.finding_id for decision in decisions}
    missing = tuple(sorted(actionable - decided))
    status = CheckStatus.FAIL if missing else CheckStatus.PASS
    message = (
        "missing Codex governance decisions: " + ", ".join(missing)
        if missing
        else "Codex supplied decisions for every actionable rule signal"
    )
    return CheckResult(
        "governance.coverage", "codex.governance", subject, True, status,
        True, True, 1.0, (message,), LifecycleState.VALIDATED, subject,
    )


def _diagnostic_failure(subject: str) -> CheckResult:
    return CheckResult(
        "diagnostic.evidence", "codex.diagnostics", subject, True,
        CheckStatus.FAIL, True, True, 1.0,
        ("Codex recorded insufficient failure evidence",),
        LifecycleState.VALIDATED, subject,
    )


def _missing_behavioral_check(subject: str) -> CheckResult:
    return CheckResult(
        "behavioral.create", "behavioral.runner", subject, True,
        CheckStatus.NOT_EXECUTED, True, True, 1.0,
        ("No Create behavioral test was executed",),
        LifecycleState.VALIDATED, subject,
    )


def _missing_regression_check(subject: str) -> CheckResult:
    return CheckResult(
        "B07", "regression.runner", subject, True,
        CheckStatus.NOT_EXECUTED, True, True, 1.0,
        ("Required regression command was not supplied",),
        LifecycleState.VALIDATED, subject,
    )


def _audit_failure(
    source: Path | None,
    gate: GateResult,
    workspace_diff: WorkspaceDiff,
    evidence: tuple[CheckResult, ...],
) -> EngineeringOutcome:
    if source is None:
        raise ValueError("Audit Only failure requires a source Skill")
    findings = tuple(
        {
            "finding_id": finding.split(":", 1)[0].strip(),
            "affected_path": str(source),
            "blocking_reason": finding,
            "required_next_action": "Codex must address or explicitly resolve the blocking evidence",
        }
        for finding in gate.blocking_findings
    )
    return EngineeringOutcome(
        "Unchanged Skill + Minimal Blocking Findings",
        source,
        gate,
        findings,
        workspace_diff,
        None,
        evidence,
    )
