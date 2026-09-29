"""Official OpenSpace MCP search transport and source normalization."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Callable, Mapping, Protocol, Sequence, runtime_checkable

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from engine.skill_sources import CandidateSignal, SkillCandidate, SkillOrigin


class DiscoverySourceError(RuntimeError):
    """Raised when a discovery source cannot return a trustworthy payload."""


@runtime_checkable
class OpenSpaceSearchTransport(Protocol):
    def search(self, query: str, limit: int) -> tuple[Mapping[str, object], ...]:
        """Return raw OpenSpace search rows without importing Skills."""


class OpenSpaceMcpSearchTransport:
    """Call the official OpenSpace cloud browsing search action over stdio."""

    def __init__(self, command: Sequence[str], *, timeout_seconds: int = 30) -> None:
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("OpenSpace MCP command must be a nonempty string sequence")
        if timeout_seconds <= 0:
            raise ValueError("OpenSpace MCP timeout must be positive")
        self.command = tuple(command)
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int) -> tuple[Mapping[str, object], ...]:
        if not query.strip():
            raise ValueError("OpenSpace search query must be nonblank")
        if limit <= 0:
            raise ValueError("OpenSpace search limit must be positive")
        return asyncio.run(self._search(query, limit))

    async def _search(
        self,
        query: str,
        limit: int,
    ) -> tuple[Mapping[str, object], ...]:
        parameters = StdioServerParameters(
            command=self.command[0],
            args=list(self.command[1:]),
            encoding="utf-8",
            encoding_error_handler="strict",
        )
        try:
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    result = await asyncio.wait_for(
                        session.call_tool(
                            "cloud_browse_skills",
                            arguments={
                                "action": "search_skills",
                                "query": query,
                                "limit": limit,
                                "audience": "requester_visible",
                                "artifact_filter": "downloadable_only",
                            },
                        ),
                        timeout=self.timeout_seconds,
                    )
        except DiscoverySourceError:
            raise
        except (OSError, RuntimeError, TimeoutError, asyncio.TimeoutError) as exc:
            raise DiscoverySourceError(
                f"OpenSpace MCP search failed: {type(exc).__name__}: {exc}"
            ) from exc
        return _parse_search_result(result)


def _parse_search_result(result: object) -> tuple[Mapping[str, object], ...]:
    if getattr(result, "isError", False):
        raise DiscoverySourceError("OpenSpace MCP returned a tool error")
    text_items = [
        item.text
        for item in getattr(result, "content", ())
        if getattr(item, "type", None) == "text" and isinstance(item.text, str)
    ]
    if len(text_items) != 1:
        raise DiscoverySourceError("OpenSpace MCP must return exactly one JSON text item")
    try:
        payload = json.loads(text_items[0])
    except json.JSONDecodeError as exc:
        raise DiscoverySourceError("OpenSpace MCP returned invalid JSON") from exc
    if not isinstance(payload, Mapping):
        raise DiscoverySourceError("OpenSpace MCP result must be a JSON object")
    error = payload.get("error")
    if error:
        raise DiscoverySourceError(f"OpenSpace MCP error: {error}")
    rows = payload.get("results")
    if not isinstance(rows, list):
        raise DiscoverySourceError("OpenSpace MCP result requires a results array")
    if any(not isinstance(row, Mapping) for row in rows):
        raise DiscoverySourceError("OpenSpace MCP results must contain only objects")
    return tuple(rows)


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _signal(name: str, value: object) -> CandidateSignal | None:
    if value is None:
        return None
    rendered = (
        json.dumps(value, ensure_ascii=False, sort_keys=True)
        if isinstance(value, (dict, list))
        else str(value)
    )
    return CandidateSignal(name, rendered)


def _signals(
    row: Mapping[str, object],
    names: Sequence[str],
) -> tuple[CandidateSignal, ...]:
    return tuple(
        signal
        for name in names
        if (signal := _signal(name, row.get(name))) is not None
    )


class OpenSpaceCloudSource:
    """Normalize untrusted OpenSpace Cloud metadata as Skill candidates."""

    source_type = "openspace-cloud"

    def __init__(
        self,
        transport: OpenSpaceSearchTransport,
        *,
        clock: Callable[[], datetime] | None = None,
        default_limit: int = 20,
    ) -> None:
        if default_limit <= 0:
            raise ValueError("OpenSpace default limit must be positive")
        self.transport = transport
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.default_limit = default_limit

    def search(
        self,
        query: str,
        context: Mapping[str, object] | None = None,
    ) -> tuple[SkillCandidate, ...]:
        if not query.strip():
            raise ValueError("OpenSpace search query must be nonblank")
        limit = self.default_limit
        if context is not None and "limit" in context:
            raw_limit = context["limit"]
            if not isinstance(raw_limit, int) or isinstance(raw_limit, bool) or raw_limit <= 0:
                raise ValueError("OpenSpace search limit must be a positive integer")
            limit = raw_limit
        return tuple(self._candidate(row) for row in self.transport.search(query, limit))

    def _candidate(self, row: Mapping[str, object]) -> SkillCandidate:
        skill_id = _optional_text(row.get("cloud_skill_id")) or _optional_text(
            row.get("skill_id")
        )
        name = _optional_text(row.get("title")) or _optional_text(row.get("name"))
        if skill_id is None or name is None:
            raise DiscoverySourceError(
                "OpenSpace result requires cloud_skill_id/title or skill_id/name"
            )
        source = _optional_text(row.get("source"))
        if source is not None and source != "cloud":
            raise DiscoverySourceError("OpenSpace Cloud search returned a non-cloud row")
        description = _optional_text(row.get("summary")) or _optional_text(
            row.get("description")
        ) or ""
        source_url = _optional_text(row.get("origin"))
        origin = SkillOrigin(
            source_type=self.source_type,
            source_id=skill_id,
            source_url=source_url,
            fetch_reference=skill_id,
            publisher=_optional_text(row.get("created_by")),
            revision=None,
            trust_signals=_signals(
                row,
                (
                    "effective_visibility",
                    "visibility",
                    "artifact_state",
                    "downloadable",
                    "metadata_only",
                    "safety_flags",
                ),
            ),
            popularity_signals=_signals(row, ("downloads",)),
            quality_signals=_signals(row, ("score", "rank", "manifest_hash", "tags")),
        )
        candidate_hash = hashlib.sha256(skill_id.encode("utf-8")).hexdigest()
        return SkillCandidate(
            candidate_id=f"openspace-cloud:{candidate_hash}",
            name=name,
            description=description,
            canonical_repository=None,
            content_digest=None,
            origins=(origin,),
            discovered_at=self._clock().astimezone(timezone.utc).isoformat(),
        )


__all__ = [
    "DiscoverySourceError",
    "OpenSpaceCloudSource",
    "OpenSpaceMcpSearchTransport",
    "OpenSpaceSearchTransport",
]
