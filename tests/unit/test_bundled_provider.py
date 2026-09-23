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
