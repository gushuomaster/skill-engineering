# Task 8 Report — Minimal Runnable Governance Loop

## Outcome

Implemented the internal-only Create, Modify, Fix, Audit Only, and Audit + Optimize governance loop.

- Added `engine/orchestrator.py` with explicit lifecycle transitions, isolated workspace handling, internal diagnostics/mechanism selection, validators, evidence collection through Gate inputs, and explicit project-policy loading.
- Added `engine/output.py` with the two legal output projections only.
- Added `scripts/skill_engineering.py` with the frozen flags and exit codes (`0` PASS, `2` Audit Only FAIL, `1` blocked/error).
- Added end-to-end and CLI integration coverage for legal outputs and staging-first behavior.

## TDD Evidence

- RED: `python -m pytest tests/integration/test_minimal_pipeline.py -q` failed during collection because `engine.orchestrator` did not exist.
- GREEN: `python -m pytest tests/integration/test_cli.py tests/integration/test_minimal_pipeline.py -q` — **9 passed**.

## Regression Verification

`python -m pytest -q` — **200 passed, 2 skipped**. Skips are Windows symlink tests requiring privileges.

## Commit

`3037269 feat: run minimal skill governance pipeline`

Follow-up correctness fix: `19b3978 fix: return valid staged artifacts for change flows`.

Fix-round correction: Audit + Optimize now defers its final Gate transition while read-only audit establishes modification need, then stages and re-runs validation/Gate; synthetic B07 PASS evidence was removed so defect flows without a regression runner remain blocked.

Fix-round verification: Task 8 integration tests — **8 passed**; full suite — **202 passed, 2 skipped**.

Fix Round 2: `optimization_needed` now derives only from supplied failure/defect evidence; requirement wording alone keeps Audit + Optimize read-only. The needed-case test supplies evidence, while the no-evidence case asserts no staging and no publication authority. Verification: Task 8 integration tests — **9 passed**; full suite — **203 passed, 2 skipped**.

## Concerns / Deferred Scope

- Candidate generation is intentionally minimal and internal; no Rule Bloat, regression enhancement, Provider, or atomic publication behavior is included.
- Mutating operations return the validated isolated candidate path; publication remains deferred to the later workspace/publication task.
- Audit + Optimize copies an unchanged source when the initial audit fails and authorization is present; later remediation tasks can add candidate edits.
