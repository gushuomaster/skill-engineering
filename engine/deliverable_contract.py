"""Deterministic validation for Provider-owned deliverable contracts."""
from __future__ import annotations

import re
from pathlib import Path

from engine.models import (
    ArtifactManifest,
    CheckResult,
    CheckStatus,
    DeliverableContract,
    DeliverableEvidence,
    DeliverableEvidenceStatus,
    LifecycleState,
    ProviderExecution,
)


_FILE_REFERENCE = re.compile(r"(?:^|[;\s])file=([^;\s]+)")


def _evidence_paths(contract: DeliverableContract) -> tuple[str, ...]:
    values: list[str] = list(contract.applicability_evidence)
    for item in contract.deliverables:
        values.extend(item.declarations)
        values.extend(item.exposure_evidence)
        values.extend(item.implementation_evidence)
        values.extend(item.behavioral_evidence)
    paths: list[str] = []
    for value in values:
        match = _FILE_REFERENCE.search(value)
        if match:
            paths.append(match.group(1))
    return tuple(paths)


def _within_manifest(path: str, manifest: ArtifactManifest) -> bool:
    candidate = Path(path.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        return False
    normalized = str(candidate).replace("\\", "/").lstrip("./")
    return normalized in set(manifest.files)


def _safe_relative(value: str | None) -> bool:
    if not value:
        return False
    path = Path(value.replace("\\", "/"))
    return not path.is_absolute() and ".." not in path.parts


def _result(
    status: CheckStatus, subject: str, evidence: tuple[str, ...], *, required: bool,
) -> CheckResult:
    return CheckResult(
        "capability.deliverable_contract",
        "internal.deliverable-contract",
        subject,
        required,
        status,
        True,
        True,
        1.0,
        evidence or ("deliverable contract produced no evidence",),
        LifecycleState.VALIDATED_PENDING_CONFIRMATION,
        subject,
    )


def _missing_output(item: DeliverableEvidence) -> tuple[str, ...]:
    findings: list[str] = []
    if item.exposure_status is not DeliverableEvidenceStatus.PRESENT:
        findings.append(f"DECLARED_OUTPUT_NOT_EXPOSED:{item.deliverable_id}")
    elif not item.exposure_entrypoint or not item.exposure_selector:
        findings.append(f"DECLARED_OUTPUT_NOT_EXPOSED:{item.deliverable_id}")
    if item.implementation_status is not DeliverableEvidenceStatus.PRESENT:
        findings.append(f"DECLARED_OUTPUT_NOT_DISPATCHED:{item.deliverable_id}")
    elif not item.implementation_dispatch_route:
        findings.append(f"DECLARED_OUTPUT_NOT_DISPATCHED:{item.deliverable_id}")
    if item.implementation_status is DeliverableEvidenceStatus.PRESENT and not item.implementation_artifact_pattern:
        findings.append(f"DECLARED_OUTPUT_NOT_GENERATED:{item.deliverable_id}")
    if item.behavioral_status is not DeliverableEvidenceStatus.PRESENT:
        findings.append(f"DECLARED_OUTPUT_WITHOUT_BEHAVIORAL_PROOF:{item.deliverable_id}")
    elif not item.behavioral_commands or not item.behavioral_evidence:
        findings.append(f"DECLARED_OUTPUT_WITHOUT_BEHAVIORAL_PROOF:{item.deliverable_id}")
    elif not any(item.deliverable_id in evidence for evidence in item.behavioral_evidence):
        findings.append(f"DECLARED_OUTPUT_WITHOUT_BEHAVIORAL_PROOF:{item.deliverable_id}")
    return tuple(findings)


def validate_deliverable_contract(
    contract: DeliverableContract,
    manifest: ArtifactManifest,
    *,
    inspection_id: str,
    inspection_nonce: str,
    provider_id: str,
    provider_execution: ProviderExecution,
    required: bool = True,
) -> CheckResult:
    """Validate a semantic contract without interpreting its business meaning."""
    subject = manifest.skill_name
    if provider_execution is not ProviderExecution.EXECUTED:
        return _result(
            CheckStatus.NOT_EXECUTED,
            subject,
            ("OUTPUT_CONTRACT_PROVIDER_NOT_EXECUTED", f"provider_execution={provider_execution.value}"),
            required=required,
        )
    if contract.evidence_origin == "target_self_report":
        return _result(CheckStatus.NOT_EXECUTED, subject, ("SELF_REPORTED_EVIDENCE_ONLY",), required=required)
    if contract.inspection_id != inspection_id or contract.inspection_nonce != inspection_nonce:
        return _result(CheckStatus.NOT_EXECUTED, subject, ("OUTPUT_CONTRACT_EVIDENCE_STALE", "inspection identity mismatch"), required=required)
    if contract.provider_identity != provider_id:
        return _result(CheckStatus.NOT_EXECUTED, subject, ("OUTPUT_CONTRACT_PROVIDER_NOT_EXECUTED", "provider identity mismatch"), required=required)
    if contract.target_digest != manifest.content_digest:
        return _result(CheckStatus.NOT_EXECUTED, subject, ("OUTPUT_CONTRACT_EVIDENCE_STALE", "target digest mismatch"), required=required)
    if contract.applicability_status == "unknown":
        return _result(CheckStatus.NOT_EXECUTED, subject, ("OUTPUT_CONTRACT_UNRESOLVED", contract.applicability_reason), required=required)
    if contract.applicability_status == "not_applicable":
        if not contract.applicability_evidence:
            return _result(CheckStatus.NOT_EXECUTED, subject, ("OUTPUT_CONTRACT_UNRESOLVED", "not_applicable lacks evidence"), required=required)
        return _result(CheckStatus.PASS, subject, ("DELIVERABLE_CONTRACT_NOT_APPLICABLE", contract.applicability_reason), required=required)

    evidence_paths = _evidence_paths(contract)
    invalid_paths = tuple(path for path in evidence_paths if not _within_manifest(path, manifest))
    if invalid_paths:
        return _result(
            CheckStatus.NOT_EXECUTED,
            subject,
            ("OUTPUT_CONTRACT_EVIDENCE_STALE", "evidence path outside or absent from target: " + ", ".join(invalid_paths)),
            required=required,
        )
    blocking_scope_conflicts = tuple(
        item for item in contract.scope_conflicts if item.blocking
    )
    if blocking_scope_conflicts:
        return _result(
            CheckStatus.FAIL,
            subject,
            tuple(
                f"OUTPUT_SCOPE_CONFLICT:{item.summary}"
                for item in blocking_scope_conflicts
            ),
            required=required,
        )

    failures: list[str] = []
    incomplete: list[str] = []
    implemented = tuple(
        item for item in contract.deliverables if item.declared_status == "implemented"
    )
    missing_ids: set[str] = set()
    for item in implemented:
        for label, value in (
            ("exposure_entrypoint", item.exposure_entrypoint),
            ("implementation_artifact_pattern", item.implementation_artifact_pattern),
        ):
            if value and not _safe_relative(value):
                failures.append(f"OUTPUT_CONTRACT_PATH_OUT_OF_SCOPE:{item.deliverable_id}:{label}")
                missing_ids.add(item.deliverable_id)
        for finding in _missing_output(item):
            if "BEHAVIORAL_PROOF" in finding:
                incomplete.append(finding)
            else:
                failures.append(finding)
            missing_ids.add(item.deliverable_id)
        for artifact in item.expected_artifacts:
            if not _safe_relative(artifact):
                failures.append(
                    f"OUTPUT_CONTRACT_PATH_OUT_OF_SCOPE:{item.deliverable_id}:expected_artifact"
                )
                missing_ids.add(item.deliverable_id)
    summary = (
        f"deliverable_coverage: declared={len(implemented)}; "
        f"verified={len(implemented) - len(missing_ids)}; missing={len(missing_ids)}"
    )
    if failures:
        return _result(CheckStatus.FAIL, subject, tuple((summary, *failures, *incomplete)), required=required)
    if incomplete:
        return _result(CheckStatus.NOT_EXECUTED, subject, tuple((summary, *incomplete)), required=required)
    return _result(
        CheckStatus.PASS,
        subject,
        tuple((summary, *(f"deliverable={item.deliverable_id}; status=covered" for item in contract.deliverables))),
        required=required,
    )
