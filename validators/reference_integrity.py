"""Deterministic Markdown reference checks."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from engine.models import ArtifactManifest, CheckResult, CheckStatus, LifecycleState

_LINK_PATTERN = re.compile(r"!?(?:\[[^\]]*\])\(([^)\s]+)(?:\s+['\"][^)]*['\"])?\)")


def _result(check_id: str, subject: str, required: bool, status: CheckStatus, evidence: str) -> CheckResult:
    return CheckResult(check_id, "internal.reference", subject, required, status, True, True,
                       1.0 if status is CheckStatus.PASS else 0.95, (evidence,), LifecycleState.VALIDATED, subject)


def validate_references(manifest: ArtifactManifest) -> tuple[CheckResult, ...]:
    root = Path(manifest.artifact_root)
    links: list[tuple[str, str]] = []
    for relative in manifest.files:
        if not relative.lower().endswith((".md", ".markdown")):
            continue
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for target in _LINK_PATTERN.findall(text):
            parsed = urlparse(target)
            if parsed.scheme or target.startswith("#"):
                continue
            links.append((relative, unquote(parsed.path)))
    linked_targets = {target.replace("\\", "/").lstrip("./") for _, target in links}
    for required_reference in manifest.required_references:
        normalized = required_reference.replace("\\", "/").lstrip("./")
        if normalized not in linked_targets:
            links.append(("<manifest>", normalized))
    if not links:
        return (_result("reference.integrity", manifest.skill_name, False, CheckStatus.PASS, "no local Markdown references"),)
    results: list[CheckResult] = []
    resolved_root = root.resolve(strict=False)
    for source, target in links:
        normalized = target.replace("\\", "/").lstrip("./")
        resolved = (root / source).parent / normalized
        is_required = normalized in manifest.required_references or normalized.startswith("references/")
        try:
            in_scope = resolved.resolve(strict=False).is_relative_to(resolved_root)
        except (OSError, ValueError):
            in_scope = False
        exists = in_scope and resolved.is_file()
        check_id = "reference.required.exists" if is_required else "reference.optional.exists"
        status = CheckStatus.PASS if exists else (CheckStatus.FAIL if is_required else CheckStatus.WARN)
        if not in_scope:
            evidence = f"{source} -> {normalized} escapes artifact root"
        else:
            evidence = f"{source} -> {normalized} exists" if exists else f"{source} -> {normalized} is missing"
        results.append(_result(check_id, f"{source}:{normalized}", is_required, status, evidence))
    return tuple(results)
