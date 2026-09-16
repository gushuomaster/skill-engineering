import json
import subprocess
import sys
import shutil
from pathlib import Path

from engine.models import Intent

from tests.integration.test_cli import ROOT, SCRIPT, decision_file
from engine.mechanism_selection import MERGE_INVARIANT
from tests.support import copy_candidate


SKILL = ROOT / "tests" / "fixtures" / "skills" / "minimal-valid"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )


def test_cli_inspect_validate_confirm_json_round_trip(tmp_path: Path) -> None:
    inspection_path = tmp_path / "inspection.json"
    inspected = run_cli(
        "inspect",
        "--target",
        str(SKILL),
        "--mode",
        "AUDIT_ONLY",
        "--output",
        str(inspection_path),
    )
    assert inspected.returncode == 0, inspected.stderr
    inspection = json.loads(inspection_path.read_text(encoding="utf-8"))
    assert inspection["finding_ids"]

    governance = tmp_path / "governance.json"
    governance.write_text("[]", encoding="utf-8")
    validation_path = tmp_path / "validation.json"
    validated = run_cli(
        "validate",
        "--inspection",
        str(inspection_path),
        "--decision-record",
        str(decision_file(tmp_path, Intent.AUDIT_ONLY)),
        "--governance-decisions",
        str(governance),
        "--output",
        str(validation_path),
    )
    assert validated.returncode == 0, validated.stderr
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    assert validation["pending_semantic_confirmation"] is True

    confirmation_path = tmp_path / "confirmation.json"
    confirmation_path.write_text(
        json.dumps(
            {
                "artifact_digest": validation["artifact_digest"],
                "rationale": "Codex reviewed the validated artifact and evidence",
                "confirmed_by": "CODEX",
            }
        ),
        encoding="utf-8",
    )
    outcome_path = tmp_path / "outcome.json"
    confirmed = run_cli(
        "confirm",
        "--validation",
        str(validation_path),
        "--semantic-confirmation",
        str(confirmation_path),
        "--output",
        str(outcome_path),
    )
    assert confirmed.returncode in {0, 1}, confirmed.stderr
    outcome = json.loads(outcome_path.read_text(encoding="utf-8"))
    assert outcome["audit_execution"] == "COMPLETE"
    assert outcome["gate_result"]["semantic_confirmed"] is True


def test_cli_accepts_governance_decisions_from_inspection_ids(tmp_path: Path) -> None:
    source = tmp_path / "rules"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: rules\ndescription: Test rules.\n---\n\n"
        "Must keep output stable.\nMust keep output stable.\n",
        encoding="utf-8",
    )
    inspection_path = tmp_path / "inspection.json"
    assert run_cli(
        "inspect", "--target", str(source), "--mode", "AUDIT_ONLY",
        "--output", str(inspection_path),
    ).returncode == 0
    inspection = json.loads(inspection_path.read_text(encoding="utf-8"))
    finding = next(item for item in inspection["findings"] if item["confidence"] > 0)
    governance = tmp_path / "governance.json"
    governance.write_text(json.dumps([{
        "finding_id": finding["finding_id"],
        "action": "KEEP",
        "rationale": "Codex reviewed and kept the scoped rules",
        "evidence_refs": finding["evidence_refs"],
        "target_layer": "SKILL.md",
        "decided_by": "CODEX",
    }]), encoding="utf-8")
    validation_path = tmp_path / "validation.json"
    result = run_cli(
        "validate", "--inspection", str(inspection_path),
        "--decision-record", str(decision_file(tmp_path, Intent.AUDIT_ONLY)),
        "--governance-decisions", str(governance),
        "--output", str(validation_path),
    )
    assert result.returncode == 0, result.stderr


def test_cli_publish_is_independent_and_revalidates_outcome(tmp_path: Path) -> None:
    source = tmp_path / "source" / "minimal-valid"
    source.parent.mkdir()
    shutil.copytree(SKILL, source)
    candidate_parent = tmp_path / "candidate"
    candidate_parent.mkdir()
    candidate = copy_candidate(source, candidate_parent)
    (candidate / "change.txt").write_text("candidate", encoding="utf-8")
    destination = tmp_path / "destination"
    destination.mkdir()
    inspection_path = tmp_path / "inspection.json"
    assert run_cli(
        "inspect", "--target", str(source), "--mode", "MODIFY",
        "--output", str(inspection_path),
    ).returncode == 0
    governance = tmp_path / "governance.json"
    governance.write_text("[]", encoding="utf-8")
    validation_path = tmp_path / "validation.json"
    validated = run_cli(
        "validate", "--inspection", str(inspection_path),
        "--decision-record",
        str(decision_file(tmp_path, Intent.MODIFY, selected=(MERGE_INVARIANT,))),
        "--governance-decisions", str(governance), "--candidate", str(candidate),
        "--target-parent", str(destination), "--authorize-modify",
        "--publish-requested", "--output", str(validation_path),
    )
    assert validated.returncode == 0, validated.stderr
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    confirmation = tmp_path / "confirmation.json"
    confirmation.write_text(json.dumps({
        "artifact_digest": validation["artifact_digest"],
        "rationale": "Codex reviewed the validated candidate and evidence",
        "confirmed_by": "CODEX",
    }), encoding="utf-8")
    outcome_path = tmp_path / "outcome.json"
    confirmed = run_cli(
        "confirm", "--validation", str(validation_path),
        "--semantic-confirmation", str(confirmation), "--output", str(outcome_path),
    )
    assert confirmed.returncode == 0, confirmed.stderr
    assert not (destination / source.name).exists()
    published_path = tmp_path / "published.json"
    published = run_cli(
        "publish", "--outcome", str(outcome_path), "--output", str(published_path),
    )
    assert published.returncode == 0, published.stderr
    payload = json.loads(published_path.read_text(encoding="utf-8"))
    assert payload["publication_result"]["status"] == "PUBLISHED"
    assert (destination / source.name / "change.txt").is_file()
