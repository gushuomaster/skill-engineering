#!/usr/bin/env python3
"""CLI for deterministic Skill staging, validation, and explicit publication."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.contracts import validate_contract
from engine.models import (
    ControlGap,
    CheckResult,
    CheckStatus,
    DecisionRecord,
    Intent,
    PrimaryIssueClass,
    RegressionDisposition,
    SemanticConfirmation,
    LifecycleState,
)
from engine.orchestrator import EngineeringRequest, PipelineBlockedError, PipelineOrchestrator, publish


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skill_engineering.py")
    parser.add_argument("requirement")
    parser.add_argument("--intent", required=True, choices=[intent.value for intent in Intent])
    parser.add_argument("--decision", required=True, type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--failure-evidence", type=Path)
    parser.add_argument("--authorize-modify", action="store_true")
    parser.add_argument("--target-parent", type=Path, default=Path.cwd())
    parser.add_argument("--project-policy", type=Path)
    parser.add_argument("--confirmed-digest")
    parser.add_argument("--semantic-rationale")
    parser.add_argument("--behavior-command-json")
    parser.add_argument("--regression-command-json")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def _load_decision(path: Path) -> DecisionRecord:
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_contract("decision-record", payload)
    return DecisionRecord(
        intent=Intent(payload["intent"]),
        primary_issue_class=PrimaryIssueClass(payload["primary_issue_class"]),
        control_gaps=tuple(ControlGap(value) for value in payload["control_gaps"]),
        regression_disposition=RegressionDisposition(payload["regression_disposition"]),
        root_cause=payload["root_cause"],
        evidence_limitations=tuple(payload["evidence_limitations"]),
        selected_mechanisms=tuple(payload["selected_mechanisms"]),
        rejected_mechanisms=tuple(payload["rejected_mechanisms"]),
        prompt_rule_justification=payload["prompt_rule_justification"],
        decided_by=payload["decided_by"],
    )


def _confirmation(args: argparse.Namespace) -> SemanticConfirmation | None:
    if args.confirmed_digest is None and args.semantic_rationale is None:
        return None
    if not args.confirmed_digest or not args.semantic_rationale:
        raise ValueError("confirmed digest and semantic rationale must be supplied together")
    return SemanticConfirmation(args.confirmed_digest, args.semantic_rationale)


def _command_runner(raw: str | None, check_id: str):
    if raw is None:
        return None
    command = json.loads(raw)
    if not isinstance(command, list) or not command or any(
        not isinstance(part, str) or not part for part in command
    ):
        raise ValueError(f"{check_id} command must be a nonempty JSON string array")

    def run(artifact: Path) -> CheckResult:
        rendered_command = json.dumps(command, ensure_ascii=False)
        try:
            completed = subprocess.run(
                command,
                cwd=artifact,
                text=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            status = CheckStatus.PASS if completed.returncode == 0 else CheckStatus.FAIL
            stdout = completed.stdout.strip()[-2000:]
            stderr = completed.stderr.strip()[-2000:]
            evidence = (
                f"command={rendered_command}",
                f"exit_code={completed.returncode}",
                f"stdout={stdout}",
                f"stderr={stderr}",
            )
        except OSError as exc:
            status = CheckStatus.ERROR
            evidence = (
                f"command={rendered_command}",
                "exit_code=NOT_STARTED",
                "stdout=",
                f"stderr={type(exc).__name__}: {exc}",
            )
        return CheckResult(
            check_id, "cli.command", str(artifact), True, status,
            True, True, 1.0, evidence, LifecycleState.VALIDATED, str(artifact),
        )

    return run


def _payload(outcome: object, publication_result: object | None = None) -> dict[str, object]:
    return {
        "outcome_type": outcome.outcome_type,
        "artifact_path": str(outcome.artifact_path),
        "gate_result": asdict(outcome.gate_result),
        "minimal_blocking_findings": list(outcome.minimal_blocking_findings),
        "workspace_diff": asdict(outcome.workspace_diff),
        "evidence": [asdict(result) for result in outcome.evidence],
        "publication_ready": outcome.publication_session is not None,
        "published_path": (
            str(publication_result.published_path)
            if publication_result is not None else None
        ),
        "publication_result": (
            asdict(publication_result) if publication_result is not None else None
        ),
    }


def _json_default(value: object) -> object:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    evidence: tuple[str, ...] = ()
    if args.failure_evidence is not None:
        evidence = tuple(
            line.strip()
            for line in args.failure_evidence.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    try:
        request = EngineeringRequest(
            requirement=args.requirement,
            intent=Intent(args.intent),
            decision=_load_decision(args.decision),
            source=args.source,
            candidate=args.candidate,
            failure_evidence=evidence,
            authorized_to_modify=args.authorize_modify,
            target_parent=args.target_parent,
            semantic_confirmation=_confirmation(args),
            project_policy=args.project_policy,
            behavioral_runner=_command_runner(args.behavior_command_json, "behavioral.create"),
            regression_runner=_command_runner(args.regression_command_json, "B07"),
            publish_requested=args.publish,
        )
        outcome = PipelineOrchestrator().run(request)
        publication_result = publish(outcome) if args.publish else None
    except PipelineBlockedError as exc:
        payload = {
            "gate_result": asdict(exc.gate_result),
            "artifact_path": str(exc.artifact_path) if exc.artifact_path is not None else None,
            "workspace_diff": asdict(exc.workspace_diff) if exc.workspace_diff is not None else None,
            "evidence": [asdict(result) for result in exc.evidence],
        }
        if args.json:
            print(json.dumps(payload, default=_json_default, ensure_ascii=False))
        else:
            print("Pipeline blocked by Quality Gate")
            for finding in exc.gate_result.blocking_findings:
                print(f"- {finding}")
        return 1
    except (OSError, ValueError) as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1
    payload = _payload(outcome, publication_result)
    if args.json:
        print(json.dumps(payload, default=_json_default, ensure_ascii=False))
    else:
        print(outcome.outcome_type)
        print(outcome.artifact_path)
        for finding in outcome.minimal_blocking_findings:
            print(f"- {finding['finding_id']}: {finding['blocking_reason']}")
    return 2 if outcome.gate_result.verdict.value == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
