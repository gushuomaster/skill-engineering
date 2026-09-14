"""Versioned policy loading and sole final quality adjudication."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
import re
from pathlib import Path

import yaml

from engine.contracts import validate_contract
from engine.evidence import EvidenceCollector, InvalidEvidence
from engine.mechanism_selection import PROMPT_RULE, prompt_rule_allowed
from engine.models import (
    CheckResult,
    CheckStatus,
    DecisionRecord,
    GateOutcome,
    GateResult,
    GateVerdict,
    Intent,
    LifecycleState,
    RegressionDisposition,
)


POLICY_PATH = Path(__file__).resolve().parents[1] / "config" / "gate-policy.yaml"
_ERROR_STATUSES = frozenset(
    {CheckStatus.ERROR, CheckStatus.SKIP, CheckStatus.NOT_EXECUTED}
)
_CHANGE_INTENTS = frozenset(
    {Intent.CREATE, Intent.MODIFY, Intent.FIX, Intent.AUDIT_OPTIMIZE}
)
_CHECK_POLICY = {
    "skill.structure.skill_md": "B02",
    "skill.structure.placeholders": "B02",
    "skill.structure.frontmatter": "B03",
    "skill.structure.name_format": "B03",
    "skill.structure.directory_name": "B03",
    "skill.structure.critical_assets": "B11",
    "skill.structure.schema": "B11",
    "skill.structure.executables": "B11",
    "skill.structure.required_dependencies": "B11",
    "reference.required.exists": "B02",
}
_CORE_POLICY_IDS = frozenset(f"B{number:02d}" for number in range(1, 13))
_CORE_REQUIRED_CHECKS = frozenset(
    {
        "skill.structure.skill_md",
        "skill.structure.frontmatter",
        "skill.structure.name_format",
        "skill.structure.directory_name",
        "skill.structure.placeholders",
        "skill.structure.critical_assets",
        "skill.structure.schema",
        "skill.structure.executables",
        "skill.structure.required_dependencies",
    }
)
_EXTERNAL_MAPPING = re.compile(r"(?:maps_to|mapping)\s*[:=]\s*(B(?:0[1-9]|1[01]))\b")


class InvalidGatePolicy(ValueError):
    """Raised when a project policy is invalid or weakens the core policy."""


@dataclass(frozen=True)
class GateContext:
    intent: Intent
    state: LifecycleState
    authorized_to_modify: bool
    candidate_requires_publish: bool
    workspace_publishable: bool
    decision: DecisionRecord | None


def _read_policy(path: Path) -> dict[str, object]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise InvalidGatePolicy(f"cannot load Gate policy: {exc}") from exc
    if not isinstance(payload, dict):
        raise InvalidGatePolicy("Gate policy schema requires an object")
    try:
        validate_contract("gate-policy", payload)
    except Exception as exc:
        raise InvalidGatePolicy(f"Gate policy schema validation failed: {exc}") from exc
    return payload


def _ordered_union(core: object, extension: object) -> list[str]:
    values: list[str] = []
    for value in (*core, *extension):
        if value not in values:
            values.append(value)
    return values


def load_gate_policy(project_policy: Path | None = None) -> dict[str, object]:
    """Load the core policy and merge a schema-valid strengthening extension."""
    core = _read_policy(POLICY_PATH)
    if project_policy is None:
        return core

    project = _read_policy(project_policy)
    core_required = set(core["required_checks"])
    project_required = set(project["required_checks"])
    core_blocking = set(core["blocking_policy_ids"])
    project_blocking = set(project["blocking_policy_ids"])
    if not core_required.issubset(project_required) or not core_blocking.issubset(
        project_blocking
    ):
        raise InvalidGatePolicy("project policy cannot weaken core B01-B12")

    merged: dict[str, object] = {
        "policy_version": (
            f'{core["policy_version"]}+{project["policy_version"]}'
        ),
        "required_checks": _ordered_union(
            core["required_checks"], project["required_checks"]
        ),
        "blocking_policy_ids": _ordered_union(
            core["blocking_policy_ids"], project["blocking_policy_ids"]
        ),
        "warning_policy_ids": _ordered_union(
            core["warning_policy_ids"], project["warning_policy_ids"]
        ),
        "project_extensions": _ordered_union(
            core["project_extensions"], project["project_extensions"]
        ),
    }
    try:
        validate_contract("gate-policy", merged)
    except Exception as exc:
        raise InvalidGatePolicy(
            f"effective Gate policy schema validation failed: {exc}"
        ) from exc
    return merged


def _finding(policy_id: str, result: CheckResult) -> str:
    detail = "; ".join(result.evidence) or result.status.value
    return f"{policy_id}: {result.check_id} ({result.subject}): {detail}"


def _warning(result: CheckResult) -> str:
    detail = "; ".join(result.evidence) or result.status.value
    reference = f" [{result.artifact_reference}]" if result.artifact_reference else ""
    return f"{result.check_id}{reference}: {detail}"


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _collect_valid_evidence(
    evidence: tuple[CheckResult, ...],
) -> tuple[tuple[CheckResult, ...], tuple[str, ...], tuple[str, ...]]:
    collector = EvidenceCollector()
    required_errors: list[str] = []
    optional_errors: list[str] = []
    for result in evidence:
        try:
            collector.add(result)
        except InvalidEvidence as exc:
            target = (
                optional_errors
                if getattr(result, "required", True) is False
                else required_errors
            )
            target.append(str(exc))
    return collector.snapshot(), tuple(required_errors), tuple(optional_errors)


def _is_trustworthy(result: CheckResult) -> bool:
    return result.deterministic and result.reproducible and result.confidence > 0


def _blocking_policy_for(
    result: CheckResult, blocking_policy_ids: set[str]
) -> str | None:
    if result.check_id.startswith(("rule-bloat", "rule_bloat")):
        return None
    if result.check_id in _CHECK_POLICY:
        return _CHECK_POLICY[result.check_id]
    source = result.source.lower()
    if not source.startswith("internal"):
        if _EXTERNAL_MAPPING.search(" ".join(result.evidence)):
            return "B12"
        return (
            result.check_id
            if result.check_id in blocking_policy_ids
            and result.check_id not in _CORE_POLICY_IDS
            else None
        )
    if result.check_id in blocking_policy_ids:
        return result.check_id
    if result.required:
        return "B04"
    return None


def _validate_effective_policy(policy: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(policy, Mapping):
        raise InvalidGatePolicy("effective Gate policy must be a mapping")
    effective = dict(policy)
    try:
        validate_contract("gate-policy", effective)
    except Exception as exc:
        raise InvalidGatePolicy(
            f"effective Gate policy schema validation failed: {exc}"
        ) from exc
    if not _CORE_REQUIRED_CHECKS.issubset(set(effective["required_checks"])):
        raise InvalidGatePolicy("effective policy cannot weaken core required checks")
    if not _CORE_POLICY_IDS.issubset(set(effective["blocking_policy_ids"])):
        raise InvalidGatePolicy("effective policy cannot weaken core B01-B12")
    return effective


def _adjudicate_findings(
    context: GateContext,
    evidence: tuple[CheckResult, ...],
    policy: dict[str, object],
) -> tuple[tuple[str, ...], tuple[str, ...], int, int, int]:
    blocking: list[str] = []
    warnings: list[str] = []
    valid_evidence, invalid_required, invalid_optional = _collect_valid_evidence(
        evidence
    )
    required_results = tuple(result for result in valid_evidence if result.required)
    required_ids = set(policy["required_checks"])
    present_required_ids = {result.check_id for result in required_results}
    missing_required = sorted(required_ids - present_required_ids)

    if invalid_required:
        _append_unique(
            blocking,
            "B08: invalid required evidence: " + "; ".join(invalid_required),
        )
    for error in invalid_optional:
        _append_unique(warnings, f"invalid optional evidence: {error}")
    if missing_required:
        _append_unique(
            blocking,
            "B08: missing required evidence: " + ", ".join(missing_required),
        )

    blocking_policy_ids = set(policy["blocking_policy_ids"])
    for result in valid_evidence:
        mapped_policy = _blocking_policy_for(result, blocking_policy_ids)
        if result.required and (
            result.status in _ERROR_STATUSES or not _is_trustworthy(result)
        ):
            _append_unique(blocking, _finding("B08", result))
            if mapped_policy == "B11":
                _append_unique(blocking, _finding("B11", result))
            continue
        optional_b11 = mapped_policy == "B11" and not result.required
        if (
            result.status is CheckStatus.FAIL
            and mapped_policy in blocking_policy_ids
            and not optional_b11
        ):
            _append_unique(blocking, _finding(mapped_policy, result))
            continue
        if result.status in {
            CheckStatus.WARN,
            CheckStatus.FAIL,
            CheckStatus.ERROR,
            CheckStatus.SKIP,
            CheckStatus.NOT_EXECUTED,
        }:
            _append_unique(warnings, _warning(result))

    decision = context.decision
    if (
        decision is not None
        and PROMPT_RULE in decision.selected_mechanisms
        and not prompt_rule_allowed(decision)
    ):
        _append_unique(
            blocking,
            "B06: Prompt Rule lacks capability-invariant classification or justification",
        )
    if (
        decision is not None
        and decision.regression_disposition is RegressionDisposition.REQUIRED
    ):
        regression = next(
            (result for result in required_results if result.check_id == "B07"),
            None,
        )
        if regression is None or regression.status is not CheckStatus.PASS:
            _append_unique(blocking, "B07: required regression is absent or not passing")
    elif (
        decision is not None
        and decision.regression_disposition is RegressionDisposition.RECOMMENDED
        and not any(result.check_id == "B07" for result in valid_evidence)
    ):
        _append_unique(warnings, "recommended regression is absent")

    if (
        context.candidate_requires_publish
        and context.intent in _CHANGE_INTENTS
        and not context.authorized_to_modify
    ):
        _append_unique(blocking, "B09: candidate exceeds modification authorization")

    return (
        tuple(blocking),
        tuple(warnings),
        len(required_ids & present_required_ids),
        len(missing_required),
        len(valid_evidence),
    )


def adjudicate(
    context: GateContext,
    evidence: tuple[CheckResult, ...],
    *,
    policy: Mapping[str, object] | None = None,
) -> GateResult:
    """Return the sole final verdict after applying an effective Gate policy."""
    effective_policy = (
        _read_policy(POLICY_PATH)
        if policy is None
        else _validate_effective_policy(policy)
    )
    (
        blocking,
        warnings,
        required_count,
        missing_count,
        evidence_count,
    ) = _adjudicate_findings(context, evidence, effective_policy)
    verdict = GateVerdict.FAIL if blocking else GateVerdict.PASS

    publish_authorized = (
        verdict is GateVerdict.PASS
        and context.intent in _CHANGE_INTENTS
        and context.authorized_to_modify
        and context.candidate_requires_publish
        and context.workspace_publishable
        and context.state is LifecycleState.VALIDATED
    )
    if verdict is GateVerdict.FAIL:
        outcome = (
            GateOutcome.UNCHANGED_BLOCKED
            if context.intent is Intent.AUDIT_ONLY
            else GateOutcome.REMEDIATION_REQUIRED
        )
    elif publish_authorized:
        outcome = GateOutcome.READY_TO_PUBLISH
    elif (
        context.intent is Intent.AUDIT_ONLY
        or not context.candidate_requires_publish
    ):
        outcome = GateOutcome.UNCHANGED_VALIDATED
    else:
        outcome = GateOutcome.REMEDIATION_REQUIRED

    required_checks_summary = (
        f"{required_count} required checks received; "
        f"{missing_count} missing; {len(blocking)} blocking findings."
    )
    evidence_summary = (
        f"{evidence_count} valid evidence results; {len(warnings)} warnings."
    )
    return GateResult(
        verdict=verdict,
        outcome=outcome,
        blocking_findings=blocking,
        warnings=warnings,
        required_checks_summary=required_checks_summary,
        evidence_summary=evidence_summary,
        publish_authorized=publish_authorized,
        policy_version=str(effective_policy["policy_version"]),
    )
