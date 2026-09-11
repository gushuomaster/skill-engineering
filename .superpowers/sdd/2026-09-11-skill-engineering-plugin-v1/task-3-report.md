# Task 3 Report

## Result

Implemented the non-linear lifecycle state machine with immutable transition context and guarded pure transitions.

## Covered behavior

- Create/Modify/Fix may stage before classification; Audit Only never stages or publishes.
- Audit Only supports the read-only `MECHANISM_SELECTED → AUDITED` path and unchanged outcomes.
- Gate failure supports remediation loops back to responsible stages.
- Publication requires authorization, staging, and same-cycle audit/validation freshness.
- Remediated candidates cannot publish directly from `STAGED`.
- Gate freshness requires a remediation cycle strictly newer than the last failed cycle.
- Audit + Optimize may return `UNCHANGED_VALIDATED` when no modification is needed.

## Verification

- `python -m pytest tests/unit/test_state_machine.py -v` — 16 passed.
- `python -m pytest tests/unit/test_contracts.py tests/unit/test_plugin_scaffold.py -q` — 28 passed.
- Changed files: `engine/state_machine.py`, `tests/unit/test_state_machine.py`, this report.

## Fix Round 1

### RED

Command: `python -m pytest tests/unit/test_state_machine.py -q`

The newly added counterexamples failed as expected before implementation:

- `TransitionContext` rejected the new `last_failed_cycle` positional value and `modification_needed` keyword because the fields did not exist yet (`TypeError`, 4 tests).
- Audit Only `DISCOVERED → CLASSIFIED` was rejected (`InvalidTransition`, 1 test).
- Create/Modify/Fix allowed `DISCOVERED → CLASSIFIED` despite staging-first (`DID NOT RAISE`, 3 parametrized cases).
- Same-cycle gate re-entry could not express the new cycle field (`TypeError`).

The explicit Audit Optimize unauthorized-staging counterexample did not fail in this RED run because the pre-existing Audit Optimize branch already removed `STAGED`; it remained a regression guard and was retained for the GREEN run.

Observed summary: `8 failed, 17 passed`.

### GREEN

- `python -m pytest tests/unit/test_state_machine.py -q` → `25 passed`.
- `python -m pytest tests/unit/test_contracts.py tests/unit/test_plugin_scaffold.py -q` → `28 passed`.

### Full suite

Command: `python -m pytest -q`.

Observed summary: `9 failed, 81 passed, 2 skipped`.
The failures were in parallel Task 4/5 worktree files (`engine/workspace.py`, `engine/inventory.py`, their integration/unit tests) plus the then-unfixed Task 3 counterexamples. After the Task 3 fixes, the Task 3 failures were green; the remaining full-suite failures belong to the concurrently developed, uncommitted Task 4/5 implementation and are outside Task 3 scope.

## Fix Round 2

### RED

Command: `python -m pytest tests/unit/test_state_machine.py -q`

Added counterexamples failed before the guards were tightened:

- Create/Modify/Fix could bypass staging through `DISCOVERED → AUDITED` (`DID NOT RAISE`, 3 parametrized cases).
- Audit Only and Audit + Optimize with `defect_found=True` could finish `GATE_PASSED → UNCHANGED_VALIDATED` (`DID NOT RAISE`, 2 cases).
- Audit Only with `modification_needed=True` could finish unchanged (`DID NOT RAISE`, 1 case).

Observed summary: `6 failed, 27 passed`.

### GREEN

- `python -m pytest tests/unit/test_state_machine.py -q` → `33 passed`.
- `python -m pytest tests/unit/test_contracts.py tests/unit/test_plugin_scaffold.py -q` → `28 passed`.
- `python -m pytest -q` → `112 passed, 2 skipped`.

The two skips are Windows symlink tests skipped because the runtime lacks symlink privilege (`WinError 1314`); no test failure remains.

## Fix Round 3

### RED

Command: `python -m pytest tests/unit/test_state_machine.py -q`

Added staging-present indirect-bypass cases for Create/Modify/Fix. Before the fix, each could take `DISCOVERED → AUDITED` without using the staged state (`DID NOT RAISE`). Observed summary: `3 failed, 33 passed`.

### GREEN

- `python -m pytest tests/unit/test_state_machine.py -q` → `36 passed`.
- `python -m pytest tests/unit/test_contracts.py tests/unit/test_plugin_scaffold.py -q` → `28 passed`.
- `git diff --check` → passed.

Mutating flows now always remove `DISCOVERED → AUDITED` and `AUDITED → CLASSIFIED`; Audit Only retains its read-only classification/audit path.

## Fix Round 4

### RED

Added a regression for Audit + Optimize's delayed-staging read-only audit path:

- With `staging_exists=False`, `DISCOVERED → AUDITED → CLASSIFIED` must remain legal.
- `DISCOVERED → STAGED` remains forbidden until the orchestrator creates staging after confirming modification is needed.

Before the implementation fix, the new test failed at `DISCOVERED → AUDITED` (`InvalidTransition`); observed summary: `1 failed, 36 passed`.

### GREEN

- `python -m pytest tests/unit/test_state_machine.py -q` → `37 passed`.
- `python -m pytest tests/unit/test_contracts.py tests/unit/test_plugin_scaffold.py -q` → `28 passed`.
- `python -m pytest -q` → `116 passed, 2 skipped`.

The two skips are Windows symlink tests skipped because the runtime lacks symlink privilege (`WinError 1314`). The state-machine guard now applies staging-first bypass prevention only to Create/Modify/Fix; Audit + Optimize retains its pre-staging audit/classification path while still requiring an existing staging workspace before `STAGED` transitions.
