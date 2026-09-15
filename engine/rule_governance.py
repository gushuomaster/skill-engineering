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
    decided_by: str = "CODEX"


def validate_governance_decisions(
    findings: tuple[object, ...],
    decisions: tuple[GovernanceDecision, ...],
) -> tuple[GovernanceDecision, ...]:
    """Validate explicit Codex decisions; never derive actions from detector signals."""
    finding_by_id = {finding.finding_id: finding for finding in findings}
    if len(finding_by_id) != len(findings):
        raise ValueError("rule findings must have unique identifiers")
    decision_by_id = {decision.finding_id: decision for decision in decisions}
    if len(decision_by_id) != len(decisions):
        raise ValueError("governance decisions must have unique finding identifiers")
    unknown = sorted(set(decision_by_id) - set(finding_by_id))
    if unknown:
        raise ValueError("governance decisions reference unknown findings: " + ", ".join(unknown))
    validated: list[GovernanceDecision] = []
    for decision in decisions:
        if decision.decided_by != "CODEX":
            raise ValueError(f"decision {decision.finding_id} must be authored by Codex")
        if not isinstance(decision.action, GovernanceAction):
            raise ValueError(f"decision {decision.finding_id} requires a valid action")
        if not isinstance(decision.rationale, str) or not decision.rationale.strip():
            raise ValueError(f"decision {decision.finding_id} requires Codex rationale")
        if not decision.evidence_refs or any(not ref.strip() for ref in decision.evidence_refs):
            raise ValueError(f"decision {decision.finding_id} requires evidence references")
        finding = finding_by_id[decision.finding_id]
        validated.append(
            GovernanceDecision(
                decision.finding_id,
                decision.action,
                decision.rationale.strip(),
                tuple(ref.strip() for ref in decision.evidence_refs),
                decision.target_layer,
                decision.blocking,
                tuple(finding.signals),
                tuple(finding.limitations),
                "CODEX",
            )
        )
    return tuple(validated)


def signal_evidence(findings: tuple[object, ...]) -> tuple[CheckResult, ...]:
    """Project detector output as advisory evidence without governance actions."""
    evidence: list[CheckResult] = []
    for finding in findings:
        status = CheckStatus.SKIP if finding.confidence == 0 else CheckStatus.WARN
        evidence.append(CheckResult(
            check_id=f"rule-signal.{finding.finding_id}",
            source="rule_bloat_detector",
            subject=",".join(finding.evidence_refs)[:200] or finding.finding_id,
            required=False,
            status=status,
            deterministic=True,
            reproducible=True,
            confidence=finding.confidence,
            evidence=(finding.rationale, *finding.signals, *finding.limitations),
            remediation_stage=LifecycleState.AUDITED,
            artifact_reference=None,
        ))
    return tuple(evidence)


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
