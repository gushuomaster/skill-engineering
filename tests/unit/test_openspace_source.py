from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import engine.openspace_source as openspace_source
from engine.openspace_source import (
    DiscoverySourceError,
    OpenSpaceCloudSource,
    OpenSpaceMcpSearchTransport,
)


class RecordingTransport:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def search(self, query: str, limit: int):
        self.calls.append((query, limit))
        return self.rows


def test_cloud_source_normalizes_metadata_without_claiming_evidence() -> None:
    transport = RecordingTransport(({
        "skill_id": "demo__clo_12345678",
        "name": "demo",
        "description": "Demo Skill",
        "source": "cloud",
        "score": 0.9,
        "visibility": "public",
        "created_by": "publisher-a",
    },))
    source = OpenSpaceCloudSource(
        transport,
        clock=lambda: datetime(2026, 9, 29, tzinfo=timezone.utc),
    )

    candidate = source.search("demo")[0]

    assert transport.calls == [("demo", 20)]
    assert candidate.origins[0].source_type == "openspace-cloud"
    assert candidate.origins[0].fetch_reference == "demo__clo_12345678"
    assert candidate.origins[0].revision is None
    assert candidate.content_digest is None
    assert candidate.origins[0].quality_signals[0].name == "score"
    assert not hasattr(candidate, "evidence")


def test_mcp_transport_uses_safe_cloud_search_arguments(monkeypatch) -> None:
    calls = []

    class AsyncContext:
        async def __aenter__(self):
            return (object(), object())

        async def __aexit__(self, *args):
            return False

    class FakeSession:
        def __init__(self, reader, writer):
            del reader, writer

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def initialize(self):
            return None

        async def call_tool(self, name, arguments):
            calls.append((name, arguments))
            return SimpleNamespace(
                isError=False,
                content=[SimpleNamespace(
                    type="text",
                    text=json.dumps({"results": [], "count": 0}),
                )],
            )

    monkeypatch.setattr(openspace_source, "stdio_client", lambda parameters: AsyncContext())
    monkeypatch.setattr(openspace_source, "ClientSession", FakeSession)

    rows = OpenSpaceMcpSearchTransport(("openspace-mcp", "--transport", "stdio")).search(
        "demo", 20
    )

    assert rows == ()
    assert calls == [("search_skills", {
        "query": "demo",
        "source": "cloud",
        "limit": 20,
        "auto_import": False,
    })]


@pytest.mark.parametrize(
    "payload",
    (
        "not-json",
        json.dumps({"error": "authentication failed"}),
        json.dumps({"results": {"skill_id": "wrong-shape"}}),
        json.dumps({"results": ["wrong-row"]}),
    ),
)
def test_mcp_transport_rejects_malformed_or_error_payloads(monkeypatch, payload) -> None:
    class AsyncContext:
        async def __aenter__(self):
            return (object(), object())

        async def __aexit__(self, *args):
            return False

    class FakeSession:
        def __init__(self, reader, writer):
            del reader, writer

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def initialize(self):
            return None

        async def call_tool(self, name, arguments):
            del name, arguments
            return SimpleNamespace(
                isError=False,
                content=[SimpleNamespace(type="text", text=payload)],
            )

    monkeypatch.setattr(openspace_source, "stdio_client", lambda parameters: AsyncContext())
    monkeypatch.setattr(openspace_source, "ClientSession", FakeSession)

    with pytest.raises(DiscoverySourceError):
        OpenSpaceMcpSearchTransport(("openspace-mcp",)).search("demo", 20)
