from engine.models import CapabilityChange, CapabilityChangeKind, CapabilityDiff
from engine.workspace import WorkspaceDiff, build_semantic_workspace_diff


def test_semantic_workspace_diff_uses_structured_capability_changes() -> None:
    file_changes = WorkspaceDiff(
        added=("docs/new.md",),
        modified=("SKILL.md", "scripts/run.py"),
        deleted=("tests/test_old.py",),
    )
    capability_diff = CapabilityDiff(
        "a" * 64,
        "b" * 64,
        (
            CapabilityChange(
                "STD",
                CapabilityChangeKind.REMOVED,
                ("capability",),
                ("capability=STD",),
                (),
            ),
        ),
    )

    result = build_semantic_workspace_diff(file_changes, capability_diff)

    assert result.file_changes is file_changes
    assert result.capability_changes == capability_diff.changes
    assert result.declaration_changes == ("STD:REMOVED",)
    assert result.entrypoint_changes == ()
    assert result.schema_changes == ()
    assert result.template_changes == ()
    assert result.test_coverage_changes == ()


def test_file_names_do_not_create_semantic_capability_changes() -> None:
    result = build_semantic_workspace_diff(
        WorkspaceDiff((), ("templates/STD.docx",), ("schemas/STR.json",)),
        None,
    )

    assert result.capability_changes == ()
    assert result.declaration_changes == ()
    assert result.schema_changes == ()
    assert result.template_changes == ()
