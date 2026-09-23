from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "skill-engineer" / "SKILL.md"
PIPELINE = ROOT / "skills" / "skill-engineer" / "references" / "pipeline.md"


def test_skill_requires_engine_receipt_before_completion_claim() -> None:
    content = SKILL.read_text(encoding="utf-8")

    assert "ManagedCompletionReceipt" in content
    assert "UNMANAGED_CHANGE" in content
    assert "target pytest cannot replace the Quality Gate" in content


def test_skill_does_not_claim_platform_write_interception() -> None:
    content = PIPELINE.read_text(encoding="utf-8")

    assert "cannot intercept every out-of-band write" in content
    assert "UNMANAGED_CHANGE" in content
