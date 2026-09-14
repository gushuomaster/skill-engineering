"""Minimal internal-only governance loop for Skill engineering."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from engine.diagnostics import validate_classification
from engine.evidence import EvidenceCollector
from engine.mechanism_selection import select_mechanisms
from engine.models import (
    CheckResult,
    CheckStatus,
    ControlGap,
    DecisionRecord,
    GateResult,
    Intent,
    LifecycleState,
    PrimaryIssueClass,
    RegressionDisposition,
)
from engine.quality_gate import GateContext, adjudicate, load_gate_policy
from engine.providers import AUDIT_SKILL, ProviderGateway, provider_result_to_check_result
from engine.state_machine import TransitionContext, transition
from engine.workspace import WorkspaceSession, publish_atomic
from engine.inventory import build_artifact_manifest
from engine.rule_bloat import detect_rule_bloat, extract_rule_units
from engine.rule_governance import governance_evidence, govern_findings
from validators.reference_integrity import validate_references
from validators.skill_structure import validate_skill_structure


@dataclass(frozen=True)
class EngineeringRequest:
    requirement: str
    intent: Intent | None
    source: Path | None
    failure_evidence: tuple[str, ...]
    authorized_to_modify: bool
    target_parent: Path
    project_policy: Path | None = None
    regression_runner: Callable[[Path], CheckResult] | None = None


@dataclass(frozen=True)
class EngineeringOutcome:
    outcome_type: str
    artifact_path: Path
    gate_result: GateResult
    minimal_blocking_findings: tuple[dict[str, str], ...]


class PipelineBlockedError(RuntimeError):
    def __init__(self, gate_result: GateResult) -> None:
        super().__init__("Skill engineering pipeline blocked by the Quality Gate")
        self.gate_result = gate_result


class PipelineOrchestrator:
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

    def _move(self, state: LifecycleState, target: LifecycleState, context: TransitionContext) -> LifecycleState:
        state = transition(state, target, context)
        self._record(state)
        return state

    def run(self, request: EngineeringRequest) -> EngineeringOutcome:
        intent = request.intent or _detect_intent(request)
        _validate_request(intent, request)
        self.state_history.clear()
        self._record(LifecycleState.DISCOVERED)
        session = _session_for(intent, request)
        if intent in {Intent.CREATE, Intent.MODIFY, Intent.FIX} and not request.authorized_to_modify:
            raise PipelineBlockedError(_blocked_gate(intent, request))
        staging_allowed = request.authorized_to_modify and intent is not Intent.AUDIT_ONLY
        if intent in {Intent.CREATE, Intent.MODIFY, Intent.FIX} and staging_allowed:
            session.prepare(request.target_parent)
            if intent in {Intent.MODIFY, Intent.FIX} and session.staging is not None:
                renamed = session.staging.with_name("staged-skill")
                session.staging.rename(renamed)
                session.staging = renamed
                skill_md = renamed / "SKILL.md"
                if skill_md.is_file():
                    text = skill_md.read_text(encoding="utf-8")
                    text = re.sub(r"(?m)^name:\s*[^\r\n]+", "name: staged-skill", text, count=1)
                    skill_md.write_text(text, encoding="utf-8")
            state = self._move(
                LifecycleState.DISCOVERED,
                LifecycleState.STAGED,
                _context(intent, request, staging_exists=session.staging is not None),
            )
        else:
            state = LifecycleState.DISCOVERED

        if intent is Intent.CREATE:
            if session.staging is None:
                gate = _blocked_gate(intent, request)
                raise PipelineBlockedError(gate)
            artifact = _write_internal_candidate(session.staging, request.requirement)
        else:
            artifact = session.staging if session.staging is not None else session.source

        decision = _make_decision(intent, request)
        if state is LifecycleState.DISCOVERED:
            state = self._move(
                state,
                LifecycleState.AUDITED if intent is Intent.AUDIT_ONLY else LifecycleState.CLASSIFIED,
                _context(intent, request, staging_exists=session.staging is not None),
            )
        elif state is LifecycleState.STAGED:
            state = self._move(
                state, LifecycleState.CLASSIFIED,
                _context(intent, request, staging_exists=session.staging is not None),
            )
        if intent is Intent.AUDIT_ONLY:
            state = self._move(
                state,
                LifecycleState.CLASSIFIED,
                _context(intent, request, staging_exists=False),
            )
        validate_classification(decision)
        decision = select_mechanisms(decision)
        state = self._move(state, LifecycleState.MECHANISM_SELECTED,
                           _context(intent, request, staging_exists=session.staging is not None))
        if intent is Intent.AUDIT_ONLY:
            state = self._move(state, LifecycleState.AUDITED,
                               _context(intent, request, staging_exists=False))

        effective_policy = load_gate_policy(request.project_policy)
        optimization_needed = intent is Intent.AUDIT_OPTIMIZE and bool(request.failure_evidence)
        gate, state = self._audit_and_gate(
            intent, request, session, artifact, decision, state, effective_policy,
            defer_gate_transition=optimization_needed,
        )
        if intent is Intent.AUDIT_OPTIMIZE and optimization_needed and request.authorized_to_modify:
            session.prepare_optimization(
                request.target_parent,
                modification_needed=True,
                authorized_to_modify=request.authorized_to_modify,
            )
            if session.staging is not None:
                renamed = session.staging.with_name("staged-skill")
                session.staging.rename(renamed)
                session.staging = renamed
                skill_md = renamed / "SKILL.md"
                if skill_md.is_file():
                    text = skill_md.read_text(encoding="utf-8")
                    text = re.sub(r"(?m)^name:\s*[^\r\n]+", "name: staged-skill", text, count=1)
                    skill_md.write_text(text, encoding="utf-8")
            artifact = session.staging
            state = self._move(
                state,
                LifecycleState.STAGED,
                _context(intent, request, staging_exists=True, modification_needed=True),
            )
            state = self._move(
                state,
                LifecycleState.CLASSIFIED,
                _context(intent, request, staging_exists=True, modification_needed=True),
            )
            state = self._move(
                state,
                LifecycleState.MECHANISM_SELECTED,
                _context(intent, request, staging_exists=True, modification_needed=True),
            )
            gate, state = self._audit_and_gate(
                intent, request, session, artifact, decision, state, effective_policy,
                candidate_requires_publish=True,
            )

        if gate.verdict.value == "FAIL":
            if intent is Intent.AUDIT_ONLY:
                from engine.output import project_audit_failure

                return project_audit_failure(request.source, gate)
            raise PipelineBlockedError(gate)
        if gate.publish_authorized and gate.outcome.value == "READY_TO_PUBLISH":
            publish_atomic(session, gate)
            self._record(LifecycleState.PUBLISHED)
        from engine.output import project_validated

        output_path = (
            request.source
            if intent is Intent.AUDIT_ONLY
            or decision.primary_issue_class is PrimaryIssueClass.TASK_LOCAL_PREFERENCE
            else (artifact or request.source)
        )
        return project_validated(output_path, gate)

    def _audit_and_gate(
        self,
        intent: Intent,
        request: EngineeringRequest,
        session: WorkspaceSession,
        artifact: Path | None,
        decision: DecisionRecord,
        state: LifecycleState,
        policy: dict[str, object],
        *,
        candidate_requires_publish: bool | None = None,
        defer_gate_transition: bool = False,
    ) -> tuple[GateResult, LifecycleState]:
        if artifact is None:
            gate = _blocked_gate(intent, request, decision=decision, policy=policy)
            return gate, state
        manifest = build_artifact_manifest(artifact, intent, session.source_digest)
        evidence = validate_skill_structure(manifest) + validate_references(manifest)
        if decision.regression_disposition is RegressionDisposition.REQUIRED and request.regression_runner is not None:
            evidence += (request.regression_runner(artifact),)
        rule_units = extract_rule_units(artifact)
        rule_findings = detect_rule_bloat(rule_units, history=None)
        governance = govern_findings(rule_findings, decision.selected_mechanisms)
        evidence += governance_evidence(governance)
        if decision.primary_issue_class is PrimaryIssueClass.INSUFFICIENT_EVIDENCE:
            evidence += (_diagnostic_failure(manifest.skill_name),)
        collector = EvidenceCollector()
        for result in evidence:
            collector.add(result)
        if self._provider_gateway is not None:
            provider_result = self._provider_gateway.invoke(
                AUDIT_SKILL,
                {"subject": manifest.skill_name},
                formal_run=True,
            )
            collector.add(
                provider_result_to_check_result(
                    provider_result,
                    subject=manifest.skill_name,
                )
            )
        evidence = collector.snapshot()
        state = self._move(
            state,
            LifecycleState.AUDITED,
            _context(intent, request, staging_exists=session.staging is not None),
        ) if state is not LifecycleState.AUDITED else state
        if defer_gate_transition:
            return _deferred_adjudication(intent, request, decision, evidence, policy), state
        state = self._move(
            state, LifecycleState.VALIDATED,
            _context(intent, request, staging_exists=session.staging is not None),
        )
        publish = (
            candidate_requires_publish
            if candidate_requires_publish is not None
            else intent in {Intent.CREATE, Intent.MODIFY, Intent.FIX}
            and request.authorized_to_modify
            and decision.primary_issue_class is not PrimaryIssueClass.TASK_LOCAL_PREFERENCE
        )
        gate = adjudicate(
            GateContext(
                intent=intent,
                state=LifecycleState.VALIDATED,
                authorized_to_modify=request.authorized_to_modify,
                candidate_requires_publish=publish,
                workspace_publishable=session.staging is not None,
                decision=decision,
            ),
            evidence,
            policy=policy,
        )
        target = LifecycleState.GATE_PASSED if gate.verdict.value == "PASS" else LifecycleState.GATE_FAILED
        state = self._move(
            state,
            target,
            _context(
                intent,
                request,
                staging_exists=session.staging is not None,
                modification_needed=publish,
            ),
        )
        return gate, state


def _context(intent: Intent, request: EngineeringRequest, *, staging_exists: bool, modification_needed: bool = False) -> TransitionContext:
    return TransitionContext(
        intent=intent,
        authorized_to_modify=request.authorized_to_modify,
        defect_found=bool(request.failure_evidence),
        staging_exists=staging_exists,
        audit_cycle=0,
        validation_cycle=0,
        modification_needed=modification_needed,
    )


def _session_for(intent: Intent, request: EngineeringRequest) -> WorkspaceSession:
    if intent is Intent.CREATE:
        return WorkspaceSession.for_create()
    return WorkspaceSession.for_existing(intent, request.source)


def _validate_request(intent: Intent, request: EngineeringRequest) -> None:
    if intent is Intent.CREATE:
        if request.source is not None:
            raise ValueError("Create does not accept a source Skill")
    elif request.source is None:
        raise ValueError(f"{intent.value} requires a source Skill")
    if not request.target_parent.exists() or not request.target_parent.is_dir():
        raise ValueError("target parent must be an existing directory")


def _detect_intent(request: EngineeringRequest) -> Intent:
    text = request.requirement.lower()
    if any(token in text for token in ("audit + optimize", "audit and optimize", "optimize")) and request.source:
        return Intent.AUDIT_OPTIMIZE
    if request.source is None:
        return Intent.CREATE
    if request.failure_evidence or any(token in text for token in ("fix", "repair", "修复", "修理")):
        return Intent.FIX
    if any(token in text for token in ("modify", "change", "update", "改", "修改")):
        return Intent.MODIFY
    return Intent.AUDIT_ONLY


def _make_decision(intent: Intent, request: EngineeringRequest) -> DecisionRecord:
    requirement = request.requirement.lower()
    if intent is Intent.FIX and not request.failure_evidence:
        return DecisionRecord(intent, PrimaryIssueClass.INSUFFICIENT_EVIDENCE, (ControlGap.NONE,), RegressionDisposition.NOT_APPLICABLE, None, ("no failure evidence was supplied",), (), (), None)
    if intent is Intent.AUDIT_OPTIMIZE and request.failure_evidence:
        return DecisionRecord(intent, PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE, (ControlGap.IMPLEMENTATION_GAP,), RegressionDisposition.NOT_APPLICABLE, None, (), (), (), None)
    if request.failure_evidence:
        primary = PrimaryIssueClass.IMPLEMENTATION_DEFECT
        root = "; ".join(request.failure_evidence)
        return DecisionRecord(intent, primary, (ControlGap.IMPLEMENTATION_GAP,), RegressionDisposition.REQUIRED, root, (), (), (), None)
    if intent is Intent.AUDIT_OPTIMIZE and any(token in requirement for token in ("optimize", "优化")):
        primary = PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE
    elif intent is Intent.MODIFY and any(token in requirement for token in ("prefer", "style", "format", "preference", "偏好", "格式")):
        primary = PrimaryIssueClass.TASK_LOCAL_PREFERENCE
    elif intent is Intent.MODIFY:
        primary = PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE
    else:
        primary = PrimaryIssueClass.NO_DEFECT
    return DecisionRecord(intent, primary, (ControlGap.NONE,), RegressionDisposition.NOT_APPLICABLE, None, (), (), (), None)


def _write_internal_candidate(staging: Path, requirement: str) -> Path:
    name = "generated-skill"
    candidate = staging / name
    candidate.mkdir()
    (candidate / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Internally generated Skill.\n---\n\n# {name}\n\n{requirement.strip()}\n",
        encoding="utf-8",
    )
    return candidate


def _diagnostic_failure(subject: str) -> CheckResult:
    return CheckResult("diagnostic.evidence", "internal.diagnostics", subject, True, CheckStatus.FAIL, True, True, 1.0, ("insufficient failure evidence",), LifecycleState.VALIDATED, subject)


def _blocked_gate(intent: Intent, request: EngineeringRequest, *, decision: DecisionRecord | None = None, policy: dict[str, object] | None = None) -> GateResult:
    effective = policy or load_gate_policy(request.project_policy)
    return adjudicate(
        GateContext(intent, LifecycleState.VALIDATED, request.authorized_to_modify, True, False, decision),
        (),
        policy=effective,
    )


def _deferred_adjudication(
    intent: Intent,
    request: EngineeringRequest,
    decision: DecisionRecord,
    evidence: tuple[CheckResult, ...],
    policy: dict[str, object],
) -> GateResult:
    return adjudicate(
        GateContext(intent, LifecycleState.VALIDATED, request.authorized_to_modify, False, False, decision),
        evidence,
        policy=policy,
    )
