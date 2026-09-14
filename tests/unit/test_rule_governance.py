from engine.rule_bloat import RuleFinding
from engine.rule_governance import GovernanceAction, governance_evidence, govern_findings


def test_detector_finding_reaches_gate_only_through_governance() -> None:
    finding = RuleFinding(
        finding_id="f1", affected_rule_units=("r1",), signals=("conflict",), confidence=0.9,
        risk="high", rationale="conflicting directives", candidate_action=GovernanceAction.DELETE,
        candidate_target_layer="validator", evidence_refs=("SKILL.md:1",), limitations=(),
    )
    decisions = govern_findings((finding,), mechanisms=("regression_test",))
    evidence = governance_evidence(decisions)
    assert evidence[0].source == "rule_governance"
    assert evidence[0].check_id.startswith("rule-governance")
    assert not hasattr(finding, "verdict")
