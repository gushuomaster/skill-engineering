"""Read-only inventory helpers for Skill artifacts."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from engine.models import ArtifactManifest, DirectorySnapshot, Intent, TreeEntry


_EXECUTABLE_SUFFIXES = frozenset({".bat", ".cmd", ".ps1", ".py", ".sh"})
_TEST_DIRECTORIES = frozenset({"test", "tests"})


def _is_reparse_point(path: Path) -> bool:
    reparse_attribute = getattr(os, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    try:
        return bool(path.stat(follow_symlinks=False).st_file_attributes & reparse_attribute)
    except AttributeError:
        return False


def assert_no_scope_escape(root: Path) -> None:
    """Reject links below *root* that resolve outside the artifact scope."""
    if not root.exists() or not root.is_dir():
        raise ValueError(f"artifact root must be an existing directory: {root}")
    if root.is_symlink() or _is_reparse_point(root):
        raise ValueError(f"artifact root cannot be a link or reparse point: {root}")

    for path in root.rglob("*"):
        is_symlink = path.is_symlink()
        is_reparse = _is_reparse_point(path)
        if not (is_symlink or is_reparse):
            continue
        raise ValueError(f"path cannot be a link or reparse point: {path}")


def _inventory_files(root: Path) -> tuple[Path, ...]:
    assert_no_scope_escape(root)
    return tuple(
        sorted(
            (path for path in root.rglob("*") if path.is_file() and not path.is_symlink()),
            key=lambda path: path.relative_to(root).as_posix(),
        )
    )


def digest_tree(root: Path) -> str:
    """Return a deterministic SHA-256 digest of all regular artifact files."""
    assert_no_scope_escape(root)
    resolved_root = root.resolve(strict=False)
    digest = hashlib.sha256()
    for path in _inventory_files(resolved_root):
        relative_path = path.relative_to(resolved_root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(relative_path)
        digest.update(b"\0")
        digest.update(str(len(content)).encode("ascii"))
        digest.update(b"\0")
        digest.update(content)
    return digest.hexdigest()


def snapshot_tree(root: Path) -> DirectorySnapshot:
    """Capture a recursive, content-bound source baseline for later comparison."""
    assert_no_scope_escape(root)
    resolved_root = root.resolve(strict=False)
    entries: list[TreeEntry] = []
    digest = hashlib.sha256()
    for path in sorted(
        resolved_root.rglob("*"), key=lambda item: item.relative_to(resolved_root).as_posix()
    ):
        relative = path.relative_to(resolved_root).as_posix()
        stat = path.stat(follow_symlinks=False)
        if path.is_dir():
            entry = TreeEntry(relative, "directory", 0, None, stat.st_mode)
        elif path.is_file():
            content = path.read_bytes()
            entry = TreeEntry(
                relative,
                "file",
                len(content),
                hashlib.sha256(content).hexdigest(),
                stat.st_mode,
            )
        else:
            entry = TreeEntry(relative, "other", stat.st_size, None, stat.st_mode)
        entries.append(entry)
        for value in (
            entry.path,
            entry.entry_type,
            str(entry.size),
            entry.content_hash or "",
            str(entry.mode),
        ):
            digest.update(value.encode("utf-8"))
            digest.update(b"\0")
    return DirectorySnapshot(str(resolved_root), tuple(entries), digest.hexdigest())


def _required_references(root: Path, files: tuple[Path, ...]) -> tuple[str, ...]:
    references: list[str] = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        if relative.startswith("references/"):
            references.append(relative)
    return tuple(references)


def build_artifact_manifest(
    root: Path, intent: Intent, source_revision: str | None
) -> ArtifactManifest:
    """Build an immutable artifact manifest without mutating the Skill."""
    assert_no_scope_escape(root)
    root = root.resolve(strict=False)
    files = _inventory_files(root)
    relative_files = tuple(path.relative_to(root).as_posix() for path in files)
    content_digest = digest_tree(root)
    source_digest = None if intent is Intent.CREATE else content_digest
    executable_assets = tuple(
        relative
        for relative in relative_files
        if Path(relative).suffix.lower() in _EXECUTABLE_SUFFIXES
    )
    test_inventory = tuple(
        relative
        for relative in relative_files
        if any(part.lower() in _TEST_DIRECTORIES for part in Path(relative).parts)
    )
    return ArtifactManifest(
        intent=intent,
        artifact_root=str(root),
        skill_name=root.name,
        source_revision=None if intent is Intent.CREATE else source_revision,
        source_digest=source_digest,
        files=relative_files,
        executable_assets=executable_assets,
        required_references=_required_references(root, files),
        test_inventory=test_inventory,
        content_digest=content_digest,
    )
