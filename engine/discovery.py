"""Resilient multi-source discovery and Codex-authored candidate selection."""

from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Callable, Mapping, Sequence
from uuid import uuid4

from engine.discovery_models import (
    DiscoveryBundle,
    SelectionRecord,
    SourceSearchReport,
    SourceSearchStatus,
)
from engine.discovery_serialization import canonical_record_digest
from engine.skill_sources import (
    SkillCandidate,
    SkillSource,
    deduplicate_candidates,
    search_sources,
)


def build_discovery_bundle(
    query: str,
    reports: Sequence[SourceSearchReport],
    candidates: Sequence[SkillCandidate],
    discovered_at: datetime,
) -> DiscoveryBundle:
    values = {
        "schema_version": "1.0",
        "discovery_id": str(uuid4()),
        "query": query.strip(),
        "source_reports": tuple(reports),
        "candidates": tuple(candidates),
        "discovered_at": discovered_at.astimezone(timezone.utc).isoformat(),
    }
    return DiscoveryBundle(
        **values,
        bundle_digest=canonical_record_digest(values),
    )


class DiscoveryService:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def discover(
        self,
        query: str,
        sources: Sequence[SkillSource],
        context: Mapping[str, object] | None = None,
    ) -> DiscoveryBundle:
        if not query.strip():
            raise ValueError("discovery query must be nonblank")
        reports: list[SourceSearchReport] = []
        candidates: list[SkillCandidate] = []
        for source in sources:
            try:
                found = search_sources((source,), query, context)
            except Exception as exc:
                reports.append(SourceSearchReport(
                    source.source_type,
                    SourceSearchStatus.INCOMPLETE,
                    (),
                    (f"{type(exc).__name__}: {exc}",),
                ))
            else:
                candidates.extend(found)
                reports.append(SourceSearchReport(
                    source.source_type,
                    SourceSearchStatus.COMPLETE,
                    tuple(item.candidate_id for item in found),
                    (),
                ))
        return build_discovery_bundle(
            query,
            reports,
            deduplicate_candidates(candidates),
            self._clock(),
        )


def record_selection(
    bundle: DiscoveryBundle,
    candidate_id: str,
    rationale: str,
    *,
    clock: Callable[[], datetime],
) -> SelectionRecord:
    actual_digest = canonical_record_digest(
        bundle, omit=frozenset({"bundle_digest"})
    )
    if not hmac.compare_digest(actual_digest, bundle.bundle_digest):
        raise ValueError("discovery bundle digest mismatch")
    if candidate_id not in {item.candidate_id for item in bundle.candidates}:
        raise ValueError("selected candidate is not present in discovery bundle")
    values = {
        "schema_version": "1.0",
        "selection_id": str(uuid4()),
        "discovery_bundle_digest": bundle.bundle_digest,
        "selected_candidate_id": candidate_id,
        "selection_rationale": rationale.strip(),
        "selected_by": "CODEX",
        "selected_at": clock().astimezone(timezone.utc).isoformat(),
    }
    return SelectionRecord(
        **values,
        selection_record_digest=canonical_record_digest(values),
    )


__all__ = ["DiscoveryService", "build_discovery_bundle", "record_selection"]
