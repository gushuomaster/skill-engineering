"""Integration tests for isolated Skill workspaces."""
from pathlib import Path

import pytest

from engine.models import Intent
from engine.workspace import WorkspaceSession


@pytest.fixture
def skill_fixture() -> Path:
    return Path(__file__).parents[1] / "fixtures" / "skills" / "minimal-valid"


@pytest.mark.parametrize("intent", (Intent.MODIFY, Intent.FIX))
def test_existing_change_intents_copy_source_without_mutating_it(
    intent: Intent, skill_fixture: Path, tmp_path: Path
) -> None:
    session = WorkspaceSession.for_existing(intent, skill_fixture)
    session.prepare(tmp_path)

    assert session.staging is not None
    (session.staging / "SKILL.md").write_text("changed", encoding="utf-8")

    assert (skill_fixture / "SKILL.md").read_text(encoding="utf-8") != "changed"
    assert session.verify_source_unchanged()


def test_create_uses_empty_staging_under_target_parent(tmp_path: Path) -> None:
    session = WorkspaceSession.for_create()
    session.prepare(tmp_path)

    assert session.staging is not None
    assert session.staging.parent == tmp_path.resolve()
    assert tuple(session.staging.iterdir()) == ()


def test_audit_only_has_no_staging(skill_fixture: Path, tmp_path: Path) -> None:
    session = WorkspaceSession.for_existing(Intent.AUDIT_ONLY, skill_fixture)
    session.prepare(tmp_path)

    assert session.staging is None
    assert session.verify_source_unchanged()


def test_audit_optimize_requires_need_and_authorization_before_copy(
    skill_fixture: Path, tmp_path: Path
) -> None:
    session = WorkspaceSession.for_existing(Intent.AUDIT_OPTIMIZE, skill_fixture)
    session.prepare(tmp_path)

    assert session.staging is None
    with pytest.raises(PermissionError):
        session.prepare_optimization(tmp_path, modification_needed=True, authorized_to_modify=False)
    assert session.staging is None

    session.prepare_optimization(tmp_path, modification_needed=True, authorized_to_modify=True)
    assert session.staging is not None
    assert (session.staging / "SKILL.md").read_text(encoding="utf-8") == (
        skill_fixture / "SKILL.md"
    ).read_text(encoding="utf-8")


def test_audit_optimize_does_not_stage_when_no_modification_is_needed(
    skill_fixture: Path, tmp_path: Path
) -> None:
    session = WorkspaceSession.for_existing(Intent.AUDIT_OPTIMIZE, skill_fixture)
    session.prepare_optimization(tmp_path, modification_needed=False, authorized_to_modify=True)

    assert session.staging is None


def test_source_change_is_detected_after_staging(skill_fixture: Path, tmp_path: Path) -> None:
    copied_source = tmp_path / "source"
    copied_source.mkdir()
    (copied_source / "SKILL.md").write_text(
        (skill_fixture / "SKILL.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    session = WorkspaceSession.for_existing(Intent.MODIFY, copied_source)
    session.prepare(tmp_path)
    (copied_source / "SKILL.md").write_text("changed source", encoding="utf-8")

    assert not session.verify_source_unchanged()
