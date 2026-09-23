from __future__ import annotations

import json
import os
import sys
from pathlib import Path
import re
import subprocess
import textwrap
import time

import pytest

from engine.capabilities import SKILL_CREATION_OR_RESTRUCTURE
from engine.host_adapters import _build_text_snapshot, build_codex_skill_adapter
from engine.models import (
    CapabilityStatus, FallbackEquivalence, GateVerdict, Intent, ProviderExecution,
    ProviderStatus,
)
from engine.orchestrator import PipelineBlockedError, PipelineOrchestrator
from engine.providers import ProviderGateway
from engine.rule_governance import GovernanceAction, GovernanceDecision
from tests.support import codex_decision, confirmation, copy_candidate


ROOT = Path(__file__).resolve().parents[2]


class RecordingCodexExecutor:
    def __init__(self, *, finding: str | None = None, invalid: bool = False, crash: bool = False):
        self.finding = finding
        self.invalid = invalid
        self.crash = crash
        self.calls: list[tuple[list[str], str]] = []

    def __call__(self, command, *, input, **kwargs):
        self.calls.append((list(command), input))
        if self.crash:
            raise RuntimeError("host process crashed")
        output = Path(command[command.index("--output-last-message") + 1])
        if self.invalid:
            payload = {"provider_id": "openai.skill-creator"}
        else:
            nonce = re.search(r"invocation_nonce=([0-9a-f]+)", input).group(1)
            digest = re.search(r"provider_skill_digest=([0-9a-f]+)", input).group(1)
            payload = {
                "provider_id": "openai.skill-creator",
                "capability": "CREATE_CANDIDATE",
                "provider_status": "AVAILABLE",
                "findings": [self.finding] if self.finding else [],
                "candidate_changes": [],
                "evidence": [
                    "provider_skill=skill-creator",
                    f"provider_skill_digest={digest}",
                    f"invocation_nonce={nonce}",
                    "SKILL.md:1 provider inspection completed",
                ],
                "limitations": [],
                "fallback_used": False,
            }
        output.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


def _installed_adapter(tmp_path: Path, executor: RecordingCodexExecutor):
    skills_root = tmp_path / "installed-skills"
    skill = skills_root / ".system" / "skill-creator"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: skill-creator\ndescription: Create or update Skills.\n---\n",
        encoding="utf-8",
    )
    return build_codex_skill_adapter(
        "skill-creator",
        config_path=ROOT / "config" / "providers.yaml",
        schema_path=ROOT / "schemas" / "provider-result.schema.json",
        roots=(skills_root,), executor=executor,
    )


def _governance(inspection) -> tuple[GovernanceDecision, ...]:
    return tuple(
        GovernanceDecision(
            item.finding_id, GovernanceAction.KEEP, "Reviewed for host Provider test.",
            item.evidence_refs, "SKILL.md", False, item.signals, item.limitations,
        )
        for item in inspection.findings if item.confidence > 0
    )


def _validate_modify(tmp_path: Path, executor: RecordingCodexExecutor, *, levels=None):
    source = tmp_path / "source" / "demo"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Execute a deterministic test workflow.\n---\n\n"
        "Run the requested workflow.\n",
        encoding="utf-8",
    )
    candidate_parent = tmp_path / "candidate"
    candidate_parent.mkdir()
    candidate = copy_candidate(source, candidate_parent)
    destination = tmp_path / "destination"
    destination.mkdir()
    adapter = _installed_adapter(tmp_path, executor)
    orchestrator = PipelineOrchestrator(
        provider_gateway=ProviderGateway([adapter]), fallback_equivalences=levels,
    )
    inspection = orchestrator.inspect(Intent.MODIFY, source)
    validation = orchestrator.validate(
        inspection, codex_decision(Intent.MODIFY), _governance(inspection),
        candidate=candidate, target_parent=destination, authorized_to_modify=True,
        apply_requested=True,
    )
    return orchestrator, inspection, validation


def test_production_host_adapter_executes_selected_provider_and_reaches_gate(
    tmp_path: Path,
) -> None:
    executor = RecordingCodexExecutor()
    orchestrator, inspection, validation = _validate_modify(tmp_path, executor)
    outcome = orchestrator.confirm(validation, confirmation(validation.artifact_path))

    provider = next(item for item in inspection.provider_evidence if item.provider_id == "openai.skill-creator")
    capability = next(
        item for item in validation.capability_preflight
        if item.capability == SKILL_CREATION_OR_RESTRUCTURE
    )
    execution = next(
        item for item in validation.deterministic_evidence
        if item.check_id == "capability.skill_creation_or_restructure"
    )
    assert provider.provider_available is True
    assert provider.provider_execution is ProviderExecution.EXECUTED
    assert provider.fallback_used is False
    assert provider.evidence_valid is True
    assert capability.status is CapabilityStatus.READY
    assert capability.selected_provider == "openai.skill-creator"
    assert execution.status.value == "PASS"
    assert outcome.gate_result.verdict is GateVerdict.PASS
    command, prompt = executor.calls[0]
    assert command[:2] == ["codex", "exec"]
    assert "--sandbox" in command and "read-only" in command
    assert "Use $skill-creator" in prompt


def test_production_host_adapter_finding_is_required_gate_failure(tmp_path: Path) -> None:
    executor = RecordingCodexExecutor(finding="SKILL.md:5 trigger is ambiguous")
    orchestrator, _, validation = _validate_modify(tmp_path, executor)

    with pytest.raises(PipelineBlockedError) as caught:
        orchestrator.confirm(validation, confirmation(validation.artifact_path))

    assert any(
        item.source == "provider:openai.skill-creator"
        and item.required and item.status.value == "FAIL"
        for item in validation.deterministic_evidence
    )
    assert caught.value.gate_result.verdict is GateVerdict.FAIL
    assert caught.value.gate_result.apply_authorized is False


@pytest.mark.parametrize("mode", ["invalid", "crash"])
def test_failed_host_provider_uses_full_fallback(tmp_path: Path, mode: str) -> None:
    executor = RecordingCodexExecutor(invalid=mode == "invalid", crash=mode == "crash")
    orchestrator, inspection, validation = _validate_modify(tmp_path, executor)
    outcome = orchestrator.confirm(validation, confirmation(validation.artifact_path))

    provider = next(item for item in inspection.provider_evidence if item.capability == "CREATE_CANDIDATE")
    capability = next(
        item for item in validation.capability_preflight
        if item.capability == SKILL_CREATION_OR_RESTRUCTURE
    )
    assert provider.provider_available is True
    assert provider.provider_execution is ProviderExecution.FAILED
    assert provider.evidence_valid is False
    assert capability.status is CapabilityStatus.FALLBACK
    assert capability.selected_provider is None
    assert capability.fallback_equivalence is FallbackEquivalence.FULL
    assert any(
        item.check_id == "capability.skill_creation_or_restructure"
        and item.source == "internal.capability-fallback"
        for item in validation.deterministic_evidence
    )
    assert outcome.gate_result.verdict is GateVerdict.PASS


def test_crashed_host_provider_with_none_fallback_is_incomplete(tmp_path: Path) -> None:
    executor = RecordingCodexExecutor(crash=True)
    orchestrator, _, validation = _validate_modify(
        tmp_path, executor,
        levels={SKILL_CREATION_OR_RESTRUCTURE: FallbackEquivalence.NONE},
    )

    with pytest.raises(PipelineBlockedError) as caught:
        orchestrator.confirm(validation, confirmation(validation.artifact_path))

    capability = next(
        item for item in validation.capability_preflight
        if item.capability == SKILL_CREATION_OR_RESTRUCTURE
    )
    assert capability.status is CapabilityStatus.BLOCKED
    assert caught.value.gate_result.verdict is GateVerdict.INCOMPLETE
    assert caught.value.gate_result.apply_authorized is False


def test_configured_but_missing_optional_provider_uses_direct_core(tmp_path: Path) -> None:
    missing_root = tmp_path / "empty-skills"
    missing_root.mkdir()
    adapter = build_codex_skill_adapter(
        "skill-creator",
        config_path=ROOT / "config" / "providers.yaml",
        schema_path=ROOT / "schemas" / "provider-result.schema.json",
        roots=(missing_root,),
    )
    assert adapter.descriptor.availability is ProviderStatus.UNAVAILABLE

    source = tmp_path / "source" / "demo"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Execute a deterministic test workflow.\n---\n\n"
        "Run the requested workflow.\n",
        encoding="utf-8",
    )
    orchestrator = PipelineOrchestrator(provider_gateway=ProviderGateway([adapter]))
    inspection = orchestrator.inspect(Intent.MODIFY, source)
    provider = next(
        item for item in inspection.provider_evidence
        if item.capability == "CREATE_CANDIDATE"
    )
    capability = next(
        item for item in inspection.capability_preflight
        if item.capability == SKILL_CREATION_OR_RESTRUCTURE
    )

    assert provider.provider_available is False
    assert provider.provider_execution is ProviderExecution.NOT_STARTED
    assert provider.evidence_valid is False
    assert provider.fallback_used is False
    assert "installed Skill not found: skill-creator" in "; ".join(provider.limitations)
    assert capability.status is CapabilityStatus.READY
    assert capability.selected_provider == "internal.core"
    assert capability.fallback_equivalence is FallbackEquivalence.NONE


def test_default_host_command_isolates_user_codex_configuration(
    tmp_path: Path,
) -> None:
    adapter = _installed_adapter(tmp_path, RecordingCodexExecutor())
    command = adapter._command(tmp_path, tmp_path / "provider-result.json")

    assert "--ignore-user-config" in command
    assert "model_reasoning_effort=\"low\"" in command


def test_structured_output_completion_does_not_wait_for_child_cleanup(
    tmp_path: Path,
) -> None:
    script = tmp_path / "slow-provider.py"
    script.write_text(textwrap.dedent("""
        import json
        import sys
        import time
        output = sys.argv[1]
        json.dump({
            "provider_id": "openai.skill-creator",
            "capability": "CREATE_CANDIDATE",
            "provider_status": "AVAILABLE",
            "findings": [],
            "candidate_changes": [],
            "evidence": [
                "provider_skill=skill-creator",
                "provider_skill_digest=placeholder",
                "invocation_nonce=placeholder",
            ],
            "limitations": [],
            "fallback_used": False,
        }, open(output, "w", encoding="utf-8"))
        time.sleep(30)
    """), encoding="utf-8")
    adapter = _installed_adapter(tmp_path, RecordingCodexExecutor())
    adapter._executor = subprocess.run
    adapter.executable = sys.executable
    adapter._command = lambda target, output: [sys.executable, str(script), str(output)]

    with pytest.raises(ValueError, match="execution markers"):
        adapter.invoke("CREATE_CANDIDATE", {"target_path": str(tmp_path)})

    assert adapter.last_timing is not None
    assert adapter.last_timing.structured_output_completed is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object regression")
def test_provider_child_exits_when_host_process_is_killed(tmp_path: Path) -> None:
    child_pid_file = tmp_path / "child.pid"
    child_script = tmp_path / "slow-child.py"
    child_script.write_text(
        textwrap.dedent(
            """
            import os
            import sys
            import time

            with open(sys.argv[1], "w", encoding="utf-8") as marker:
                marker.write(str(os.getpid()))
            time.sleep(60)
            """
        ),
        encoding="utf-8",
    )
    helper_script = tmp_path / "provider-host.py"
    helper_script.write_text(
        textwrap.dedent(
            f"""
            import sys
            import time
            from pathlib import Path

            from engine.host_adapters import CodexSkillProviderAdapter, ProviderExecutionTiming

            adapter = CodexSkillProviderAdapter.__new__(CodexSkillProviderAdapter)
            adapter.timeout_seconds = 60
            adapter._run_subprocess(
                [sys.executable, {str(child_script)!r}, {str(child_pid_file)!r}],
                "",
                ProviderExecutionTiming(requested_at=time.perf_counter()),
                Path({str(tmp_path / 'unused-output.json')!r}),
            )
            """
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        (str(ROOT), env.get("PYTHONPATH", ""))
    ).rstrip(os.pathsep)
    helper = subprocess.Popen([sys.executable, str(helper_script)], env=env)
    child_pid: int | None = None
    child_handle = None
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not child_pid_file.is_file():
            if helper.poll() is not None:
                raise AssertionError(f"provider host exited early: {helper.returncode}")
            time.sleep(0.05)
        assert child_pid_file.is_file(), "provider child did not start"
        child_pid = int(child_pid_file.read_text(encoding="utf-8"))

        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        child_handle = kernel32.OpenProcess(0x00100000, False, child_pid)
        assert child_handle, f"could not open provider child process {child_pid}"

        helper.kill()
        helper.wait(timeout=5)

        wait_result = kernel32.WaitForSingleObject(child_handle, 5_000)
        assert wait_result == 0, "provider child survived host termination"
    finally:
        if helper.poll() is None:
            helper.kill()
            helper.wait(timeout=5)
        if child_handle:
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            if kernel32.WaitForSingleObject(child_handle, 0) != 0 and child_pid:
                subprocess.run(
                    ["taskkill", "/PID", str(child_pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            kernel32.CloseHandle(child_handle)


def test_snapshot_excludes_build_cache_and_keeps_declared_dependency_graph(
    tmp_path: Path,
) -> None:
    (tmp_path / "SKILL.md").write_text("Use `references/contract.md`.", encoding="utf-8")
    (tmp_path / "references").mkdir()
    (tmp_path / "references" / "contract.md").write_text("contract", encoding="utf-8")
    (tmp_path / "scripts" / "demo").mkdir(parents=True)
    (tmp_path / "scripts" / "demo" / "cli.py").write_text(
        "from .worker import run\n", encoding="utf-8"
    )
    (tmp_path / "scripts" / "demo" / "worker.py").write_text(
        "def run(): return 'report.txt'\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\ndemo = "demo.cli:run"\n', encoding="utf-8"
    )
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "generated.py").write_text("noise = True\n", encoding="utf-8")

    snapshot, profile = _build_text_snapshot(tmp_path, max_bytes=100_000)

    assert "FILE: references/contract.md" in snapshot
    assert "FILE: scripts/demo/cli.py" in snapshot
    assert "FILE: scripts/demo/worker.py" in snapshot
    assert "build/generated.py" not in snapshot
    assert profile["required_complete"] == 1


def test_snapshot_prioritizes_behavioral_tests_for_entrypoint_dependencies(
    tmp_path: Path,
) -> None:
    (tmp_path / "SKILL.md").write_text("Demo provider target.", encoding="utf-8")
    (tmp_path / "scripts" / "demo").mkdir(parents=True)
    (tmp_path / "scripts" / "demo" / "cli.py").write_text(
        "from .workflow import run\n", encoding="utf-8"
    )
    (tmp_path / "scripts" / "demo" / "workflow.py").write_text(
        "def run(): return 'report.txt'\n", encoding="utf-8"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\ndemo = "demo.cli:run"\n', encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "a_unrelated.py").write_text(
        "noise = " + repr("x" * 1_200) + "\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "z_workflow.py").write_text(
        "from demo.workflow import run\n\ndef test_run(): assert run() == 'report.txt'\n",
        encoding="utf-8",
    )

    snapshot, profile = _build_text_snapshot(tmp_path, max_bytes=1_500)

    assert "FILE: tests/z_workflow.py" in snapshot
    assert "FILE: tests/a_unrelated.py" not in snapshot
    assert profile["required_complete"] == 1


def test_real_document_skill_required_snapshot_fits_budget() -> None:
    target = Path(
        r"D:\project\skills\test2\.hypercode\skills\gjb438c-document-engineering"
    )
    if not target.is_dir():
        pytest.skip("real document-engineering fixture is not installed")

    _, profile = _build_text_snapshot(target, max_bytes=360_000)

    assert profile["required_complete"] == 1


def test_incomplete_required_snapshot_fails_before_provider_invocation(
    tmp_path: Path,
) -> None:
    executor = RecordingCodexExecutor()
    adapter = _installed_adapter(tmp_path, executor)
    adapter.snapshot_max_bytes = 1
    target = tmp_path / "target"
    target.mkdir()
    (target / "SKILL.md").write_text("required evidence", encoding="utf-8")

    with pytest.raises(ValueError, match="required evidence coverage is incomplete"):
        adapter.invoke("CREATE_CANDIDATE", {"target_path": str(target)})

    assert executor.calls == []
