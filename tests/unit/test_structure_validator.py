from pathlib import Path

from engine.inventory import build_artifact_manifest
from engine.models import CheckStatus, Intent
from validators.skill_structure import validate_skill_structure


def _check(results, check_id):
    return next(result for result in results if result.check_id == check_id)


def test_missing_skill_md_is_required_failure(tmp_path: Path) -> None:
    manifest = build_artifact_manifest(tmp_path, Intent.CREATE, None)
    result = _check(validate_skill_structure(manifest), "skill.structure.skill_md")
    assert result.status is CheckStatus.FAIL
    assert result.required is True


def test_invalid_frontmatter_and_placeholder_are_failures(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("---\nname: Bad Name\n---\nTODO\n", encoding="utf-8")
    manifest = build_artifact_manifest(tmp_path, Intent.CREATE, None)
    results = validate_skill_structure(manifest)
    assert _check(results, "skill.structure.frontmatter").status is CheckStatus.FAIL
    assert _check(results, "skill.structure.name_format").status is CheckStatus.FAIL
    assert _check(results, "skill.structure.placeholders").status is CheckStatus.FAIL
