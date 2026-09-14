"""Deterministic structural checks for Skill artifacts."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from engine.models import ArtifactManifest, CheckResult, CheckStatus, LifecycleState

_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PLACEHOLDER_PATTERN = re.compile(r"\b(?:TODO|TBD|FIXME|PLACEHOLDER|IMPLEMENT[_ -]?ME)\b", re.IGNORECASE)


def _result(check_id: str, subject: str, status: CheckStatus, required: bool, evidence: str) -> CheckResult:
    return CheckResult(check_id, "internal.structure", subject, required, status, True, True,
                       1.0 if status is CheckStatus.PASS else 0.95,
                       (evidence,), LifecycleState.VALIDATED, subject)


def _frontmatter(skill_path: Path) -> tuple[dict[str, object] | None, str | None]:
    try:
        text = skill_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return None, f"cannot read SKILL.md: {exc}"
    if not text.startswith("---"):
        return None, "frontmatter must start with ---"
    lines = text.splitlines()
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        return None, "frontmatter closing --- is missing"
    try:
        value = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as exc:
        return None, f"frontmatter YAML is invalid: {exc}"
    if not isinstance(value, dict):
        return None, "frontmatter must be a mapping"
    if not isinstance(value.get("name"), str) or not isinstance(value.get("description"), str):
        return None, "frontmatter requires string name and description"
    return value, None


def validate_skill_structure(manifest: ArtifactManifest) -> tuple[CheckResult, ...]:
    root = Path(manifest.artifact_root)
    subject = manifest.skill_name
    skill_path = root / "SKILL.md"
    exists = skill_path.is_file() and "SKILL.md" in manifest.files
    results = [_result("skill.structure.skill_md", subject, CheckStatus.PASS if exists else CheckStatus.FAIL,
                       True, "SKILL.md exists" if exists else "SKILL.md is missing")]
    frontmatter, frontmatter_error = _frontmatter(skill_path) if exists else (None, "SKILL.md unavailable")
    results.append(_result("skill.structure.frontmatter", subject,
                           CheckStatus.PASS if frontmatter_error is None else CheckStatus.FAIL,
                           True, "frontmatter is valid" if frontmatter_error is None else frontmatter_error))

    name = frontmatter.get("name") if frontmatter else None
    name_ok = isinstance(name, str) and bool(_NAME_PATTERN.fullmatch(name))
    results.append(_result("skill.structure.name_format", subject, CheckStatus.PASS if name_ok else CheckStatus.FAIL,
                           True, "name follows kebab-case" if name_ok else "name must use lowercase kebab-case"))
    agreement = name == manifest.skill_name
    results.append(_result("skill.structure.directory_name", subject,
                           CheckStatus.PASS if agreement else CheckStatus.FAIL, True,
                           "directory and frontmatter name agree" if agreement else "directory and name disagree"))

    files_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in root.rglob("*") if path.is_file())
    placeholders = _PLACEHOLDER_PATTERN.search(files_text)
    results.append(_result("skill.structure.placeholders", subject,
                           CheckStatus.FAIL if placeholders else CheckStatus.PASS, True,
                           f"placeholder token found: {placeholders.group(0)}" if placeholders else "no placeholder tokens found"))

    declared_assets = ()
    if frontmatter:
        raw = frontmatter.get("critical_assets", frontmatter.get("assets", ()))
        if isinstance(raw, str):
            declared_assets = (raw,)
        elif isinstance(raw, (list, tuple)):
            declared_assets = tuple(item for item in raw if isinstance(item, str))
    missing_assets = tuple(item for item in declared_assets if not (root / item).is_file())
    results.append(_result("skill.structure.critical_assets", subject,
                           CheckStatus.FAIL if missing_assets else CheckStatus.PASS, True,
                           "missing critical assets: " + ", ".join(missing_assets) if missing_assets else "critical assets verified"))

    schema_files = tuple(path for path in manifest.files if path.startswith("schemas/") and path.endswith(".schema.json"))
    missing_schema = frontmatter.get("required_schemas", ()) if frontmatter else ()
    if isinstance(missing_schema, str):
        missing_schema = (missing_schema,)
    missing_schema = tuple(item for item in missing_schema if isinstance(item, str) and not (root / item).is_file())
    results.append(_result("skill.structure.schema", subject,
                           CheckStatus.FAIL if missing_schema else CheckStatus.PASS, True,
                           "missing schema files: " + ", ".join(missing_schema) if missing_schema else f"schema files verified ({len(schema_files)})"))

    executable_ok = all(item in manifest.files for item in manifest.executable_assets)
    results.append(_result("skill.structure.executables", subject, CheckStatus.PASS if executable_ok else CheckStatus.FAIL,
                           True, "executable assets are inventoried" if executable_ok else "executable asset inventory mismatch"))

    dependencies = frontmatter.get("required_dependencies", frontmatter.get("dependencies", ())) if frontmatter else ()
    if isinstance(dependencies, str):
        dependencies = (dependencies,)
    dependencies = tuple(item for item in dependencies if isinstance(item, str))
    missing_dependencies = tuple(item for item in dependencies if not (root / item).exists())
    results.append(_result("skill.structure.required_dependencies", subject,
                           CheckStatus.FAIL if missing_dependencies else CheckStatus.PASS, True,
                           "missing required dependencies: " + ", ".join(missing_dependencies) if missing_dependencies else "required dependencies verified"))
    return tuple(results)
