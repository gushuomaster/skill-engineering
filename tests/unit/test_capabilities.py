from pathlib import Path

from engine.capabilities import (
    AGENT_INSTRUCTION_GOVERNANCE,
    PDF_VALIDATION,
    SKILL_CONFORMANCE,
    SKILL_CREATION_OR_RESTRUCTURE,
    SKILL_DUPLICATION_AND_BLOAT,
    build_capability_preflight,
)
from engine.models import (
    CapabilityStatus, CheckStatus, FallbackEquivalence, Intent, ProviderEvidence,
    ProviderExecution,
)
from engine.providers import (
    CHECK_SKILL_CONFORMANCE, CREATE_CANDIDATE,
)


def _provider(capability: str, status: CheckStatus, provider_id: str) -> ProviderEvidence:
    return ProviderEvidence(
        provider_id, capability, "INSPECT", status, "test evidence",
        provider_available=True, provider_execution=ProviderExecution.EXECUTED,
        evidence_valid=True,
    )


def test_preflight_uses_selected_provider_and_core_for_unselected_help(
    tmp_path: Path,
) -> None:
    evidence = (
        _provider(CREATE_CANDIDATE, CheckStatus.PASS, "openai.skill-creator"),
        _provider(CHECK_SKILL_CONFORMANCE, CheckStatus.NOT_EXECUTED, "validate-skills"),
    )

    matrix = {
        item.capability: item
        for item in build_capability_preflight(Intent.MODIFY, tmp_path, evidence)
    }

    assert matrix[SKILL_CREATION_OR_RESTRUCTURE].status is CapabilityStatus.READY
    assert matrix[SKILL_CREATION_OR_RESTRUCTURE].selected_provider == "openai.skill-creator"
    assert matrix[SKILL_CONFORMANCE].status is CapabilityStatus.READY
    assert matrix[SKILL_CONFORMANCE].selected_provider == "internal.core"
    assert matrix[SKILL_DUPLICATION_AND_BLOAT].selected_provider == "internal.core"
    assert matrix[AGENT_INSTRUCTION_GOVERNANCE].selected_provider == "internal.core"


def test_declared_unknown_required_capability_is_blocked(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo.\n"
        "required_capabilities:\n  - domain_x\n---\n",
        encoding="utf-8",
    )

    matrix = {
        item.capability: item
        for item in build_capability_preflight(Intent.AUDIT_ONLY, tmp_path, ())
    }

    assert matrix["domain_x"].status is CapabilityStatus.BLOCKED
    assert matrix["domain_x"].fallback is None
    assert matrix["domain_x"].fallback_equivalence is FallbackEquivalence.NONE


def test_declared_domain_capability_can_use_dynamically_registered_provider_evidence(
    tmp_path: Path,
) -> None:
    (tmp_path / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo.\n"
        "required_capabilities:\n  - security_review\n---\n",
        encoding="utf-8",
    )
    evidence = (
        _provider("security_review", CheckStatus.PASS, "security-best-practices"),
    )

    matrix = {
        item.capability: item
        for item in build_capability_preflight(Intent.AUDIT_ONLY, tmp_path, evidence)
    }

    assert matrix["security_review"].status is CapabilityStatus.READY
    assert matrix["security_review"].selected_provider == "security-best-practices"


def test_domain_capability_is_not_inferred_from_description(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text(
        "---\nname: pdf-helper\ndescription: Validate PDF artifacts.\n---\n",
        encoding="utf-8",
    )

    matrix = {
        item.capability: item
        for item in build_capability_preflight(Intent.AUDIT_ONLY, tmp_path, ())
    }

    assert PDF_VALIDATION not in matrix


def test_unselected_domain_capability_is_absent(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Execute a text workflow.\n---\n",
        encoding="utf-8",
    )

    matrix = {
        item.capability: item
        for item in build_capability_preflight(Intent.AUDIT_ONLY, tmp_path, ())
    }

    assert PDF_VALIDATION not in matrix


def test_secondary_provider_is_an_alternative_fallback(tmp_path: Path) -> None:
    evidence = (
        _provider(CHECK_SKILL_CONFORMANCE, CheckStatus.PASS, "validate-skills"),
    )

    matrix = {
        item.capability: item
        for item in build_capability_preflight(Intent.MODIFY, tmp_path, evidence)
    }

    trigger = matrix["skill_trigger_and_description"]
    assert trigger.status is CapabilityStatus.FALLBACK
    assert trigger.selected_provider == "validate-skills"
    assert trigger.fallback_equivalence is FallbackEquivalence.ALTERNATIVE
