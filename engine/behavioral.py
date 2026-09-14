"""Runner-neutral behavioral evaluation records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from engine.contracts import validate_contract
from engine.models import CheckStatus


@dataclass(frozen=True)
class BehavioralScenario:
    scenario_id: str
    task: str
    expected_behavior: str
    required: bool
    inputs: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {**asdict(self), "inputs": list(self.inputs), "limitations": list(self.limitations)}


@dataclass(frozen=True)
class BehavioralResult:
    scenario_id: str
    status: CheckStatus
    observations: tuple[str, ...]
    evidence: tuple[str, ...]
    limitation: str | None
    runner_id: str | None = None
    artifact_digest: str | None = None
    observed_assertions: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["observations"] = list(self.observations)
        payload["evidence"] = list(self.evidence)
        payload["observed_assertions"] = list(self.observed_assertions)
        return payload


class BehavioralRunner(Protocol):
    def run(self, scenario: BehavioralScenario, artifact_root: Path) -> BehavioralResult: ...


def _validate_scenario(scenario: BehavioralScenario) -> None:
    validate_contract("behavioral-scenario", scenario.to_payload())


def _validate_result(result: BehavioralResult) -> None:
    if not isinstance(result.status, CheckStatus):
        raise ValueError("behavioral result status must be a CheckStatus")
    validate_contract("behavioral-result", result.to_payload())


def evaluate_behavior(
    scenario: BehavioralScenario, runner: BehavioralRunner | None, root: Path
) -> BehavioralResult:
    """Evaluate a scenario, explicitly recording absent runners as NOT_EXECUTED."""
    _validate_scenario(scenario)
    if runner is None:
        result = BehavioralResult(
            scenario_id=scenario.scenario_id,
            status=CheckStatus.NOT_EXECUTED,
            observations=(),
            evidence=("No behavioral runner is available.",),
            limitation="No behavioral runner is available.",
        )
        _validate_result(result)
        return result
    try:
        result = runner.run(scenario, root)
    except Exception as exc:
        result = BehavioralResult(
            scenario_id=scenario.scenario_id,
            status=CheckStatus.ERROR,
            observations=(),
            evidence=(f"Behavioral runner error: {exc}",),
            limitation="Behavioral runner failed.",
        )
    if not isinstance(result, BehavioralResult):
        raise TypeError("behavioral runner must return BehavioralResult")
    _validate_result(result)
    if result.scenario_id != scenario.scenario_id:
        raise ValueError("behavioral result scenario_id does not match scenario")
    return result
