"""Tests for deterministic, read-only Skill inventories."""
from pathlib import Path

import pytest

import engine.inventory as inventory
from engine.inventory import assert_no_scope_escape, build_artifact_manifest, digest_tree
from engine.models import Intent


@pytest.fixture
def skill_fixture() -> Path:
    return Path(__file__).parents[1] / "fixtures" / "skills" / "minimal-valid"


def test_digest_is_path_order_independent(tmp_path: Path) -> None:
    (tmp_path / "b.txt").write_text("二", encoding="utf-8")
    (tmp_path / "a.txt").write_text("一", encoding="utf-8")
    first = digest_tree(tmp_path)

    (tmp_path / "a.txt").unlink()
    (tmp_path / "b.txt").unlink()
    (tmp_path / "a.txt").write_text("一", encoding="utf-8")
    (tmp_path / "b.txt").write_text("二", encoding="utf-8")

    assert digest_tree(tmp_path) == first


def test_digest_changes_when_path_or_content_changes(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("same", encoding="utf-8")
    first = digest_tree(tmp_path)
    (tmp_path / "b.txt").write_text("same", encoding="utf-8")
    assert digest_tree(tmp_path) != first


def test_existing_source_manifest_records_digest_and_revision(
    skill_fixture: Path,
) -> None:
    manifest = build_artifact_manifest(skill_fixture, Intent.MODIFY, "rev-1")

    assert manifest.source_revision == "rev-1"
    assert manifest.source_digest
    assert manifest.content_digest == manifest.source_digest
    assert manifest.files == ("SKILL.md",)


def test_create_manifest_has_no_source_identity(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("# New skill", encoding="utf-8")

    manifest = build_artifact_manifest(tmp_path, Intent.CREATE, None)

    assert manifest.source_revision is None
    assert manifest.source_digest is None
    assert manifest.content_digest


def test_create_manifest_discards_inapplicable_source_revision(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("# New skill", encoding="utf-8")

    manifest = build_artifact_manifest(tmp_path, Intent.CREATE, "stale-revision")

    assert manifest.source_revision is None


def test_manifest_includes_unicode_file_paths() -> None:
    fixture = Path(__file__).parents[1] / "fixtures" / "skills" / "with-unicode"

    manifest = build_artifact_manifest(fixture, Intent.AUDIT_ONLY, None)

    assert manifest.files == ("技能说明.md",)
    assert manifest.source_digest


def test_scope_escape_rejects_symlink_to_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    link = tmp_path / "outside-link.txt"
    try:
        link.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    with pytest.raises(ValueError, match="link or reparse point"):
        assert_no_scope_escape(tmp_path)


def test_scope_escape_rejects_root_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("# Source", encoding="utf-8")
    link = tmp_path / "root-link"
    try:
        link.symlink_to(source, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    with pytest.raises(ValueError, match="root"):
        assert_no_scope_escape(link)


def test_scope_escape_rejects_internal_reparse_point_without_symlink_privilege(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    internal_file = tmp_path / "internal-link.txt"
    internal_file.write_text("# Internal", encoding="utf-8")
    monkeypatch.setattr(
        inventory,
        "_is_reparse_point",
        lambda path: path == internal_file,
    )

    with pytest.raises(ValueError, match="link or reparse point"):
        assert_no_scope_escape(tmp_path)
