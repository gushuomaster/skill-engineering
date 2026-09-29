"""Strict, non-secret configuration for Skill discovery sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from engine.openspace_source import OpenSpaceCloudSource, OpenSpaceMcpSearchTransport
from engine.skill_sources import LocalSkillSource, SkillSource


_SOURCE_TYPES = frozenset({"local", "openspace-cloud"})
_LOCAL_KEYS = frozenset({"source_type", "enabled"})
_CLOUD_KEYS = frozenset({
    "source_type",
    "enabled",
    "transport",
    "command",
    "search_tool",
    "source_argument",
    "auto_import",
    "download_command",
})


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    source_type: str
    enabled: bool
    transport: str | None = None
    command: tuple[str, ...] = ()
    search_tool: str | None = None
    source_argument: str | None = None
    auto_import: bool | None = None
    download_command: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceConfig:
    definitions: tuple[SourceDefinition, ...]

    def by_type(self, source_type: str) -> SourceDefinition:
        try:
            return next(item for item in self.definitions if item.source_type == source_type)
        except StopIteration as exc:
            raise ValueError(f"source is not configured: {source_type}") from exc


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError(f"{label} must be a nonempty string array")
    return tuple(value)


def load_source_config(path: Path) -> SourceConfig:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid source configuration: {exc}") from exc
    if not isinstance(payload, Mapping) or set(payload) != {"sources"}:
        raise ValueError("source configuration requires only a sources list")
    rows = payload["sources"]
    if not isinstance(rows, list):
        raise ValueError("source configuration sources must be a list")
    definitions: list[SourceDefinition] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("source definitions must be objects")
        source_type = row.get("source_type")
        if source_type not in _SOURCE_TYPES:
            raise ValueError(f"unknown source type: {source_type}")
        if source_type in seen:
            raise ValueError(f"duplicate source type: {source_type}")
        seen.add(source_type)
        allowed = _LOCAL_KEYS if source_type == "local" else _CLOUD_KEYS
        unknown = set(row) - allowed
        if unknown:
            raise ValueError(
                f"unsupported {source_type} configuration keys: {sorted(unknown)}"
            )
        enabled = row.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError(f"{source_type} enabled must be boolean")
        if source_type == "local":
            definitions.append(SourceDefinition(source_type, enabled))
            continue
        if row.get("transport") != "mcp-stdio":
            raise ValueError("OpenSpace transport must be mcp-stdio")
        if row.get("search_tool") != "search_skills":
            raise ValueError("OpenSpace search tool must be search_skills")
        if row.get("source_argument") != "cloud":
            raise ValueError("OpenSpace source argument must be cloud")
        if row.get("auto_import") is not False:
            raise ValueError("OpenSpace auto_import must be false")
        definitions.append(SourceDefinition(
            source_type=source_type,
            enabled=enabled,
            transport="mcp-stdio",
            command=_string_tuple(row.get("command"), "OpenSpace command"),
            search_tool="search_skills",
            source_argument="cloud",
            auto_import=False,
            download_command=_string_tuple(
                row.get("download_command"), "OpenSpace download command"
            ),
        ))
    return SourceConfig(tuple(definitions))


def build_sources(
    config: SourceConfig,
    requested: Sequence[str],
    *,
    local_roots: Sequence[Path],
    openspace_command: Sequence[str] | None,
) -> tuple[SkillSource, ...]:
    source_types = tuple(requested) if requested else tuple(
        item.source_type for item in config.definitions if item.enabled
    )
    if len(set(source_types)) != len(source_types):
        raise ValueError("discovery source cannot be requested more than once")
    sources: list[SkillSource] = []
    for source_type in source_types:
        definition = config.by_type(source_type)
        if not definition.enabled:
            raise ValueError(f"discovery source is disabled: {source_type}")
        if source_type == "local":
            sources.append(LocalSkillSource(tuple(local_roots) or None))
            continue
        command = tuple(openspace_command) if openspace_command is not None else definition.command
        sources.append(OpenSpaceCloudSource(OpenSpaceMcpSearchTransport(command)))
    return tuple(sources)


__all__ = [
    "SourceConfig",
    "SourceDefinition",
    "build_sources",
    "load_source_config",
]
