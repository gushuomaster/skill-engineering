from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from engine.contracts import load_schema
from engine.quality_gate import InvalidGatePolicy, load_gate_policy


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
