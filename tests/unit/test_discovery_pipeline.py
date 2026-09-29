from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Mapping

import pytest

from engine.discovery import DiscoveryService, record_selection
from engine.discovery_models import SourceSearchStatus
from engine.discovery_serialization import canonical_record_digest
from engine.skill_sources import SkillCandidate, SkillOrigin


NOW = "2026-09-29T00:00:00+00:00"


def fixed_clock() -> datetime:
    return datetime(2026, 9, 29, tzinfo=timezone.utc)


def candidate(source_type: str, source_id: str) -> SkillCandidate:
    return SkillCandidate(
        candidate_id=f"{source_type}:{source_id}",
        name="demo",
        description="Demo workflow",
        canonical_repository=None,
        content_digest=None,
        origins=(SkillOrigin(
            source_type=source_type,
            source_id=source_id,
            fetch_reference=source_id,
        ),),
        discovered_at=NOW,
    )


@dataclass
class StubSource:
    source_type: str
    results: tuple[SkillCandidate, ...]

    def search(self, query: str, context: Mapping[str, object] | None = None):
        del query, context
        return self.results


@dataclass
class FailingSource:
    source_type: str
    message: str

    def search(self, query: str, context: Mapping[str, object] | None = None):
        del query, context
        raise RuntimeError(self.message)


def test_discovery_preserves_local_results_when_cloud_is_unavailable() -> None:
    local = candidate("local", "local-demo")

    bundle = DiscoveryService(clock=fixed_clock).discover(
        "demo workflow",
        (
            StubSource("local", (local,)),
            FailingSource("openspace-cloud", "authentication failed"),
        ),
    )

    assert bundle.candidates == (local,)
    assert bundle.source_reports[0].status is SourceSearchStatus.COMPLETE
    assert bundle.source_reports[1].status is SourceSearchStatus.INCOMPLETE
    assert bundle.source_reports[1].errors == (
        "RuntimeError: authentication failed",
    )


def test_discovery_bundle_digest_covers_source_status_and_candidates() -> None:
    bundle = DiscoveryService(clock=fixed_clock).discover(
        "demo", (StubSource("local", (candidate("local", "demo"),)),)
    )

    assert bundle.bundle_digest == canonical_record_digest(
        bundle, omit=frozenset({"bundle_digest"})
    )


def test_selection_is_bound_to_existing_candidate_and_current_bundle() -> None:
    bundle = DiscoveryService(clock=fixed_clock).discover(
        "demo", (StubSource("local", (candidate("local", "demo"),)),)
    )

    selection = record_selection(
        bundle,
        bundle.candidates[0].candidate_id,
        "Best match for the requested workflow.",
        clock=fixed_clock,
    )

    assert selection.discovery_bundle_digest == bundle.bundle_digest
    assert selection.selected_by == "CODEX"
    assert selection.selection_record_digest == canonical_record_digest(
        selection, omit=frozenset({"selection_record_digest"})
    )


def test_selection_rejects_missing_candidate_and_tampered_bundle() -> None:
    bundle = DiscoveryService(clock=fixed_clock).discover(
        "demo", (StubSource("local", (candidate("local", "demo"),)),)
    )
    with pytest.raises(ValueError, match="candidate is not present"):
        record_selection(bundle, "missing", "best match", clock=fixed_clock)

    tampered = replace(bundle, query="other query")
    with pytest.raises(ValueError, match="discovery bundle digest mismatch"):
        record_selection(
            tampered,
            bundle.candidates[0].candidate_id,
            "best match",
            clock=fixed_clock,
        )
