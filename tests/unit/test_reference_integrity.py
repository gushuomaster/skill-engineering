from pathlib import Path

from engine.inventory import build_artifact_manifest
from engine.models import CheckStatus, Intent
from dataclasses import replace
from validators.reference_integrity import validate_references


def _check(results, check_id):
    return next(result for result in results if result.check_id == check_id)


def test_required_reference_missing_is_failure(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("---\nname: demo\ndescription: x\n---\n[guide](references/guide.md)\n", encoding="utf-8")
    (tmp_path / "references").mkdir()
    manifest = build_artifact_manifest(tmp_path, Intent.CREATE, None)
    result = _check(validate_references(manifest), "reference.required.exists")
    assert result.status is CheckStatus.FAIL
    assert result.required is True


def test_optional_broken_link_is_warning(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("---\nname: demo\ndescription: x\n---\n[guide](docs/guide.md)\n", encoding="utf-8")
    manifest = build_artifact_manifest(tmp_path, Intent.CREATE, None)
    result = _check(validate_references(manifest), "reference.optional.exists")
    assert result.status is CheckStatus.WARN
    assert result.required is False


def test_manifest_required_reference_is_checked_even_without_link(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("---\nname: demo\ndescription: x\n---\n", encoding="utf-8")
    manifest = build_artifact_manifest(tmp_path, Intent.CREATE, None)
    manifest = replace(manifest, required_references=("references/runtime.md",))
    result = _check(validate_references(manifest), "reference.required.exists")
    assert result.status is CheckStatus.FAIL


def test_reference_escaping_artifact_root_is_not_verified(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    (tmp_path / "SKILL.md").write_text("---\nname: demo\ndescription: x\n---\n[bad](../outside.md)\n", encoding="utf-8")
    manifest = build_artifact_manifest(tmp_path, Intent.CREATE, None)
    result = _check(validate_references(manifest), "reference.optional.exists")
    assert result.status is CheckStatus.WARN
