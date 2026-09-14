from pathlib import Path

from engine.inventory import build_artifact_manifest
from engine.models import CheckStatus, Intent
from validators.skill_structure import validate_skill_structure


def _check(results, check_id):
    return next(result for result in results if result.check_id == check_id)


def test_missing_skill_md_is_required_failure(tmp_path: Path) -> None:
    manifest = build_artifact_manifest(tmp_path, Intent.CREATE, None)
    result = _check(validate_skill_structure(manifest), "skill.structure.skill_md")
    assert result.status is CheckStatus.FAIL
    assert result.required is True


def test_invalid_frontmatter_and_placeholder_are_failures(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("---\nname: Bad Name\n---\nTODO\n", encoding="utf-8")
    manifest = build_artifact_manifest(tmp_path, Intent.CREATE, None)
    results = validate_skill_structure(manifest)
    assert _check(results, "skill.structure.frontmatter").status is CheckStatus.FAIL
    assert _check(results, "skill.structure.name_format").status is CheckStatus.FAIL
    assert _check(results, "skill.structure.placeholders").status is CheckStatus.FAIL


def _valid_skill(root: Path) -> None:
    (root / "SKILL.md").write_text(
        "---\nname: example-skill\ndescription: Example\n---\n\nComplete.\n",
        encoding="utf-8",
    )


def _placeholder_check(root: Path):
    manifest = build_artifact_manifest(root, Intent.CREATE, None)
    return _check(validate_skill_structure(manifest), "skill.structure.placeholders")


def test_third_party_venv_tbd_does_not_block(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    path = tmp_path / ".venv.stale-20260821-125147" / "Lib" / "site-packages" / "PIL" / "ImageMorph.py"
    path.parent.mkdir(parents=True)
    path.write_text("# TBD: generated package note\n", encoding="utf-8")
    assert _placeholder_check(tmp_path).status is CheckStatus.PASS


def test_bundled_runtime_todo_does_not_block(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    path = tmp_path / ".runtime" / "cpython-3.9.7-windows-x86_64" / "Lib" / "stdlib.py"
    path.parent.mkdir(parents=True)
    path.write_text("# TODO: runtime implementation\n", encoding="utf-8")
    assert _placeholder_check(tmp_path).status is CheckStatus.PASS


def test_generated_bytecode_does_not_block(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    path = tmp_path / "scripts" / "__pycache__" / "check.cpython-311.pyc"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"PLACEHOLDER\x00")
    assert _placeholder_check(tmp_path).status is CheckStatus.PASS


def test_skill_md_tbd_blocks(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    (tmp_path / "SKILL.md").write_text(
        "---\nname: example-skill\ndescription: Example\n---\nTBD\n",
        encoding="utf-8",
    )
    result = _placeholder_check(tmp_path)
    assert result.status is CheckStatus.FAIL
    assert any("SKILL.md:5: TBD" in evidence for evidence in result.evidence)


def test_reference_todo_blocks(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    path = tmp_path / "references" / "output-contract.md"
    path.parent.mkdir()
    path.write_text("line one\nTODO\n", encoding="utf-8")
    result = _placeholder_check(tmp_path)
    assert result.status is CheckStatus.FAIL
    assert any("references/output-contract.md:2: TODO" in evidence for evidence in result.evidence)


def test_authoritative_script_placeholder_is_detected(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    path = tmp_path / "scripts" / "check.py"
    path.parent.mkdir()
    path.write_text("# FIXME: implement check\n", encoding="utf-8")
    result = _placeholder_check(tmp_path)
    assert result.status is CheckStatus.FAIL
    assert any("scripts/check.py:1: FIXME" in evidence for evidence in result.evidence)


def test_third_party_placeholders_do_not_enter_b02_evidence(tmp_path: Path) -> None:
    _valid_skill(tmp_path)
    (tmp_path / "references").mkdir()
    (tmp_path / "references" / "guide.md").write_text("No marker here.\n", encoding="utf-8")
    package = tmp_path / "vendor" / "package.py"
    package.parent.mkdir()
    package.write_text("# PLACEHOLDER from vendored dependency\n", encoding="utf-8")
    result = _placeholder_check(tmp_path)
    assert result.status is CheckStatus.PASS
    assert all("vendor/" not in evidence for evidence in result.evidence)
