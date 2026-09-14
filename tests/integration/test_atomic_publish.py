from pathlib import Path
import os
import pytest

from engine.models import GateOutcome, GateResult, GateVerdict, Intent
from engine.workspace import (WorkspaceSession, publish_atomic, PublishNotAuthorized,
    SourceChangedError, CrossFilesystemPublishError, PublishRecoveryError)
import engine.workspace as workspace

def gate(**kw):
    values = dict(verdict=GateVerdict.PASS, outcome=GateOutcome.READY_TO_PUBLISH,
                  blocking_findings=(), warnings=(), required_checks_summary="ok",
                  evidence_summary="ok", publish_authorized=True, policy_version="v1")
    values.update(kw)
    return GateResult(**values)

def staged(tmp_path, source):
    tmp_path.mkdir(parents=True, exist_ok=True)
    session = WorkspaceSession.for_existing(Intent.MODIFY, source)
    session.prepare(tmp_path)
    assert session.staging
    return session

def test_authorization_required(tmp_path):
    source = tmp_path / "source"; source.mkdir(); (source / "SKILL.md").write_text("ok")
    session = staged(tmp_path / "out", source)
    with pytest.raises(PublishNotAuthorized): publish_atomic(session, gate(publish_authorized=False))
    with pytest.raises(PublishNotAuthorized): publish_atomic(session, gate(verdict=GateVerdict.FAIL, publish_authorized=False))

def test_source_race_blocks(tmp_path):
    source = tmp_path / "source"; source.mkdir(); (source / "SKILL.md").write_text("ok")
    session = staged(tmp_path / "out", source); (source / "SKILL.md").write_text("changed")
    with pytest.raises(SourceChangedError): publish_atomic(session, gate())

def test_cross_filesystem_blocks(tmp_path, monkeypatch):
    source = tmp_path / "source"; source.mkdir(); (source / "SKILL.md").write_text("ok")
    session = staged(tmp_path / "out", source)
    monkeypatch.setattr("engine.workspace._same_filesystem", lambda *_: False)
    with pytest.raises(CrossFilesystemPublishError): publish_atomic(session, gate())

def test_move_failure_restores_backup(tmp_path, monkeypatch):
    source = tmp_path / "source"; source.mkdir(); (source / "SKILL.md").write_text("original")
    out = tmp_path / "out"; out.mkdir(); (out / "source" / "SKILL.md").parent.mkdir(); (out / "source" / "SKILL.md").write_text("old")
    session = staged(out, source)
    real = os.replace; calls = []
    def fail(src, dst):
        calls.append((src, dst))
        if len(calls) == 2: raise OSError("injected")
        return real(src, dst)
    monkeypatch.setattr("engine.workspace.os.replace", fail)
    with pytest.raises(PublishRecoveryError): publish_atomic(session, gate())
    assert (out / "source" / "SKILL.md").read_text() == "old"
    assert len(list(out.glob("*.backup"))) == 0

def test_post_publish_loadability_failure_recovers(tmp_path):
    source = tmp_path / "source"; source.mkdir(); (source / "SKILL.md").write_text("original")
    session = staged(tmp_path / "out", source); (session.staging / "SKILL.md").unlink()
    with pytest.raises(PublishRecoveryError): publish_atomic(session, gate())

def test_candidate_digest_mismatch_recovers(tmp_path, monkeypatch):
    source = tmp_path / "source"; source.mkdir(); (source / "SKILL.md").write_text("original")
    session = staged(tmp_path / "out", source)
    real = workspace.build_artifact_manifest
    def altered(path, intent, revision):
        manifest = real(path, intent, revision)
        from dataclasses import replace
        return replace(manifest, content_digest="0" * 64)
    monkeypatch.setattr(workspace, "build_artifact_manifest", altered)
    with pytest.raises(PublishRecoveryError): publish_atomic(session, gate())
