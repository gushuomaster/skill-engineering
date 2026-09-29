from __future__ import annotations

from pathlib import Path

import pytest

from engine.discovery_config import load_source_config


ROOT = Path(__file__).resolve().parents[2]


def test_checked_in_source_config_is_non_secret_and_safe() -> None:
    config = load_source_config(ROOT / "config" / "skill-sources.yaml")

    assert [item.source_type for item in config.definitions] == [
        "local",
        "openspace-cloud",
    ]
    cloud = config.by_type("openspace-cloud")
    assert cloud.search_tool == "cloud_browse_skills"
    assert cloud.search_action == "search_skills"
    assert cloud.artifact_filter == "downloadable_only"


@pytest.mark.parametrize(
    "unsafe_yaml",
    (
        "sources:\n  - source_type: openspace-cloud\n    enabled: true\n    search_action: import_skill\n",
        "sources:\n  - source_type: openspace-cloud\n    enabled: true\n    api_key: secret\n",
        "sources:\n  - source_type: unknown\n    enabled: true\n",
        "sources:\n  - source_type: local\n    enabled: true\n  - source_type: local\n    enabled: true\n",
    ),
)
def test_source_config_rejects_unsafe_or_ambiguous_values(
    tmp_path: Path, unsafe_yaml: str
) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(unsafe_yaml, encoding="utf-8")

    with pytest.raises(ValueError):
        load_source_config(path)
