"""User-visible preflight for Codex-selected standard Skill dependencies."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from engine.host_adapters import discover_skill_path
from engine.models import (
    CheckResult,
    CheckStatus,
    LifecycleState,
    StandardDependencyAssessment,
    StandardDependencyStatus,
    StandardSkillRequirement,
)


class MissingStandardDependencyError(RuntimeError):
    """Raised before work continues when the user has not chosen limited mode."""

    def __init__(self, missing: tuple[StandardDependencyAssessment, ...]) -> None:
        self.missing = missing
        details = "; ".join(
            f"{item.skill_name}: {item.responsibility}; gap={item.coverage_gap}"
            for item in missing
        )
        super().__init__(
            "required standard Skill missing; ask the user to install/connect it or "
            f"explicitly continue with a limited audit: {details}"
        )


def assess_standard_dependencies(
    requirements: tuple[StandardSkillRequirement, ...],
    *,
    roots: Sequence[Path] | None = None,
) -> tuple[StandardDependencyAssessment, ...]:
    """Discover only the dependencies Codex has semantically selected as required."""
    assessments: list[StandardDependencyAssessment] = []
    for item in requirements:
        try:
            path = discover_skill_path(item.skill_name, roots=roots)
        except FileNotFoundError:
            assessments.append(StandardDependencyAssessment(
                item.skill_name, item.responsibility, item.coverage_gap,
                StandardDependencyStatus.MISSING, None,
            ))
        else:
            assessments.append(StandardDependencyAssessment(
                item.skill_name, item.responsibility, item.coverage_gap,
                StandardDependencyStatus.AVAILABLE, str(path),
            ))
    return tuple(assessments)


def dependency_evidence(
    assessments: tuple[StandardDependencyAssessment, ...],
    subject: str,
    *,
    continue_limited: bool,
) -> tuple[CheckResult, ...]:
    """Make declined dependencies Gate-visible so limited work can never be FULL PASS."""
    results: list[CheckResult] = []
    for item in assessments:
        if item.status is StandardDependencyStatus.AVAILABLE:
            continue
        status = (
            StandardDependencyStatus.DECLINED
            if continue_limited else StandardDependencyStatus.MISSING
        )
        results.append(CheckResult(
            f"standard-dependency.{item.skill_name}",
            "environment.standard-toolchain",
            subject,
            True,
            CheckStatus.NOT_EXECUTED,
            True,
            True,
            1.0,
            (
                f"dependency_status={status.value}",
                f"responsibility={item.responsibility}",
                f"coverage_gap={item.coverage_gap}",
                "result_scope=LIMITED_AUDIT",
            ),
            LifecycleState.VALIDATED_PENDING_CONFIRMATION,
            item.skill_name,
        ))
    return tuple(results)
