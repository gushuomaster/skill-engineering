from __future__ import annotations

import importlib

import pytest

from engine.models import DeliverableContractApplicability, Intent


def _module():
    try:
        return importlib.import_module("engine.applicability")
    except ModuleNotFoundError:
        pytest.fail("engine.applicability must resolve explicit deliverable requiredness")


@pytest.mark.parametrize(
    ("mode", "dimensions", "public_status", "expected"),
    [
        (Intent.AUDIT_REPAIR, (), "present", DeliverableContractApplicability.REQUIRED),
        (Intent.TARGETED_REPAIR, (), "unknown", DeliverableContractApplicability.REQUIRED),
        (Intent.CREATE, (), "present", DeliverableContractApplicability.REQUIRED),
        (Intent.AUDIT, ("DELIVERABLES",), "absent", DeliverableContractApplicability.REQUIRED),
        (Intent.AUDIT, ("STRUCTURE",), "absent", DeliverableContractApplicability.NOT_REQUIRED),
        (Intent.AUDIT, ("STRUCTURE",), "unknown", DeliverableContractApplicability.REQUIRED),
    ],
)
def test_explicit_applicability_matrix(mode, dimensions, public_status, expected) -> None:
    module = _module()
    audit_dimensions = tuple(module.AuditDimension(item) for item in dimensions)

    decision = module.resolve_deliverable_applicability(
        mode,
        audit_dimensions,
        public_status,
    )

    assert decision.applicability is expected


def test_legacy_omission_remains_compatibility_not_full_requiredness() -> None:
    module = _module()

    decision = module.resolve_deliverable_applicability(Intent.AUDIT, None, None)

    assert decision.applicability is DeliverableContractApplicability.COMPATIBILITY
    assert decision.reason == "legacy_compatibility"
