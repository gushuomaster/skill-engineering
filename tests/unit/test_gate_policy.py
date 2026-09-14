from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import engine.quality_gate as quality_gate
from engine.contracts import load_schema
from engine.models import CheckResult, CheckStatus, GateVerdict, Intent, LifecycleState
from engine.quality_gate import GateContext, InvalidGatePolicy, adjudicate, load_gate_policy


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "policies"
CORE_POLICY_IDS = {f"B{number:02d}" for number in range(1, 13)}
CORE_REQUIRED_CHECKS = {
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
    return tuple(_check(check_id) for check_id in CORE_REQUIRED_CHECKS)


def _context() -> GateContext:
    return GateContext(
        intent=Intent.CREATE,
        state=LifecycleState.VALIDATED,
        authorized_to_modify=True,
        candidate_requires_publish=True,
        workspace_publishable=True,
        decision=None,
    )


def test_core_policy_is_schema_valid_and_keeps_all_blocking_rules() -> None:
    policy = load_gate_policy()

    Draft202012Validator(load_schema("gate-policy")).validate(policy)
    assert set(policy["blocking_policy_ids"]) == CORE_POLICY_IDS
    assert set(policy["required_checks"]) == CORE_REQUIRED_CHECKS
    assert policy["policy_version"] == "v1"


def test_project_policy_can_only_add_requirements_and_records_version() -> None:
    policy = load_gate_policy(FIXTURE_ROOT / "valid-stricter-policy.yaml")

    Draft202012Validator(load_schema("gate-policy")).validate(policy)
    assert CORE_POLICY_IDS <= set(policy["blocking_policy_ids"])
    assert CORE_REQUIRED_CHECKS <= set(policy["required_checks"])
    assert "project.security" in policy["required_checks"]
    assert "project.security" in policy["project_extensions"]
    assert policy["policy_version"] == "v1+project-v2"


def test_project_policy_cannot_remove_a_core_requirement() -> None:
    with pytest.raises(InvalidGatePolicy, match="weaken"):
        load_gate_policy(FIXTURE_ROOT / "invalid-weakened-policy.yaml")


def test_project_policy_must_be_schema_valid(tmp_path: Path) -> None:
    policy_path = tmp_path / "invalid.yaml"
    policy_path.write_text("policy_version: ''\n", encoding="utf-8")

    with pytest.raises(InvalidGatePolicy, match="schema"):
        load_gate_policy(policy_path)


def test_project_policy_must_be_utf8(tmp_path: Path) -> None:
    policy_path = tmp_path / "invalid-encoding.yaml"
    policy_path.write_bytes(b"policy_version: \xff")

    with pytest.raises(InvalidGatePolicy, match="load"):
        load_gate_policy(policy_path)


def test_adjudicate_policy_none_uses_core_policy() -> None:
    result = adjudicate(_context(), _passing_evidence())

    assert result.verdict is GateVerdict.PASS
    assert result.policy_version == "v1"


def test_project_policy_warning_extension_appears_in_gate_result() -> None:
    policy = load_gate_policy(FIXTURE_ROOT / "valid-stricter-policy.yaml")
    evidence = _passing_evidence() + (_check("project.security"),) + (
        _check(
            "W_PROJECT_MAINTAINABILITY",
            required=False,
            status=CheckStatus.WARN,
            evidence=("monitor",),
        ),
    )

    result = adjudicate(_context(), evidence, policy=policy)

    assert result.verdict is GateVerdict.PASS
    assert any("W_PROJECT_MAINTAINABILITY" in warning for warning in result.warnings)


def test_project_policy_blocking_extension_affects_verdict() -> None:
    policy = load_gate_policy(FIXTURE_ROOT / "valid-stricter-policy.yaml")
    evidence = _passing_evidence() + (
        _check(
            "P_CUSTOM",
            required=False,
            status=CheckStatus.FAIL,
            evidence=("project rule failed",),
        ),
    )

    result = adjudicate(_context(), evidence, policy=policy)

    assert result.verdict is GateVerdict.FAIL
    assert any(finding.startswith("P_CUSTOM") for finding in result.blocking_findings)


def test_effective_policy_version_is_recorded_by_adjudication() -> None:
    policy = load_gate_policy(FIXTURE_ROOT / "valid-stricter-policy.yaml")

    result = adjudicate(_context(), _passing_evidence(), policy=policy)

    assert result.policy_version == "v1+project-v2"


def test_explicit_policies_are_independent_without_global_state() -> None:
    base = load_gate_policy()
    blocking_policy = {
        **base,
        "policy_version": "v1+blocking",
        "blocking_policy_ids": [*base["blocking_policy_ids"], "P_CUSTOM"],
        "project_extensions": ["P_CUSTOM"],
    }
    warning_policy = {
        **base,
        "policy_version": "v1+warning",
        "warning_policy_ids": [*base["warning_policy_ids"], "W_CUSTOM"],
        "project_extensions": ["W_CUSTOM"],
    }
    evidence = _passing_evidence() + (
        _check(
            "P_CUSTOM",
            required=False,
            status=CheckStatus.FAIL,
            evidence=("project rule failed",),
        ),
    )

    first = adjudicate(_context(), evidence, policy=blocking_policy)
    second = adjudicate(_context(), evidence, policy=warning_policy)

    assert first.verdict is GateVerdict.FAIL
    assert second.verdict is GateVerdict.PASS
    assert first.policy_version == "v1+blocking"
    assert second.policy_version == "v1+warning"


def test_explicit_effective_policy_does_not_read_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = load_gate_policy()

    def fail_if_read(_path: Path) -> dict[str, object]:
        raise AssertionError("explicit policy must not read configuration")

    monkeypatch.setattr(quality_gate, "_read_policy", fail_if_read)

    result = adjudicate(_context(), _passing_evidence(), policy=policy)

    assert result.verdict is GateVerdict.PASS
