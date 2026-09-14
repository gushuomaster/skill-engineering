from pathlib import Path

import pytest

from engine.models import CheckStatus, LifecycleState
from engine.regression import DuplicateRegressionFamily, RegressionCase, load_case, run_regressions


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "regression"


class PassingRunner:
    def run(self, case: RegressionCase, artifact_root: Path):
        from engine.models import CheckResult

        return CheckResult(
            check_id="runner.result",
            source="internal.regression",
            subject=case.case_id,
            required=case.required,
            status=CheckStatus.PASS,
            deterministic=True,
            reproducible=True,
            confidence=1.0,
            evidence=tuple(f"fixture:{fixture}" for fixture in case.fixtures),
            remediation_stage=LifecycleState.VALIDATED,
            artifact_reference=str(artifact_root),
        )


def test_same_failure_family_uses_one_parameterized_case() -> None:
    case = load_case("windows-encoding", root=FIXTURE_ROOT)
    assert case.failure_family_id == "windows-encoding"
    assert len(case.fixtures) >= 2


def test_regression_runner_result_is_normalized_to_required_gate_check(tmp_path: Path) -> None:
    results = run_regressions((load_case("windows-encoding", root=FIXTURE_ROOT),), PassingRunner(), tmp_path)
    assert len(results) == 1
    assert results[0].check_id == "B07"
    assert results[0].status is CheckStatus.PASS
    assert len(results[0].evidence) >= 2


def test_duplicate_failure_families_are_rejected(tmp_path: Path) -> None:
    case = load_case("windows-encoding", root=FIXTURE_ROOT)
    with pytest.raises(DuplicateRegressionFamily):
        run_regressions((case, case), PassingRunner(), tmp_path)
