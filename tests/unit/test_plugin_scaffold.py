import json
from pathlib import Path

import engine
import validators


def test_plugin_manifest_exposes_only_skill_component():
    manifest_path = Path(__file__).parents[2] / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["name"] == "skill-engineering"
    assert manifest["version"] == "0.1.0"
    assert manifest["skills"] == "./skills/"
    assert "mcpServers" not in manifest
    assert "apps" not in manifest
    assert "hooks" not in manifest


def test_project_packages_are_importable():
    assert engine is not None
    assert validators is not None
