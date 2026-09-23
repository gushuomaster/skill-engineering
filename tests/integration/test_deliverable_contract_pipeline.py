from __future__ import annotations

from pathlib import Path

from engine.models import (
    CheckResult, CheckStatus, CoverageStatus, DeliverableContract,
    DeliverableContractApplicability, DeliverableEvidence,
    DeliverableEvidenceStatus, GateOutcome, GateVerdict, Intent, LifecycleState,
    ProviderDescriptor, ProviderResult, ProviderStatus,
)
from engine.orchestrator import PipelineOrchestrator
from engine.providers import ProviderGateway
from tests.support import codex_decision, confirmation, copy_candidate


class ContractProvider:
    descriptor = ProviderDescriptor(
        "provider.contract", "test://provider.contract", "1", "DELIVERABLE_CONTRACT",
        ProviderStatus.AVAILABLE, "test", (), None,
    )

    def __init__(
        self, *, exposed: bool = True, stale: bool = False,
        escaped_path: bool = False, deliverable_count: int = 1,
        verified_count: int | None = None,
    ) -> None:
        self.exposed = exposed
        self.stale = stale
        self.escaped_path = escaped_path
        self.deliverable_count = deliverable_count
        self.verified_count = deliverable_count if verified_count is None else verified_count

    def invoke(self, capability: str, request: dict[str, object]) -> ProviderResult:
        deliverables = tuple(
            _deliverable(
                f"output-{index + 1}",
                exposed=self.exposed,
                escaped_path=self.escaped_path and index == 0,
                verified=index < self.verified_count,
            )
            for index in range(self.deliverable_count)
        )
        contract = DeliverableContract(
            "1.0", str(request["inspection_id"]),
            "0" * 64 if self.stale else str(request["target_digest"]),
            str(request["inspection_nonce"]), self.descriptor.provider_id,
            deliverables, (), "applicable", "declared output",
            ("file=SKILL.md",), "provider",
        )
        return ProviderResult(
            self.descriptor.provider_id, capability, ProviderStatus.AVAILABLE,
            (), (), ("provider executed",), (), False, True,
            deliverable_contract=contract,
        )


class SelectedButFailedProvider:
    descriptor = ContractProvider.descriptor

    def invoke(self, capability: str, request: dict[str, object]) -> ProviderResult:
        raise RuntimeError("selected Provider failed before returning a contract")


def _deliverable(
    deliverable_id: str, *, exposed: bool = True,
    escaped_path: bool = False, verified: bool = True,
) -> DeliverableEvidence:
    artifact = f"docs/{deliverable_id}.txt"
    return DeliverableEvidence(
        deliverable_id, "implemented", ("file=SKILL.md",),
        DeliverableEvidenceStatus.PRESENT if exposed else DeliverableEvidenceStatus.MISSING,
        "scripts/run.py", deliverable_id,
        ("file=../outside.txt",) if escaped_path else ("file=scripts/run.py",),
        DeliverableEvidenceStatus.PRESENT, f"run_{deliverable_id}", artifact,
        ("file=scripts/run.py",),
        DeliverableEvidenceStatus.PRESENT if verified else DeliverableEvidenceStatus.MISSING,
        (f"python tests/test_{deliverable_id}.py",) if verified else (),
        (artifact,),
        (f"covered={deliverable_id}; exit_code=0",) if verified else (),
    )


def _source(root: Path, deliverable_count: int = 1) -> Path:
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Run declared outputs.\n---\n\nRun outputs.\n",
        encoding="utf-8",
    )
    (root / "scripts").mkdir()
    (root / "scripts" / "run.py").write_text("def run_output(): pass\n", encoding="utf-8")
    (root / "docs").mkdir()
    for index in range(deliverable_count):
        (root / "docs" / f"output-{index + 1}.txt").write_text(
            f"output-{index + 1}\n", encoding="utf-8",
        )
    return root


def _behavior(path: Path) -> CheckResult:
    return CheckResult(
        "behavioral.outputs", "test.runner", path.name, True, CheckStatus.PASS,
        True, True, 1.0, ("declared output behavior executed",),
        LifecycleState.VALIDATED_PENDING_CONFIRMATION, str(path),
    )


def _audit(
    source: Path,
    applicability: DeliverableContractApplicability | None,
    provider: object | None = None,
):
    gateway = ProviderGateway([provider]) if provider is not None else None
    orchestrator = PipelineOrchestrator(provider_gateway=gateway)
    kwargs = {}
    if applicability is not None:
        kwargs["deliverable_contract_applicability"] = applicability
    inspection = orchestrator.inspect(Intent.AUDIT, source, **kwargs)
    validation = orchestrator.validate(
        inspection, codex_decision(Intent.AUDIT), (), candidate=None,
        target_parent=source.parent, authorized_to_modify=False,
        behavioral_runner=_behavior,
    )
    outcome = orchestrator.confirm(validation, confirmation(source))
    return inspection, validation, outcome


def test_required_missing_provider_is_incomplete_and_not_full(tmp_path: Path) -> None:
    source = _source(tmp_path / "demo")
    _, validation, outcome = _audit(source, DeliverableContractApplicability.REQUIRED)

    assert validation.coverage_status is CoverageStatus.PARTIAL
    assert outcome.gate_result.verdict is GateVerdict.INCOMPLETE
    assert outcome.gate_result.outcome is GateOutcome.AUDIT_INCOMPLETE
    assert outcome.gate_result.apply_authorized is False
    assert validation.deliverable_contract_provenance.provider_discovered is False
    assert validation.deliverable_contract_provenance.provider_executed is False
    assert validation.deliverable_contract_provenance.reason == "provider_unavailable"


def test_required_selected_provider_not_executed_is_explicit(tmp_path: Path) -> None:
    source = _source(tmp_path / "demo")
    _, validation, outcome = _audit(
        source, DeliverableContractApplicability.REQUIRED,
        SelectedButFailedProvider(),
    )

    provenance = validation.deliverable_contract_provenance
    assert provenance.provider_discovered is True
    assert provenance.provider_selected is True
    assert provenance.provider_executed is False
    assert provenance.contract_present is False
    assert provenance.reason == "provider_execution_failed"
    assert validation.coverage_status is CoverageStatus.PARTIAL
    assert outcome.gate_result.outcome is not GateOutcome.AUDIT_COMPLETE_VALID


def test_optional_missing_provider_passes_with_partial_coverage(tmp_path: Path) -> None:
    source = _source(tmp_path / "demo")
    _, validation, outcome = _audit(source, DeliverableContractApplicability.OPTIONAL)

    assert outcome.gate_result.verdict is GateVerdict.PASS
    assert validation.coverage_status is CoverageStatus.PARTIAL
    assert outcome.gate_result.coverage_status is CoverageStatus.PARTIAL
    assert outcome.gate_result.outcome is GateOutcome.UNCHANGED_VALIDATED
    assert validation.deliverable_contract_provenance.reason == "provider_unavailable"


def test_not_required_missing_provider_keeps_full_coverage(tmp_path: Path) -> None:
    source = _source(tmp_path / "demo")
    inspection, validation, outcome = _audit(
        source, DeliverableContractApplicability.NOT_REQUIRED,
    )

    assert validation.coverage_status is CoverageStatus.FULL
    assert outcome.gate_result.verdict is GateVerdict.PASS
    assert outcome.gate_result.outcome is GateOutcome.AUDIT_COMPLETE_VALID
    assert inspection.deliverable_contract_provenance.applicability is DeliverableContractApplicability.NOT_REQUIRED
    assert validation.deliverable_contract_provenance.reason == "not_required"


def test_required_valid_contract_has_full_coverage_and_allows_apply(tmp_path: Path) -> None:
    source = _source(tmp_path / "source" / "demo")
    candidate_parent = tmp_path / "candidate"
    candidate_parent.mkdir()
    candidate = copy_candidate(source, candidate_parent)
    destination = tmp_path / "destination"
    destination.mkdir()
    orchestrator = PipelineOrchestrator(
        provider_gateway=ProviderGateway([ContractProvider()]),
    )
    inspection = orchestrator.inspect(
        Intent.TARGETED_REPAIR, source,
        deliverable_contract_applicability=DeliverableContractApplicability.REQUIRED,
    )
    validation = orchestrator.validate(
        inspection, codex_decision(Intent.TARGETED_REPAIR), (), candidate=candidate,
        target_parent=destination, authorized_to_modify=True,
        behavioral_runner=_behavior, apply_requested=True,
    )
    outcome = orchestrator.confirm(validation, confirmation(validation.artifact_path))

    provenance = validation.deliverable_contract_provenance
    assert provenance.provider_selected is True
    assert provenance.provider_executed is True
    assert provenance.contract_present is True
    assert provenance.contract_validated is True
    assert validation.coverage_status is CoverageStatus.FULL
    assert outcome.gate_result.verdict is GateVerdict.PASS
    assert outcome.gate_result.apply_authorized is True


def test_required_stale_contract_is_not_full_and_blocks(tmp_path: Path) -> None:
    source = _source(tmp_path / "demo")
    _, validation, outcome = _audit(
        source, DeliverableContractApplicability.REQUIRED,
        ContractProvider(stale=True),
    )

    assert validation.coverage_status is CoverageStatus.PARTIAL
    assert validation.deliverable_contract_provenance.contract_validated is False
    assert validation.deliverable_contract_provenance.reason == "contract_stale"
    assert outcome.gate_result.verdict is GateVerdict.INCOMPLETE
    assert outcome.gate_result.apply_authorized is False


def test_required_evidence_path_escape_blocks_coverage(tmp_path: Path) -> None:
    source = _source(tmp_path / "demo")
    _, validation, outcome = _audit(
        source, DeliverableContractApplicability.REQUIRED,
        ContractProvider(escaped_path=True),
    )

    check = next(item for item in validation.deterministic_evidence
                 if item.check_id == "capability.deliverable_contract")
    assert check.status is CheckStatus.NOT_EXECUTED
    assert validation.coverage_status is CoverageStatus.PARTIAL
    assert outcome.gate_result.verdict is GateVerdict.INCOMPLETE
    assert outcome.gate_result.apply_authorized is False


def test_five_declared_one_verified_reports_coverage_mismatch(tmp_path: Path) -> None:
    source = _source(tmp_path / "demo", deliverable_count=5)
    _, validation, outcome = _audit(
        source, DeliverableContractApplicability.REQUIRED,
        ContractProvider(deliverable_count=5, verified_count=1),
    )

    check = next(item for item in validation.deterministic_evidence
                 if item.check_id == "capability.deliverable_contract")
    assert "deliverable_coverage: declared=5; verified=1; missing=4" in check.evidence
    assert validation.coverage_status is CoverageStatus.PARTIAL
    assert outcome.gate_result.outcome is not GateOutcome.AUDIT_COMPLETE_VALID


def test_legacy_caller_uses_compatibility_coverage_not_full_audit(tmp_path: Path) -> None:
    source = _source(tmp_path / "demo")
    inspection, validation, outcome = _audit(source, None)

    assert inspection.deliverable_contract_applicability is DeliverableContractApplicability.COMPATIBILITY
    assert validation.coverage_status is CoverageStatus.COMPATIBILITY
    assert outcome.gate_result.verdict is GateVerdict.PASS
    assert outcome.gate_result.coverage_status is CoverageStatus.COMPATIBILITY
    assert outcome.gate_result.outcome is GateOutcome.UNCHANGED_VALIDATED
    assert validation.deliverable_contract_provenance.reason == "legacy_compatibility"


def test_contract_exposure_gap_blocks_gate(tmp_path: Path) -> None:
    source = _source(tmp_path / "demo")
    _, validation, outcome = _audit(
        source, DeliverableContractApplicability.REQUIRED,
        ContractProvider(exposed=False),
    )
    check = next(item for item in validation.deterministic_evidence
                 if item.check_id == "capability.deliverable_contract")
    assert check.status is CheckStatus.FAIL
    assert outcome.gate_result.verdict is GateVerdict.FAIL
