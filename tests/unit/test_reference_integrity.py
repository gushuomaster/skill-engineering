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
    (tmp_path / "outside.md").write_text("inside", encoding="utf-8")
    (tmp_path / "SKILL.md").write_text("---\nname: demo\ndescription: x\n---\n[bad](../outside.md)\n", encoding="utf-8")
    manifest = build_artifact_manifest(tmp_path, Intent.CREATE, None)
    result = _check(validate_references(manifest), "reference.optional.exists")
    assert result.status is CheckStatus.WARN
    assert "escapes artifact root" in result.evidence[0]


def test_relative_link_is_classified_by_resolved_artifact_path(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "references").mkdir()
    (tmp_path / "SKILL.md").write_text("---\nname: demo\ndescription: x\n---\n[guide](docs/guide.md)\n", encoding="utf-8")
    (tmp_path / "docs" / "guide.md").write_text("[runtime](../references/runtime.md)\n", encoding="utf-8")
    (tmp_path / "references" / "runtime.md").write_text("runtime", encoding="utf-8")
    manifest = replace(build_artifact_manifest(tmp_path, Intent.CREATE, None), required_references=("references/runtime.md",))
    results = validate_references(manifest)
    required = [result for result in results if result.check_id == "reference.required.exists"]
    assert len(required) == 1
    assert required[0].status is CheckStatus.PASS
    assert not any(result.check_id == "reference.optional.exists" and "references/runtime.md" in result.subject for result in results)


def test_frontmatter_critical_asset_link_is_required(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "runtime.md").write_text("runtime", encoding="utf-8")
    (tmp_path / "SKILL.md").write_text("---\nname: demo\ndescription: x\ncritical_assets:\n  - docs/runtime.md\n---\n[runtime](docs/runtime.md)\n", encoding="utf-8")
    manifest = build_artifact_manifest(tmp_path, Intent.CREATE, None)
    result = _check(validate_references(manifest), "reference.required.exists")
    assert result.status is CheckStatus.PASS


def test_out_of_scope_critical_asset_without_link_is_required_failure(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("---\nname: demo\ndescription: x\ncritical_assets: [../outside.md]\n---\n", encoding="utf-8")
    manifest = build_artifact_manifest(tmp_path, Intent.CREATE, None)
    results = validate_references(manifest)
    required = _check(results, "reference.required.exists")
    assert required.status is CheckStatus.FAIL
    assert "escapes artifact root" in required.evidence[0]
    assert not any(result.check_id == "reference.optional.exists" for result in results)


def test_out_of_scope_critical_asset_link_is_required_failure(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("---\nname: demo\ndescription: x\ncritical_assets: [../outside.md]\n---\n[asset](../outside.md)\n", encoding="utf-8")
    manifest = build_artifact_manifest(tmp_path, Intent.CREATE, None)
    result = _check(validate_references(manifest), "reference.required.exists")
    assert result.status is CheckStatus.FAIL
    assert "escapes artifact root" in result.evidence[0]


def test_out_of_scope_manifest_required_reference_is_required_failure(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("---\nname: demo\ndescription: x\n---\n", encoding="utf-8")
    manifest = replace(build_artifact_manifest(tmp_path, Intent.CREATE, None), required_references=("../outside.md",))
    result = _check(validate_references(manifest), "reference.required.exists")
    assert result.status is CheckStatus.FAIL
    assert "escapes artifact root" in result.evidence[0]
