from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from engine.discovery_serialization import (
    candidate_governance_result_from_data,
    discovery_bundle_from_data,
    resolved_candidate_from_data,
    selection_record_from_data,
)
from tests.integration.test_cli import ROOT, SCRIPT


FAKE_MCP = ROOT / "tests" / "fixtures" / "openspace" / "fake_mcp_server.py"
FAKE_DOWNLOADER = (
    ROOT / "tests" / "fixtures" / "openspace" / "fake_download_skill.py"
)


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


def test_resolve_candidate_writes_quarantine_record_without_installing(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    installed = codex_home / "skills"
    installed.mkdir(parents=True)
    discovery_path = tmp_path / "discovery.json"
    assert run_cli(
        "discover",
        "--query", "demo",
        "--source", "openspace-cloud",
        "--openspace-mcp-command-json", json.dumps([sys.executable, str(FAKE_MCP)]),
        "--output", str(discovery_path),
        env={"CODEX_HOME": str(codex_home)},
    ).returncode == 0
    bundle = discovery_bundle_from_data(
        json.loads(discovery_path.read_text(encoding="utf-8"))
    )
    selection_path = tmp_path / "selection.json"
    assert run_cli(
        "record-selection",
        "--discovery-bundle", str(discovery_path),
        "--expected-bundle-digest", bundle.bundle_digest,
        "--candidate-id", bundle.candidates[0].candidate_id,
        "--rationale", "Best remote match.",
        "--output", str(selection_path),
    ).returncode == 0
    output = tmp_path / "resolved.json"

    result = run_cli(
        "resolve-candidate",
        "--discovery-bundle", str(discovery_path),
        "--selection-record", str(selection_path),
        "--project-id", "cli-test",
        "--artifact-root", str(tmp_path / "artifacts"),
        "--download-command-json", json.dumps([sys.executable, str(FAKE_DOWNLOADER)]),
        "--output", str(output),
        env={"CODEX_HOME": str(codex_home)},
    )

    assert result.returncode == 2, result.stderr
    resolved = resolved_candidate_from_data(
        json.loads(output.read_text(encoding="utf-8"))
    )
    assert resolved.quarantine_path.is_relative_to((tmp_path / "artifacts").resolve())
    assert not tuple(installed.iterdir())


def test_resolve_candidate_failure_writes_incomplete_result(tmp_path: Path) -> None:
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
    selection_path = tmp_path / "selection.json"
    assert run_cli(
        "record-selection",
        "--discovery-bundle", str(discovery_path),
        "--expected-bundle-digest", bundle.bundle_digest,
        "--candidate-id", bundle.candidates[0].candidate_id,
        "--rationale", "Best remote match.",
        "--output", str(selection_path),
    ).returncode == 0
    failure_path = tmp_path / "resolution-failure.json"

    result = run_cli(
        "resolve-candidate",
        "--discovery-bundle", str(discovery_path),
        "--selection-record", str(selection_path),
        "--project-id", "cli-failure-test",
        "--artifact-root", str(tmp_path / "artifacts"),
        "--download-command-json", json.dumps(["definitely-absent-openspace-downloader"]),
        "--failure-output", str(failure_path),
        "--output", str(tmp_path / "resolved.json"),
    )

    assert result.returncode == 2
    failure = candidate_governance_result_from_data(
        json.loads(failure_path.read_text(encoding="utf-8"))
    )
    assert failure.governance_status.value == "INCOMPLETE"
    assert failure.inspection_id is None
    assert failure.gate_verdict is None
    assert failure.receipt is None


def test_finalize_candidate_writes_incomplete_result_for_unproven_revision(
    tmp_path: Path,
) -> None:
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
    selection_path = tmp_path / "selection.json"
    assert run_cli(
        "record-selection",
        "--discovery-bundle", str(discovery_path),
        "--expected-bundle-digest", bundle.bundle_digest,
        "--candidate-id", bundle.candidates[0].candidate_id,
        "--rationale", "Best remote match.",
        "--output", str(selection_path),
    ).returncode == 0
    resolved_path = tmp_path / "resolved.json"
    assert run_cli(
        "resolve-candidate",
        "--discovery-bundle", str(discovery_path),
        "--selection-record", str(selection_path),
        "--project-id", "cli-finalize-test",
        "--artifact-root", str(tmp_path / "artifacts"),
        "--download-command-json", json.dumps([sys.executable, str(FAKE_DOWNLOADER)]),
        "--output", str(resolved_path),
    ).returncode == 2
    resolved = resolved_candidate_from_data(
        json.loads(resolved_path.read_text(encoding="utf-8"))
    )
    inspection_path = tmp_path / "inspection.json"
    assert run_cli(
        "inspect",
        "--target", str(resolved.quarantine_path),
        "--mode", "AUDIT",
        "--compatibility-no-default-providers",
        "--output", str(inspection_path),
    ).returncode == 0
    gate_path = tmp_path / "gate.json"
    gate_path.write_text(json.dumps({
        "verdict": "INCOMPLETE",
        "outcome": "AUDIT_INCOMPLETE",
        "blocking_findings": [],
        "warnings": [],
        "required_checks_summary": "required=not-complete",
        "evidence_summary": "immutable revision has not been proven",
        "semantic_confirmed": False,
        "apply_authorized": False,
        "policy_version": "v1",
        "coverage_status": "PARTIAL",
        "capability_preservation": None,
    }), encoding="utf-8")
    output = tmp_path / "candidate-governance.json"

    result = run_cli(
        "finalize-candidate",
        "--resolved-candidate", str(resolved_path),
        "--selection-record", str(selection_path),
        "--inspection", str(inspection_path),
        "--gate-result", str(gate_path),
        "--output", str(output),
    )

    assert result.returncode == 2, result.stderr
    finalized = candidate_governance_result_from_data(
        json.loads(output.read_text(encoding="utf-8"))
    )
    assert finalized.governance_status.value == "INCOMPLETE"
    assert finalized.receipt is None
