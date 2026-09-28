from __future__ import annotations

import importlib
from pathlib import Path
import warnings

import pytest

from engine.providers import normalize_provider_result


ROOT = Path(__file__).resolve().parents[2]


def _host_adapters():
    module = importlib.import_module("engine.host_adapters")
    assert hasattr(module, "build_default_provider_adapters"), (
        "host adapters must expose packaged default semantic Providers"
    )
    return module


def _manifest_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "inspection_id": "inspection-1",
        "inspection_nonce": "nonce-1",
        "artifact_role": "BASELINE",
        "artifact_digest": "a" * 64,
        "provider_identity": "bundled.capability-contract",
        "capabilities": [],
        "public_output_contract_status": "absent",
        "public_output_contract_evidence": ["file=SKILL.md;line=1"],
        "evidence_origin": "provider",
    }


def _deliverable_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "inspection_id": "inspection-1",
        "target_digest": "a" * 64,
        "inspection_nonce": "nonce-1",
        "provider_identity": "bundled.deliverable-contract",
        "deliverables": [],
        "scope_conflicts": [],
        "applicability_status": "not_applicable",
        "applicability_reason": "The target declares no deliverables.",
        "applicability_evidence": ["file=SKILL.md;line=1"],
        "evidence_origin": "provider",
    }


def _provider_payload(capability: str, provider_id: str) -> dict[str, object]:
    return {
        "provider_id": provider_id,
        "capability": capability,
        "provider_status": "AVAILABLE",
        "findings": [],
        "candidate_changes": [],
        "evidence": ["provider executed"],
        "limitations": [],
        "fallback_used": False,
        "deliverable_contract": None,
        "capability_manifest": None,
    }


def test_default_semantic_providers_are_packaged_and_selected() -> None:
    adapters = _host_adapters().build_default_provider_adapters(ROOT)

    assert {item.descriptor.capability for item in adapters} == {
        "CAPABILITY_CONTRACT",
        "DELIVERABLE_CONTRACT",
    }
    assert all(item.descriptor.availability.value == "AVAILABLE" for item in adapters)


def test_provider_result_accepts_typed_capability_manifest() -> None:
    payload = {
        "provider_id": "bundled.capability-contract",
        "capability": "CAPABILITY_CONTRACT",
        "provider_status": "AVAILABLE",
        "findings": [],
        "candidate_changes": [],
        "evidence": ["provider executed"],
        "limitations": [],
        "fallback_used": False,
        "capability_manifest": _manifest_payload(),
    }

    result = normalize_provider_result(payload, capability="CAPABILITY_CONTRACT")

    assert result.capability_manifest is not None
    assert result.capability_manifest.artifact_digest == "a" * 64


def test_provider_result_accepts_owned_deliverable_contract() -> None:
    payload = _provider_payload(
        "DELIVERABLE_CONTRACT", "bundled.deliverable-contract",
    )
    payload["deliverable_contract"] = _deliverable_payload()

    result = normalize_provider_result(payload, capability="DELIVERABLE_CONTRACT")

    assert result.deliverable_contract is not None
    assert result.capability_manifest is None


@pytest.mark.parametrize(
    ("capability", "provider_id", "evidence_field", "evidence_factory"),
    (
        (
            "CAPABILITY_CONTRACT",
            "bundled.capability-contract",
            "capability_manifest",
            _manifest_payload,
        ),
        (
            "DELIVERABLE_CONTRACT",
            "bundled.deliverable-contract",
            "deliverable_contract",
            _deliverable_payload,
        ),
    ),
)
def test_normalizer_rejects_nested_provider_identity_mismatch(
    capability: str,
    provider_id: str,
    evidence_field: str,
    evidence_factory,
) -> None:
    payload = _provider_payload(capability, provider_id)
    evidence = evidence_factory()
    evidence["provider_identity"] = "capability-contract-provider"
    payload[evidence_field] = evidence

    with pytest.raises(ValueError, match="provider_identity does not match descriptor"):
        normalize_provider_result(
            payload, capability=capability, provider_id=provider_id,
        )


def test_nested_provider_schema_uses_local_reference_registry() -> None:
    payload = {
        "provider_id": "bundled.capability-contract",
        "capability": "CAPABILITY_CONTRACT",
        "provider_status": "AVAILABLE",
        "findings": [],
        "candidate_changes": [],
        "evidence": [],
        "limitations": [],
        "fallback_used": False,
        "capability_manifest": _manifest_payload(),
    }

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        normalize_provider_result(payload, capability="CAPABILITY_CONTRACT")

    assert not [item for item in captured if item.category is DeprecationWarning]


def test_provider_result_still_rejects_authority_fields() -> None:
    payload = {
        "provider_id": "bundled.capability-contract",
        "capability": "CAPABILITY_CONTRACT",
        "provider_status": "AVAILABLE",
        "findings": [],
        "candidate_changes": [],
        "evidence": [],
        "limitations": [],
        "fallback_used": False,
        "capability_manifest": _manifest_payload(),
        "apply_authorization": True,
    }

    with pytest.raises(ValueError, match="forbidden authority fields"):
        normalize_provider_result(payload, capability="CAPABILITY_CONTRACT")


def test_capability_provider_cannot_return_deliverable_contract() -> None:
    payload = _provider_payload(
        "CAPABILITY_CONTRACT", "bundled.capability-contract",
    )
    payload["capability_manifest"] = _manifest_payload()
    payload["deliverable_contract"] = _deliverable_payload()

    with pytest.raises(
        ValueError, match="CAPABILITY_CONTRACT provider cannot return deliverable_contract"
    ):
        normalize_provider_result(payload, capability="CAPABILITY_CONTRACT")


def test_deliverable_provider_cannot_return_capability_manifest() -> None:
    payload = _provider_payload(
        "DELIVERABLE_CONTRACT", "bundled.deliverable-contract",
    )
    payload["deliverable_contract"] = _deliverable_payload()
    manifest = _manifest_payload()
    manifest["provider_identity"] = "bundled.deliverable-contract"
    payload["capability_manifest"] = manifest

    with pytest.raises(
        ValueError, match="DELIVERABLE_CONTRACT provider cannot return capability_manifest"
    ):
        normalize_provider_result(payload, capability="DELIVERABLE_CONTRACT")


def test_bundled_provider_prompts_enforce_capability_specific_ownership() -> None:
    adapters = {
        item.descriptor.capability: item
        for item in _host_adapters().build_default_provider_adapters(ROOT)
    }
    request = {
        "mode": "AUDIT",
        "inspection_id": "inspection-1",
        "inspection_nonce": "nonce-1",
        "artifact_role": "BASELINE",
        "target_digest": "a" * 64,
        "deliverable_contract_applicability": "REQUIRED",
    }
    target = ROOT / "tests" / "fixtures" / "skills" / "minimal-valid"

    capability_prompt = adapters["CAPABILITY_CONTRACT"]._prompt(
        "CAPABILITY_CONTRACT", target, request, "invoke-1", "b" * 64,
    )
    deliverable_prompt = adapters["DELIVERABLE_CONTRACT"]._prompt(
        "DELIVERABLE_CONTRACT", target, request, "invoke-2", "b" * 64,
    )

    assert "deliverable_contract to null" in capability_prompt
    assert "capability_manifest as the only formal evidence payload" in capability_prompt
    assert "capability_manifest to null" in deliverable_prompt
    assert "deliverable_contract as the only formal evidence payload" in deliverable_prompt
    assert "provider_identity=bundled.deliverable-contract" in deliverable_prompt


def test_host_derives_capability_specific_structured_output_schemas() -> None:
    adapters = {
        item.descriptor.capability: item
        for item in _host_adapters().build_default_provider_adapters(ROOT)
    }

    request = {
        "inspection_id": "inspection-1",
        "inspection_nonce": "nonce-1",
        "artifact_role": "BASELINE",
        "target_digest": "a" * 64,
    }
    capability_schema = adapters["CAPABILITY_CONTRACT"]._structured_output_schema(
        "CAPABILITY_CONTRACT", request=request,
    )
    deliverable_schema = adapters["DELIVERABLE_CONTRACT"]._structured_output_schema(
        "DELIVERABLE_CONTRACT", request=request,
    )

    for capability, schema in (
        ("CAPABILITY_CONTRACT", capability_schema),
        ("DELIVERABLE_CONTRACT", deliverable_schema),
    ):
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert not {"anyOf", "oneOf", "allOf", "enum", "const"}.intersection(schema)
        assert schema["properties"]["capability"] == {
            "type": "string", "const": capability,
        }
    assert capability_schema["properties"]["provider_id"] == {
        "type": "string", "const": "bundled.capability-contract",
    }
    assert deliverable_schema["properties"]["provider_id"] == {
        "type": "string", "const": "bundled.deliverable-contract",
    }
    capability_contract = capability_schema["$defs"]["capabilityManifest"]
    deliverable_contract = deliverable_schema["$defs"]["deliverableContract"]
    assert capability_contract["properties"]["provider_identity"] == {
        "type": "string", "const": "bundled.capability-contract",
    }
    assert capability_contract["properties"]["artifact_digest"] == {
        "type": "string", "const": "a" * 64,
    }
    assert deliverable_contract["properties"]["provider_identity"] == {
        "type": "string", "const": "bundled.deliverable-contract",
    }
    assert deliverable_contract["properties"]["inspection_id"] == {
        "type": "string", "const": "inspection-1",
    }
    assert capability_schema["properties"]["deliverable_contract"] == {"type": "null"}
    assert deliverable_schema["properties"]["capability_manifest"] == {"type": "null"}
