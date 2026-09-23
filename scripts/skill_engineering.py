#!/usr/bin/env python3
"""CLI for Codex-led Skill audit, repair, validation, and safe apply."""
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
from engine.models import (
    CheckResult, CheckStatus, DeliverableContractApplicability, Intent,
    LifecycleState, ManagedOperationStatus, ManagedStatusResult,
    StandardSkillRequirement,
)
from engine.applicability import AuditDimension
from engine.host_adapters import (
    build_codex_skill_adapter,
    build_default_provider_adapters,
)
from engine.managed_completion import managed_status
from engine.orchestrator import (
    EngineeringRequest, PipelineBlockedError, PipelineOrchestrator, apply,
)
from engine.toolchain import MissingStandardDependencyError
from engine.providers import ProviderGateway
from engine.serialization import (
    completion_receipt_from_data, confirmation_from_data, decision_from_data,
    governance_from_data,
    inspection_from_data, outcome_to_data, to_data, validation_from_data,
)


PHASE_COMMANDS = frozenset({"inspect", "validate", "confirm", "apply", "status"})
USER_MODES = (Intent.AUDIT, Intent.AUDIT_REPAIR, Intent.TARGETED_REPAIR)


def _phase_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skill_engineering.py")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--target", type=Path)
    inspect.add_argument("--mode", required=True, choices=[item.value for item in USER_MODES])
    inspect.add_argument("--output", required=True, type=Path)
    inspect.add_argument(
        "--provider-skill", action="append", default=[],
        help="Codex-selected Skill, optionally NAME=CAPABILITY for an open domain capability",
    )
    inspect.add_argument("--provider-timeout-seconds", type=int, default=300)
    inspect.add_argument(
        "--audit-dimension",
        action="append",
        choices=[item.value for item in AuditDimension],
        default=None,
    )
    inspect.add_argument("--deliverable-not-required-rationale")
    inspect.add_argument(
        "--compatibility-no-default-providers",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    inspect.add_argument(
        "--deliverable-contract-applicability",
        choices=[item.value for item in DeliverableContractApplicability],
        default=DeliverableContractApplicability.COMPATIBILITY.value,
    )
    inspect.add_argument(
        "--require-standard-skill", action="append", default=[], metavar="NAME|RESPONSIBILITY|GAP",
        help="Codex-selected required standard Skill and its user-visible coverage gap",
    )

    validate = commands.add_parser("validate")
    validate.add_argument("--inspection", required=True, type=Path)
    validate.add_argument("--decision-record", required=True, type=Path)
    validate.add_argument("--governance-decisions", required=True, type=Path)
    validate.add_argument("--candidate", type=Path)
    validate.add_argument("--target-parent", type=Path)
    validate.add_argument("--authorize-modify", action="store_true")
    validate.add_argument("--apply-requested", action="store_true")
    validate.add_argument("--continue-limited", action="store_true")
    validate.add_argument("--project-policy", type=Path)
    validate.add_argument("--behavior-command-json")
    validate.add_argument("--contract-command-json")
    validate.add_argument("--regression-command-json")
    validate.add_argument("--output", required=True, type=Path)

    confirm = commands.add_parser("confirm")
    confirm.add_argument("--validation", required=True, type=Path)
    confirm.add_argument("--semantic-confirmation", required=True, type=Path)
    confirm.add_argument("--output", required=True, type=Path)

    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("--outcome", required=True, type=Path)
    apply_parser.add_argument("--output", type=Path)

    status_parser = commands.add_parser("status")
    status_parser.add_argument("--target", required=True, type=Path)
    status_parser.add_argument("--receipt", type=Path)
    status_parser.add_argument("--output", required=True, type=Path)
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
    parser.add_argument("--contract-command-json")
    parser.add_argument(
        "--deliverable-contract-applicability",
        choices=[item.value for item in DeliverableContractApplicability],
        default=DeliverableContractApplicability.COMPATIBILITY.value,
    )
    parser.add_argument("--regression-command-json")
    parser.add_argument("--apply", action="store_true")
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


def _standard_requirements(values: list[str]) -> tuple[StandardSkillRequirement, ...]:
    requirements: list[StandardSkillRequirement] = []
    for value in values:
        parts = value.split("|", 2)
        if len(parts) != 3 or not all(part.strip() for part in parts):
            raise ValueError(
                "--require-standard-skill must be NAME|RESPONSIBILITY|GAP"
            )
        requirements.append(StandardSkillRequirement(*(part.strip() for part in parts)))
    return tuple(requirements)


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
    try:
        if args.command == "inspect":
            provider_specs = tuple(
                (value.split("=", 1) + [None])[:2]
                if "=" in value else (value, None)
                for value in args.provider_skill
            )
            selected_adapters = tuple(
                build_codex_skill_adapter(
                    name, capability=capability,
                    config_path=ROOT / "config" / "providers.yaml",
                    schema_path=ROOT / "schemas" / "provider-result.schema.json",
                    timeout_seconds=args.provider_timeout_seconds,
                )
                for name, capability in provider_specs
            )
            default_adapters = (
                ()
                if args.compatibility_no_default_providers
                else build_default_provider_adapters(
                    ROOT,
                    timeout_seconds=args.provider_timeout_seconds,
                )
            )
            adapters = (*default_adapters, *selected_adapters)
            gateway = ProviderGateway(adapters) if adapters else None
            orchestrator = PipelineOrchestrator(
                provider_gateway=gateway,
                required_standard_skills=_standard_requirements(args.require_standard_skill),
            )
            bundle = orchestrator.inspect(
                Intent(args.mode), args.target,
                deliverable_contract_applicability=DeliverableContractApplicability(
                    args.deliverable_contract_applicability
                ),
                audit_dimensions=(
                    tuple(AuditDimension(item) for item in args.audit_dimension)
                    if args.audit_dimension is not None else None
                ),
                deliverable_not_required_rationale=args.deliverable_not_required_rationale,
            )
            payload = to_data(bundle)
            validate_contract("inspection-bundle", payload)
            _write_json(args.output, payload)
            return 0
        if args.command == "validate":
            inspection = inspection_from_data(_read_json(args.inspection))
            gateway = None
            if inspection.capability_provider_id is not None:
                gateway = ProviderGateway(build_default_provider_adapters(ROOT))
            orchestrator = PipelineOrchestrator(provider_gateway=gateway)
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
                contract_runner=_command_runner(args.contract_command_json, "contract.behavior"),
                regression_runner=_command_runner(args.regression_command_json, "B07"),
                apply_requested=args.apply_requested,
                continue_limited=args.continue_limited,
                project_policy=args.project_policy,
            )
            payload = to_data(bundle)
            validate_contract("validation-bundle", payload)
            _write_json(args.output, payload)
            return 0
        if args.command == "confirm":
            orchestrator = PipelineOrchestrator()
            validation = validation_from_data(_read_json(args.validation))
            confirmation = confirmation_from_data(_read_json(args.semantic_confirmation))
            outcome = orchestrator.confirm(validation, confirmation)
            _write_json(args.output, outcome_to_data(outcome))
            if outcome.audit_execution is None:
                return 0
            if outcome.audit_execution.value == "INCOMPLETE":
                return 2
            return 0 if outcome.artifact_assessment.value == "VALID" else 1
        if args.command == "status":
            receipt = None
            if args.receipt is not None:
                try:
                    receipt = completion_receipt_from_data(_read_json(args.receipt))
                except Exception as exc:
                    result = ManagedStatusResult(
                        ManagedOperationStatus.AUDIT_INCOMPLETE,
                        False,
                        None,
                        f"invalid managed completion receipt: {exc}",
                    )
                    _write_json(args.output, to_data(result))
                    return 2
            result = managed_status(args.target, receipt)
            _write_json(args.output, to_data(result))
            return 0 if result.formal_completion else 2
        orchestrator = PipelineOrchestrator()
        payload = _read_json(args.outcome)
        validation = validation_from_data(payload["validation"])
        confirmation = confirmation_from_data(payload["semantic_confirmation"])
        outcome = orchestrator.confirm(validation, confirmation)
        receipt_payload = payload.get("completion_receipt")
        if not isinstance(receipt_payload, dict):
            raise ValueError("formal completion receipt is required for Apply")
        receipt = completion_receipt_from_data(receipt_payload)
        result = apply(outcome, receipt)
        output = {"outcome": outcome_to_data(outcome), "apply_result": to_data(result)}
        if args.output:
            _write_json(args.output, output)
        else:
            print(json.dumps(output, ensure_ascii=False))
        return 0
    except MissingStandardDependencyError as exc:
        print(json.dumps({
            "error": str(exc),
            "action_required": "install_or_connect_or_continue_limited",
            "missing_standard_skills": to_data(exc.missing),
        }, ensure_ascii=False), file=sys.stderr)
        return 3
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
            contract_runner=_command_runner(args.contract_command_json, "contract.behavior"),
            regression_runner=_command_runner(args.regression_command_json, "B07"),
            apply_requested=args.apply,
            deliverable_contract_applicability=DeliverableContractApplicability(
                args.deliverable_contract_applicability
            ),
        ))
        application = apply(outcome) if args.apply else None
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
    payload["applied_path"] = str(application.applied_path) if application else None
    payload["apply_result"] = to_data(application) if application else None
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
