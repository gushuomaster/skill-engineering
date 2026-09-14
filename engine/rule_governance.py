"""Internal governance of advisory rule-bloat findings."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from engine.models import CheckResult, CheckStatus, LifecycleState


class GovernanceAction(StrEnum):
    KEEP = "KEEP"
    MERGE = "MERGE"
    MOVE = "MOVE"
    DELETE = "DELETE"


@dataclass(frozen=True)
class GovernanceDecision:
    finding_id: str
    action: GovernanceAction
    rationale: str
    evidence_refs: tuple[str, ...]
    target_layer: str | None
    blocking: bool = False
    signals: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


def govern_findings(findings: tuple[object, ...], mechanisms: tuple[str, ...]) -> tuple[GovernanceDecision, ...]:
    decisions: list[GovernanceDecision] = []
    for finding in findings:
        raw_rationale = finding.rationale
        if not isinstance(raw_rationale, str) or not raw_rationale.strip():
            raise ValueError(f"finding {finding.finding_id} requires governance rationale")
        raw_refs = tuple(finding.evidence_refs)
        if not raw_refs or any(not isinstance(ref, str) or not ref.strip() for ref in raw_refs):
            raise ValueError(f"finding {finding.finding_id} requires evidence references")
        rationale = raw_rationale.strip()
        refs = tuple(ref.strip() for ref in raw_refs)
        action = finding.candidate_action
        if not isinstance(action, GovernanceAction):
            action = GovernanceAction.KEEP
        signals = set(finding.signals)
        blocking = bool(
            action in {GovernanceAction.DELETE, GovernanceAction.MERGE}
            and "conflict" in signals
            and any("regression" in mechanism.lower() or "validator" in mechanism.lower() for mechanism in mechanisms)
        )
        decisions.append(
            GovernanceDecision(
                finding.finding_id,
                action,
                rationale,
                refs,
                finding.candidate_target_layer,
                blocking,
                tuple(finding.signals),
                tuple(finding.limitations),
            )
        )
    return tuple(decisions)


def governance_evidence(decisions: tuple[GovernanceDecision, ...]) -> tuple[CheckResult, ...]:
    evidence: list[CheckResult] = []
    for decision in decisions:
        status = CheckStatus.FAIL if decision.blocking else CheckStatus.WARN
        if "historical_growth" in decision.signals and any(
            "missing git history" in limitation.lower()
            for limitation in decision.limitations
        ):
            status = CheckStatus.SKIP
        elif decision.action is GovernanceAction.KEEP and not decision.blocking:
            status = CheckStatus.PASS
        check_id = f"rule-governance.{decision.finding_id}"
        subject = ",".join(decision.evidence_refs)[:200] or decision.finding_id
        evidence.append(CheckResult(
            check_id=check_id,
            source="rule_governance",
            subject=subject,
            required=decision.blocking,
            status=status,
            deterministic=True,
            reproducible=True,
            confidence=1.0,
            evidence=(f"{decision.action.value}: {decision.rationale}", *decision.evidence_refs),
            remediation_stage=LifecycleState.VALIDATED,
            artifact_reference=decision.target_layer,
        ))
    return tuple(evidence)
