from pathlib import Path
import re


SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills" / "skill-engineer"
REFERENCE_NAMES = {
    "pipeline.md",
    "issue-classification.md",
    "mechanism-selection.md",
    "rule-governance.md",
    "provider-contracts.md",
    "quality-gate.md",
}


def read_skill() -> str:
    return (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")


def test_skill_entry_is_thin_and_routes_every_mode() -> None:
    body = read_skill()
    assert all(mode in body for mode in ["Create", "Modify", "Fix", "Audit Only", "Audit + Optimize"])
    assert len(body.splitlines()) < 220
    assert "scripts/skill_engineering.py" in body


def test_audit_guidance_forbids_transient_target_writes() -> None:
    body = read_skill()
    assert "byte-for-byte unchanged throughout the run" in body
    assert "PYTHONDONTWRITEBYTECODE=1" in body
    assert "Do not run `py_compile`" in body
    assert "instead of writing and cleaning up afterward" in body


def test_every_reference_is_directly_linked_from_skill_md() -> None:
    body = read_skill()
    links = set(re.findall(r"\]\(references/([^)]*)\)", body))
    assert links == REFERENCE_NAMES
