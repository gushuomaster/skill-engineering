#!/usr/bin/env python3
"""CLI for phased Skill inspection, validation, confirmation, and publication."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.contracts import validate_contract
from engine.models import CheckResult, CheckStatus, Intent, LifecycleState
from engine.orchestrator import (
    EngineeringRequest, PipelineBlockedError, PipelineOrchestrator, publish,
)
from engine.serialization import (
    confirmation_from_data, decision_from_data, governance_from_data,
    inspection_from_data, outcome_to_data, to_data, validation_from_data,
)


PHASE_COMMANDS = frozenset({"inspect", "validate", "confirm", "publish"})


def _phase_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skill_engineering.py")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--target", type=Path)
    inspect.add_argument("--mode", required=True, choices=[item.value for item in Intent])
    inspect.add_argument("--output", required=True, type=Path)

    validate = commands.add_parser("validate")
    validate.add_argument("--inspection", required=True, type=Path)
    validate.add_argument("--decision-record", required=True, type=Path)
    validate.add_argument("--governance-decisions", required=True, type=Path)
    validate.add_argument("--candidate", type=Path)
    validate.add_argument("--target-parent", type=Path)
    validate.add_argument("--authorize-modify", action="store_true")
    validate.add_argument("--publish-requested", action="store_true")
    validate.add_argument("--project-policy", type=Path)
    validate.add_argument("--behavior-command-json")
    validate.add_argument("--regression-command-json")
    validate.add_argument("--output", required=True, type=Path)

    confirm = commands.add_parser("confirm")
    confirm.add_argument("--validation", required=True, type=Path)
    confirm.add_argument("--semantic-confirmation", required=True, type=Path)
    confirm.add_argument("--output", required=True, type=Path)

    publish_parser = commands.add_parser("publish")
    publish_parser.add_argument("--outcome", required=True, type=Path)
    publish_parser.add_argument("--output", type=Path)
    return parser


def _legacy_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skill_engineering.py")
    parser.add_argument("requirement")
    parser.add_argument("--intent", required=True, choices=[item.value for item in Intent])
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


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _load_decision(path: Path):
    payload = _read_json(path)
    validate_contract("decision-record", payload)
    return decision_from_data(payload)


def _command_runner(raw: str | None, check_id: str):
    if raw is None:
        return None
    command = json.loads(raw)
    if not isinstance(command, list) or not command or any(
        not isinstance(part, str) or not part for part in command
    ):
        raise ValueError(f"{check_id} command must be a nonempty JSON string array")

    def run(artifact: Path) -> CheckResult:
        rendered = json.dumps(command, ensure_ascii=False)
        try:
            completed = subprocess.run(
                command, cwd=artifact, text=True, capture_output=True,
                encoding="utf-8", errors="replace", check=False,
            )
            status = CheckStatus.PASS if completed.returncode == 0 else CheckStatus.FAIL
            evidence = (
                f"command={rendered}", f"exit_code={completed.returncode}",
                f"stdout={completed.stdout.strip()[-2000:]}",
                f"stderr={completed.stderr.strip()[-2000:]}",
            )
        except OSError as exc:
            status = CheckStatus.ERROR
            evidence = (f"command={rendered}", "exit_code=NOT_STARTED", "stdout=",
                        f"stderr={type(exc).__name__}: {exc}")
        return CheckResult(
            check_id, "cli.command", str(artifact), True, status, True, True, 1.0,
            evidence, LifecycleState.VALIDATED_PENDING_CONFIRMATION, str(artifact),
        )
    return run


def _phase_main(argv: list[str]) -> int:
    args = _phase_parser().parse_args(argv)
    orchestrator = PipelineOrchestrator()
    try:
        if args.command == "inspect":
            bundle = orchestrator.inspect(Intent(args.mode), args.target)
            payload = to_data(bundle)
            validate_contract("inspection-bundle", payload)
            _write_json(args.output, payload)
            return 0
        if args.command == "validate":
            inspection = inspection_from_data(_read_json(args.inspection))
            governance_payload = _read_json(args.governance_decisions)
            if not isinstance(governance_payload, list):
                raise ValueError("governance decisions must be a JSON array")
            target_parent = args.target_parent
            if target_parent is None:
                target_parent = (
                    inspection.source_path.parent
                    if inspection.source_path is not None else Path.cwd()
                )
            bundle = orchestrator.validate(
                inspection, _load_decision(args.decision_record),
                governance_from_data(governance_payload), candidate=args.candidate,
                target_parent=target_parent,
                authorized_to_modify=args.authorize_modify,
                behavioral_runner=_command_runner(args.behavior_command_json, "behavioral.audit"),
                regression_runner=_command_runner(args.regression_command_json, "B07"),
                publish_requested=args.publish_requested,
                project_policy=args.project_policy,
            )
            payload = to_data(bundle)
            validate_contract("validation-bundle", payload)
            _write_json(args.output, payload)
            return 0
        if args.command == "confirm":
            validation = validation_from_data(_read_json(args.validation))
            confirmation = confirmation_from_data(_read_json(args.semantic_confirmation))
            outcome = orchestrator.confirm(validation, confirmation)
            _write_json(args.output, outcome_to_data(outcome))
            if outcome.audit_execution is None:
                return 0
            if outcome.audit_execution.value == "INCOMPLETE":
                return 2
            return 0 if outcome.artifact_assessment.value == "VALID" else 1
        payload = _read_json(args.outcome)
        validation = validation_from_data(payload["validation"])
        confirmation = confirmation_from_data(payload["semantic_confirmation"])
        outcome = orchestrator.confirm(validation, confirmation)
        result = publish(outcome)
        output = {"outcome": outcome_to_data(outcome), "publication_result": to_data(result)}
        if args.output:
            _write_json(args.output, output)
        else:
            print(json.dumps(output, ensure_ascii=False))
        return 0
    except PipelineBlockedError as exc:
        print(json.dumps({"error": str(exc), "gate_result": to_data(exc.gate_result)},
                         ensure_ascii=False), file=sys.stderr)
        return 1
    except (OSError, TypeError, ValueError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


def _legacy_main(argv: list[str]) -> int:
    args = _legacy_parser().parse_args(argv)
    failure_evidence: tuple[str, ...] = ()
    if args.failure_evidence:
        failure_evidence = tuple(
            line.strip() for line in args.failure_evidence.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    confirmation = None
    if args.confirmed_digest or args.semantic_rationale:
        if not args.confirmed_digest or not args.semantic_rationale:
            raise ValueError("confirmed digest and semantic rationale must be supplied together")
        from engine.models import SemanticConfirmation
        confirmation = SemanticConfirmation(args.confirmed_digest, args.semantic_rationale)
    try:
        outcome = PipelineOrchestrator().run(EngineeringRequest(
            args.requirement, Intent(args.intent), _load_decision(args.decision), args.source,
            args.candidate, failure_evidence, args.authorize_modify, args.target_parent,
            semantic_confirmation=confirmation, project_policy=args.project_policy,
            behavioral_runner=_command_runner(args.behavior_command_json, "behavioral.create"),
            regression_runner=_command_runner(args.regression_command_json, "B07"),
            publish_requested=args.publish,
        ))
        publication = publish(outcome) if args.publish else None
    except PipelineBlockedError as exc:
        payload = {"gate_result": to_data(exc.gate_result),
                   "artifact_path": str(exc.artifact_path) if exc.artifact_path else None,
                   "workspace_diff": to_data(exc.workspace_diff),
                   "evidence": to_data(exc.evidence)}
        print(json.dumps(payload, ensure_ascii=False) if args.json
              else "Pipeline blocked by Quality Gate")
        return 1
    except (OSError, TypeError, ValueError, KeyError) as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1
    payload = outcome_to_data(outcome)
    payload["published_path"] = str(publication.published_path) if publication else None
    payload["publication_result"] = to_data(publication) if publication else None
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(outcome.outcome_type)
        print(outcome.artifact_path)
    if outcome.audit_execution is not None:
        if outcome.audit_execution.value == "INCOMPLETE":
            return 2
        return 0 if outcome.artifact_assessment.value == "VALID" else 1
    return 0


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    return _phase_main(values) if values and values[0] in PHASE_COMMANDS else _legacy_main(values)


if __name__ == "__main__":
    raise SystemExit(main())
