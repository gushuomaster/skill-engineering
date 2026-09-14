from pathlib import Path

import yaml

from engine.contracts import validate_contract
from engine.quality_gate import load_gate_policy


ROOT = Path(__file__).resolve().parents[2]
CORE_BLOCKING_IDS = {f"B{number:02d}" for number in range(1, 13)}


def test_agents_md_contains_no_case_specific_bug_rules() -> None:
    content = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "Windows encoding bug" not in content
    assert len(content.splitlines()) <= 40


def test_project_policy_cannot_weaken_core_rules() -> None:
    policy = load_gate_policy(ROOT / "config" / "gate-policy.yaml")
    assert CORE_BLOCKING_IDS.issubset(set(policy["blocking_policy_ids"]))


def test_provider_configuration_is_separate_and_schema_shaped() -> None:
    config = yaml.safe_load((ROOT / "config" / "providers.yaml").read_text(encoding="utf-8"))
    assert isinstance(config, dict)
    assert isinstance(config.get("providers"), list)
    for provider in config["providers"]:
        assert {"provider_id", "capability", "optional", "fallback_provider"}.issubset(provider)
        assert "blocking_policy_ids" not in provider

