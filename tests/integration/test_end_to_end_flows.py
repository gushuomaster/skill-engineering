from pathlib import Path

from engine.mechanism_selection import MERGE_INVARIANT
from engine.models import Intent, PrimaryIssueClass
from engine.orchestrator import EngineeringRequest, PipelineOrchestrator, publish
from tests.support import codex_decision, confirmation, copy_candidate


FIXTURE = Path(__file__).parents[1] / "fixtures" / "skills" / "minimal-valid"


def test_audit_optimize_without_candidate_remains_read_only(tmp_path: Path) -> None:
    outcome = PipelineOrchestrator().run(EngineeringRequest(
        "audit and optimize", Intent.AUDIT_OPTIMIZE,
        codex_decision(Intent.AUDIT_OPTIMIZE),
        FIXTURE, None, (), True, tmp_path,
        semantic_confirmation=confirmation(FIXTURE),
    ))
    assert outcome.artifact_path == FIXTURE
    assert outcome.gate_result.publish_authorized is False
    assert outcome.publication_session is None
    assert not list(tmp_path.glob(".skill-engineering-*"))


def test_ready_candidate_is_not_published_until_explicit_call(tmp_path: Path) -> None:
    source_parent = tmp_path / "published"
    source_parent.mkdir()
    source = copy_candidate(FIXTURE, source_parent)
    original = (source / "SKILL.md").read_text(encoding="utf-8")
    candidate_parent = tmp_path / "codex"
    candidate_parent.mkdir()
    candidate = copy_candidate(source, candidate_parent)
    changed = (candidate / "SKILL.md").read_text(encoding="utf-8") + "\nCodex-authored capability.\n"
    (candidate / "SKILL.md").write_text(changed, encoding="utf-8")

    outcome = PipelineOrchestrator().run(EngineeringRequest(
        "add a stable capability", Intent.MODIFY,
        codex_decision(Intent.MODIFY, primary=PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE,
                       selected=(MERGE_INVARIANT,)),
        source, candidate, (), True, source.parent,
        semantic_confirmation=confirmation(candidate),
        publish_requested=True,
    ))

    assert (source / "SKILL.md").read_text(encoding="utf-8") == original
    assert outcome.gate_result.publish_authorized is True
    result = publish(outcome)
    assert result.published_path == source
    assert (source / "SKILL.md").read_text(encoding="utf-8") == changed
    assert result.backup_path is not None
