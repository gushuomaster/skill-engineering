from pathlib import Path

from engine.rule_bloat import RuleUnit, extract_rule_units, detect_rule_bloat
from engine.rule_governance import GovernanceAction


def test_extracts_directives_and_ignores_reference_prose(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\n\nMust validate every artifact.\nThis paragraph explains the context.\nNever publish without tests.\n",
        encoding="utf-8",
    )
    units = extract_rule_units(tmp_path)
    assert len(units) == 2
    assert all(unit.modality in {"MUST", "NEVER"} for unit in units)


def test_keyword_density_never_returns_gate_verdict(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\n\nMust always and never do this.\n" * 5,
        encoding="utf-8",
    )
    findings = detect_rule_bloat(extract_rule_units(tmp_path), history=None)
    assert all(not hasattr(finding, "verdict") for finding in findings)


def test_similar_rules_are_merge_candidates(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\n\nMust validate generated artifacts before publish.\nMust validate generated artifacts before release.\n",
        encoding="utf-8",
    )
    findings = detect_rule_bloat(extract_rule_units(tmp_path), history=None)
    finding = next(item for item in findings if "semantic_similarity" in item.signals)
    assert finding.candidate_action is GovernanceAction.MERGE
    assert finding.confidence < 1.0
