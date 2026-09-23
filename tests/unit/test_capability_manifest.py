from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from engine.models import ArtifactManifest, CheckStatus, Intent, ProviderExecution


def _module():
    try:
        return importlib.import_module("engine.capability_manifest")
    except ModuleNotFoundError:
        pytest.fail("engine.capability_manifest must validate semantic manifests")


def _models():
    import engine.models as models

    required = ("ArtifactRole", "CapabilityEvidenceState", "CapabilityRecord", "CapabilityManifest")
    missing = tuple(name for name in required if not hasattr(models, name))
    assert not missing, f"missing capability manifest models: {missing}"
    return models


def _record(capability_id: str):
    models = _models()
    return models.CapabilityRecord(
        capability_id=capability_id,
        public_name=capability_id,
        capability_type="deliverable",
        declared_status="implemented",
        implementation_status="implemented",
        entrypoints=("scripts/run.py",),
        supported_profiles=(),
        supported_deliverables=(capability_id,),
        templates=(),
        schemas=(),
        validation_coverage=(f"test:{capability_id}",),
        public_claim_sources=("file=SKILL.md;line=1",),
        implementation_evidence=("file=scripts/run.py;line=1",),
        confidence=1.0,
        evidence_state=models.CapabilityEvidenceState.COMPLETE,
    )


def _manifest(role="BASELINE", capabilities=None):
    models = _models()
    return models.CapabilityManifest(
        schema_version="1.0",
        inspection_id="inspection-1",
        inspection_nonce="nonce-1",
        artifact_role=models.ArtifactRole(role),
        artifact_digest="a" * 64,
        provider_identity="bundled.capability-contract",
        capabilities=tuple(capabilities or (_record("alpha"),)),
        public_output_contract_status="present",
        public_output_contract_evidence=("file=SKILL.md;line=1",),
        evidence_origin="provider",
    )


def _artifact(root: Path) -> ArtifactManifest:
    return ArtifactManifest(
        intent=Intent.AUDIT,
        artifact_root=str(root),
        skill_name="demo",
        source_revision=None,
        source_digest="a" * 64,
        files=("SKILL.md", "scripts/run.py"),
        executable_assets=("scripts/run.py",),
        required_references=(),
        test_inventory=(),
        content_digest="a" * 64,
    )


def test_capability_manifest_digest_is_order_stable() -> None:
    module = _module()
    left = _manifest(capabilities=(_record("beta"), _record("alpha")))
    right = _manifest(capabilities=(_record("alpha"), _record("beta")))

    assert module.capability_manifest_digest(left) == module.capability_manifest_digest(right)


def test_manifest_rejects_wrong_artifact_role(tmp_path: Path) -> None:
    module = _module()
    models = _models()
    (tmp_path / "SKILL.md").write_text("demo", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run.py").write_text("pass", encoding="utf-8")

    result = module.validate_capability_manifest(
        _manifest(role="BASELINE"),
        _artifact(tmp_path),
        inspection_id="inspection-1",
        inspection_nonce="nonce-1",
        provider_id="bundled.capability-contract",
        provider_execution=ProviderExecution.EXECUTED,
        expected_role=models.ArtifactRole.CANDIDATE,
    )

    assert result.status is CheckStatus.NOT_EXECUTED
    assert "CAPABILITY_MANIFEST_ROLE_MISMATCH" in result.evidence


def test_manifest_rejects_duplicate_capability_ids(tmp_path: Path) -> None:
    module = _module()
    models = _models()
    manifest = _manifest(capabilities=(_record("alpha"), _record("alpha")))

    result = module.validate_capability_manifest(
        manifest,
        _artifact(tmp_path),
        inspection_id="inspection-1",
        inspection_nonce="nonce-1",
        provider_id="bundled.capability-contract",
        provider_execution=ProviderExecution.EXECUTED,
        expected_role=models.ArtifactRole.BASELINE,
    )

    assert result.status is CheckStatus.FAIL
    assert "CAPABILITY_MANIFEST_DUPLICATE_ID:alpha" in result.evidence
