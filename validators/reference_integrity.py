"""Deterministic Markdown reference checks."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml

from engine.models import ArtifactManifest, CheckResult, CheckStatus, LifecycleState

_LINK_PATTERN = re.compile(r"!?(?:\[[^\]]*\])\(([^)\s]+)(?:\s+['\"][^)]*['\"])?\)")


def _result(check_id: str, subject: str, required: bool, status: CheckStatus, evidence: str) -> CheckResult:
    return CheckResult(check_id, "internal.reference", subject, required, status, True, True,
                       1.0 if status is CheckStatus.PASS else 0.95, (evidence,), LifecycleState.VALIDATED, subject)


def _remove_current_directory_prefix(target: str) -> str:
    return target[2:] if target.startswith("./") else target


def _resolve(root: Path, source: str, target: str) -> tuple[Path, str | None]:
    base = root if source == "<manifest>" else (root / source).parent
    resolved_root = root.resolve(strict=False)
    resolved = (base / _remove_current_directory_prefix(target)).resolve(strict=False)
    try:
        return resolved, resolved.relative_to(resolved_root).as_posix()
    except ValueError:
        return resolved, None


def _frontmatter_required_paths(root: Path) -> set[str]:
    skill_path = root / "SKILL.md"
    try:
        lines = skill_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return set()
    if not lines or lines[0].strip() != "---":
        return set()
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
        frontmatter = yaml.safe_load("\n".join(lines[1:end]))
    except (StopIteration, yaml.YAMLError):
        return set()
    if not isinstance(frontmatter, dict):
        return set()
    paths: set[str] = set()
    for key in ("critical_assets", "required_references"):
        values = frontmatter.get(key, ())
        if isinstance(values, str):
            values = (values,)
        if not isinstance(values, (list, tuple)):
            continue
        for value in values:
            if isinstance(value, str):
                _, relative = _resolve(root, "<manifest>", value.replace("\\", "/"))
                if relative is not None:
                    paths.add(relative)
    return paths


def validate_references(manifest: ArtifactManifest) -> tuple[CheckResult, ...]:
    root = Path(manifest.artifact_root)
    links: list[tuple[str, str]] = []
    for source in manifest.files:
        if not source.lower().endswith((".md", ".markdown")):
            continue
        try:
            text = (root / source).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for target in _LINK_PATTERN.findall(text):
            parsed = urlparse(target)
            if not parsed.scheme and not target.startswith("#"):
                links.append((source, unquote(parsed.path).replace("\\", "/")))

    required_paths = _frontmatter_required_paths(root)
    for required_reference in manifest.required_references:
        _, relative = _resolve(root, "<manifest>", required_reference.replace("\\", "/"))
        if relative is not None:
            required_paths.add(relative)
    linked_paths = {_resolve(root, source, target)[1] for source, target in links}
    for required_reference in sorted(required_paths - linked_paths):
        links.append(("<manifest>", required_reference))
    if not links:
        return (_result("reference.integrity", manifest.skill_name, False, CheckStatus.PASS, "no local Markdown references"),)

    results: list[CheckResult] = []
    seen: set[tuple[str, str]] = set()
    for source, target in links:
        resolved, relative = _resolve(root, source, target)
        identity = (source, relative if relative is not None else target)
        if identity in seen:
            continue
        seen.add(identity)
        is_required = relative in required_paths if relative is not None else False
        if relative is not None and relative.startswith("references/"):
            is_required = True
        check_id = "reference.required.exists" if is_required else "reference.optional.exists"
        exists = relative is not None and resolved.is_file()
        status = CheckStatus.PASS if exists else (CheckStatus.FAIL if is_required else CheckStatus.WARN)
        subject_target = relative if relative is not None else target
        if relative is None:
            evidence = f"{source} -> {target} escapes artifact root"
        else:
            evidence = f"{source} -> {relative} exists" if exists else f"{source} -> {relative} is missing"
        results.append(_result(check_id, f"{source}:{subject_target}", is_required, status, evidence))
    return tuple(results)
