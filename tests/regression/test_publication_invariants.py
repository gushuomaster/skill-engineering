from pathlib import Path

from engine.models import Intent
from engine.workspace import WorkspaceSession


def test_existing_session_captures_source_digest(tmp_path: Path) -> None:
    source = tmp_path / "skill"
    source.mkdir()
    (source / "SKILL.md").write_text("content", encoding="utf-8")
    session = WorkspaceSession.for_existing(Intent.MODIFY, source)
    assert session.source_digest
    assert session.verify_source_unchanged()
