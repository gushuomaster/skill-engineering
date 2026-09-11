# Task 2 Report — Contract Models and JSON Schemas

## Status

Implemented immutable contract models, schema loading/validation, nine Draft 2020-12 schemas, and positive/negative fixtures.

## TDD Evidence

- RED: `python -m pytest tests/unit/test_contracts.py -v` initially failed during collection with `ModuleNotFoundError: No module named 'engine.contracts'`.
- GREEN: `python -m pytest tests/unit/test_contracts.py -v` → `21 passed`.
- Regression: `python -m pytest -v` → `23 passed`.
- Hygiene: `git diff --check` → no output.

## Files

- `engine/models.py`
- `engine/contracts.py`
- `schemas/*.schema.json` (nine schemas)
- `tests/unit/test_contracts.py`
- `tests/fixtures/contracts/*.json`

## Self-review

Conditional contracts enforce existing-source digests, defect root causes, provider authority boundaries, and publication authorization. Provider results use `additionalProperties: false`; gate publication requires PASS + READY_TO_PUBLISH, while FAIL and UNCHANGED_VALIDATED prohibit publication. Text files are UTF-8 without BOM.

## Commit

`feat: define skill engineering contracts`

## Fix Round 1

### RED

Command: `python -m pytest tests/unit/test_contracts.py -q`

Output: `4 failed, 21 passed`. The failures proved that a Modify implementation defect without root cause, FAIL plus READY_TO_PUBLISH, empty SKIP evidence, and an unknown remediation stage were accepted.

### GREEN and verification

- `python -m pytest tests/unit/test_contracts.py -q` → `25 passed in 0.08s`
- `python -m pytest -q` → `27 passed in 0.07s`
- `git diff --check` → no whitespace errors

The schemas now require root causes for all existing-source defect classes, use non-empty `evidence` as the explicit SKIP/NOT_EXECUTED reason field, restrict check remediation stages to lifecycle states, make READY_TO_PUBLISH exactly PASS plus authorized, prohibit authorization for every other outcome, and require all B01–B12 core blocking policy IDs while preserving extensible project fields.

### Fix commit

`fix: tighten frozen contract invariants`
