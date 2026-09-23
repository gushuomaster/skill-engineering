from pathlib import Path
import re


SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills" / "skill-engineer"
REFERENCE_NAMES = {
    "pipeline.md",
    "issue-classification.md",
    "mechanism-selection.md",
    "rule-governance.md",
    "required-capabilities.md",
    "provider-contracts.md",
    "quality-gate.md",
}


def read_skill() -> str:
    return (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")


def test_skill_entry_is_thin_and_routes_every_mode() -> None:
    body = read_skill()
    assert all(mode in body for mode in ["AUDIT", "AUDIT_REPAIR", "TARGETED_REPAIR"])
    assert len(body.splitlines()) < 220
    assert "safe apply" in body.lower()


def test_audit_guidance_forbids_transient_target_writes() -> None:
    body = read_skill()
    assert "prove the source tree did not change" in body
    assert "disposable snapshot" in body
    assert "never a full `PASS`" in body


def test_every_reference_is_directly_linked_from_skill_md() -> None:
    body = read_skill()
    links = set(re.findall(r"\]\(references/([^)]*)\)", body))
    assert links == REFERENCE_NAMES
