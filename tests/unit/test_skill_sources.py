from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from engine.governance_api import GateStatus, GovernanceEngine, GovernanceRequest
from engine.host_adapters import discover_skill_path
from engine.skill_sources import (
    CandidateSignal,
    LocalSkillSource,
    SkillCandidate,
    SkillOrigin,
    deduplicate_candidates,
    search_sources,
)


NOW = "2026-09-27T00:00:00+00:00"
REPOSITORY = "https://github.com/example/commerce-skill"
REVISION = "0123456789abcdef"


def _candidate(
    source_type: str,
    source_id: str,
    *,
    digest: str | None = "a" * 64,
    name: str = "commerce-operations",
    repository: str | None = REPOSITORY,
    revision: str | None = REVISION,
    popularity: bool = False,
) -> SkillCandidate:
    return SkillCandidate(
        candidate_id=f"{source_type}:{source_id}",
        name=name,
        description="Operate ecommerce orders and inventory.",
        canonical_repository=repository,
        content_digest=digest,
        origins=(SkillOrigin(
            source_type=source_type,
            source_id=source_id,
            source_url=f"https://catalog.example/{source_id}",
            fetch_reference=f"opaque:{source_id}",
            publisher="example",
            version="1.0.0",
            revision=revision,
            trust_signals=(CandidateSignal("official", "true"),),
            popularity_signals=(CandidateSignal("downloads", "10000"),)
            if popularity else (),
            quality_signals=(CandidateSignal("source_score", "0.99"),),
        ),),
        discovered_at=NOW,
    )


@dataclass
class StubOpenSpaceSource:
    candidates: tuple[SkillCandidate, ...]
    source_type: str = "openspace-cloud"

    def search(
        self,
        query: str,
        context: Mapping[str, object] | None = None,
    ) -> tuple[SkillCandidate, ...]:
        del query, context
        return self.candidates


def test_local_discovery_returns_candidate_and_preserves_existing_exact_lookup(
    tmp_path: Path,
) -> None:
    skill = tmp_path / ".system" / "commerce-operations"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: commerce-operations\n"
        "description: Operate ecommerce orders and inventory.\n---\n",
        encoding="utf-8",
    )
    source = LocalSkillSource(
        (tmp_path,),
        clock=lambda: datetime(2026, 9, 27, tzinfo=timezone.utc),
    )

    candidates = source.search("ecommerce inventory")

    assert len(candidates) == 1
    assert candidates[0].name == "commerce-operations"
    assert candidates[0].content_digest is not None
    assert candidates[0].origins[0].source_type == "local"
    assert candidates[0].origins[0].fetch_reference == str(skill.resolve())
    assert discover_skill_path("commerce-operations", roots=(tmp_path,)) == skill.resolve()


def test_local_discovery_honors_codex_home(
    tmp_path: Path,
    monkeypatch,
) -> None:
    skill = tmp_path / "skills" / "commerce-operations"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: commerce-operations\n"
        "description: Operate ecommerce orders and inventory.\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))

    candidates = LocalSkillSource(
        clock=lambda: datetime(2026, 9, 27, tzinfo=timezone.utc),
    ).search("commerce")

    assert len(candidates) == 1
    assert candidates[0].origins[0].fetch_reference == str(skill.resolve())


def test_openspace_candidate_remains_untrusted_until_governance_evidence_exists() -> None:
    candidate = _candidate("openspace-cloud", "catalog-123", popularity=True)
    selected = search_sources((StubOpenSpaceSource((candidate,)),), "commerce")[0]

    result = GovernanceEngine().evaluate(GovernanceRequest(
        request_id="candidate-review",
        action_type="INSTALL",
        target_skill_ids=(selected.candidate_id,),
        required_capabilities=("SAFE_TO_INSTALL",),
        validation_status="UNKNOWN",
        coverage_status="UNKNOWN",
        integrity_status="UNKNOWN",
    ))

    assert selected.origins[0].popularity_signals
    assert result.gate_status is GateStatus.INCOMPLETE
    assert result.publish_authorized is False


def test_duplicate_project_version_content_merges_and_preserves_provenance() -> None:
    openspace = _candidate("openspace-cloud", "catalog-123")
    official = _candidate("official", "official-456")

    result = deduplicate_candidates((openspace, official))

    assert len(result) == 1
    assert {(item.source_type, item.source_id) for item in result[0].origins} == {
        ("openspace-cloud", "catalog-123"),
        ("official", "official-456"),
    }


def test_same_name_with_different_content_is_not_merged() -> None:
    first = _candidate("openspace-cloud", "catalog-123", digest="a" * 64)
    second = _candidate("github", "repository-456", digest="b" * 64)

    result = deduplicate_candidates((first, second))

    assert len(result) == 2
    assert {item.content_digest for item in result} == {"a" * 64, "b" * 64}


def test_same_repository_and_mutable_ref_without_digest_is_not_merged() -> None:
    first = _candidate("openspace-cloud", "catalog-123", digest=None)
    second = _candidate("github", "repository-456", digest=None)

    result = deduplicate_candidates((first, second))

    assert len(result) == 2


def test_source_metadata_cannot_become_evidence_or_install_authority() -> None:
    candidate = _candidate("openspace-cloud", "catalog-123", popularity=True)

    assert candidate.origins[0].trust_signals
    assert candidate.origins[0].quality_signals
    assert not hasattr(candidate, "evidence")
    assert not hasattr(candidate, "gate")
    assert not hasattr(candidate, "install")
    assert not hasattr(StubOpenSpaceSource, "install")
    assert not hasattr(LocalSkillSource, "install")
    assert not hasattr(LocalSkillSource, "fetch")
