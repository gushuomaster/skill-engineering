from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from engine.models import (
    ArtifactAssessment,
    AuditExecution,
    CheckResult,
    CheckStatus,
    GateOutcome,
    GateVerdict,
    Intent,
    LifecycleState,
)
from engine.orchestrator import EngineeringRequest, PipelineOrchestrator
from tests.support import codex_decision, confirmation


FIXTURE = Path(__file__).parents[1] / "fixtures" / "skills" / "minimal-valid"


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "source" / "minimal-valid"
    shutil.copytree(FIXTURE, source)
    (source / "references").mkdir()
    (source / "references" / "behavior.md").write_text("baseline\n", encoding="utf-8")
    return source


def _check(artifact: Path, status: CheckStatus = CheckStatus.PASS) -> CheckResult:
    exit_code = 0 if status is CheckStatus.PASS else 7
    return CheckResult(
        "behavioral.audit",
        "cli.command",
        str(artifact),
        True,
        status,
        True,
        True,
        1.0,
        (
            'command=["python", "probe.py"]',
            f"exit_code={exit_code}",
            "stdout=probe stdout",
            "stderr=probe stderr",
        ),
        LifecycleState.VALIDATED,
        str(artifact),
    )


def _probe(source: Path, artifact: Path, code: str, expected: int = 0) -> CheckResult:
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code, str(source)],
        cwd=artifact,
        text=True,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == expected
    return _check(artifact, CheckStatus.PASS if expected == 0 else CheckStatus.FAIL)


def _run(source: Path, tmp_path: Path, runner):
    return PipelineOrchestrator().run(
        EngineeringRequest(
            requirement="audit only immutability probe",
            intent=Intent.AUDIT_ONLY,
            decision=codex_decision(Intent.AUDIT_ONLY),
            source=source,
            candidate=None,
            failure_evidence=(),
            authorized_to_modify=False,
            target_parent=tmp_path,
            semantic_confirmation=confirmation(source),
            behavioral_runner=runner,
        )
    )


def _assert_source_change_invalidates(outcome, *, added=(), modified=(), deleted=()) -> None:
    assert outcome.audit_execution is AuditExecution.INCOMPLETE
    assert outcome.artifact_assessment is ArtifactAssessment.UNKNOWN
    assert outcome.gate_result.verdict is GateVerdict.INCOMPLETE
    assert outcome.gate_result.outcome is not GateOutcome.UNCHANGED_VALIDATED
    assert outcome.gate_result.semantic_confirmed is False
    assert outcome.gate_result.apply_authorized is False
    assert outcome.workspace_diff.added == added
    assert outcome.workspace_diff.modified == modified
    assert outcome.workspace_diff.deleted == deleted


def test_a1_added_source_file_invalidates_audit(tmp_path: Path) -> None:
    source = _source(tmp_path)

    def runner(artifact: Path) -> CheckResult:
        return _probe(
            source, artifact,
            "from pathlib import Path; import sys; (Path(sys.argv[1]) / 'runner-write.txt').write_text('written', encoding='utf-8')",
        )

    outcome = _run(source, tmp_path, runner)
    _assert_source_change_invalidates(outcome, added=("runner-write.txt",))


def test_a2_modified_source_file_invalidates_audit(tmp_path: Path) -> None:
    source = _source(tmp_path)

    def runner(artifact: Path) -> CheckResult:
        return _probe(
            source, artifact,
            "from pathlib import Path; import sys; (Path(sys.argv[1]) / 'SKILL.md').write_text('changed', encoding='utf-8')",
        )

    outcome = _run(source, tmp_path, runner)
    _assert_source_change_invalidates(outcome, modified=("SKILL.md",))


def test_a3_deleted_source_file_invalidates_audit(tmp_path: Path) -> None:
    source = _source(tmp_path)

    def runner(artifact: Path) -> CheckResult:
        return _probe(
            source, artifact,
            "from pathlib import Path; import sys; (Path(sys.argv[1]) / 'references' / 'behavior.md').unlink()",
        )

    outcome = _run(source, tmp_path, runner)
    _assert_source_change_invalidates(outcome, deleted=("references/behavior.md",))


def test_a4_renamed_source_file_invalidates_audit(tmp_path: Path) -> None:
    source = _source(tmp_path)

    def runner(artifact: Path) -> CheckResult:
        return _probe(
            source, artifact,
            "from pathlib import Path; import sys; p=Path(sys.argv[1])/'references'; (p/'behavior.md').rename(p/'renamed.md')",
        )

    outcome = _run(source, tmp_path, runner)
    _assert_source_change_invalidates(
        outcome,
        added=("references/renamed.md",),
        deleted=("references/behavior.md",),
    )


def test_a5_nested_source_write_invalidates_audit(tmp_path: Path) -> None:
    source = _source(tmp_path)

    def runner(artifact: Path) -> CheckResult:
        return _probe(
            source, artifact,
            "from pathlib import Path; import sys; p=Path(sys.argv[1])/'deep'/'nested'; p.mkdir(parents=True); (p/'write.txt').write_text('written', encoding='utf-8')",
        )

    outcome = _run(source, tmp_path, runner)
    _assert_source_change_invalidates(outcome, added=("deep/nested/write.txt",))


def test_a6_failed_command_without_source_change_is_incomplete(tmp_path: Path) -> None:
    source = _source(tmp_path)
    outcome = _run(
        source,
        tmp_path,
        lambda artifact: _probe(source, artifact, "raise SystemExit(7)", expected=7),
    )

    assert outcome.audit_execution is AuditExecution.INCOMPLETE
    assert outcome.artifact_assessment is ArtifactAssessment.UNKNOWN
    assert outcome.gate_result.verdict is GateVerdict.INCOMPLETE
    assert outcome.gate_result.semantic_confirmed is True
    assert outcome.workspace_diff.added == ()
    assert outcome.workspace_diff.modified == ()
    assert outcome.workspace_diff.deleted == ()
    command = next(item for item in outcome.deterministic_evidence if item.source == "cli.command")
    assert command.evidence == (
        'command=["python", "probe.py"]',
        "exit_code=7",
        "stdout=probe stdout",
        "stderr=probe stderr",
    )


def test_a7_concurrent_external_source_change_invalidates_without_restore(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)

    def runner(artifact: Path) -> CheckResult:
        return _probe(
            source, artifact,
            "from pathlib import Path; import sys; (Path(sys.argv[1])/'external-change.txt').write_text('external', encoding='utf-8')",
        )

    outcome = _run(source, tmp_path, runner)

    _assert_source_change_invalidates(outcome, added=("external-change.txt",))
    assert (source / "external-change.txt").read_text(encoding="utf-8") == "external"
    assert any(
        "origin is not attributed" in detail
        for result in outcome.deterministic_evidence
        for detail in result.evidence
    )


def test_audit_runner_receives_isolated_snapshot(tmp_path: Path) -> None:
    source = _source(tmp_path)
    observed: list[Path] = []

    def runner(artifact: Path) -> CheckResult:
        observed.append(artifact)
        return _probe(
            artifact, artifact,
            "from pathlib import Path; import sys; (Path(sys.argv[1])/'snapshot-only.txt').write_text('isolated', encoding='utf-8')",
        )

    outcome = _run(source, tmp_path, runner)

    assert observed and observed[0].resolve() != source.resolve()
    assert not (source / "snapshot-only.txt").exists()
    assert outcome.audit_execution is AuditExecution.COMPLETE
