import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from engine.inventory import digest_tree
from engine.models import Intent
from engine.mechanism_selection import MERGE_INVARIANT
from tests.support import codex_decision


ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "skill_engineering.py"
SKILL = ROOT / "tests" / "fixtures" / "skills" / "minimal-valid"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True,
        capture_output=True, encoding="utf-8",
    )


def decision_file(tmp_path: Path, intent: Intent, *, selected: tuple[str, ...] = ()) -> Path:
    path = tmp_path / "decision.json"
    payload = asdict(codex_decision(intent, selected=selected))
    for key, value in list(payload.items()):
        if hasattr(value, "value"):
            payload[key] = value.value
        elif isinstance(value, tuple):
            payload[key] = [item.value if hasattr(item, "value") else item for item in value]
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_cli_requires_explicit_intent_and_decision() -> None:
    result = run_cli("audit", "--source", str(SKILL), "--json")
    assert result.returncode == 2
    assert "--intent" in result.stderr
    assert "--decision" in result.stderr


def test_cli_read_only_pass_returns_json_and_exit_zero(tmp_path: Path) -> None:
    result = run_cli(
        "audit this skill", "--intent", "AUDIT",
        "--decision", str(decision_file(tmp_path, Intent.AUDIT_ONLY)),
        "--source", str(SKILL), "--confirmed-digest", digest_tree(SKILL),
        "--semantic-rationale", "Codex reviewed the current Skill", "--json",
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["gate_result"]["semantic_confirmed"] is True
    assert payload["gate_result"]["apply_authorized"] is False


def test_cli_complete_audit_with_blocking_findings_uses_exit_one_without_copy(tmp_path: Path) -> None:
    source = tmp_path / "broken"
    source.mkdir()
    (source / "SKILL.md").write_text("# broken", encoding="utf-8")
    result = run_cli(
        "audit", "--intent", "AUDIT",
        "--decision", str(decision_file(tmp_path, Intent.AUDIT_ONLY)),
        "--source", str(source), "--confirmed-digest", digest_tree(source),
        "--semantic-rationale", "Codex reviewed the broken Skill",
        "--json", "--target-parent", str(tmp_path),
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["outcome_type"] == "AUDIT_COMPLETE_BLOCKING_FINDINGS"
    assert payload["audit_execution"] == "COMPLETE"
    assert payload["artifact_assessment"] == "BLOCKING_FINDINGS"
    assert not list(tmp_path.glob(".skill-engineering-*"))


def test_cli_create_runs_real_behavior_command_and_stages_only(tmp_path: Path) -> None:
    candidate = tmp_path / "codex" / "demo"
    candidate.mkdir(parents=True)
    (candidate / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Perform a demonstrable task.\n---\n\n# Demo\n",
        encoding="utf-8",
    )
    destination = tmp_path / "destination"
    destination.mkdir()
    result = run_cli(
        "create demo", "--intent", "CREATE",
        "--decision", str(decision_file(tmp_path, Intent.CREATE, selected=(MERGE_INVARIANT,))),
        "--candidate", str(candidate), "--authorize-modify",
        "--target-parent", str(destination),
        "--confirmed-digest", digest_tree(candidate),
        "--semantic-rationale", "Codex verified the complete demo Skill",
        "--behavior-command-json", json.dumps([sys.executable, "-c", "print('behavior ok')"]),
        "--json",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["apply_ready"] is False
    assert payload["gate_result"]["apply_authorized"] is False
    assert payload["applied_path"] is None
    assert not (destination / "demo").exists()
