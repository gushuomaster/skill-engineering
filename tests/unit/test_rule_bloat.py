from pathlib import Path

from engine.rule_bloat import RuleUnit, extract_rule_units, detect_rule_bloat


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


def test_similar_rules_are_signals_without_actions(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\n\nMust validate generated artifacts before publish.\nMust validate generated artifacts before release.\n",
        encoding="utf-8",
    )
    findings = detect_rule_bloat(extract_rule_units(tmp_path), history=None)
    finding = next(item for item in findings if "semantic_similarity" in item.signals)
    assert not hasattr(finding, "candidate_action")
    assert not hasattr(finding, "candidate_target_layer")
    assert finding.confidence < 1.0


def test_missing_history_is_skip_limitation(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("---\nname: demo\ndescription: demo\n---\n", encoding="utf-8")
    finding = next(item for item in detect_rule_bloat(extract_rule_units(tmp_path), None) if "historical_growth" in item.signals)
    from engine.rule_governance import signal_evidence
    evidence = signal_evidence((finding,))
    assert evidence[0].status.value == "SKIP"


def test_required_and_never_contradiction_is_conflict(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("---\nname: demo\ndescription: demo\n---\n\nRequired publish checks.\nNever publish checks.\n", encoding="utf-8")
    findings = detect_rule_bloat(extract_rule_units(tmp_path), None)
    assert any("conflict" in finding.signals for finding in findings)


def test_obsolete_resource_signal(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("---\nname: demo\ndescription: demo\n---\n\nNever use Python 2 command /old/tool.exe.\n", encoding="utf-8")
    findings = detect_rule_bloat(extract_rule_units(tmp_path), None)
    assert any("obsolete_resource" in finding.signals for finding in findings)


def test_collects_applicable_ancestor_agents(tmp_path: Path) -> None:
    nested = tmp_path / "skills" / "demo"
    nested.mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("Must obey repository policy.\n", encoding="utf-8")
    (nested / "SKILL.md").write_text("---\nname: demo\ndescription: demo\n---\n", encoding="utf-8")
    units = extract_rule_units(nested)
    assert any(unit.scope == "AGENTS.md" for unit in units)


def test_collects_applicable_ancestor_claude_instructions(tmp_path: Path) -> None:
    nested = tmp_path / "skills" / "demo"
    nested.mkdir(parents=True)
    (tmp_path / "CLAUDE.md").write_text("Never bypass repository policy.\n", encoding="utf-8")
    (nested / "SKILL.md").write_text("---\nname: demo\ndescription: demo\n---\n", encoding="utf-8")
    units = extract_rule_units(nested)
    assert any(unit.scope == "CLAUDE.md" for unit in units)
