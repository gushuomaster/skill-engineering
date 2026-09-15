from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import pytest

import engine.workspace as workspace
from engine.inventory import digest_tree
from engine.mechanism_selection import IMPLEMENTATION_FIX, REFERENCE_OR_INSTRUCTION
from engine.models import (
    CheckResult,
    CheckStatus,
    Intent,
    PrimaryIssueClass,
    ProviderDescriptor,
    ProviderResult,
    ProviderStatus,
    RegressionDisposition,
)
from engine.orchestrator import (
    EngineeringRequest,
    PipelineBlockedError,
    PipelineOrchestrator,
    publish,
)
from engine.providers import AUDIT_SKILL, ProviderGateway
from engine.rule_governance import GovernanceDecision
from engine.workspace import PublishRecoveryError, SourceChangedError
from scripts.skill_engineering import _command_runner
from tests.support import ALL_MECHANISMS, codex_decision, confirmation, copy_candidate


ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "skill_engineering.py"
FIXTURES = Path(__file__).parent / "fixtures"
SOURCE_FIXTURE = FIXTURES / "source-skill"
MODIFY_FIXTURE = FIXTURES / "modify-candidate" / "source-skill"
CREATE_FIXTURE = FIXTURES / "create-candidate" / "candidate-skill"


def _copy(source: Path, parent: Path) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    return copy_candidate(source, parent)


def _recorded_runner(
    command: list[str], check_id: str, records: list[CheckResult]
):
    runner = _command_runner(json.dumps(command), check_id)
    assert runner is not None

    def run(artifact: Path) -> CheckResult:
        result = runner(artifact)
        records.append(result)
        return result

    return run


def _modify_request(
    source: Path,
    candidate: Path,
    target_parent: Path,
    *,
    publish_requested: bool,
    records: list[CheckResult] | None = None,
    behavior_command: list[str] | None = None,
    regression_command: list[str] | None = None,
    include_regression: bool = True,
    semantic: bool = True,
    governance_decisions: tuple[GovernanceDecision, ...] = (),
) -> EngineeringRequest:
    records = records if records is not None else []
    behavior_command = behavior_command or [
        sys.executable,
        "scripts/check.py",
        "--value",
        " Example ",
        "--expect",
        "EXAMPLE",
    ]
    regression_command = regression_command or [
        sys.executable,
        "scripts/check.py",
        "--value",
        " stable ",
        "--expect",
        "STABLE",
    ]
    return EngineeringRequest(
        requirement="Change normalization from lowercase to uppercase",
        intent=Intent.MODIFY,
        decision=codex_decision(
            Intent.MODIFY,
            primary=PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE,
            selected=(IMPLEMENTATION_FIX,),
            regression=RegressionDisposition.REQUIRED,
        ),
        source=source,
        candidate=candidate,
        failure_evidence=(),
        authorized_to_modify=True,
        target_parent=target_parent,
        semantic_confirmation=confirmation(candidate) if semantic else None,
        governance_decisions=governance_decisions,
        behavioral_runner=_recorded_runner(behavior_command, "behavioral.modify", records),
        regression_runner=(
            _recorded_runner(regression_command, "B07", records)
            if include_regression else None
        ),
        publish_requested=publish_requested,
    )


def _create_request(
    candidate: Path,
    target_parent: Path,
    *,
    publish_requested: bool,
    records: list[CheckResult] | None = None,
) -> EngineeringRequest:
    records = records if records is not None else []
    behavior = [sys.executable, "scripts/check.py", "--topic", "release"]
    regression = [sys.executable, "scripts/check.py", "--topic", "upgrade"]
    return EngineeringRequest(
        requirement="Create a release checklist Skill",
        intent=Intent.CREATE,
        decision=codex_decision(
            Intent.CREATE,
            primary=PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE,
            selected=(REFERENCE_OR_INSTRUCTION,),
            regression=RegressionDisposition.REQUIRED,
        ),
        source=None,
        candidate=candidate,
        failure_evidence=(),
        authorized_to_modify=True,
        target_parent=target_parent,
        semantic_confirmation=confirmation(candidate),
        behavioral_runner=_recorded_runner(behavior, "behavioral.create", records),
        regression_runner=_recorded_runner(regression, "B07", records),
        publish_requested=publish_requested,
    )


def _modify_workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    published_parent = tmp_path / "published"
    source = _copy(SOURCE_FIXTURE, published_parent)
    candidate = _copy(MODIFY_FIXTURE, tmp_path / "codex")
    return published_parent, source, candidate


def _json_decision(path: Path, intent: Intent) -> Path:
    decision = codex_decision(
        intent,
        primary=PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE,
        selected=(REFERENCE_OR_INSTRUCTION,),
        regression=RegressionDisposition.REQUIRED,
    )
    payload = asdict(decision)
    for key, value in tuple(payload.items()):
        if hasattr(value, "value"):
            payload[key] = value.value
        elif isinstance(value, tuple):
            payload[key] = [item.value if hasattr(item, "value") else item for item in value]
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_m1_modify_without_publish_keeps_source_and_staged_candidate(tmp_path: Path) -> None:
    parent, source, candidate = _modify_workspace(tmp_path)
    before = digest_tree(source)
    records: list[CheckResult] = []

    outcome = PipelineOrchestrator().run(
        _modify_request(source, candidate, parent, publish_requested=False, records=records)
    )

    assert outcome.gate_result.verdict.value == "PASS"
    assert outcome.gate_result.semantic_confirmed is True
    assert outcome.gate_result.publish_authorized is False
    assert outcome.publication_session is None
    assert digest_tree(source) == before
    assert digest_tree(outcome.artifact_path) == digest_tree(candidate)
    assert outcome.artifact_path.parent.name.startswith(".skill-engineering-")
    assert outcome.workspace_diff.modified == (
        "SKILL.md",
        "references/behavior.md",
        "scripts/check.py",
    )
    assert [result.status for result in records] == [CheckStatus.PASS, CheckStatus.PASS]
    assert not (parent / "source-skill.backup").exists()


def test_m2_modify_explicit_publish_records_atomic_replacement_and_backup(tmp_path: Path) -> None:
    parent, source, candidate = _modify_workspace(tmp_path)
    sentinel = parent / "unrelated.txt"
    sentinel.write_text("unchanged", encoding="utf-8")
    before = digest_tree(source)
    candidate_digest = digest_tree(candidate)
    outcome = PipelineOrchestrator().run(
        _modify_request(source, candidate, parent, publish_requested=True)
    )
    assert outcome.gate_result.verdict.value == "PASS"
    assert outcome.gate_result.publish_authorized is True

    result = publish(outcome)

    assert result.status == "PUBLISHED"
    assert result.source_digest_before == before
    assert result.candidate_digest == candidate_digest
    assert result.published_digest == candidate_digest == digest_tree(source)
    assert result.backup_path == parent / "source-skill.backup"
    assert result.backup_path is not None and digest_tree(result.backup_path) == before
    assert result.workspace_diff == outcome.workspace_diff
    assert not result.restored_after_failure
    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert {path.name for path in parent.iterdir() if path.is_dir()} == {
        "source-skill",
        "source-skill.backup",
        outcome.artifact_path.parent.name,
    }


def test_m3_source_digest_race_rejects_publish_without_overwrite(tmp_path: Path) -> None:
    parent, source, candidate = _modify_workspace(tmp_path)
    outcome = PipelineOrchestrator().run(
        _modify_request(source, candidate, parent, publish_requested=True)
    )
    staged_digest = digest_tree(outcome.artifact_path)
    external = source / "external-change.txt"
    external.write_text("preserve me", encoding="utf-8")
    assert outcome.publication_session is not None
    assert digest_tree(source) != outcome.publication_session.source_digest

    with pytest.raises(SourceChangedError, match="after staging"):
        publish(outcome)

    assert external.read_text(encoding="utf-8") == "preserve me"
    assert digest_tree(outcome.artifact_path) == staged_digest
    assert not (parent / "source-skill.backup").exists()


def test_m5_behavior_failure_preserves_command_streams_and_blocks_publish(tmp_path: Path) -> None:
    parent, source, candidate = _modify_workspace(tmp_path)
    before = digest_tree(source)
    records: list[CheckResult] = []
    failing = [
        sys.executable,
        "scripts/check.py",
        "--value",
        "Example",
        "--expect",
        "WRONG",
    ]

    with pytest.raises(PipelineBlockedError) as caught:
        PipelineOrchestrator().run(
            _modify_request(
                source,
                candidate,
                parent,
                publish_requested=True,
                records=records,
                behavior_command=failing,
            )
        )

    behavior = records[0]
    assert behavior.status is CheckStatus.FAIL and behavior.required
    assert behavior.evidence[0].startswith("command=")
    assert behavior.evidence[1] == "exit_code=1"
    assert behavior.evidence[2].startswith("stdout=actual=EXAMPLE")
    assert behavior.evidence[3] == "stderr="
    assert caught.value.gate_result.verdict.value == "FAIL"
    assert caught.value.gate_result.publish_authorized is False
    assert digest_tree(source) == before
    assert not (parent / "source-skill.backup").exists()


def test_m6_required_regression_absent_is_not_executed_and_blocks(tmp_path: Path) -> None:
    parent, source, candidate = _modify_workspace(tmp_path)
    with pytest.raises(PipelineBlockedError) as caught:
        PipelineOrchestrator().run(
            _modify_request(
                source,
                candidate,
                parent,
                publish_requested=True,
                include_regression=False,
            )
        )

    regression = next(result for result in caught.value.evidence if result.check_id == "B07")
    assert regression.status is CheckStatus.NOT_EXECUTED
    assert regression.evidence == ("Required regression command was not supplied",)
    assert any(finding.startswith("B07") for finding in caught.value.gate_result.blocking_findings)


@pytest.mark.parametrize(
    ("command", "expected_error"),
    [
        (["missing-skill-engineering-e2e-tool"], "FileNotFoundError"),
        (None, "PermissionError"),
    ],
    ids=("tool-missing", "cannot-start"),
)
def test_m6_regression_launch_error_is_explicit_and_blocks(
    tmp_path: Path, command: list[str] | None, expected_error: str
) -> None:
    parent, source, candidate = _modify_workspace(tmp_path)
    actual_command = command or [str(candidate / "scripts")]
    records: list[CheckResult] = []
    with pytest.raises(PipelineBlockedError) as caught:
        PipelineOrchestrator().run(
            _modify_request(
                source,
                candidate,
                parent,
                publish_requested=True,
                records=records,
                regression_command=actual_command,
            )
        )

    regression = records[1]
    assert regression.status is CheckStatus.ERROR
    assert regression.evidence[1] == "exit_code=NOT_STARTED"
    assert expected_error in regression.evidence[3]
    assert caught.value.gate_result.publish_authorized is False
    assert not (parent / "source-skill.backup").exists()


def test_m7_injected_publish_failure_restores_original_and_records_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent, source, candidate = _modify_workspace(tmp_path)
    before = digest_tree(source)
    outcome = PipelineOrchestrator().run(
        _modify_request(source, candidate, parent, publish_requested=True)
    )
    real_replace = os.replace
    calls: list[tuple[str, str]] = []

    def fail_candidate_move(src: str, dst: str) -> None:
        calls.append((src, dst))
        if len(calls) == 2:
            raise OSError("controlled E2E failure injection")
        real_replace(src, dst)

    monkeypatch.setattr(workspace.os, "replace", fail_candidate_move)
    with pytest.raises(PublishRecoveryError) as caught:
        publish(outcome)

    result = caught.value.result
    assert result.status == "RECOVERED"
    assert result.restored_after_failure is True
    assert result.backup_path == parent / "source-skill.backup"
    assert result.source_digest_before == before
    assert result.candidate_digest == digest_tree(candidate)
    assert result.published_digest == before == digest_tree(source)
    assert not result.backup_path.exists()
    assert outcome.artifact_path.exists()


def test_c1_create_without_publish_keeps_complete_candidate_in_staging(tmp_path: Path) -> None:
    candidate = _copy(CREATE_FIXTURE, tmp_path / "codex")
    destination = tmp_path / "destination"
    destination.mkdir()
    records: list[CheckResult] = []

    outcome = PipelineOrchestrator().run(
        _create_request(candidate, destination, publish_requested=False, records=records)
    )

    assert outcome.gate_result.verdict.value == "PASS"
    assert outcome.gate_result.publish_authorized is False
    assert outcome.publication_session is None
    assert digest_tree(outcome.artifact_path) == digest_tree(candidate)
    assert outcome.artifact_path.name == "candidate-skill"
    assert not (destination / "candidate-skill").exists()
    assert not (destination / "staged-skill").exists()
    assert [result.status for result in records] == [CheckStatus.PASS, CheckStatus.PASS]


def test_c2_cli_create_explicit_publish_creates_exact_candidate(tmp_path: Path) -> None:
    candidate = _copy(CREATE_FIXTURE, tmp_path / "codex")
    destination = tmp_path / "destination"
    destination.mkdir()
    decision = _json_decision(tmp_path / "decision.json", Intent.CREATE)
    behavior = [sys.executable, "scripts/check.py", "--topic", "release"]
    regression = [sys.executable, "scripts/check.py", "--topic", "upgrade"]

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "Create a release checklist Skill",
            "--intent",
            "CREATE",
            "--decision",
            str(decision),
            "--candidate",
            str(candidate),
            "--authorize-modify",
            "--target-parent",
            str(destination),
            "--confirmed-digest",
            digest_tree(candidate),
            "--semantic-rationale",
            "Codex verified the complete candidate against the requested workflow",
            "--behavior-command-json",
            json.dumps(behavior),
            "--regression-command-json",
            json.dumps(regression),
            "--publish",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    published = destination / "candidate-skill"
    assert published.is_dir()
    assert digest_tree(published) == digest_tree(candidate)
    assert payload["gate_result"]["publish_authorized"] is True
    assert payload["publication_result"]["status"] == "PUBLISHED"
    assert payload["publication_result"]["backup_path"] is None
    assert payload["publication_result"]["candidate_digest"] == digest_tree(candidate)
    assert payload["publication_result"]["published_digest"] == digest_tree(candidate)
    checks = {item["check_id"]: item for item in payload["evidence"]}
    assert checks["behavioral.create"]["status"] == "PASS"
    assert checks["B07"]["status"] == "PASS"
    assert not (destination / "staged-skill").exists()


def test_audit_only_rejects_publish_request_without_staging_or_backup(tmp_path: Path) -> None:
    source = _copy(SOURCE_FIXTURE, tmp_path / "source")
    before = digest_tree(source)
    outcome = PipelineOrchestrator().run(
        EngineeringRequest(
            "Audit the source Skill",
            Intent.AUDIT_ONLY,
            codex_decision(Intent.AUDIT_ONLY),
            source,
            None,
            (),
            False,
            source.parent,
            semantic_confirmation=confirmation(source),
            publish_requested=True,
        )
    )

    assert outcome.gate_result.verdict.value == "PASS"
    assert outcome.gate_result.publish_authorized is False
    assert outcome.publication_session is None
    with pytest.raises(ValueError, match="no publication-ready workspace"):
        publish(outcome)
    assert digest_tree(source) == before
    assert not list(source.parent.glob(".skill-engineering-*"))
    assert not list(source.parent.glob("*.backup"))
    assert any(item.check_id.startswith("rule-signal.") for item in outcome.evidence)


def test_cli_audit_only_with_publish_flag_still_cannot_publish(tmp_path: Path) -> None:
    source = _copy(SOURCE_FIXTURE, tmp_path / "source")
    before = digest_tree(source)
    decision = codex_decision(Intent.AUDIT_ONLY)
    payload = asdict(decision)
    for key, value in tuple(payload.items()):
        if hasattr(value, "value"):
            payload[key] = value.value
        elif isinstance(value, tuple):
            payload[key] = [item.value if hasattr(item, "value") else item for item in value]
    decision_path = tmp_path / "audit-decision.json"
    decision_path.write_text(json.dumps(payload), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "Audit the source Skill",
            "--intent",
            "AUDIT_ONLY",
            "--decision",
            str(decision_path),
            "--source",
            str(source),
            "--target-parent",
            str(source.parent),
            "--confirmed-digest",
            before,
            "--semantic-rationale",
            "Codex verified the audited source",
            "--publish",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 1
    assert "no publication-ready workspace" in json.loads(completed.stdout)["error"]
    assert digest_tree(source) == before
    assert not list(source.parent.glob(".skill-engineering-*"))
    assert not list(source.parent.glob("*.backup"))


def test_missing_codex_semantic_confirmation_blocks_even_with_passing_provider(tmp_path: Path) -> None:
    @dataclass
    class PassingProvider:
        descriptor: ProviderDescriptor

        def invoke(self, capability: str, request: dict[str, object]) -> ProviderResult:
            return ProviderResult(
                self.descriptor.provider_id,
                capability,
                ProviderStatus.AVAILABLE,
                (),
                (),
                ("provider analysis completed",),
                (),
                False,
            )

    parent, source, candidate = _modify_workspace(tmp_path)
    descriptor = ProviderDescriptor(
        "e2e.provider",
        "test/provider",
        "1",
        AUDIT_SKILL,
        ProviderStatus.AVAILABLE,
        "e2e",
        (),
        None,
    )
    gateway = ProviderGateway([PassingProvider(descriptor)])
    with pytest.raises(PipelineBlockedError) as caught:
        PipelineOrchestrator(provider_gateway=gateway).run(
            _modify_request(
                source,
                candidate,
                parent,
                publish_requested=True,
                semantic=False,
            )
        )

    assert caught.value.gate_result.semantic_confirmed is False
    assert caught.value.gate_result.publish_authorized is False
    assert any(finding.startswith("B12") for finding in caught.value.gate_result.blocking_findings)


def test_missing_codex_governance_action_blocks_signal_without_heuristic_action(tmp_path: Path) -> None:
    parent, source, candidate = _modify_workspace(tmp_path)
    skill_md = candidate / "SKILL.md"
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8")
        + "\nMust preserve output stability.\nMust preserve output stability.\n",
        encoding="utf-8",
    )
    with pytest.raises(PipelineBlockedError) as caught:
        PipelineOrchestrator().run(
            _modify_request(source, candidate, parent, publish_requested=True)
        )

    signal = next(item for item in caught.value.evidence if item.check_id.startswith("rule-signal.exact-"))
    coverage = next(item for item in caught.value.evidence if item.check_id == "governance.coverage")
    assert signal.source == "rule_bloat_detector" and signal.required is False
    assert coverage.status is CheckStatus.FAIL and coverage.required is True
    assert "missing Codex governance decisions" in coverage.evidence[0]


def test_engine_rejects_non_codex_decision_and_missing_candidate(tmp_path: Path) -> None:
    parent, source, candidate = _modify_workspace(tmp_path)
    request = _modify_request(source, candidate, parent, publish_requested=False)
    forged = replace(request.decision, decided_by="ENGINE")
    with pytest.raises(ValueError, match="authored by Codex"):
        PipelineOrchestrator().run(replace(request, decision=forged))
    with pytest.raises(ValueError, match="complete candidate"):
        PipelineOrchestrator().run(replace(request, candidate=None))


def test_engine_rejects_incomplete_mechanism_decision_without_inference(tmp_path: Path) -> None:
    parent, source, candidate = _modify_workspace(tmp_path)
    request = _modify_request(source, candidate, parent, publish_requested=False)
    incomplete = replace(request.decision, rejected_mechanisms=())
    assert set(incomplete.selected_mechanisms) != set(ALL_MECHANISMS)
    with pytest.raises(ValueError, match="select or reject every known mechanism"):
        PipelineOrchestrator().run(replace(request, decision=incomplete))
