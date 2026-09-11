"""Machine-contract validation tests."""
import json
from pathlib import Path
import pytest
from jsonschema import ValidationError
from engine.contracts import validate_contract
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "contracts"
def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
@pytest.mark.parametrize("schema_name, fixture_name", [("artifact-manifest", "artifact_manifest_create.json"), ("decision-record", "decision_create.json"), ("provider-result", "provider_result.json"), ("check-result", "check_result.json"), ("regression-case", "regression_case.json"), ("behavioral-scenario", "behavioral_scenario.json"), ("behavioral-result", "behavioral_result.json"), ("gate-policy", "gate_policy.json"), ("gate-result", "gate_audit_pass.json")])
def test_each_schema_accepts_positive_fixture(schema_name: str, fixture_name: str) -> None:
    validate_contract(schema_name, load_fixture(fixture_name))
@pytest.mark.parametrize("schema_name, fixture_name", [("check-result", "check_result_invalid.json"), ("regression-case", "regression_case_invalid.json"), ("behavioral-scenario", "behavioral_scenario_invalid.json"), ("behavioral-result", "behavioral_result_invalid.json"), ("gate-policy", "gate_policy_invalid.json")])
def test_each_remaining_schema_rejects_invalid_fixture(schema_name: str, fixture_name: str) -> None:
    with pytest.raises(ValidationError): validate_contract(schema_name, load_fixture(fixture_name))
def test_modify_manifest_requires_source_digest() -> None:
    with pytest.raises(ValidationError): validate_contract("artifact-manifest", load_fixture("artifact_manifest_modify_missing_digest.json"))
def test_fix_decision_requires_root_cause() -> None:
    with pytest.raises(ValidationError): validate_contract("decision-record", load_fixture("decision_fix_missing_root_cause.json"))
def test_defect_audit_decision_requires_root_cause() -> None:
    with pytest.raises(ValidationError): validate_contract("decision-record", load_fixture("decision_audit_defect_missing_root_cause.json"))
def test_provider_cannot_emit_final_authority_fields() -> None:
    with pytest.raises(ValidationError): validate_contract("provider-result", load_fixture("provider_result_with_verdict.json"))
@pytest.mark.parametrize("fixture_name", ["gate_publish_with_fail.json", "gate_unchanged_authorized.json"])
def test_gate_rejects_invalid_publication_authority(fixture_name: str) -> None:
    with pytest.raises(ValidationError): validate_contract("gate-result", load_fixture(fixture_name))
def test_audit_pass_is_not_publish_authorized() -> None:
    payload = load_fixture("gate_audit_pass.json")
    validate_contract("gate-result", payload)
    assert payload["verdict"] == "PASS"
    assert payload["publish_authorized"] is False
    assert payload["outcome"] == "UNCHANGED_VALIDATED"
