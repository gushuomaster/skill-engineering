"""Legal output projections for the minimal governance loop."""
from __future__ import annotations

from pathlib import Path

from engine.models import GateResult, GateVerdict
from engine.orchestrator import EngineeringOutcome
from engine.workspace import WorkspaceDiff


def project_validated(artifact_path: Path | None, gate_result: GateResult) -> EngineeringOutcome:
    if artifact_path is None or gate_result.verdict is not GateVerdict.PASS:
        raise ValueError("validated output requires a complete artifact and Gate PASS")
    return EngineeringOutcome(
        "Validated Complete Skill", artifact_path, gate_result, (),
        WorkspaceDiff((), (), ()), None,
    )


def project_audit_failure(source: Path | None, gate_result: GateResult) -> EngineeringOutcome:
    if source is None or gate_result.verdict is not GateVerdict.FAIL:
        raise ValueError("Audit Only failure requires unchanged source and Gate FAIL")
    findings = tuple(
        {
            "finding_id": finding.split(":", 1)[0].strip(),
            "affected_path": str(source),
            "blocking_reason": finding,
            "required_next_action": "remediate the blocking finding and rerun Audit Only",
        }
        for finding in gate_result.blocking_findings
    )
    return EngineeringOutcome(
        "Unchanged Skill + Minimal Blocking Findings", source, gate_result, findings,
        WorkspaceDiff((), (), ()), None,
    )
