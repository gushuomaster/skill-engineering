from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.candidate_governance import finalize_candidate
from engine.candidate_resolution import OpenSpaceCliResolver
from engine.discovery import DiscoveryService, record_selection
from engine.discovery_models import (
    CandidateGovernanceStatus,
    ImmutabilityStatus,
    SourceSearchStatus,
)
from engine.discovery_serialization import (
    candidate_governance_result_from_data,
    canonical_record_digest,
    discovery_bundle_from_data,
)
from engine.inventory import digest_tree
from engine.models import (
    CapabilityPreservationStatus,
    CoverageStatus,
    GateOutcome,
    GateResult,
    GateVerdict,
    Intent,
    ManagedCompletionReceipt,
)
from engine.openspace_source import OpenSpaceCloudSource
from tests.integration.test_cli import ROOT
from tests.integration.test_discovery_cli import FAKE_MCP, run_cli


FAKE_DOWNLOADER = ROOT / "tests" / "fixtures" / "openspace" / "fake_download_skill.py"
CLOUD_ROW = {
    "skill_id": "remote-valid__clo_12345678",
    "name": "remote-valid",
    "description": "Remote fixture",
    "source": "cloud",
    "score": 0.9,
    "visibility": "public",
    "created_by": "fixture-publisher",
}


def fixed_clock() -> datetime:
    return datetime(2026, 9, 29, tzinfo=timezone.utc)


class RecordingTransport:
    def search(self, query: str, limit: int):
        del query, limit
        return (CLOUD_ROW,)


class FailingCloud:
    source_type = "openspace-cloud"

    def __init__(self, message: str) -> None:
        self.message = message

    def search(self, query: str, context=None):
        del query, context
        raise RuntimeError(self.message)


def _resolved_context(tmp_path: Path, *, proven: bool):
    bundle = DiscoveryService(clock=fixed_clock).discover(
        "remote workflow",
        (OpenSpaceCloudSource(RecordingTransport(), clock=fixed_clock),),
    )
    candidate = bundle.candidates[0]
    selection = record_selection(
        bundle,
        candidate.candidate_id,
        "Best remote match for the requested workflow.",
        clock=fixed_clock,
    )
    resolved = OpenSpaceCliResolver(
        (sys.executable, str(FAKE_DOWNLOADER)),
        clock=fixed_clock,
    ).resolve(
        candidate,
        selection,
        artifact_root=tmp_path / "artifacts",
        forbidden_roots=(),
    )
    if proven:
        resolved = replace(
            resolved,
            resolved_revision="fixture-revision-1",
            immutability_status=ImmutabilityStatus.PROVEN,
            immutability_evidence=("fixture_revision=fixture-revision-1",),
            resolution_record_digest="0" * 64,
        )
        resolved = replace(
            resolved,
            resolution_record_digest=canonical_record_digest(
                resolved,
                omit=frozenset({"resolution_record_digest"}),
            ),
        )
    return resolved, selection


def _gate(verdict: GateVerdict) -> GateResult:
    return GateResult(
        verdict,
        {
            GateVerdict.PASS: GateOutcome.AUDIT_COMPLETE_VALID,
            GateVerdict.FAIL: GateOutcome.AUDIT_COMPLETE_BLOCKING_FINDINGS,
            GateVerdict.INCOMPLETE: GateOutcome.AUDIT_INCOMPLETE,
        }[verdict],
        ("B04: candidate failed",) if verdict is GateVerdict.FAIL else (),
        (),
        "required=complete" if verdict is not GateVerdict.INCOMPLETE else "required=incomplete",
        "candidate governance evidence",
        verdict is GateVerdict.PASS,
        False,
        "v1",
        CoverageStatus.FULL if verdict is not GateVerdict.INCOMPLETE else CoverageStatus.PARTIAL,
        CapabilityPreservationStatus.CAPABILITY_PRESERVED,
    )


def _managed_receipt(candidate_digest: str) -> ManagedCompletionReceipt:
    return ManagedCompletionReceipt(
        inspection_id="inspection-1",
        operation_mode=Intent.AUDIT,
        source_digest=candidate_digest,
        candidate_digest=candidate_digest,
        baseline_capability_digest="b" * 64,
        candidate_capability_digest="b" * 64,
        validation_bundle_digest="c" * 64,
        semantic_confirmation_digest="d" * 64,
        coverage_status=CoverageStatus.FULL,
        capability_preservation=CapabilityPreservationStatus.CAPABILITY_PRESERVED,
        gate_verdict=GateVerdict.PASS,
        gate_outcome=GateOutcome.AUDIT_COMPLETE_VALID,
        formal_completion=True,
    )


@pytest.mark.parametrize(
    ("proven", "verdict", "expected", "has_receipt"),
    (
        (True, GateVerdict.PASS, CandidateGovernanceStatus.APPROVED, True),
        (True, GateVerdict.FAIL, CandidateGovernanceStatus.BLOCKED, False),
        (False, GateVerdict.INCOMPLETE, CandidateGovernanceStatus.INCOMPLETE, False),
    ),
)
def test_every_governance_outcome_has_no_install_side_effect(
    tmp_path: Path,
    proven: bool,
    verdict: GateVerdict,
    expected: CandidateGovernanceStatus,
    has_receipt: bool,
) -> None:
    installed = tmp_path / "codex-home" / "skills"
    plugin_cache = tmp_path / "codex-home" / "plugins" / "cache"
    installed.mkdir(parents=True)
    plugin_cache.mkdir(parents=True)
    before = (digest_tree(installed), digest_tree(plugin_cache))
    resolved, selection = _resolved_context(tmp_path, proven=proven)
    receipt = _managed_receipt(resolved.candidate_digest) if has_receipt else None

    result = finalize_candidate(
        resolved,
        selection,
        SimpleNamespace(inspection_id="inspection-1"),
        _gate(verdict),
        receipt,
        plugin_version="1.1.0+codex.20260929000000",
        clock=fixed_clock,
    )

    assert result.governance_status is expected
    assert (result.receipt is not None) is has_receipt
    assert (digest_tree(installed), digest_tree(plugin_cache)) == before


def test_mcp_unavailability_is_a_visible_incomplete_source_report() -> None:
    bundle = DiscoveryService(clock=fixed_clock).discover(
        "document generation",
        (FailingCloud("authentication failed"),),
    )

    assert bundle.source_reports[0].status is SourceSearchStatus.INCOMPLETE
    assert "authentication failed" in bundle.source_reports[0].errors[0]


@pytest.mark.parametrize(
    "failure_mode",
    ("missing-command", "nonzero", "malformed-json", "missing-skill-md", "path-escape"),
)
def test_resolver_failure_writes_incomplete_result(
    tmp_path: Path,
    failure_mode: str,
) -> None:
    discovery_path = tmp_path / "discovery.json"
    assert run_cli(
        "discover",
        "--query", "remote",
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
    if failure_mode == "missing-command":
        command = ["definitely-absent-openspace-downloader"]
    else:
        command = [
            sys.executable,
            str(FAKE_DOWNLOADER),
            "--fixture-mode",
            failure_mode,
        ]
    result_path = tmp_path / "resolution-failure.json"

    completed = run_cli(
        "resolve-candidate",
        "--discovery-bundle", str(discovery_path),
        "--selection-record", str(selection_path),
        "--project-id", "failure-matrix",
        "--artifact-root", str(tmp_path / "artifacts"),
        "--download-command-json", json.dumps(command),
        "--failure-output", str(result_path),
        "--output", str(tmp_path / "resolved.json"),
    )

    result = candidate_governance_result_from_data(
        json.loads(result_path.read_text(encoding="utf-8"))
    )
    assert completed.returncode == 2
    assert result.governance_status is CandidateGovernanceStatus.INCOMPLETE
    assert result.inspection_id is None
    assert result.gate_verdict is None
    assert result.receipt is None

