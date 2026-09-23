from __future__ import annotations

from pathlib import Path

from engine.deliverable_contract import validate_deliverable_contract
from engine.models import (
    ArtifactManifest,
    CheckStatus,
    DeliverableContract,
    DeliverableEvidence,
    DeliverableEvidenceStatus,
    DeliverableScopeConflict,
    LifecycleState,
    ProviderExecution,
)


def _manifest(root: Path) -> ArtifactManifest:
    return ArtifactManifest(
        intent="AUDIT",
        artifact_root=str(root),
        skill_name="demo",
        source_revision=None,
        source_digest="target-digest",
        files=("SKILL.md", "scripts/run.py", "docs/alpha.txt"),
        executable_assets=("scripts/run.py",),
        required_references=(),
        test_inventory=("tests/test_alpha.py",),
        content_digest="target-digest",
    )


def _complete(root: Path) -> DeliverableContract:
    return DeliverableContract(
        schema_version="1.0",
        inspection_id="inspection-1",
        target_digest="target-digest",
        inspection_nonce="nonce-1",
        provider_identity="provider.contracts",
        deliverables=(
            DeliverableEvidence(
                deliverable_id="alpha",
                declared_status="implemented",
                declarations=("SKILL.md:10",),
                exposure_status=DeliverableEvidenceStatus.PRESENT,
                exposure_entrypoint="scripts/run.py",
                exposure_selector="alpha",
                exposure_evidence=("file=scripts/run.py; line=4",),
                implementation_status=DeliverableEvidenceStatus.PRESENT,
                implementation_dispatch_route="run_alpha",
                implementation_artifact_pattern="docs/alpha.txt",
                implementation_evidence=("file=scripts/run.py; line=12",),
                behavioral_status=DeliverableEvidenceStatus.PRESENT,
                behavioral_commands=("python tests/test_alpha.py",),
                expected_artifacts=("docs/alpha.txt",),
                behavioral_evidence=("covered=alpha; exit_code=0",),
            ),
        ),
        scope_conflicts=(),
        applicability_status="applicable",
        applicability_reason="The Skill declares a selectable deliverable.",
        applicability_evidence=("file=SKILL.md; line=10",),
        evidence_origin="provider",
    )


def test_complete_contract_passes(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("alpha", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run.py").write_text("def run_alpha(): pass", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "alpha.txt").write_text("alpha", encoding="utf-8")
    result = validate_deliverable_contract(
        _complete(tmp_path), _manifest(tmp_path),
        inspection_id="inspection-1", inspection_nonce="nonce-1",
        provider_id="provider.contracts", provider_execution=ProviderExecution.EXECUTED,
    )
    assert result.status is CheckStatus.PASS


def test_generator_contract_does_not_require_runtime_outputs_in_source_tree(
    tmp_path: Path,
) -> None:
    (tmp_path / "SKILL.md").write_text("alpha", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run.py").write_text(
        "def run_alpha(): pass", encoding="utf-8"
    )
    manifest = ArtifactManifest(
        **{
            **_manifest(tmp_path).__dict__,
            "files": ("SKILL.md", "scripts/run.py"),
        }
    )

    result = validate_deliverable_contract(
        _complete(tmp_path),
        manifest,
        inspection_id="inspection-1",
        inspection_nonce="nonce-1",
        provider_id="provider.contracts",
        provider_execution=ProviderExecution.EXECUTED,
    )

    assert result.status is CheckStatus.PASS


def test_non_blocking_scope_note_does_not_fail_contract(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("alpha", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run.py").write_text("def run_alpha(): pass", encoding="utf-8")
    contract = DeliverableContract(
        **{
            **_complete(tmp_path).__dict__,
            "scope_conflicts": (
                DeliverableScopeConflict(
                    summary="A registered-only profile asset is intentionally not public.",
                    blocking=False,
                    evidence_refs=("file=SKILL.md;line=10",),
                ),
            ),
        }
    )

    result = validate_deliverable_contract(
        contract,
        _manifest(tmp_path),
        inspection_id="inspection-1",
        inspection_nonce="nonce-1",
        provider_id="provider.contracts",
        provider_execution=ProviderExecution.EXECUTED,
    )

    assert result.status is CheckStatus.PASS


def test_blocking_scope_conflict_fails_contract(tmp_path: Path) -> None:
    contract = DeliverableContract(
        **{
            **_complete(tmp_path).__dict__,
            "scope_conflicts": (
                DeliverableScopeConflict(
                    summary="Registry marks STP implemented but the public selector rejects it.",
                    blocking=True,
                    evidence_refs=("file=registry.yaml;line=10", "file=cli.py;line=20"),
                ),
            ),
        }
    )

    result = validate_deliverable_contract(
        contract,
        _manifest(tmp_path),
        inspection_id="inspection-1",
        inspection_nonce="nonce-1",
        provider_id="provider.contracts",
        provider_execution=ProviderExecution.EXECUTED,
    )

    assert result.status is CheckStatus.FAIL
    assert result.evidence == (
        "OUTPUT_SCOPE_CONFLICT:Registry marks STP implemented but the public selector rejects it.",
    )


def test_implemented_output_without_exposure_fails(tmp_path: Path) -> None:
    contract = _complete(tmp_path)
    item = contract.deliverables[0]
    broken = DeliverableContract(
        **{
            **contract.__dict__,
            "deliverables": (
                DeliverableEvidence(
                    **{**item.__dict__, "exposure_status": DeliverableEvidenceStatus.MISSING}
                ),
            ),
        }
    )
    result = validate_deliverable_contract(
        broken, _manifest(tmp_path),
        inspection_id="inspection-1", inspection_nonce="nonce-1",
        provider_id="provider.contracts", provider_execution=ProviderExecution.EXECUTED,
    )
    assert result.status is CheckStatus.FAIL
    assert any("DECLARED_OUTPUT_NOT_EXPOSED" in item for item in result.evidence)


def test_missing_behavioral_proof_is_incomplete(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "alpha.txt").write_text("alpha", encoding="utf-8")
    contract = _complete(tmp_path)
    item = contract.deliverables[0]
    incomplete = DeliverableContract(
        **{
            **contract.__dict__,
            "deliverables": (
                DeliverableEvidence(
                    **{
                        **item.__dict__,
                        "behavioral_status": DeliverableEvidenceStatus.MISSING,
                        "behavioral_commands": (),
                        "behavioral_evidence": (),
                    }
                ),
            ),
        }
    )
    result = validate_deliverable_contract(
        incomplete, _manifest(tmp_path),
        inspection_id="inspection-1", inspection_nonce="nonce-1",
        provider_id="provider.contracts", provider_execution=ProviderExecution.EXECUTED,
    )
    assert result.status is CheckStatus.NOT_EXECUTED
    assert any("DECLARED_OUTPUT_WITHOUT_BEHAVIORAL_PROOF" in item for item in result.evidence)


def test_stale_digest_and_unexecuted_provider_are_not_pass(tmp_path: Path) -> None:
    contract = _complete(tmp_path)
    result = validate_deliverable_contract(
        contract, _manifest(tmp_path),
        inspection_id="inspection-1", inspection_nonce="nonce-1",
        provider_id="provider.contracts", provider_execution=ProviderExecution.NOT_STARTED,
    )
    assert result.status is CheckStatus.NOT_EXECUTED
    assert any("OUTPUT_CONTRACT_PROVIDER_NOT_EXECUTED" in item for item in result.evidence)
