from __future__ import annotations

import engine.models as models
import pytest
from jsonschema import ValidationError

from engine.contracts import validate_contract


def _payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "inspection_id": "inspection-1",
        "inspection_nonce": "nonce-1",
        "artifact_role": "BASELINE",
        "artifact_digest": "a" * 64,
        "provider_identity": "bundled.capability-contract",
        "capabilities": [
            {
                "capability_id": "document-generation",
                "public_name": "Document generation",
                "capability_type": "deliverable_set",
                "declared_status": "implemented",
                "implementation_status": "implemented",
                "entrypoints": ["cli:generate"],
                "supported_profiles": ["profile-a", "profile-b"],
                "supported_deliverables": ["A", "B"],
                "templates": ["template-a", "template-b"],
                "schemas": ["schema-a"],
                "validation_coverage": ["test:A", "test:B"],
                "public_claim_sources": ["file=SKILL.md;line=10"],
                "implementation_evidence": ["file=scripts/run.py;line=20"],
                "confidence": 1.0,
                "evidence_state": "COMPLETE",
            }
        ],
        "public_output_contract_status": "present",
        "public_output_contract_evidence": ["file=SKILL.md;line=10"],
        "evidence_origin": "provider",
    }


def test_capability_record_preserves_structured_public_scope() -> None:
    capability_record = getattr(models, "CapabilityRecord", None)
    evidence_state = getattr(models, "CapabilityEvidenceState", None)
    assert capability_record is not None, "CapabilityRecord must model public capability scope"
    assert evidence_state is not None, "CapabilityEvidenceState must distinguish unverifiable evidence"

    record = capability_record(
        capability_id="document-generation",
        public_name="Document generation",
        capability_type="deliverable_set",
        declared_status="implemented",
        implementation_status="implemented",
        entrypoints=("cli:generate",),
        supported_profiles=("profile-a", "profile-b"),
        supported_deliverables=("A", "B"),
        templates=("template-a", "template-b"),
        schemas=("schema-a",),
        validation_coverage=("test:A", "test:B"),
        public_claim_sources=("file=SKILL.md;line=10",),
        implementation_evidence=("file=scripts/run.py;line=20",),
        confidence=1.0,
        evidence_state=evidence_state.COMPLETE,
    )

    assert record.supported_deliverables == ("A", "B")
    assert record.validation_coverage == ("test:A", "test:B")


def test_capability_manifest_schema_requires_artifact_digest() -> None:
    payload = _payload()
    payload.pop("artifact_digest")
    with pytest.raises((ValidationError, FileNotFoundError)):
        validate_contract("capability-manifest", payload)


def test_capability_manifest_schema_accepts_complete_payload() -> None:
    try:
        validate_contract("capability-manifest", _payload())
    except FileNotFoundError:
        pytest.fail("capability-manifest schema must exist")
