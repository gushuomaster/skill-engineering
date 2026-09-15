import json
import sys
from pathlib import Path

import pytest

from engine.inventory import digest_tree
from engine.mechanism_selection import IMPLEMENTATION_FIX
from engine.models import Intent, PrimaryIssueClass, RegressionDisposition
from engine.orchestrator import EngineeringRequest, PipelineOrchestrator, publish
from engine.workspace import CandidateChangedError
from scripts.skill_engineering import _command_runner
from tests.support import codex_decision, confirmation, copy_candidate


FIXTURES = Path(__file__).parent / "fixtures"


def _request(source: Path, candidate: Path, target_parent: Path) -> EngineeringRequest:
    behavior = _command_runner(
        json.dumps([sys.executable, "scripts/check.py", "--value", " Example ", "--expect", "EXAMPLE"]),
        "behavioral.modify",
    )
    regression = _command_runner(
        json.dumps([sys.executable, "scripts/check.py", "--value", " stable ", "--expect", "STABLE"]),
        "B07",
    )
    return EngineeringRequest(
        requirement="Change normalization from lowercase to uppercase",
        intent=Intent.MODIFY,
        decision=codex_decision(
            Intent.MODIFY,
            primary=PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE,
            selected=(IMPLEMENTATION_FIX,),
            regression=RegressionDisposition.REQUIRED,
        ),
        source=source,
        candidate=candidate,
        failure_evidence=(),
        authorized_to_modify=True,
        target_parent=target_parent,
        semantic_confirmation=confirmation(candidate),
        behavioral_runner=behavior,
        regression_runner=regression,
        publish_requested=True,
    )


def test_publish_rejects_candidate_changed_after_semantic_confirmation(tmp_path: Path) -> None:
    published_parent = tmp_path / "published"
    published_parent.mkdir()
    source = copy_candidate(FIXTURES / "source-skill", published_parent)
    codex_parent = tmp_path / "codex"
    codex_parent.mkdir()
    candidate = copy_candidate(FIXTURES / "modify-candidate" / "source-skill", codex_parent)

    outcome = PipelineOrchestrator().run(_request(source, candidate, published_parent))
    source_before = (source / "scripts" / "check.py").read_bytes()
    staged_script = outcome.artifact_path / "scripts" / "check.py"
    staged_script.write_text(
        staged_script.read_text(encoding="utf-8") + "\n# post-confirmation edit\n",
        encoding="utf-8",
    )

    with pytest.raises(CandidateChangedError, match="after semantic confirmation"):
        publish(outcome)
    assert (source / "scripts" / "check.py").read_bytes() == source_before

    reconfirmed = PipelineOrchestrator().run(
        _request(source, outcome.artifact_path, published_parent)
    )
    result = publish(reconfirmed)
    assert result.published_digest == digest_tree(outcome.artifact_path)
