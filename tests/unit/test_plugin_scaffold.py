import json
import re
import tomllib
from pathlib import Path

import engine
import validators


def test_plugin_manifest_exposes_only_skill_component():
    manifest_path = Path(__file__).parents[2] / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["name"] == "skill-engineering"
    assert manifest["version"] == "1.0.2"
    assert manifest["skills"] == "./skills/"
    assert "mcpServers" not in manifest
    assert "apps" not in manifest
    assert "hooks" not in manifest


def test_project_packages_are_importable():
    assert engine is not None
    assert validators is not None


def test_plugin_and_package_versions_match():
    root = Path(__file__).parents[2]
    manifest = json.loads((root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    package = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    plugin_version = manifest["version"]
    package_version = package["project"]["version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", plugin_version)
    assert plugin_version == package_version
