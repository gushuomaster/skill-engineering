"""Bounded extraction and advisory detection of Skill rules."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuleUnit:
    id: str
    source_location: str
    normalized_meaning: str
    modality: str
    condition: str | None = None
    exception: str | None = None
    scope: str | None = None
    environment_qualifier: str | None = None
    referenced_mechanism: str | None = None
    history_metadata: tuple[str, ...] | None = None


@dataclass(frozen=True)
class RuleHistory:
    rule_counts: tuple[int, ...] = ()
    metadata: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuleFinding:
    finding_id: str
    affected_rule_units: tuple[str, ...]
    signals: tuple[str, ...]
    confidence: float
    risk: str
    rationale: str
    evidence_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


_DIRECTIVE = re.compile(r"^\s*(?:[-*+]\s*)?(?P<mod>must|never|required|shall|should|do not|don't|不得|必须|禁止|应当)\b(?P<body>.*)$", re.I)
_MODALITY = {"must": "MUST", "required": "REQUIRED", "shall": "MUST", "never": "NEVER", "do not": "NEVER", "don't": "NEVER", "should": "SHOULD", "不得": "NEVER", "必须": "MUST", "禁止": "NEVER", "应当": "MUST"}
_ENV = re.compile(r"\b(windows|linux|macos|osx|powershell|bash|cmd|python\s*[23](?:\.\d+)?)\b", re.I)
_MECHANISM = re.compile(r"\b(schema|validator|validation|test|regression|tooling|implementation|workflow)\b", re.I)
_OBSOLETE = re.compile(
    r"\b(?:legacy|deprecated|obsolete|old|unsupported|sunset|no\s+longer|"
    r"python\s*[12](?:\.\d+)?|node\s*(?:0|[1-9])|ruby\s*[12]|java\s*[0-8])\b",
    re.I,
)


def _sources(skill_root: Path) -> list[Path]:
    paths: list[Path] = []
    skill_root = skill_root.resolve()
    skill_file = skill_root / "SKILL.md"
    if skill_file.is_file():
        paths.append(skill_file)
    for ancestor in (skill_root, *skill_root.parents):
        for filename in ("AGENTS.md", "CLAUDE.md"):
            candidate = ancestor / filename
            if candidate.is_file() and candidate not in paths:
                paths.append(candidate)
    references = skill_root / "references"
    if references.is_dir():
        for candidate in sorted(references.rglob("*.md")):
            if candidate.is_file() and candidate not in paths:
                paths.append(candidate)
    return paths


def extract_rule_units(skill_root: Path) -> tuple[RuleUnit, ...]:
    units: list[RuleUnit] = []
    for path in _sources(Path(skill_root)):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        in_frontmatter = False
        for line_number, line in enumerate(lines, 1):
            if line_number == 1 and line.strip() == "---":
                in_frontmatter = True
                continue
            if in_frontmatter:
                if line.strip() == "---":
                    in_frontmatter = False
                continue
            match = _DIRECTIVE.match(line)
            if not match:
                continue
            body = re.sub(r"\s+", " ", match.group("body")).strip(" .:;\t")
            if len(body) < 3:
                continue
            modality = _MODALITY[match.group("mod").lower()]
            normalized = re.sub(r"[^a-z0-9]+", " ", body.lower()).strip()
            condition = None
            condition_match = re.search(r"\bif\b(.+?)(?:\bunless\b|\bexcept\b|$)", body, re.I)
            if condition_match:
                condition = condition_match.group(1).strip()
            exception_match = re.search(r"\b(?:unless|except)\b(.+)$", body, re.I)
            exception = exception_match.group(1).strip() if exception_match else None
            environment = _ENV.search(body)
            mechanism = _MECHANISM.search(body)
            location = f"{path.as_posix()}:{line_number}"
            units.append(RuleUnit(
                id=f"rule-{len(units) + 1}", source_location=location,
                normalized_meaning=normalized, modality=modality,
                condition=condition, exception=exception, scope=path.name,
                environment_qualifier=environment.group(1).lower() if environment else None,
                referenced_mechanism=mechanism.group(1).lower() if mechanism else None,
            ))
    return tuple(units)


def _tokens(value: str) -> set[str]:
    return set(value.split())


def detect_rule_bloat(units: tuple[RuleUnit, ...], history: RuleHistory | None) -> tuple[RuleFinding, ...]:
    findings: list[RuleFinding] = []
    def add(
        fid: str,
        affected: tuple[str, ...],
        signals: tuple[str, ...],
        confidence: float,
        risk: str,
        rationale: str,
        limitations: tuple[str, ...] = (),
        evidence_refs: tuple[str, ...] = (),
    ) -> None:
        refs = evidence_refs or tuple(
            next((u.source_location for u in units if u.id == rid), rid)
            for rid in affected
        )
        findings.append(
            RuleFinding(
                fid,
                affected,
                signals,
                max(0.0, min(1.0, confidence)),
                risk,
                rationale,
                refs,
                limitations,
            )
        )

    seen: dict[tuple[str, str], list[RuleUnit]] = {}
    for unit in units:
        seen.setdefault((unit.normalized_meaning, unit.modality), []).append(unit)
    for _identity, group in seen.items():
        if len(group) > 1:
            add(f"exact-{len(findings)+1}", tuple(u.id for u in group), ("exact_duplicate",), 1.0, "medium", "Rules have identical normalized meaning.")
    for index, left in enumerate(units):
        for right in units[index + 1:]:
            lt, rt = _tokens(left.normalized_meaning), _tokens(right.normalized_meaning)
            score = len(lt & rt) / len(lt | rt) if lt | rt else 0.0
            modalities = {left.modality, right.modality}
            if lt & rt and (
                modalities == {"MUST", "NEVER"}
                or modalities == {"REQUIRED", "NEVER"}
            ):
                add(
                    f"conflict-{len(findings)+1}",
                    (left.id, right.id),
                    ("conflict", "branch_depth"),
                    min(0.95, score + 0.4),
                    "high",
                    "Opposing directives share overlapping meaning.",
                )
            if left.normalized_meaning == right.normalized_meaning:
                continue
            if score >= 0.6:
                add(f"similar-{len(findings)+1}", (left.id, right.id), ("semantic_similarity",), score, "low", "Rules are near-duplicates and require Codex review.", limitations=("similarity is heuristic",))
    directive_count = len(units)
    if directive_count >= 8:
        add("pressure", tuple(u.id for u in units), ("directive_pressure",), min(0.99, directive_count / 20), "low", "High directive density is advisory only.")
    complex_units = tuple(u.id for u in units if u.condition or u.exception)
    if complex_units:
        add("complexity", complex_units, ("conditional_complexity", "branch_depth"), 0.7, "low", "Conditional or exception-heavy rules require mechanism review.")
    env_units = tuple(u.id for u in units if u.environment_qualifier)
    if len(env_units) >= 2:
        add("environment", env_units, ("environment_concentration", "environment_leakage"), 0.7, "low", "Environment-specific rules may indicate environment leakage.")
    workaround_units = tuple(u.id for u in units if re.search(r"workaround|temporary|hack|until\s+fixed|临时|绕过", u.normalized_meaning, re.I))
    if workaround_units:
        add("workaround", workaround_units, ("case_specific_patch_smell",), 0.75, "medium", "Workaround language suggests a case-specific prompt patch.")
    obsolete_units = tuple(u.id for u in units if _OBSOLETE.search(u.normalized_meaning))
    if obsolete_units:
        add(
            "obsolete-resource",
            obsolete_units,
            ("obsolete_resource",),
            0.8,
            "medium",
            "Rules reference potentially obsolete paths, commands, versions, or resources.",
        )
    mechanism_units = tuple(u.id for u in units if u.referenced_mechanism)
    if len(mechanism_units) >= 2:
        add("cross-layer", mechanism_units, ("cross_layer_duplication", "mechanism_substitution"), 0.65, "low", "Rules reference mechanisms that may already enforce the invariant.")
    if history is None:
        add("history", (), ("historical_growth",), 0.0, "low", "Git history unavailable; growth check skipped.", limitations=("missing Git history",), evidence_refs=("git-history:unavailable",))
    elif len(history.rule_counts) >= 2 and history.rule_counts[-1] > history.rule_counts[0]:
        add("growth", tuple(u.id for u in units), ("historical_growth",), 0.8, "medium", "Rule count increased across available history.")
    return tuple(findings)
