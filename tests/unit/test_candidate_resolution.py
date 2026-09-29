from __future__ import annotations

import re
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.candidate_resolution import CandidateResolutionError, OpenSpaceCliResolver
from engine.discovery import DiscoveryService, record_selection
from engine.discovery_models import ImmutabilityStatus
from engine.discovery_serialization import canonical_record_digest
from engine.inventory import digest_tree
from engine.skill_sources import SkillCandidate, SkillOrigin


ROOT = Path(__file__).resolve().parents[2]
FAKE_DOWNLOADER = ROOT / "tests" / "fixtures" / "openspace" / "fake_download_skill.py"


def fixed_clock() -> datetime:
    return datetime(2026, 9, 29, tzinfo=timezone.utc)


def candidate() -> SkillCandidate:
    return SkillCandidate(
        candidate_id="openspace-cloud:" + "1" * 64,
        name="remote-valid",
        description="Remote fixture",
        canonical_repository=None,
        content_digest=None,
        origins=(SkillOrigin(
            source_type="openspace-cloud",
            source_id="remote-valid__clo_12345678",
            fetch_reference="remote-valid__clo_12345678",
        ),),
        discovered_at="2026-09-29T00:00:00+00:00",
    )


class Source:
    source_type = "openspace-cloud"

    def search(self, query, context=None):
        del query, context
        return (candidate(),)


def selection():
    bundle = DiscoveryService(clock=fixed_clock).discover("remote", (Source(),))
    return record_selection(
        bundle, candidate().candidate_id, "Best remote match.", clock=fixed_clock
    )


def resolver(mode: str = "valid") -> OpenSpaceCliResolver:
    command = [sys.executable, str(FAKE_DOWNLOADER)]
    if mode != "valid":
        command.extend(("--fixture-mode", mode))
    return OpenSpaceCliResolver(command, clock=fixed_clock)


def test_resolver_downloads_below_quarantine_and_never_installs(tmp_path: Path) -> None:
    installed = tmp_path / "codex-home" / "skills"
    installed.mkdir(parents=True)
    before = digest_tree(installed)

    resolved = resolver().resolve(
        candidate(),
        selection(),
        artifact_root=tmp_path / "artifacts",
        forbidden_roots=(installed,),
    )

    assert resolved.quarantine_path.is_relative_to(
        (tmp_path / "artifacts" / "quarantine").resolve()
    )
    assert (resolved.quarantine_path / "SKILL.md").is_file()
    assert resolved.immutability_status is ImmutabilityStatus.UNPROVEN
    assert resolved.resolved_revision is None
    assert resolved.resolution_record_digest == canonical_record_digest(
        resolved, omit=frozenset({"resolution_record_digest"})
    )
    assert digest_tree(installed) == before


@pytest.mark.parametrize(
    ("mode", "message"),
    (
        ("path-escape", "outside quarantine"),
        ("missing-skill-md", "SKILL.md"),
        ("skill-id-mismatch", ".skill_id"),
        ("too-many-files", "1000 files"),
        ("too-large", "10 MiB"),
        ("nonzero", "download failed"),
        ("malformed-json", "invalid JSON"),
    ),
)
def test_resolver_rejects_unsafe_or_failed_downloads(
    tmp_path: Path, mode: str, message: str
) -> None:
    with pytest.raises(CandidateResolutionError, match=re.escape(message)):
        resolver(mode).resolve(
            candidate(),
            selection(),
            artifact_root=tmp_path / "artifacts",
            forbidden_roots=(),
        )


def test_resolver_rejects_valid_selection_for_another_candidate(tmp_path: Path) -> None:
    current = selection()
    mismatched = replace(
        current,
        selected_candidate_id="openspace-cloud:other",
        selection_record_digest="0" * 64,
    )
    mismatched = replace(
        mismatched,
        selection_record_digest=canonical_record_digest(
            mismatched, omit=frozenset({"selection_record_digest"})
        ),
    )

    with pytest.raises(ValueError, match="selected candidate"):
        resolver().resolve(
            candidate(),
            mismatched,
            artifact_root=tmp_path / "artifacts",
            forbidden_roots=(),
        )
