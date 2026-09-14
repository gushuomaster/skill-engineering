#!/usr/bin/env python3
"""Command-line entry point for the internal Skill governance loop."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.models import Intent
from engine.orchestrator import EngineeringRequest, PipelineBlockedError, PipelineOrchestrator


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skill_engineering.py")
    parser.add_argument("requirement")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--failure-evidence", type=Path)
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--authorize-optimize", action="store_true")
    parser.add_argument("--target-parent", type=Path, default=Path.cwd())
    parser.add_argument("--project-policy", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser


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
    intent = Intent.AUDIT_ONLY if args.read_only else None
    request = EngineeringRequest(
        requirement=args.requirement,
        intent=intent,
        source=args.source,
        failure_evidence=evidence,
        authorized_to_modify=args.authorize_optimize,
        target_parent=args.target_parent,
        project_policy=args.project_policy,
    )
    try:
        outcome = PipelineOrchestrator().run(request)
    except PipelineBlockedError as exc:
        payload = {"gate_result": asdict(exc.gate_result)}
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
    payload = asdict(outcome)
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
