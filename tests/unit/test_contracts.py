"""Machine-contract validation tests."""
import json
from pathlib import Path
import pytest
from jsonschema import ValidationError
from engine.contracts import validate_contract
FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "contracts"
def load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))
@pytest.mark.parametrize("schema_name, fixture_name", [("artifact-manifest", "artifact_manifest_create.json"), ("decision-record", "decision_create.json"), ("provider-result", "provider_result.json"), ("check-result", "check_result.json"), ("regression-case", "regression_case.json"), ("behavioral-scenario", "behavioral_scenario.json"), ("behavioral-result", "behavioral_result.json"), ("gate-policy", "gate_policy.json"), ("gate-result", "gate_audit_pass.json"), ("semantic-confirmation", "semantic_confirmation.json")])
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


def test_provider_result_schema_is_compatible_with_codex_structured_outputs() -> None:
    from engine.contracts import load_schema

    assert "allOf" not in load_schema("provider-result")
@pytest.mark.parametrize("fixture_name", ["gate_publish_with_fail.json", "gate_unchanged_authorized.json"])
def test_gate_rejects_invalid_publication_authority(fixture_name: str) -> None:
    with pytest.raises(ValidationError): validate_contract("gate-result", load_fixture(fixture_name))
def test_audit_pass_is_not_apply_authorized() -> None:
    payload = load_fixture("gate_audit_pass.json")
    validate_contract("gate-result", payload)
    assert payload["verdict"] == "PASS"
    assert payload["apply_authorized"] is False
    assert payload["outcome"] == "UNCHANGED_VALIDATED"


def test_audit_complete_valid_rejects_non_full_coverage() -> None:
    payload = load_fixture("gate_audit_pass.json")
    payload["outcome"] = "AUDIT_COMPLETE_VALID"
    payload["coverage_status"] = "PARTIAL"
    with pytest.raises(ValidationError):
        validate_contract("gate-result", payload)

def test_modify_defect_decision_requires_root_cause() -> None:
    with pytest.raises(ValidationError): validate_contract("decision-record", load_fixture("decision_modify_defect_missing_root_cause.json"))

def test_gate_rejects_ready_to_publish_fail() -> None:
    with pytest.raises(ValidationError): validate_contract("gate-result", load_fixture("gate_ready_fail.json"))

@pytest.mark.parametrize("fixture_name", ["check_result_skip_empty_reason.json", "check_result_bad_stage.json"])
def test_check_result_requires_reason_and_known_stage(fixture_name: str) -> None:
    with pytest.raises(ValidationError): validate_contract("check-result", load_fixture(fixture_name))

def test_decision_rejects_unknown_control_gap() -> None:
    with pytest.raises(ValidationError): validate_contract("decision-record", load_fixture("decision_unknown_control_gap.json"))

def test_semantic_confirmation_requires_codex_and_exact_digest() -> None:
    payload = load_fixture("semantic_confirmation.json")
    payload["confirmed_by"] = "provider"
    with pytest.raises(ValidationError):
        validate_contract("semantic-confirmation", payload)


def test_inspection_bundle_schema_accepts_engine_payload(tmp_path: Path) -> None:
    from engine.models import Intent
    from engine.orchestrator import PipelineOrchestrator
    from engine.serialization import to_data

    source = tmp_path / "demo"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo skill.\n---\n\n# Demo\n",
        encoding="utf-8",
    )
    inspection = PipelineOrchestrator().inspect(Intent.AUDIT_ONLY, source)
    validate_contract("inspection-bundle", to_data(inspection))
