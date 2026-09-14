"""Validation and deterministic collection of check evidence."""
from __future__ import annotations

from dataclasses import asdict

from engine.contracts import validate_contract
from engine.models import CheckResult, CheckStatus, LifecycleState


class InvalidEvidence(ValueError):
    """Raised when evidence is malformed or contradictory."""


class EvidenceCollector:
    def __init__(self) -> None:
        self._results: dict[tuple[str, str], CheckResult] = {}

    def add(self, result: CheckResult) -> None:
        if not isinstance(result, CheckResult):
            raise InvalidEvidence("evidence must be a CheckResult")
        if not isinstance(result.status, CheckStatus):
            raise InvalidEvidence("status must be a CheckStatus")
        if not isinstance(result.remediation_stage, LifecycleState):
            raise InvalidEvidence("remediation_stage must be a LifecycleState")
        payload = asdict(result)
        for key, value in payload.items():
            if hasattr(value, "value"):
                payload[key] = value.value
            elif isinstance(value, tuple):
                payload[key] = list(value)
        try:
            validate_contract("check-result", payload)
        except Exception as exc:
            raise InvalidEvidence(f"invalid CheckResult: {exc}") from exc
        identity = (result.check_id, result.subject)
        previous = self._results.get(identity)
        if previous is not None and previous != result:
            raise InvalidEvidence(f"conflicting evidence for {identity[0]} + {identity[1]}")
        self._results[identity] = result

    def required_results(self) -> tuple[CheckResult, ...]:
        return tuple(result for result in self._results.values() if result.required)

    def optional_results(self) -> tuple[CheckResult, ...]:
        return tuple(result for result in self._results.values() if not result.required)

    def snapshot(self) -> tuple[CheckResult, ...]:
        return tuple(self._results.values())
