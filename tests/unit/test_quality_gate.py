from dataclasses import replace
from pathlib import Path

import pytest

from engine.inventory import build_artifact_manifest
from engine.models import (
    CheckResult,
    CheckStatus,
    ControlGap,
    DecisionRecord,
    GateOutcome,
    GateResult,
    GateVerdict,
    Intent,
    LifecycleState,
    PrimaryIssueClass,
    RegressionDisposition,
)
from engine.quality_gate import GateContext, adjudicate
from validators.skill_structure import validate_skill_structure


CORE_POLICY_IDS = tuple(f"B{number:02d}" for number in range(1, 13))
REQUIRED_CHECK_IDS = (
    "skill.structure.skill_md",
    "skill.structure.frontmatter",
    "skill.structure.name_format",
    "skill.structure.directory_name",
    "skill.structure.placeholders",
    "skill.structure.critical_assets",
    "skill.structure.schema",
    "skill.structure.executables",
    "skill.structure.required_dependencies",
)


def _check(check_id: str, **overrides: object) -> CheckResult:
    values: dict[str, object] = {
        "check_id": check_id,
        "source": "internal",
        "subject": "demo",
        "required": True,
        "status": CheckStatus.PASS,
        "deterministic": True,
        "reproducible": True,
        "confidence": 1.0,
        "evidence": ("verified",),
        "remediation_stage": LifecycleState.VALIDATED,
        "artifact_reference": None,
    }
    values.update(overrides)
    return CheckResult(**values)


def _passing_evidence() -> tuple[CheckResult, ...]:
    return tuple(_check(check_id) for check_id in REQUIRED_CHECK_IDS)


def _context(**overrides: object) -> GateContext:
    values: dict[str, object] = {
        "intent": Intent.CREATE,
        "state": LifecycleState.VALIDATED,
        "authorized_to_modify": True,
        "candidate_requires_publish": True,
        "workspace_publishable": True,
        "decision": None,
    }
    values.update(overrides)
    return GateContext(**values)


def _decision(**overrides: object) -> DecisionRecord:
    values: dict[str, object] = {
        "intent": Intent.CREATE,
        "primary_issue_class": PrimaryIssueClass.NO_DEFECT,
        "control_gaps": (ControlGap.NONE,),
        "regression_disposition": RegressionDisposition.NOT_APPLICABLE,
        "root_cause": None,
        "evidence_limitations": (),
        "selected_mechanisms": (),
        "rejected_mechanisms": (),
        "prompt_rule_justification": None,
    }
    values.update(overrides)
    return DecisionRecord(**values)


@pytest.mark.parametrize("policy_id", CORE_POLICY_IDS)
def test_each_core_policy_failure_is_executable_and_blocks(policy_id: str) -> None:
    evidence = _passing_evidence() + (
        _check(policy_id, status=CheckStatus.FAIL, evidence=("unresolved",)),
    )

    result = adjudicate(_context(), evidence)

    assert result.verdict is GateVerdict.FAIL
    assert any(finding.startswith(policy_id) for finding in result.blocking_findings)
    assert result.publish_authorized is False


@pytest.mark.parametrize(
    "replacement",
    [
        None,
        _check(
            "skill.structure.frontmatter",
            status=CheckStatus.ERROR,
            evidence=("checker crashed",),
        ),
        _check("skill.structure.frontmatter", deterministic=False),
        _check("skill.structure.frontmatter", reproducible=False),
    ],
)
def test_b08_blocks_missing_erroring_or_untrustworthy_required_evidence(
    replacement: CheckResult | None,
) -> None:
    evidence = tuple(
        result
        for result in _passing_evidence()
        if result.check_id != "skill.structure.frontmatter"
    )
    if replacement is not None:
        evidence += (replacement,)

    result = adjudicate(_context(), evidence)

    assert result.verdict is GateVerdict.FAIL
    assert any(finding.startswith("B08") for finding in result.blocking_findings)


def test_required_check_summary_does_not_let_an_extra_mask_a_missing_check() -> None:
    evidence = tuple(
        result
        for result in _passing_evidence()
        if result.check_id != "skill.structure.frontmatter"
    ) + (_check("tests.additional"),)

    result = adjudicate(_context(), evidence)

    assert "1 missing" in result.required_checks_summary


@pytest.mark.parametrize("source", ["provider:remote", "checker:optional"])
def test_optional_provider_or_checker_error_is_warning_only(source: str) -> None:
    evidence = _passing_evidence() + (
        _check(
            "optional.semantic-review",
            source=source,
            subject="optional review",
            required=False,
            status=CheckStatus.ERROR,
            evidence=("unavailable",),
        ),
    )

    result = adjudicate(_context(), evidence)

    assert result.verdict is GateVerdict.PASS
    assert result.blocking_findings == ()
    assert any("optional.semantic-review" in warning for warning in result.warnings)


def test_malformed_optional_provider_result_is_warning_only() -> None:
    evidence = _passing_evidence() + (
        _check(
            "",
            source="provider:remote",
            subject="optional review",
            required=False,
            status=CheckStatus.ERROR,
            evidence=(),
        ),
    )

    result = adjudicate(_context(), evidence)

    assert result.verdict is GateVerdict.PASS
    assert not any(finding.startswith("B08") for finding in result.blocking_findings)
    assert any("invalid optional evidence" in warning for warning in result.warnings)


def test_b11_blocks_unverified_runtime_critical_reference() -> None:
    evidence = tuple(
        replace(
            result,
            status=CheckStatus.FAIL,
            subject="runtime-critical reference: scripts/run.ps1",
            artifact_reference="scripts/run.ps1",
            evidence=("reference unresolved",),
        )
        if result.check_id == "skill.structure.executables"
        else result
        for result in _passing_evidence()
    )

    result = adjudicate(_context(), evidence)

    assert any(finding.startswith("B11") for finding in result.blocking_findings)


def test_b11_critical_checker_error_maps_to_b08_and_b11() -> None:
    evidence = tuple(
        replace(
            result,
            status=CheckStatus.ERROR,
            subject="schema: schemas/runtime.schema.json",
            artifact_reference="schemas/runtime.schema.json",
            evidence=("validator crashed",),
        )
        if result.check_id == "skill.structure.schema"
        else result
        for result in _passing_evidence()
    )

    result = adjudicate(_context(), evidence)

    assert any(finding.startswith("B08") for finding in result.blocking_findings)
    assert any(finding.startswith("B11") for finding in result.blocking_findings)


def test_unverified_optional_documentation_is_warning_only() -> None:
    evidence = _passing_evidence() + (
        _check(
            "reference.optional-documentation",
            subject="optional documentation: docs/background.md",
            required=False,
            status=CheckStatus.FAIL,
            evidence=("reference unresolved",),
            artifact_reference="docs/background.md",
        ),
    )

    result = adjudicate(_context(), evidence)

    assert result.verdict is GateVerdict.PASS
    assert any("docs/background.md" in warning for warning in result.warnings)


def test_b11_label_does_not_make_optional_documentation_blocking() -> None:
    evidence = _passing_evidence() + (
        _check(
            "B11",
            source="checker:links",
            subject="optional documentation: docs/background.md",
            required=False,
            status=CheckStatus.FAIL,
            evidence=("reference unresolved",),
            artifact_reference="docs/background.md",
        ),
    )

    result = adjudicate(_context(), evidence)

    assert result.verdict is GateVerdict.PASS
    assert not any(finding.startswith("B11") for finding in result.blocking_findings)
    assert any("docs/background.md" in warning for warning in result.warnings)


@pytest.mark.parametrize("required", [False, True])
def test_rule_bloat_finding_does_not_directly_fail_gate(required: bool) -> None:
    evidence = _passing_evidence() + (
        _check(
            "rule-bloat",
            required=required,
            status=CheckStatus.FAIL,
            evidence=("absolute density elevated",),
        ),
    )

    result = adjudicate(_context(), evidence)

    assert result.verdict is GateVerdict.PASS
    assert any("rule-bloat" in warning for warning in result.warnings)


def test_b12_external_finding_mapped_to_internal_policy_blocks() -> None:
    evidence = _passing_evidence() + (
        _check(
            "B12",
            source="provider:external-review",
            required=False,
            status=CheckStatus.FAIL,
            evidence=("maps_to:B04", "unresolved contract issue"),
        ),
    )

    result = adjudicate(_context(), evidence)

    assert result.verdict is GateVerdict.FAIL
    assert any(finding.startswith("B12") for finding in result.blocking_findings)


@pytest.mark.parametrize("policy_id", ["B01", "B05", "B10", "B12"])
def test_external_self_report_without_mapping_is_warning_only(policy_id: str) -> None:
    evidence = _passing_evidence() + (
        _check(
            policy_id,
            source="provider:external-review",
            required=False,
            status=CheckStatus.FAIL,
            evidence=("unresolved contract issue",),
        ),
    )

    result = adjudicate(_context(), evidence)

    assert result.verdict is GateVerdict.PASS
    assert not any(finding.startswith(policy_id) for finding in result.blocking_findings)
    assert any(policy_id in warning for warning in result.warnings)


def test_b06_blocks_unjustified_prompt_rule_decision() -> None:
    decision = _decision(
        primary_issue_class=PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE,
        selected_mechanisms=("prompt_rule",),
    )

    result = adjudicate(_context(decision=decision), _passing_evidence())

    assert result.verdict is GateVerdict.FAIL
    assert any(finding.startswith("B06") for finding in result.blocking_findings)


def test_b07_blocks_absent_required_regression() -> None:
    decision = _decision(regression_disposition=RegressionDisposition.REQUIRED)
    evidence = tuple(
        result for result in _passing_evidence() if result.check_id != "B07"
    )

    result = adjudicate(_context(decision=decision), evidence)

    assert result.verdict is GateVerdict.FAIL
    assert any(finding.startswith("B07") for finding in result.blocking_findings)


def test_task_6_structure_evidence_can_pass_the_gate() -> None:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "skills" / "minimal-valid"
    manifest = build_artifact_manifest(fixture, Intent.AUDIT_ONLY, None)
    evidence = validate_skill_structure(manifest)

    result = adjudicate(
        _context(intent=Intent.AUDIT_ONLY, candidate_requires_publish=False),
        evidence,
    )

    assert result.verdict is GateVerdict.PASS
    assert result.outcome is GateOutcome.UNCHANGED_VALIDATED


@pytest.mark.parametrize(
    "check_id,policy_id",
    [
        ("skill.structure.skill_md", "B02"),
        ("skill.structure.placeholders", "B02"),
        ("skill.structure.frontmatter", "B03"),
        ("skill.structure.name_format", "B03"),
        ("skill.structure.executables", "B11"),
        ("reference.required.exists", "B02"),
    ],
)
def test_validator_failures_map_to_internal_blocking_policy(
    check_id: str, policy_id: str
) -> None:
    evidence = tuple(
        replace(result, status=CheckStatus.FAIL, evidence=("unresolved",))
        if result.check_id == check_id
        else result
        for result in _passing_evidence()
    )
    if check_id not in REQUIRED_CHECK_IDS:
        evidence += (
            _check(check_id, status=CheckStatus.FAIL, evidence=("unresolved",)),
        )

    result = adjudicate(_context(), evidence)

    assert any(
        finding.startswith(policy_id) for finding in result.blocking_findings
    )


def test_unmapped_required_test_failure_maps_to_b04() -> None:
    evidence = _passing_evidence() + (
        _check(
            "tests.applicable",
            status=CheckStatus.FAIL,
            evidence=("test suite failed",),
        ),
    )

    result = adjudicate(_context(), evidence)

    assert any(finding.startswith("B04") for finding in result.blocking_findings)


def test_adjudicate_is_the_gate_result_authority() -> None:
    evidence = _passing_evidence()

    result = adjudicate(_context(), evidence)

    assert isinstance(result, GateResult)
    assert not any(isinstance(item, GateResult) for item in evidence)


def test_audit_only_pass_is_unchanged_and_never_publish_authorized() -> None:
    result = adjudicate(
        _context(intent=Intent.AUDIT_ONLY, candidate_requires_publish=False),
        _passing_evidence(),
    )

    assert result.verdict is GateVerdict.PASS
    assert result.outcome is GateOutcome.UNCHANGED_VALIDATED
    assert result.publish_authorized is False


def test_audit_only_pass_ignores_inconsistent_candidate_publish_flag() -> None:
    result = adjudicate(
        _context(intent=Intent.AUDIT_ONLY, candidate_requires_publish=True),
        _passing_evidence(),
    )

    assert result.verdict is GateVerdict.PASS
    assert result.outcome is GateOutcome.UNCHANGED_VALIDATED
    assert result.publish_authorized is False


def test_publishable_authorized_candidate_pass_is_ready_to_publish() -> None:
    result = adjudicate(_context(), _passing_evidence())

    assert result.verdict is GateVerdict.PASS
    assert result.outcome is GateOutcome.READY_TO_PUBLISH
    assert result.publish_authorized is True


def test_pass_without_publishable_workspace_does_not_authorize_publication() -> None:
    result = adjudicate(
        _context(workspace_publishable=False),
        _passing_evidence(),
    )

    assert result.verdict is GateVerdict.PASS
    assert result.outcome is GateOutcome.REMEDIATION_REQUIRED
    assert result.publish_authorized is False


def test_unauthorized_candidate_is_blocked_by_b09() -> None:
    result = adjudicate(
        _context(authorized_to_modify=False),
        _passing_evidence(),
    )

    assert result.verdict is GateVerdict.FAIL
    assert result.outcome is GateOutcome.REMEDIATION_REQUIRED
    assert any(finding.startswith("B09") for finding in result.blocking_findings)
    assert result.publish_authorized is False


def test_audit_only_failure_is_unchanged_blocked() -> None:
    evidence = _passing_evidence() + (
        _check(
            "tests.applicable",
            status=CheckStatus.FAIL,
            evidence=("tests failed",),
        ),
    )

    result = adjudicate(
        _context(intent=Intent.AUDIT_ONLY, candidate_requires_publish=False),
        evidence,
    )

    assert result.verdict is GateVerdict.FAIL
    assert result.outcome is GateOutcome.UNCHANGED_BLOCKED
    assert result.publish_authorized is False
