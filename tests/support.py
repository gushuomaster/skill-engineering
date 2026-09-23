from pathlib import Path
import shutil

from engine.inventory import digest_tree
from engine.mechanism_selection import (
    ENVIRONMENT_TOOLING, IMPLEMENTATION_FIX, MERGE_INVARIANT, PROMPT_RULE,
    REFERENCE_OR_INSTRUCTION, REGRESSION_TEST, SCHEMA_VALIDATOR, WORKFLOW_REFACTOR,
)
from engine.models import (
    CapabilityChangeDecision, ControlGap, DecisionRecord, Intent, PrimaryIssueClass,
    RegressionDisposition, SemanticConfirmation,
)


ALL_MECHANISMS = (
    IMPLEMENTATION_FIX, REGRESSION_TEST, SCHEMA_VALIDATOR, ENVIRONMENT_TOOLING,
    WORKFLOW_REFACTOR, MERGE_INVARIANT, REFERENCE_OR_INSTRUCTION, PROMPT_RULE,
)


def codex_decision(
    intent: Intent,
    *,
    primary: PrimaryIssueClass = PrimaryIssueClass.NO_DEFECT,
    selected: tuple[str, ...] = (),
    regression: RegressionDisposition = RegressionDisposition.NOT_APPLICABLE,
    root_cause: str | None = None,
    limitations: tuple[str, ...] = (),
    capability_change_decision: CapabilityChangeDecision | None = None,
) -> DecisionRecord:
    return DecisionRecord(
        intent, primary, (ControlGap.IMPLEMENTATION_GAP,) if root_cause else (ControlGap.NONE,),
        regression, root_cause, limitations, selected,
        tuple(item for item in ALL_MECHANISMS if item not in selected), None,
        "CODEX", capability_change_decision,
    )


def copy_candidate(source: Path, parent: Path, name: str | None = None) -> Path:
    name = name or source.name
    candidate = parent / name
    shutil.copytree(source, candidate)
    skill_md = candidate / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    source_name = source.name
    text = text.replace(f"name: {source_name}", f"name: {name}", 1)
    skill_md.write_text(text, encoding="utf-8")
    return candidate


def confirmation(path: Path, rationale: str = "Codex verified the requested semantic behavior") -> SemanticConfirmation:
    return SemanticConfirmation(digest_tree(path), rationale)
