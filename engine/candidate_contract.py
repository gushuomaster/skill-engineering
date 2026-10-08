"""Stable host contract for Candidate governance and integrity checks.

This module only re-exports existing skill-engineering objects.  It owns no
lifecycle state and adds no governance behavior.
"""

from .inventory import digest_tree
from .managed_completion import (
    completion_receipt,
    managed_status,
    validate_completion_receipt,
)
from .models import (
    CapabilityPreservationStatus,
    CoverageStatus,
    GateOutcome,
    GateVerdict,
    ManagedCompletionReceipt,
)
from .orchestrator import PipelineOrchestrator
from .serialization import (
    completion_receipt_from_data,
    confirmation_from_data,
    to_data,
    validation_from_data,
)

__all__ = (
    "digest_tree",
    "completion_receipt",
    "managed_status",
    "validate_completion_receipt",
    "CapabilityPreservationStatus",
    "CoverageStatus",
    "GateOutcome",
    "GateVerdict",
    "ManagedCompletionReceipt",
    "PipelineOrchestrator",
    "completion_receipt_from_data",
    "confirmation_from_data",
    "to_data",
    "validation_from_data",
)
