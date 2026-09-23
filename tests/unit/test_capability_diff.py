from __future__ import annotations

import importlib

import pytest


def _modules():
    try:
        diff_module = importlib.import_module("engine.capability_diff")
    except ModuleNotFoundError:
        pytest.fail("engine.capability_diff must compare baseline and candidate semantics")
    import engine.models as models

    required = ("ArtifactRole", "CapabilityEvidenceState", "CapabilityRecord", "CapabilityManifest")
    missing = tuple(name for name in required if not hasattr(models, name))
    assert not missing, f"missing capability models: {missing}"
    return diff_module, models


def _record(
    capability_id: str,
    *,
    deliverables=("SRS", "SDD_DETAIL", "STP", "STD", "STR"),
    implementation_status="implemented",
    validation_coverage=("SRS", "SDD_DETAIL", "STP", "STD", "STR"),
    evidence_state="COMPLETE",
):
    _, models = _modules()
    return models.CapabilityRecord(
        capability_id=capability_id,
        public_name="Document generation",
        capability_type="deliverable_set",
        declared_status="implemented",
        implementation_status=implementation_status,
        entrypoints=("cli:generate",),
        supported_profiles=tuple(deliverables),
        supported_deliverables=tuple(deliverables),
        templates=tuple(f"template:{item}" for item in deliverables),
        schemas=(),
        validation_coverage=tuple(validation_coverage),
        public_claim_sources=("file=SKILL.md;line=1",),
        implementation_evidence=("file=scripts/run.py;line=1",),
        confidence=1.0,
        evidence_state=models.CapabilityEvidenceState(evidence_state),
    )


def _manifest(role: str, capabilities):
    _, models = _modules()
    return models.CapabilityManifest(
        schema_version="1.0",
        inspection_id="inspection-1",
        inspection_nonce="nonce-1",
        artifact_role=models.ArtifactRole(role),
        artifact_digest=("a" if role == "BASELINE" else "b") * 64,
        provider_identity="bundled.capability-contract",
        capabilities=tuple(capabilities),
        public_output_contract_status="present",
        public_output_contract_evidence=("file=SKILL.md;line=1",),
    )


def test_five_to_one_scope_is_narrowed() -> None:
    diff_module, _ = _modules()
    baseline = _manifest("BASELINE", (_record("documents"),))
    candidate = _manifest(
        "CANDIDATE",
        (_record("documents", deliverables=("SRS",), validation_coverage=("SRS",)),),
    )

    diff = diff_module.compare_capability_manifests(baseline, candidate)

    assert diff.changes[0].kind.value == "NARROWED"
    assert "supported_deliverables" in diff.changes[0].changed_fields


def test_coordinated_deletion_is_removed_even_when_candidate_is_self_consistent() -> None:
    diff_module, _ = _modules()
    baseline = _manifest("BASELINE", (_record("documents"),))
    candidate = _manifest("CANDIDATE", ())

    diff = diff_module.compare_capability_manifests(baseline, candidate)

    assert diff.removed_capability_ids == ("documents",)
    assert diff.changes[0].kind.value == "REMOVED"


def test_declared_capability_without_implementation_is_broken() -> None:
    diff_module, _ = _modules()
    baseline = _manifest("BASELINE", (_record("documents"),))
    candidate = _manifest(
        "CANDIDATE",
        (_record("documents", implementation_status="missing", validation_coverage=()),),
    )

    diff = diff_module.compare_capability_manifests(baseline, candidate)

    assert diff.changes[0].kind.value == "BROKEN"


def test_unverifiable_candidate_never_counts_as_preserved() -> None:
    diff_module, _ = _modules()
    baseline = _manifest("BASELINE", (_record("documents"),))
    candidate = _manifest(
        "CANDIDATE",
        (_record("documents", evidence_state="UNVERIFIABLE"),),
    )

    diff = diff_module.compare_capability_manifests(baseline, candidate)

    assert diff.unverifiable_capability_ids == ("documents",)
    assert diff.changes[0].kind.value == "UNVERIFIABLE"
