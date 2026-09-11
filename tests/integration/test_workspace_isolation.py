"""Integration tests for isolated Skill workspaces."""
from pathlib import Path
from types import SimpleNamespace

import pytest

import engine.workspace as workspace
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


@pytest.mark.parametrize("intent", (Intent.MODIFY, Intent.FIX))
@pytest.mark.parametrize("target_name", ("source", "source/inside"))
def test_existing_change_rejects_staging_in_source_before_allocation(
    intent: Intent,
    target_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("# Source", encoding="utf-8")
    target_parent = tmp_path / target_name
    target_parent.mkdir(exist_ok=True)
    session = WorkspaceSession.for_existing(intent, source)

    def unexpected_allocation(_target_parent: Path) -> Path:
        raise AssertionError("staging allocation must not run")

    monkeypatch.setattr(workspace, "_allocate_staging", unexpected_allocation)

    with pytest.raises(ValueError, match="outside the source"):
        session.prepare(target_parent)


@pytest.mark.parametrize("target_name", ("source", "source/inside"))
def test_audit_optimize_rejects_staging_in_source_before_allocation(
    target_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("# Source", encoding="utf-8")
    target_parent = tmp_path / target_name
    target_parent.mkdir(exist_ok=True)
    session = WorkspaceSession.for_existing(Intent.AUDIT_OPTIMIZE, source)

    def unexpected_allocation(_target_parent: Path) -> Path:
        raise AssertionError("staging allocation must not run")

    monkeypatch.setattr(workspace, "_allocate_staging", unexpected_allocation)

    with pytest.raises(ValueError, match="outside the source"):
        session.prepare_optimization(
            target_parent, modification_needed=True, authorized_to_modify=True
        )


def test_same_filesystem_rejects_different_devices(monkeypatch: pytest.MonkeyPatch) -> None:
    devices = {"first": 1, "second": 2}
    fake_os = SimpleNamespace(name="posix", stat=lambda path: SimpleNamespace(st_dev=devices[path.name]))
    monkeypatch.setattr(workspace, "os", fake_os)

    assert not workspace._same_filesystem(Path("first"), Path("second"))


def test_same_filesystem_rejects_windows_drive_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_os = SimpleNamespace(name="nt", stat=lambda _path: SimpleNamespace(st_dev=1))
    monkeypatch.setattr(workspace, "os", fake_os)

    assert not workspace._same_filesystem(Path("C:/staging"), Path("D:/target"))
