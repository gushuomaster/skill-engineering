from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from engine.discovery_serialization import (
    discovery_bundle_from_data,
    selection_record_from_data,
)
from tests.integration.test_cli import ROOT, SCRIPT


FAKE_MCP = ROOT / "tests" / "fixtures" / "openspace" / "fake_mcp_server.py"


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    process_env = os.environ.copy()
    process_env["PYTHONUTF8"] = "1"
    process_env["PYTHONIOENCODING"] = "utf-8"
    if env:
        process_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        env=process_env,
    )


def test_discover_command_searches_local_and_cloud_without_import(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    local = tmp_path / "local" / "local-demo"
    local.mkdir(parents=True)
    (local / "SKILL.md").write_text(
        "---\nname: local-demo\ndescription: Demo local workflow.\n---\n",
        encoding="utf-8",
    )
    output = tmp_path / "discovery.json"

    result = run_cli(
        "discover",
        "--query", "demo",
        "--source", "local",
        "--source", "openspace-cloud",
        "--local-root", str(tmp_path / "local"),
        "--openspace-mcp-command-json", json.dumps([sys.executable, str(FAKE_MCP)]),
        "--output", str(output),
        env={"CODEX_HOME": str(codex_home)},
    )

    assert result.returncode == 0, result.stderr
    bundle = discovery_bundle_from_data(json.loads(output.read_text(encoding="utf-8")))
    assert {item.source_type for item in bundle.source_reports} == {
        "local",
        "openspace-cloud",
    }
    assert {item.name for item in bundle.candidates} == {"local-demo", "remote-demo"}
    assert not (codex_home / "skills").exists()


def test_record_selection_requires_current_bundle_digest(tmp_path: Path) -> None:
    discovery_path = tmp_path / "discovery.json"
    assert run_cli(
        "discover",
        "--query", "demo",
        "--source", "openspace-cloud",
        "--openspace-mcp-command-json", json.dumps([sys.executable, str(FAKE_MCP)]),
        "--output", str(discovery_path),
    ).returncode == 0
    bundle = discovery_bundle_from_data(
        json.loads(discovery_path.read_text(encoding="utf-8"))
    )
    output = tmp_path / "selection.json"

    stale = run_cli(
        "record-selection",
        "--discovery-bundle", str(discovery_path),
        "--expected-bundle-digest", "0" * 64,
        "--candidate-id", bundle.candidates[0].candidate_id,
        "--rationale", "Best match for the requested workflow.",
        "--output", str(output),
    )
    assert stale.returncode == 2
    assert not output.exists()

    selected = run_cli(
        "record-selection",
        "--discovery-bundle", str(discovery_path),
        "--expected-bundle-digest", bundle.bundle_digest,
        "--candidate-id", bundle.candidates[0].candidate_id,
        "--rationale", "Best match for the requested workflow.",
        "--output", str(output),
    )
    assert selected.returncode == 0, selected.stderr
    record = selection_record_from_data(json.loads(output.read_text(encoding="utf-8")))
    assert record.discovery_bundle_digest == bundle.bundle_digest
    assert record.selection_rationale == "Best match for the requested workflow."
