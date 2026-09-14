"""Failure-family regression case loading and runner execution."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Protocol

from engine.contracts import validate_contract
from engine.models import CheckResult, CheckStatus, LifecycleState


REGRESSION_ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "regression"


@dataclass(frozen=True)
class RegressionCase:
    case_id: str
    failure_family_id: str
    description: str
    observable_contract: str
    required: bool
    fixtures: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "RegressionCase":
        validate_contract("regression-case", payload)
        return cls(
            case_id=str(payload["case_id"]),
            failure_family_id=str(payload["failure_family"]),
            description=str(payload["description"]),
            observable_contract=str(payload["observable_contract"]),
            required=bool(payload["required"]),
            fixtures=tuple(str(value) for value in payload["fixtures"]),
        )


class RegressionRunner(Protocol):
    def run(self, case: RegressionCase, artifact_root: Path) -> CheckResult: ...


class DuplicateRegressionFamily(ValueError):
    """Raised when independent cases duplicate a failure family."""


def _case_path(case_id: str, root: Path) -> Path:
    if not case_id or Path(case_id).name != case_id or case_id in {".", ".."}:
        raise ValueError("case_id must be a simple fixture name")
    directory = root / case_id
    candidates = (directory / "case.json", root / f"{case_id}.json")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"regression case not found: {case_id}")


def load_case(case_id: str, *, root: Path | None = None) -> RegressionCase:
    """Load and schema-validate one regression case fixture."""
    path = _case_path(case_id, REGRESSION_ROOT if root is None else root)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("regression case payload must be an object")
    case = RegressionCase.from_payload(payload)
    if case.case_id != case_id:
        raise ValueError("regression case id does not match requested id")
    return case


def _error_result(case: RegressionCase, root: Path, message: str) -> CheckResult:
    return CheckResult(
        check_id="B07",
        source="internal.regression",
        subject=case.failure_family_id,
        required=case.required,
        status=CheckStatus.ERROR,
        deterministic=False,
        reproducible=False,
        confidence=0.0,
        evidence=(message,),
        remediation_stage=LifecycleState.VALIDATED,
        artifact_reference=str(root),
    )


def run_regressions(
    cases: tuple[RegressionCase, ...], runner: RegressionRunner, root: Path
) -> tuple[CheckResult, ...]:
    """Execute one normalized check per failure family."""
    seen: set[str] = set()
    results: list[CheckResult] = []
    for case in cases:
        if case.failure_family_id in seen:
            raise DuplicateRegressionFamily(case.failure_family_id)
        seen.add(case.failure_family_id)
        try:
            result = runner.run(case, root)
            if not isinstance(result, CheckResult):
                raise TypeError("regression runner must return CheckResult")
            evidence_values = list(result.evidence)
            for fixture in case.fixtures:
                fixture_evidence = f"fixture:{fixture}"
                if fixture_evidence not in evidence_values:
                    evidence_values.append(fixture_evidence)
            evidence = tuple(evidence_values)
            results.append(
                CheckResult(
                    check_id="B07",
                    source=result.source or "internal.regression",
                    subject=case.failure_family_id,
                    required=case.required,
                    status=result.status,
                    deterministic=result.deterministic,
                    reproducible=result.reproducible,
                    confidence=result.confidence,
                    evidence=evidence,
                    remediation_stage=result.remediation_stage,
                    artifact_reference=result.artifact_reference or str(root),
                )
            )
        except Exception as exc:
            results.append(_error_result(case, root, f"regression runner error: {exc}"))
    return tuple(results)
