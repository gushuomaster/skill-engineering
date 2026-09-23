"""Safe isolated staging and atomic application for Skill repairs."""
from __future__ import annotations

import os
import shutil
import tempfile
import hashlib
from dataclasses import dataclass
from pathlib import Path

from engine.inventory import assert_no_scope_escape, digest_tree, build_artifact_manifest, snapshot_tree
from engine.models import CapabilityChange, CapabilityDiff, CapabilityChangeKind, DirectorySnapshot
from engine.models import Intent
from engine.models import GateResult, GateOutcome, GateVerdict


class ApplyNotAuthorized(RuntimeError):
    pass


class SourceChangedError(RuntimeError):
    finding_id = "B10"


class CandidateChangedError(RuntimeError):
    finding_id = "B12"


class CrossFilesystemApplyError(RuntimeError):
    pass


class ApplyRecoveryError(RuntimeError):
    def __init__(self, message: str, result: "ApplyResult") -> None:
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class ApplyResult:
    applied_path: Path
    backup_path: Path | None
    restored_after_failure: bool
    source_digest_before: str | None
    candidate_digest: str
    applied_digest: str | None
    workspace_diff: WorkspaceDiff
    status: str

    @property
    def published_path(self) -> Path:
        return self.applied_path

    @property
    def published_digest(self) -> str | None:
        return self.applied_digest


@dataclass(frozen=True)
class WorkspaceDiff:
    added: tuple[str, ...]
    modified: tuple[str, ...]
    deleted: tuple[str, ...]


@dataclass(frozen=True)
class SemanticWorkspaceDiff:
    file_changes: WorkspaceDiff
    declaration_changes: tuple[str, ...]
    entrypoint_changes: tuple[str, ...]
    schema_changes: tuple[str, ...]
    template_changes: tuple[str, ...]
    test_coverage_changes: tuple[str, ...]
    capability_changes: tuple[CapabilityChange, ...]


def build_semantic_workspace_diff(
    file_changes: WorkspaceDiff,
    capability_diff: CapabilityDiff | None,
) -> SemanticWorkspaceDiff:
    changes = capability_diff.changes if capability_diff is not None else ()

    def categorized(*fields: str) -> tuple[str, ...]:
        return tuple(
            f"{item.capability_id}:{item.kind.value}"
            for item in changes
            if any(field in item.changed_fields for field in fields)
        )

    declaration_changes = tuple(
        f"{item.capability_id}:{item.kind.value}"
        for item in changes
        if item.kind in {CapabilityChangeKind.REMOVED, CapabilityChangeKind.NARROWED}
        or "declared_status" in item.changed_fields
        or "public_name" in item.changed_fields
        or "capability_type" in item.changed_fields
    )
    return SemanticWorkspaceDiff(
        file_changes,
        declaration_changes,
        categorized("entrypoints"),
        categorized("schemas"),
        categorized("templates"),
        categorized("validation_coverage"),
        changes,
    )


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
    confirmed_artifact_digest: str | None = None
    source_snapshot: DirectorySnapshot | None = None
    audit_snapshot_root: Path | None = None

    @classmethod
    def for_existing(cls, intent: Intent, source: Path) -> "WorkspaceSession":
        if intent is Intent.CREATE:
            raise ValueError("create sessions do not have a source")
        assert_no_scope_escape(source)
        source = source.resolve(strict=False)
        snapshot = snapshot_tree(source)
        return cls(
            intent=intent,
            source=source,
            staging=None,
            source_digest=digest_tree(source),
            source_snapshot=snapshot,
        )

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

    def stage_candidate(self, candidate: Path, target_parent: Path) -> Path:
        """Copy a complete Codex-authored candidate into an engine-owned workspace."""
        if self.intent is Intent.AUDIT_ONLY:
            raise PermissionError("Audit Only cannot stage a candidate")
        candidate = candidate.resolve(strict=True)
        if not candidate.is_dir() or not (candidate / "SKILL.md").is_file():
            raise ValueError("candidate must be a complete Skill directory")
        assert_no_scope_escape(candidate)
        if self.source is not None and candidate == self.source:
            raise ValueError("candidate must be separate from the source Skill")
        if self.staging is not None:
            raise RuntimeError("workspace has already been prepared")
        if self.source is not None:
            _assert_target_parent_outside_source(self.source, target_parent)
            if not self.verify_source_unchanged():
                raise SourceChangedError("source changed before candidate staging")
        staging = _allocate_staging(target_parent)
        staged_candidate = staging / candidate.name
        shutil.copytree(candidate, staged_candidate)
        assert_no_scope_escape(staged_candidate)
        self.staging = staging
        return staged_candidate

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
        if self.source_snapshot is not None:
            return snapshot_tree(self.source).content_digest == self.source_snapshot.content_digest
        return digest_tree(self.source) == self.source_digest

    def prepare_audit_snapshot(self) -> Path:
        """Copy an Audit Only source to an isolated disposable execution root."""
        if self.intent is not Intent.AUDIT_ONLY or self.source is None:
            raise ValueError("audit snapshot requires an Audit Only source")
        if self.audit_snapshot_root is not None:
            raise RuntimeError("audit snapshot has already been prepared")
        root = Path(tempfile.mkdtemp(prefix="skill-engineering-audit-"))
        artifact = root / self.source.name
        shutil.copytree(self.source, artifact)
        assert_no_scope_escape(artifact)
        self.audit_snapshot_root = root
        return artifact

    def cleanup_audit_snapshot(self) -> None:
        if self.audit_snapshot_root is not None:
            shutil.rmtree(self.audit_snapshot_root, ignore_errors=True)
            self.audit_snapshot_root = None

    def source_diff(self) -> WorkspaceDiff:
        """Compare the current source to the immutable snapshot captured at session start."""
        if self.source is None or self.source_snapshot is None:
            return WorkspaceDiff((), (), ())
        return diff_snapshots(self.source_snapshot, snapshot_tree(self.source))

    def bind_confirmed_artifact(self, artifact: Path, artifact_digest: str) -> None:
        """Bind safe apply to the exact staged artifact confirmed by Codex."""
        if self.staging is None:
            raise ValueError("a staged candidate is required for semantic binding")
        artifact = artifact.resolve(strict=True)
        try:
            artifact.relative_to(self.staging.resolve(strict=True))
        except ValueError as exc:
            raise ValueError("confirmed artifact must be inside the staging workspace") from exc
        if digest_tree(artifact) != artifact_digest:
            raise CandidateChangedError("candidate digest changed before semantic binding")
        self.confirmed_artifact_digest = artifact_digest

    def diff(self, candidate: Path) -> WorkspaceDiff:
        """Return deterministic file-level changes from the recorded source baseline."""
        if self.source is None:
            files = tuple(
                path.relative_to(candidate).as_posix()
                for path in sorted(candidate.rglob("*"))
                if path.is_file()
            )
            return WorkspaceDiff(files, (), ())
        return diff_trees(self.source, candidate)


def diff_trees(source: Path, candidate: Path) -> WorkspaceDiff:
    def inventory(root: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        for path in sorted(root.rglob("*")):
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result

    before = inventory(source)
    after = inventory(candidate)
    return WorkspaceDiff(
        added=tuple(sorted(set(after) - set(before))),
        modified=tuple(sorted(path for path in set(before) & set(after) if before[path] != after[path])),
        deleted=tuple(sorted(set(before) - set(after))),
    )


def diff_snapshots(before: DirectorySnapshot, after: DirectorySnapshot) -> WorkspaceDiff:
    """Return a real baseline/current file diff without rereading the baseline path."""
    before_files = {
        entry.path: entry
        for entry in before.entries
        if entry.entry_type == "file"
    }
    after_files = {
        entry.path: entry
        for entry in after.entries
        if entry.entry_type == "file"
    }
    return WorkspaceDiff(
        added=tuple(sorted(set(after_files) - set(before_files))),
        modified=tuple(
            sorted(
                path
                for path in set(before_files) & set(after_files)
                if before_files[path] != after_files[path]
            )
        ),
        deleted=tuple(sorted(set(before_files) - set(after_files))),
    )


def apply_atomic(session: WorkspaceSession, gate: GateResult) -> ApplyResult:
    if not (gate.verdict is GateVerdict.PASS and gate.outcome is GateOutcome.READY_TO_APPLY and gate.apply_authorized):
        raise ApplyNotAuthorized("gate is not authorized for safe apply")
    if session.staging is None or not session.staging.is_dir():
        raise ApplyNotAuthorized("staged candidate is required")
    staging = session.staging.resolve()
    target = next((p for p in staging.iterdir() if p.is_dir()), staging)
    candidate_digest = digest_tree(target)
    if session.confirmed_artifact_digest is None:
        raise ApplyNotAuthorized("staged candidate is not bound to a semantic confirmation")
    if candidate_digest != session.confirmed_artifact_digest:
        raise CandidateChangedError("candidate digest changed after semantic confirmation")
    applied = staging.parent / (session.source.name if session.source is not None else target.name)
    if not _same_filesystem(staging, applied.parent):
        raise CrossFilesystemApplyError("staging and target must share a filesystem")
    if session.source is not None and not session.verify_source_unchanged():
        raise SourceChangedError("source changed after staging")
    workspace_diff = session.diff(target)
    backup = applied.parent / (applied.name + ".backup") if applied.exists() else None
    moved_backup = False
    try:
        if applied.exists():
            if backup and backup.exists():
                _remove_exact(backup, applied.parent)
            os.replace(str(applied), str(backup))
            moved_backup = True
        os.replace(str(target), str(applied))
        if not (applied / "SKILL.md").is_file():
            raise ValueError("applied candidate is not loadable")
        manifest = build_artifact_manifest(applied, session.intent, session.source_digest)
        if manifest.content_digest != candidate_digest:
            raise ValueError("applied candidate digest mismatch")
        return ApplyResult(
            applied,
            backup if moved_backup else None,
            False,
            session.source_digest,
            candidate_digest,
            manifest.content_digest,
            workspace_diff,
            "APPLIED",
        )
    except Exception as exc:
        try:
            if applied.exists() and applied != backup:
                _remove_exact(applied, applied.parent)
            if moved_backup and backup and backup.exists():
                os.replace(str(backup), str(applied))
        except Exception as restore_exc:
            result = ApplyResult(
                applied,
                backup if moved_backup else None,
                False,
                session.source_digest,
                candidate_digest,
                _digest_if_loadable(applied),
                workspace_diff,
                "APPLY_FAILED_UNRECOVERABLE",
            )
            raise ApplyRecoveryError("safe apply and recovery failed", result) from restore_exc
        result = ApplyResult(
            applied,
            backup if moved_backup else None,
            True,
            session.source_digest,
            candidate_digest,
            _digest_if_loadable(applied),
            workspace_diff,
            "APPLY_FAILED_RECOVERED",
        )
        raise ApplyRecoveryError("safe apply failed; original restored", result) from exc


def _digest_if_loadable(path: Path) -> str | None:
    try:
        return digest_tree(path) if path.is_dir() else None
    except (OSError, ValueError):
        return None


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


# Import compatibility only; product and serialized semantics use safe apply.
PublishNotAuthorized = ApplyNotAuthorized
CrossFilesystemPublishError = CrossFilesystemApplyError
PublishRecoveryError = ApplyRecoveryError
PublishResult = ApplyResult
publish_atomic = apply_atomic
