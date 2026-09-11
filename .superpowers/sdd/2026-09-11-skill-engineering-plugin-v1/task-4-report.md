# Task 4 Report: Inventory and Isolated Workspace Control

## Delivered

- Added deterministic UTF-8-safe tree digests and read-only `ArtifactManifest` inventory.
- Added scope escape protection for symbolic links and Windows reparse points.
- Added isolated Create, Modify, Fix, Audit Only, and delayed Audit + Optimize workspace behavior.
- Added source digest verification; atomic publication remains intentionally out of scope for Task 12.

## TDD Evidence

- Initial targeted test run failed because `engine.inventory` and `engine.workspace` did not exist.
- After the minimal implementation and additional boundary tests, Task 4 tests passed.

## Verification

```text
python -m pytest tests/unit/test_inventory.py tests/integration/test_workspace_isolation.py tests/unit/test_contracts.py tests/unit/test_plugin_scaffold.py tests/unit/test_state_machine.py -v
57 passed, 2 skipped
```

The two skipped tests require Windows symlink creation privileges, unavailable in this environment. The implementation still checks both symlinks and reparse points.

`git diff --check` and UTF-8 no-BOM checks passed for Task 4 files.
