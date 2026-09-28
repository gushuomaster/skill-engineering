"""Source-neutral Skill discovery metadata.

This module deliberately stops at candidate discovery.  It does not fetch,
install, execute, validate, or promote a Skill, and candidate metadata is not
formal governance evidence.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping, Protocol, Sequence, runtime_checkable

import yaml


@dataclass(frozen=True, slots=True)
class CandidateSignal:
    """Untrusted source metadata used only for discovery or ranking."""

    name: str
    value: str


@dataclass(frozen=True, slots=True)
class SkillOrigin:
    """One source's provenance and opaque retrieval reference."""

    source_type: str
    source_id: str
    source_url: str | None = None
    fetch_reference: str | None = None
    publisher: str | None = None
    version: str | None = None
    revision: str | None = None
    trust_signals: tuple[CandidateSignal, ...] = ()
    popularity_signals: tuple[CandidateSignal, ...] = ()
    quality_signals: tuple[CandidateSignal, ...] = ()


@dataclass(frozen=True, slots=True)
class SkillCandidate:
    """Discovery result that must be staged and governed before installation."""

    candidate_id: str
    name: str
    description: str
    canonical_repository: str | None
    content_digest: str | None
    origins: tuple[SkillOrigin, ...]
    discovered_at: str

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id must be nonblank")
        if not self.name.strip():
            raise ValueError("candidate name must be nonblank")
        if not self.origins:
            raise ValueError("candidate must preserve at least one source origin")
        if self.content_digest is not None and not _is_sha256(self.content_digest):
            raise ValueError("content_digest must be a lowercase SHA-256 digest")


@runtime_checkable
class SkillSource(Protocol):
    """Minimal discovery port implemented by local or remote source adapters."""

    source_type: str

    def search(
        self,
        query: str,
        context: Mapping[str, object] | None = None,
    ) -> tuple[SkillCandidate, ...]:
        """Return untrusted candidates without fetching or installing them."""


class LocalSkillSource:
    """Discover Skills already present in configured local roots."""

    source_type = "local"

    def __init__(
        self,
        roots: Sequence[Path] | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if roots is None:
            codex_root = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
            roots = (codex_root / "skills", codex_root / "plugins" / "cache")
        self.roots = tuple(Path(root) for root in roots)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def search(
        self,
        query: str,
        context: Mapping[str, object] | None = None,
    ) -> tuple[SkillCandidate, ...]:
        del context
        terms = tuple(item for item in query.casefold().split() if item)
        candidates = tuple(self._candidate(path) for path in self._skill_paths())
        if not terms:
            return candidates
        return tuple(
            item
            for item in candidates
            if all(term in f"{item.name} {item.description}".casefold() for term in terms)
        )

    def find_exact(self, skill_name: str) -> SkillCandidate | None:
        """Resolve the first directory-name match using the legacy path order."""
        if not skill_name or Path(skill_name).name != skill_name:
            raise ValueError("skill name must be a single nonblank directory name")
        return next(
            (self._candidate(path) for path in self._skill_paths() if path.name == skill_name),
            None,
        )

    def _skill_paths(self) -> tuple[Path, ...]:
        candidates: list[Path] = []
        for root in self.roots:
            if not root.is_dir():
                continue
            candidates.extend(
                item.parent for item in root.rglob("SKILL.md") if item.is_file()
            )
        return tuple(
            sorted({item.resolve() for item in candidates}, key=lambda item: str(item).lower())
        )

    def _candidate(self, path: Path) -> SkillCandidate:
        name, description = _skill_metadata(path / "SKILL.md", fallback_name=path.name)
        resolved = path.resolve(strict=True)
        source_id = str(resolved)
        origin = SkillOrigin(
            source_type=self.source_type,
            source_id=source_id,
            source_url=resolved.as_uri(),
            fetch_reference=source_id,
        )
        return SkillCandidate(
            candidate_id=f"local:{hashlib.sha256(source_id.encode('utf-8')).hexdigest()}",
            name=name,
            description=description,
            canonical_repository=None,
            content_digest=_digest_tree(resolved),
            origins=(origin,),
            discovered_at=self._clock().astimezone(timezone.utc).isoformat(),
        )


def search_sources(
    sources: Iterable[SkillSource],
    query: str,
    context: Mapping[str, object] | None = None,
) -> tuple[SkillCandidate, ...]:
    """Aggregate discovery results without ranking, selecting, or governing them."""
    candidates: list[SkillCandidate] = []
    for source in sources:
        candidates.extend(source.search(query, context))
    return deduplicate_candidates(candidates)


def deduplicate_candidates(
    candidates: Iterable[SkillCandidate],
) -> tuple[SkillCandidate, ...]:
    """Merge proven identical project versions while retaining every origin."""
    grouped: dict[tuple[str, ...], list[SkillCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(_identity_key(candidate), []).append(candidate)
    merged: list[SkillCandidate] = []
    for key in sorted(grouped):
        values = sorted(grouped[key], key=lambda item: item.candidate_id)
        first = values[0]
        origins = tuple(
            sorted(
                {origin for item in values for origin in item.origins},
                key=lambda item: (item.source_type, item.source_id, item.revision or ""),
            )
        )
        merged.append(replace(
            first,
            origins=origins,
            discovered_at=min(item.discovered_at for item in values),
        ))
    return tuple(merged)


def _identity_key(candidate: SkillCandidate) -> tuple[str, ...]:
    repository = _canonical_repository(candidate.canonical_repository)
    revisions = {origin.revision for origin in candidate.origins if origin.revision}
    revision = next(iter(revisions)) if len(revisions) == 1 else None
    if repository and revision and candidate.content_digest:
        return ("project-version-content", repository, revision, candidate.content_digest)
    if repository and candidate.content_digest:
        return ("project-content", repository, candidate.content_digest)
    origin = min(
        candidate.origins,
        key=lambda item: (item.source_type, item.source_id, item.revision or ""),
    )
    digest = candidate.content_digest or "unknown-content"
    return ("source-candidate", origin.source_type, origin.source_id, digest)


def _canonical_repository(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    return normalized.casefold() or None


def _skill_metadata(path: Path, *, fallback_name: str) -> tuple[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return fallback_name, ""
    if not text.startswith("---"):
        return fallback_name, ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return fallback_name, ""
    try:
        metadata = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return fallback_name, ""
    if not isinstance(metadata, Mapping):
        return fallback_name, ""
    name = metadata.get("name")
    description = metadata.get("description")
    return (
        name.strip() if isinstance(name, str) and name.strip() else fallback_name,
        description.strip() if isinstance(description, str) else "",
    )


def _digest_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(
        (item for item in root.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(root).as_posix(),
    ):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(relative)
        digest.update(b"\0")
        digest.update(str(len(content)).encode("ascii"))
        digest.update(b"\0")
        digest.update(content)
    return digest.hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


__all__ = [
    "CandidateSignal",
    "LocalSkillSource",
    "SkillCandidate",
    "SkillOrigin",
    "SkillSource",
    "deduplicate_candidates",
    "search_sources",
]
