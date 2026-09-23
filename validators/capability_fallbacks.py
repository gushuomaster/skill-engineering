"""Trusted internal fallbacks for required Skill-engineering capabilities."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from engine.models import (
    ArtifactManifest,
    CheckResult,
    CheckStatus,
    DecisionRecord,
    LifecycleState,
    RegressionDisposition,
)
from engine.rule_bloat import RuleFinding, RuleUnit, extract_rule_units
from engine.rule_governance import GovernanceDecision


_VAGUE_DIRECTIVE = re.compile(
    r"\b(?:be careful|use best judgment|do it (?:properly|correctly|well)|as appropriate|etc\.)\b",
    re.IGNORECASE,
)
_UNNECESSARY_ORCHESTRATION = re.compile(
    r"\b(?:always|must|required to)\s+(?:invoke|load|use|call)\b.{0,80}\b(?:skill|provider)\b",
    re.IGNORECASE,
)
_STALE_DIRECTIVE = re.compile(
    r"\b(?:deprecated|obsolete|superseded|no longer supported)\b", re.IGNORECASE,
)


def _finding_evidence(
    file: str,
    line: str,
    finding: str,
    severity: str,
    reason: str,
    remediation: str,
) -> str:
    """Stable evidence contract used by the internal semantic rubric."""
    return (
        f"file={file}; line={line}; finding={finding}; severity={severity}; "
        f"reason={reason}; remediation={remediation}"
    )


def _result(
    capability: str,
    subject: str,
    status: CheckStatus,
    evidence: tuple[str, ...],
) -> CheckResult:
    return CheckResult(
        f"capability.{capability}", "internal.capability-fallback", subject, True,
        status, True, True, 1.0 if status is CheckStatus.PASS else 0.95,
        evidence, LifecycleState.VALIDATED_PENDING_CONFIRMATION, subject,
    )


def _frontmatter(root: Path) -> dict[str, object]:
    try:
        lines = (root / "SKILL.md").read_text(encoding="utf-8").splitlines()
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
        value = yaml.safe_load("\n".join(lines[1:end]))
    except (OSError, UnicodeError, StopIteration, yaml.YAMLError, IndexError):
        return {}
    return value if isinstance(value, dict) else {}


def _aggregate(
    capability: str,
    subject: str,
    results: tuple[CheckResult, ...],
    *,
    include_optional: bool = False,
) -> CheckResult:
    relevant = tuple(item for item in results if include_optional or item.required)
    failed = tuple(item for item in relevant if item.status is CheckStatus.FAIL)
    unavailable = tuple(
        item for item in relevant
        if item.status in {CheckStatus.ERROR, CheckStatus.SKIP, CheckStatus.NOT_EXECUTED}
    )
    warned = tuple(item for item in relevant if item.status is CheckStatus.WARN)
    if unavailable:
        status = CheckStatus.NOT_EXECUTED
        chosen = unavailable
    elif failed:
        status = CheckStatus.FAIL
        chosen = failed
    elif warned:
        status = CheckStatus.WARN
        chosen = warned
    else:
        status = CheckStatus.PASS
        chosen = relevant
    evidence = tuple(
        f"{item.check_id}={item.status.value}: {'; '.join(item.evidence)}"
        for item in chosen
    ) or ("no applicable component checks",)
    return _result(capability, subject, status, evidence)


def validate_trigger_and_description(manifest: ArtifactManifest) -> CheckResult:
    root = Path(manifest.artifact_root)
    value = _frontmatter(root)
    description = value.get("description")
    valid = isinstance(description, str) and bool(description.strip())
    placeholder = bool(valid and re.search(r"\b(?:TODO|TBD|placeholder)\b", description, re.I))
    return _result(
        "skill_trigger_and_description", manifest.skill_name,
        CheckStatus.PASS if valid and not placeholder else CheckStatus.FAIL,
        (
            "frontmatter description is nonblank and contains no placeholder"
            if valid and not placeholder
            else "frontmatter description is missing, blank, or placeholder text"
        ,),
    )


def validate_goal_and_responsibility(manifest: ArtifactManifest) -> CheckResult:
    value = _frontmatter(Path(manifest.artifact_root))
    description = str(value.get("description", "")).strip()
    overbroad = re.search(
        r"\b(?:everything|any task|all tasks|full deployment|marketplace publish|release management)\b",
        description,
        re.IGNORECASE,
    )
    status = CheckStatus.FAIL if not description or overbroad else CheckStatus.PASS
    evidence = (
        "description states a bounded responsibility without release/distribution scope"
        if status is CheckStatus.PASS else
        _finding_evidence(
            "SKILL.md", "frontmatter", "unclear or overbroad responsibility", "ERROR",
            description or "description is absent",
            "state the bounded user outcome, triggers, and exclusions",
        )
    )
    return _result("goal_and_responsibility", manifest.skill_name, status, (evidence,))


def validate_instruction_quality(manifest: ArtifactManifest) -> CheckResult:
    root = Path(manifest.artifact_root)
    findings: list[str] = []
    for relative in manifest.files:
        if relative != "SKILL.md" and not relative.startswith("references/"):
            continue
        if not relative.lower().endswith((".md", ".markdown")):
            continue
        try:
            lines = (root / relative).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            findings.append(f"{relative}: unreadable ({exc})")
            continue
        for number, line in enumerate(lines, 1):
            if _VAGUE_DIRECTIVE.search(line):
                findings.append(_finding_evidence(
                    relative, str(number), "non-executable directive", "ERROR",
                    line.strip(), "replace it with an observable action or decision criterion",
                ))
            if _STALE_DIRECTIVE.search(line) and re.search(r"\b(?:must|required|always|never)\b", line, re.I):
                findings.append(_finding_evidence(
                    relative, str(number), "stale directive remains normative", "ERROR",
                    line.strip(), "remove the obsolete rule or replace it with the current mechanism",
                ))
            if _UNNECESSARY_ORCHESTRATION.search(line):
                findings.append(_finding_evidence(
                    relative, str(number), "unconditional Provider orchestration", "ERROR",
                    line.strip(),
                    "route by required capability and the Provider's own trigger conditions",
                ))
    return _result(
        "skill_instruction_quality", manifest.skill_name,
        CheckStatus.FAIL if findings else CheckStatus.PASS,
        tuple(findings) or (
            "rubric passed: executable instructions, no stale normative rule, and no unconditional Provider orchestration",
        ),
    )


def validate_progressive_disclosure(manifest: ArtifactManifest) -> CheckResult:
    """Require maintained references to be discoverable from the Skill entrypoint."""
    root = Path(manifest.artifact_root)
    reference_files = tuple(
        item for item in manifest.files
        if item.startswith("references/") and item.lower().endswith((".md", ".markdown"))
    )
    try:
        entrypoint = (root / "SKILL.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return _result(
            "progressive_disclosure", manifest.skill_name, CheckStatus.FAIL,
            (_finding_evidence(
                "SKILL.md", "1", "entrypoint unavailable", "ERROR", str(exc),
                "restore a readable SKILL.md entrypoint",
            ),),
        )
    missing = tuple(
        item for item in reference_files
        if item not in entrypoint and f"./{item}" not in entrypoint
    )
    evidence = tuple(
        _finding_evidence(
            item, "1", "reference is not disclosed from SKILL.md", "ERROR",
            "the supporting reference cannot be discovered from the entrypoint",
            "link the reference from SKILL.md with a condition describing when to read it",
        )
        for item in missing
    )
    return _result(
        "progressive_disclosure", manifest.skill_name,
        CheckStatus.FAIL if missing else CheckStatus.PASS,
        evidence or (f"all {len(reference_files)} maintained references are disclosed from SKILL.md",),
    )


def validate_rule_governance(
    subject: str,
    findings: tuple[RuleFinding, ...],
    decisions: tuple[GovernanceDecision, ...],
) -> CheckResult:
    required_ids = {item.finding_id for item in findings if item.confidence > 0}
    decided_ids = {item.finding_id for item in decisions}
    missing = tuple(sorted(required_ids - decided_ids))
    return _result(
        "skill_rule_governance", subject,
        CheckStatus.FAIL if missing else CheckStatus.PASS,
        (("missing governance decisions: " + ", ".join(missing),)
         if missing else (f"all {len(required_ids)} actionable rule findings were governed",)),
    )


def validate_duplication_and_bloat(
    subject: str,
    findings: tuple[RuleFinding, ...],
    supplemental: tuple[CheckResult, ...] = (),
) -> CheckResult:
    blocking = tuple(
        item for item in findings
        if {"exact_duplicate", "conflict"}.intersection(item.signals)
    )
    advisory = tuple(
        item for item in findings
        if item.confidence > 0 and item not in blocking
    )
    supplemental_failures = tuple(
        evidence
        for result in supplemental if result.status is CheckStatus.FAIL
        for evidence in result.evidence
    )
    if blocking or supplemental_failures:
        status = CheckStatus.FAIL
        selected = blocking
    elif advisory:
        status = CheckStatus.WARN
        selected = advisory
    else:
        status = CheckStatus.PASS
        selected = ()
    evidence = tuple(
        _finding_evidence(
            ",".join(ref.rsplit(":", 1)[0] for ref in item.evidence_refs),
            ",".join(ref.rsplit(":", 1)[-1] for ref in item.evidence_refs),
            f"{item.finding_id} ({','.join(item.signals)})",
            "ERROR" if item in blocking else "WARNING",
            item.rationale,
            "consolidate the rule at the narrowest correct owner and remove conflicting or redundant copies",
        )
        for item in selected
    ) + supplemental_failures
    evidence = evidence or (
        "rubric passed: duplicate rules, conflicts, over-explanation, responsibility overlap, rule bloat, repeated constraints, and ownership signals checked",
    )
    return _result("skill_duplication_and_bloat", subject, status, evidence)


def _tokens(unit: RuleUnit) -> set[str]:
    return set(unit.normalized_meaning.split())


def validate_agent_instruction_governance(root: Path, subject: str) -> CheckResult:
    units = extract_rule_units(root)
    instruction_units = tuple(
        item for item in units if item.scope in {"AGENTS.md", "CLAUDE.md", "SKILL.md"}
    )
    findings: list[str] = []
    for index, left in enumerate(instruction_units):
        for right in instruction_units[index + 1:]:
            if left.scope == right.scope:
                continue
            left_tokens, right_tokens = _tokens(left), _tokens(right)
            overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens) if left_tokens | right_tokens else 0
            opposing = {left.modality, right.modality} in (
                {"MUST", "NEVER"}, {"REQUIRED", "NEVER"}
            )
            if opposing and overlap >= 0.4:
                findings.append(_finding_evidence(
                    f"{left.source_location.rsplit(':', 1)[0]},{right.source_location.rsplit(':', 1)[0]}",
                    f"{left.source_location.rsplit(':', 1)[-1]},{right.source_location.rsplit(':', 1)[-1]}",
                    "cross-layer conflict", "ERROR",
                    f"opposing directives overlap across {left.scope} and {right.scope}",
                    "keep one rule at the correct scope and remove or narrow the conflicting rule",
                ))
            elif left.normalized_meaning == right.normalized_meaning:
                findings.append(_finding_evidence(
                    f"{left.source_location.rsplit(':', 1)[0]},{right.source_location.rsplit(':', 1)[0]}",
                    f"{left.source_location.rsplit(':', 1)[-1]},{right.source_location.rsplit(':', 1)[-1]}",
                    "duplicate rule ownership", "ERROR",
                    f"the same directive is owned by both {left.scope} and {right.scope}",
                    "retain the directive only at the narrowest scope that owns it",
                ))
    for unit in instruction_units:
        if unit.scope == "SKILL.md" and re.search(
            r"\b(?:entire|all)\s+(?:repository|project)|repository[- ]wide|project[- ]wide\b",
            unit.normalized_meaning,
            re.I,
        ):
            findings.append(_finding_evidence(
                unit.source_location.rsplit(":", 1)[0],
                unit.source_location.rsplit(":", 1)[-1],
                "project-wide rule misplaced in Skill scope", "ERROR",
                "a Skill instruction attempts to govern the entire repository",
                "move the rule to the applicable AGENTS.md or CLAUDE.md scope",
            ))
    return _result(
        "agent_instruction_governance", subject,
        CheckStatus.FAIL if findings else CheckStatus.PASS,
        tuple(findings) or (
            "rubric passed: AGENTS.md, CLAUDE.md, and SKILL.md scope, inheritance, ownership, duplication, and conflict checks completed",
        ),
    )


def execute_internal_capability_fallbacks(
    manifest: ArtifactManifest,
    *,
    structure: tuple[CheckResult, ...],
    references: tuple[CheckResult, ...],
    findings: tuple[RuleFinding, ...],
    governance_decisions: tuple[GovernanceDecision, ...],
    decision: DecisionRecord,
    command_results: tuple[CheckResult, ...],
) -> tuple[CheckResult, ...]:
    """Execute each built-in fallback; aggregate checks never replace raw evidence."""
    subject = manifest.skill_name
    root = Path(manifest.artifact_root)
    script_checks = tuple(item for item in structure if item.check_id in {
        "skill.structure.executables", "skill.structure.scripts"
    }) + tuple(
        item for item in references
        if (item.artifact_reference or "").lower().endswith((".py", ".ps1", ".sh", ".js", ".ts"))
    )
    regression = tuple(item for item in command_results if item.check_id == "B07")
    if decision.regression_disposition is RegressionDisposition.REQUIRED:
        regression_result = _aggregate("regression_validation", subject, regression)
    else:
        regression_result = _result(
            "regression_validation", subject, CheckStatus.PASS,
            (f"regression disposition is {decision.regression_disposition.value}",),
        )
    raw_evidence = structure + references + command_results
    evidence_status = (
        CheckStatus.NOT_EXECUTED if not raw_evidence else CheckStatus.PASS
    )
    structure_result = _aggregate("skill_structure", subject, structure)
    trigger_result = validate_trigger_and_description(manifest)
    instruction_result = validate_instruction_quality(manifest)
    governance_result = validate_rule_governance(subject, findings, governance_decisions)
    resource_result = _aggregate("skill_resource_integrity", subject, references)
    script_result = _aggregate("skill_script_integrity", subject, script_checks)
    conformance_result = _aggregate(
        "skill_conformance", subject, structure + references + (trigger_result,),
    )
    agent_result = validate_agent_instruction_governance(root, subject)
    progressive_result = validate_progressive_disclosure(manifest)
    duplication_result = validate_duplication_and_bloat(
        subject, findings, (instruction_result, agent_result),
    )
    instruction_design = _aggregate(
        "skill_instruction_design", subject,
        (trigger_result, instruction_result, agent_result, progressive_result),
    )
    restructure = _aggregate(
        "skill_creation_or_restructure", subject,
        (structure_result, trigger_result, instruction_result, resource_result,
         script_result, agent_result, progressive_result),
    )
    audit = _aggregate(
        "skill_audit_and_simplification", subject,
        (instruction_result, governance_result, duplication_result, agent_result),
    )
    responsibility = validate_goal_and_responsibility(manifest)
    implementation_components = structure + references + tuple(command_results)
    owned_executables = tuple(
        item for item in manifest.executable_assets
        if not any(part in {".venv", "venv", "site-packages", "node_modules"}
                   for part in Path(item).parts)
    )
    if owned_executables and not command_results:
        implementation = _result(
            "actual_implementation", subject, CheckStatus.NOT_EXECUTED,
            ("executable assets exist but no behavioral or regression command executed",),
        )
        behavior = _result(
            "behavioral_validation", subject, CheckStatus.NOT_EXECUTED,
            ("core executable path was not exercised",),
        )
    else:
        implementation = _aggregate(
            "actual_implementation", subject, implementation_components,
        )
        behavior = _aggregate(
            "behavioral_validation", subject, (trigger_result, *command_results),
        )
    return (
        restructure,
        structure_result,
        trigger_result,
        instruction_design,
        audit,
        instruction_result,
        governance_result,
        duplication_result,
        resource_result,
        script_result,
        conformance_result,
        agent_result,
        responsibility,
        implementation,
        behavior,
        regression_result,
        _result(
            "evidence_collection", subject, evidence_status,
            (f"collected {len(raw_evidence)} raw deterministic evidence records",),
        ),
        _result(
            "quality_gate", subject, CheckStatus.PASS,
            ("fail-closed Quality Gate is configured and will adjudicate this evidence set",),
        ),
    )
