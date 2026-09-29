from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from engine.candidate_governance import finalize_candidate
from engine.candidate_resolution import OpenSpaceCliResolver
from engine.discovery import DiscoveryService, record_selection
from engine.discovery_models import CandidateGovernanceStatus
from engine.inventory import digest_tree
from engine.models import CoverageStatus, GateOutcome, GateResult, GateVerdict, Intent
from engine.openspace_source import OpenSpaceCloudSource
from engine.orchestrator import PipelineOrchestrator


ROOT = Path(__file__).resolve().parents[2]
FAKE_DOWNLOADER = ROOT / "tests" / "fixtures" / "openspace" / "fake_download_skill.py"


def fixed_clock() -> datetime:
    return datetime(2026, 9, 29, tzinfo=timezone.utc)


class FixtureCloudTransport:
    def search(self, query: str, limit: int):
        del query, limit
        return ({
            "skill_id": "remote-valid__clo_12345678",
            "name": "remote-valid",
            "description": "Remote fixture",
            "source": "cloud",
        },)


def test_remote_candidate_pipeline_stops_after_governance(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    installed_root = codex_home / "skills"
    plugin_cache = codex_home / "plugins" / "cache"
    installed_root.mkdir(parents=True)
    plugin_cache.mkdir(parents=True)
    before = (digest_tree(installed_root), digest_tree(plugin_cache))
    discovery = DiscoveryService(clock=fixed_clock).discover(
        "document generation",
        (OpenSpaceCloudSource(FixtureCloudTransport(), clock=fixed_clock),),
    )
    remote = discovery.candidates[0]
    selection = record_selection(
        discovery,
        remote.candidate_id,
        "Matches the requested document workflow.",
        clock=fixed_clock,
    )
    resolved = OpenSpaceCliResolver(
        (sys.executable, str(FAKE_DOWNLOADER)),
        clock=fixed_clock,
    ).resolve(
        remote,
        selection,
        artifact_root=tmp_path / "artifacts",
        forbidden_roots=(installed_root, plugin_cache),
    )
    inspection = PipelineOrchestrator().inspect(Intent.AUDIT, resolved.quarantine_path)
    gate = GateResult(
        GateVerdict.INCOMPLETE,
        GateOutcome.AUDIT_INCOMPLETE,
        (),
        (),
        "required=not-complete",
        "candidate was quarantined but immutable revision was not proven",
        False,
        False,
        "v1",
        CoverageStatus.PARTIAL,
        None,
    )

    result = finalize_candidate(
        resolved,
        selection,
        inspection,
        gate,
        None,
        plugin_version="1.1.0+codex.20260929000000",
        clock=fixed_clock,
    )

    assert result.governance_status is CandidateGovernanceStatus.INCOMPLETE
    assert result.receipt is None
    assert (digest_tree(installed_root), digest_tree(plugin_cache)) == before
    assert not any(path.name == resolved.name for path in installed_root.iterdir())
