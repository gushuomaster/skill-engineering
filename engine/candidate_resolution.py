"""Resolve OpenSpace candidates into Engine-owned quarantine directories."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence
from uuid import uuid4

from engine.discovery_models import ImmutabilityStatus, ResolvedCandidate, SelectionRecord
from engine.discovery_serialization import canonical_record_digest
from engine.inventory import assert_no_scope_escape, digest_tree
from engine.skill_sources import SkillCandidate, SkillOrigin


MAX_FILES = 1000
MAX_BYTES = 10 * 1024 * 1024
_MUTABLE_REVISIONS = frozenset({"latest", "main", "master", "head"})
_WINDOWS_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
})


class CandidateResolutionError(ValueError):
    """Raised when downloaded candidate content cannot be accepted safely."""


def _user_cache_root() -> Path:
    if local_app_data := os.environ.get("LOCALAPPDATA"):
        return Path(local_app_data)
    if xdg_cache := os.environ.get("XDG_CACHE_HOME"):
        return Path(xdg_cache)
    return Path.home() / ".cache"


def safe_component(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-")
    if not normalized or normalized.upper() in _WINDOWS_RESERVED_NAMES:
        raise ValueError("identifier is not a safe path component")
    return normalized[:80]


def default_artifact_root(project_id: str) -> Path:
    override = os.environ.get("SKILL_ENGINEERING_ARTIFACT_ROOT")
    base = (
        Path(override)
        if override
        else _user_cache_root() / "skill-engineering" / "artifacts"
    )
    return (base / safe_component(project_id)).resolve()


def assert_not_registered_root(target: Path, forbidden_roots: Sequence[Path]) -> None:
    resolved = target.resolve()
    for root in forbidden_roots:
        registered = root.resolve()
        if (
            resolved == registered
            or resolved.is_relative_to(registered)
            or registered.is_relative_to(resolved)
        ):
            raise PermissionError(
                f"quarantine target overlaps registered Skill root: {registered}"
            )


def _selected_origin(candidate: SkillCandidate) -> SkillOrigin:
    origins = tuple(
        origin for origin in candidate.origins
        if origin.source_type == "openspace-cloud"
    )
    if len(origins) != 1:
        raise CandidateResolutionError(
            "candidate must have exactly one OpenSpace Cloud origin"
        )
    origin = origins[0]
    if not origin.source_id.strip() or not (origin.fetch_reference or "").strip():
        raise CandidateResolutionError("OpenSpace origin requires retrieval references")
    return origin


class OpenSpaceCliResolver:
    def __init__(
        self,
        download_command: Sequence[str],
        *,
        timeout_seconds: int = 60,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not download_command or any(
            not isinstance(part, str) or not part for part in download_command
        ):
            raise ValueError("OpenSpace download command must be nonempty")
        if timeout_seconds <= 0:
            raise ValueError("OpenSpace download timeout must be positive")
        self.download_command = tuple(download_command)
        self.timeout_seconds = timeout_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def resolve(
        self,
        candidate: SkillCandidate,
        selection: SelectionRecord,
        *,
        artifact_root: Path,
        forbidden_roots: Sequence[Path],
    ) -> ResolvedCandidate:
        expected_selection_digest = canonical_record_digest(
            selection, omit=frozenset({"selection_record_digest"})
        )
        if expected_selection_digest != selection.selection_record_digest:
            raise ValueError("selection record digest mismatch")
        if selection.selected_candidate_id != candidate.candidate_id:
            raise ValueError("selection references a different selected candidate")
        origin = _selected_origin(candidate)

        root = artifact_root.resolve()
        assert_not_registered_root(root, forbidden_roots)
        root.mkdir(parents=True, exist_ok=True)
        quarantine_root = root / "quarantine"
        quarantine_root.mkdir(parents=True, exist_ok=True)
        resolution_id = str(uuid4())
        quarantine_run = quarantine_root / resolution_id
        quarantine_run.mkdir(exist_ok=False)
        assert_not_registered_root(quarantine_run, forbidden_roots)

        command = [
            *self.download_command,
            "--skill-id", origin.source_id,
            "--output-dir", str(quarantine_run),
        ]
        try:
            completed = subprocess.run(
                command,
                text=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CandidateResolutionError(
                f"OpenSpace download failed: {type(exc).__name__}: {exc}"
            ) from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()[-2000:]
            raise CandidateResolutionError(
                f"OpenSpace download failed with exit {completed.returncode}: {detail}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise CandidateResolutionError(
                "OpenSpace download returned invalid JSON"
            ) from exc
        if not isinstance(payload, dict) or payload.get("status") != "success":
            raise CandidateResolutionError("OpenSpace download did not report success")
        if payload.get("skill_id") != origin.source_id:
            raise CandidateResolutionError("OpenSpace response skill_id mismatch")
        local_path = payload.get("local_path")
        if not isinstance(local_path, str) or not local_path:
            raise CandidateResolutionError("OpenSpace response requires local_path")
        try:
            resolved_path = Path(local_path).resolve(strict=True)
        except OSError as exc:
            raise CandidateResolutionError(
                "OpenSpace local_path does not exist"
            ) from exc
        if not resolved_path.is_relative_to(quarantine_run.resolve()):
            raise CandidateResolutionError("downloaded Skill is outside quarantine")
        assert_not_registered_root(resolved_path, forbidden_roots)
        if root.stat().st_dev != quarantine_run.stat().st_dev or (
            root.stat().st_dev != resolved_path.stat().st_dev
        ):
            raise CandidateResolutionError("quarantine content must stay on one filesystem")
        try:
            assert_no_scope_escape(resolved_path)
        except ValueError as exc:
            raise CandidateResolutionError(str(exc)) from exc
        skill_file = resolved_path / "SKILL.md"
        if not skill_file.is_file():
            raise CandidateResolutionError("downloaded Skill is missing SKILL.md")
        identity_file = resolved_path / ".skill_id"
        if not identity_file.is_file():
            raise CandidateResolutionError("downloaded Skill is missing .skill_id")
        try:
            downloaded_id = identity_file.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            raise CandidateResolutionError("downloaded .skill_id is invalid") from exc
        if downloaded_id != origin.source_id:
            raise CandidateResolutionError("downloaded .skill_id does not match selection")
        files = tuple(item for item in resolved_path.rglob("*") if item.is_file())
        if len(files) > MAX_FILES:
            raise CandidateResolutionError("downloaded Skill exceeds 1000 files")
        total_bytes = sum(item.stat().st_size for item in files)
        if total_bytes > MAX_BYTES:
            raise CandidateResolutionError("downloaded Skill exceeds 10 MiB")

        revision = (origin.revision or "").strip()
        if revision and revision.casefold() not in _MUTABLE_REVISIONS:
            resolved_revision = revision
            immutability_status = ImmutabilityStatus.PROVEN
            evidence = (f"origin_revision={revision}",)
        else:
            resolved_revision = None
            immutability_status = ImmutabilityStatus.UNPROVEN
            evidence = (
                "OpenSpace MCP contract did not provide an immutable revision",
            )
        values = {
            "schema_version": "1.0",
            "resolution_id": resolution_id,
            "discovery_bundle_digest": selection.discovery_bundle_digest,
            "selection_record_digest": selection.selection_record_digest,
            "candidate_id": candidate.candidate_id,
            "name": candidate.name,
            "source_type": origin.source_type,
            "source_id": origin.source_id,
            "source_uri": origin.source_url,
            "fetch_reference": origin.fetch_reference,
            "resolved_revision": resolved_revision,
            "immutability_status": immutability_status,
            "immutability_evidence": evidence,
            "quarantine_path": resolved_path,
            "candidate_digest": digest_tree(resolved_path),
            "resolver": "openspace-download-skill",
            "resolved_at": self._clock().astimezone(timezone.utc).isoformat(),
        }
        return ResolvedCandidate(
            **values,
            resolution_record_digest=canonical_record_digest(values),
        )


__all__ = [
    "CandidateResolutionError",
    "OpenSpaceCliResolver",
    "assert_not_registered_root",
    "default_artifact_root",
    "safe_component",
]
