"""Safe execution of explicitly declared deliverable-contract commands."""
from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Iterable

from engine.models import CheckResult, CheckStatus, LifecycleState


def run_contract_checks(
    artifact: Path,
    commands: Iterable[str],
    *,
    expected_artifacts: Iterable[str] = (),
    timeout_seconds: int = 300,
) -> CheckResult:
    """Run only declared commands in an artifact directory.

    Commands are tokenized without a shell. Relative expected artifacts must
    remain inside the artifact root; no command is guessed when none is given.
    """
    command_list = tuple(item for item in commands if isinstance(item, str) and item.strip())
    subject = artifact.name
    if not command_list:
        return CheckResult(
            "contract.behavior", "contract.runner", subject, True,
            CheckStatus.NOT_EXECUTED, True, True, 1.0,
            ("OUTPUT_CONTRACT_COMMAND_NOT_DECLARED",),
            LifecycleState.VALIDATED_PENDING_CONFIRMATION, str(artifact),
        )
    evidence: list[str] = []
    for command in command_list:
        try:
            argv = shlex.split(command, posix=os.name != "nt")
            if not argv:
                raise ValueError("empty command")
            completed = subprocess.run(
                argv, cwd=artifact, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout_seconds,
                check=False,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            return CheckResult(
                "contract.behavior", "contract.runner", subject, True,
                CheckStatus.NOT_EXECUTED, True, True, 1.0,
                (f"OUTPUT_CONTRACT_COMMAND_FAILED:{command}:{exc}",),
                LifecycleState.VALIDATED_PENDING_CONFIRMATION, str(artifact),
            )
        evidence.append(f"command={command}; exit_code={completed.returncode}")
        if completed.returncode != 0:
            return CheckResult(
                "contract.behavior", "contract.runner", subject, True,
                CheckStatus.FAIL, True, True, 1.0, tuple(evidence),
                LifecycleState.VALIDATED_PENDING_CONFIRMATION, str(artifact),
            )
    for relative in expected_artifacts:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or not (artifact / path).is_file():
            return CheckResult(
                "contract.behavior", "contract.runner", subject, True,
                CheckStatus.FAIL, True, True, 1.0,
                tuple((*evidence, f"DECLARED_OUTPUT_NOT_GENERATED:{relative}")),
                LifecycleState.VALIDATED_PENDING_CONFIRMATION, str(artifact),
            )
        evidence.append(f"artifact={relative}")
    return CheckResult(
        "contract.behavior", "contract.runner", subject, True,
        CheckStatus.PASS, True, True, 1.0, tuple(evidence),
        LifecycleState.VALIDATED_PENDING_CONFIRMATION, str(artifact),
    )


__all__ = ["run_contract_checks"]
