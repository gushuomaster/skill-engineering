from pathlib import Path

from engine.behavioral import BehavioralScenario, evaluate_behavior
from engine.models import CheckStatus


def scenario() -> BehavioralScenario:
    return BehavioralScenario(
        scenario_id="routing",
        task="Route a valid request.",
        expected_behavior="Uses the intended skill.",
        required=False,
        inputs=("request",),
        limitations=(),
    )


def test_missing_behavioral_runner_is_not_executed(tmp_path: Path) -> None:
    result = evaluate_behavior(scenario(), runner=None, root=tmp_path)
    assert result.status is CheckStatus.NOT_EXECUTED
    assert result.limitation
    assert result.runner_id is None


class Runner:
    def run(self, scenario: BehavioralScenario, artifact_root: Path):
        from engine.behavioral import BehavioralResult

        return BehavioralResult(
            scenario_id=scenario.scenario_id,
            status=CheckStatus.PASS,
            observations=("routed",),
            evidence=("runner assertion",),
            limitation=None,
            runner_id="local-runner",
            artifact_digest="sha256:abc",
            observed_assertions=("expected behavior observed",),
        )


def test_behavioral_runner_metadata_is_retained(tmp_path: Path) -> None:
    result = evaluate_behavior(scenario(), runner=Runner(), root=tmp_path)
    assert result.status is CheckStatus.PASS
    assert result.runner_id == "local-runner"
    assert result.artifact_digest == "sha256:abc"
    assert result.observed_assertions == ("expected behavior observed",)
