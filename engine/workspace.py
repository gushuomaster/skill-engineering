"""Safe isolated staging for Skill operations, without publication."""
from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from engine.inventory import assert_no_scope_escape, digest_tree, build_artifact_manifest
from engine.models import Intent
from engine.models import GateResult, GateOutcome, GateVerdict


class PublishNotAuthorized(RuntimeError):
    pass


class SourceChangedError(RuntimeError):
    finding_id = "B10"


class CrossFilesystemPublishError(RuntimeError):
    pass


class PublishRecoveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublishResult:
    published_path: Path
    backup_path: Path | None
    restored_after_failure: bool


def _same_filesystem(first: Path, second: Path) -> bool:
    if os.stat(first).st_dev != os.stat(second).st_dev:
        return False
    if os.name == "nt":
        return first.resolve(strict=False).drive.casefold() == second.resolve(strict=False).drive.casefold()
    return True


def _allocate_staging(target_parent: Path) -> Path:
    resolved_parent = target_parent.resolve(strict=False)
    if not resolved_parent.is_dir():
        raise ValueError(f"target parent must be an existing directory: {target_parent}")
    staging = Path(tempfile.mkdtemp(prefix=".skill-engineering-", dir=resolved_parent))
    if not _same_filesystem(staging, resolved_parent):
        raise ValueError("staging and target parent must share a filesystem")
    return staging


def _assert_target_parent_outside_source(source: Path, target_parent: Path) -> None:
    resolved_source = source.resolve(strict=False)
    resolved_target = target_parent.resolve(strict=False)
    try:
        resolved_target.relative_to(resolved_source)
    except ValueError:
        return
    raise ValueError("target parent must be outside the source Skill")


@dataclass
class WorkspaceSession:
    intent: Intent
    source: Path | None
    staging: Path | None
    source_digest: str | None

    @classmethod
    def for_existing(cls, intent: Intent, source: Path) -> "WorkspaceSession":
        if intent is Intent.CREATE:
            raise ValueError("create sessions do not have a source")
        assert_no_scope_escape(source)
        source = source.resolve(strict=False)
        return cls(intent=intent, source=source, staging=None, source_digest=digest_tree(source))

    @classmethod
    def for_create(cls) -> "WorkspaceSession":
        return cls(intent=Intent.CREATE, source=None, staging=None, source_digest=None)

    def prepare(self, target_parent: Path) -> None:
        """Allocate a staging directory for create, modify, or fix operations."""
        if self.intent is Intent.AUDIT_ONLY:
            return
        if self.intent is Intent.AUDIT_OPTIMIZE:
            return
        if self.staging is not None:
            raise RuntimeError("workspace has already been prepared")
        if self.source is not None:
            _assert_target_parent_outside_source(self.source, target_parent)
        staging = _allocate_staging(target_parent)
        if self.intent in (Intent.MODIFY, Intent.FIX):
            if self.source is None:
                raise ValueError(f"{self.intent} requires a source Skill")
            assert_no_scope_escape(self.source)
            shutil.copytree(self.source, staging, dirs_exist_ok=True)
            assert_no_scope_escape(staging)
        self.staging = staging

    def prepare_optimization(
        self,
        target_parent: Path,
        *,
        modification_needed: bool,
        authorized_to_modify: bool,
    ) -> None:
        """Stage Audit + Optimize only after audit need and authorization exist."""
        if self.intent is not Intent.AUDIT_OPTIMIZE:
            raise ValueError("optimization staging is only valid for Audit + Optimize")
        if not modification_needed:
            return
        if not authorized_to_modify:
            raise PermissionError("modification authorization is required")
        if self.staging is not None:
            raise RuntimeError("workspace has already been prepared")
        if self.source is None:
            raise ValueError("Audit + Optimize requires a source Skill")
        assert_no_scope_escape(self.source)
        _assert_target_parent_outside_source(self.source, target_parent)
        staging = _allocate_staging(target_parent)
        shutil.copytree(self.source, staging, dirs_exist_ok=True)
        assert_no_scope_escape(staging)
        self.staging = staging

    def verify_source_unchanged(self) -> bool:
        """Compare the current source inventory to the pre-staging digest."""
        if self.source is None:
            return True
        assert_no_scope_escape(self.source)
        return digest_tree(self.source) == self.source_digest


def publish_atomic(session: WorkspaceSession, gate: GateResult) -> PublishResult:
    if not (gate.verdict is GateVerdict.PASS and gate.outcome is GateOutcome.READY_TO_PUBLISH and gate.publish_authorized):
        raise PublishNotAuthorized("gate is not authorized for publication")
    if session.staging is None or not session.staging.is_dir():
        raise PublishNotAuthorized("staged candidate is required")
    staging = session.staging.resolve()
    target = next((p for p in staging.iterdir() if p.is_dir()), staging)
    candidate_digest = digest_tree(target)
    published = staging.parent / (session.source.name if session.source is not None else target.name)
    if not _same_filesystem(staging, published.parent):
        raise CrossFilesystemPublishError("staging and target must share a filesystem")
    if session.source is not None and not session.verify_source_unchanged():
        raise SourceChangedError("source changed after staging")
    backup = published.parent / (published.name + ".backup") if published.exists() else None
    moved_backup = False
    try:
        if published.exists():
            if backup and backup.exists():
                _remove_exact(backup, published.parent)
            os.replace(str(published), str(backup))
            moved_backup = True
        os.replace(str(target), str(published))
        if not (published / "SKILL.md").is_file():
            raise ValueError("published candidate is not loadable")
        manifest = build_artifact_manifest(published, session.intent, session.source_digest)
        if manifest.content_digest != candidate_digest:
            raise ValueError("published candidate digest mismatch")
        return PublishResult(published, backup if moved_backup else None, False)
    except Exception as exc:
        try:
            if published.exists() and published != backup:
                _remove_exact(published, published.parent)
            if moved_backup and backup and backup.exists():
                os.replace(str(backup), str(published))
        except Exception as restore_exc:
            raise PublishRecoveryError("publication and recovery failed") from restore_exc
        raise PublishRecoveryError("publication failed; original restored") from exc


def _remove_exact(path: Path, parent: Path) -> None:
    path = path.resolve(strict=False); parent = parent.resolve(strict=False)
    if path.parent != parent or path == parent:
        raise ValueError("unsafe cleanup path")
    if path.is_dir():
        for child in list(path.iterdir()):
            _remove_exact(child, path)
        path.rmdir()
    elif path.exists():
        path.unlink()
