import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "skill_engineering.py"
SKILL = ROOT / "tests" / "fixtures" / "skills" / "minimal-valid"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
    )


def test_cli_read_only_pass_returns_json_and_exit_zero() -> None:
    result = run_cli("audit this skill", "--source", str(SKILL), "--read-only", "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["outcome_type"] == "Validated Complete Skill"
    assert payload["gate_result"]["publish_authorized"] is False


def test_cli_audit_only_failure_uses_exit_two_without_copy(tmp_path: Path) -> None:
    source = tmp_path / "broken"
    source.mkdir()
    (source / "SKILL.md").write_text("# broken", encoding="utf-8")

    result = run_cli("audit", "--source", str(source), "--read-only", "--json", "--target-parent", str(tmp_path))

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["outcome_type"] == "Unchanged Skill + Minimal Blocking Findings"
    assert payload["artifact_path"] == str(source)
    assert not list(tmp_path.glob(".skill-engineering-*"))


def test_cli_blocked_non_audit_returns_exit_one_without_artifact(tmp_path: Path) -> None:
    evidence_file = tmp_path / "empty-evidence.txt"
    evidence_file.write_text("", encoding="utf-8")
    result = run_cli(
        "fix this skill",
        "--source",
        str(SKILL),
        "--failure-evidence",
        str(evidence_file),
        "--target-parent",
        str(tmp_path),
        "--json",
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert "outcome_type" not in payload
    assert payload["gate_result"]["verdict"] == "FAIL"
