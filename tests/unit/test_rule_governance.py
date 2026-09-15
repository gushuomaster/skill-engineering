from engine.rule_bloat import RuleFinding
from engine.rule_governance import (
    GovernanceAction,
    GovernanceDecision,
    governance_evidence,
    validate_governance_decisions,
)


def test_detector_finding_reaches_gate_only_through_governance() -> None:
    finding = RuleFinding(
        finding_id="f1", affected_rule_units=("r1",), signals=("conflict",), confidence=0.9,
        risk="high", rationale="conflicting directives",
        evidence_refs=("SKILL.md:1",), limitations=(),
    )
    submitted = GovernanceDecision(
        "f1", GovernanceAction.DELETE, "Codex determined the rule is obsolete",
        ("SKILL.md:1",), None,
    )
    decisions = validate_governance_decisions((finding,), (submitted,))
    evidence = governance_evidence(decisions)
    assert evidence[0].source == "rule_governance"
    assert evidence[0].check_id.startswith("rule-governance")
    assert not hasattr(finding, "verdict")


def test_governance_rejects_missing_rationale_or_evidence() -> None:
    finding = RuleFinding(
        finding_id="f2", affected_rule_units=("r1",), signals=("conflict",), confidence=0.9,
        risk="high", rationale="detector signal", evidence_refs=("SKILL.md:1",), limitations=(),
    )
    import pytest
    with pytest.raises(ValueError):
        validate_governance_decisions(
            (finding,),
            (GovernanceDecision("f2", GovernanceAction.DELETE, "", (), None),),
        )


def test_detector_cannot_supply_governance_action() -> None:
    finding = RuleFinding(
        "f3", ("r1",), ("semantic_similarity",), 0.7, "low",
        "similar rules", ("SKILL.md:2",), (),
    )
    assert not hasattr(finding, "candidate_action")
    assert validate_governance_decisions((finding,), ()) == ()
