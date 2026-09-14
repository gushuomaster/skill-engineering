# Task 11 Report — Provider Ports, Identity Policy, Internal Fallbacks

## Outcome

- Added invocation-neutral `ProviderAdapter` and `ProviderGateway` capability ports.
- Added normalized, schema-validated Provider results with forbidden final-authority fields rejected.
- Formal runs skip unpinned/degraded Providers; unavailable, invalid, timeout, incompatible, and formal degraded results use internal fallbacks.
- Added deterministic V1 fallbacks for candidate creation, Skill audit, AGENTS/CLAUDE governance, and structure conformance.
- Added disabled external Provider candidate configuration in `config/providers.yaml`.

## TDD Evidence

- RED: targeted Provider tests failed during collection because `engine.providers` was missing.
- GREEN: `python -m pytest tests/unit/test_providers.py tests/integration/test_provider_fallback.py -v` — **17 passed**.

## Regression Verification

`python -m pytest -q` — **233 passed, 2 skipped** (Windows symlink privilege skips).

## Commit

Provider implementation was recorded in `39f790f` (`feat: add replaceable skill providers`); this report is finalized separately because concurrent tasks advanced the shared branch.

## Scope

No Task 12 publication or recovery behavior was added.

## Fix Round 1

- Formal Provider runs now require a non-blank `source_identity` and `revision_or_version`; blank or whitespace-only values use the internal fallback.
- Fallback results set `fallback_used=True` whenever a configured fallback is invoked, while an explicitly empty fallback is represented as an optional unavailable result rather than an exception.
- The orchestrator can receive a `ProviderGateway`; normalized Provider results are adapted to optional `CheckResult` evidence, collected by `EvidenceCollector`, and evaluated by the Quality Gate. Provider findings and limitations remain advisory warnings and cannot supply a final verdict.
- Reverted the unrelated Task11 change to `engine/rule_bloat.py`.

### Fix Verification

- `python -m pytest tests/unit/test_providers.py tests/integration/test_provider_fallback.py -q` — **26 passed**.
- `python -m pytest tests/integration/test_minimal_pipeline.py -q` — **9 passed**.
- `python -m pytest -q` — **253 passed, 2 skipped** (Windows symlink privilege skips).

### Hygiene Verification

- `engine/rule_bloat.py` now matches the Task9-approved `_DIRECTIVE` definition from `fba2111`; the later Task9 governance changes from `ab39827` remain intact.
- `python -m pytest tests/unit/test_providers.py tests/integration/test_provider_fallback.py tests/unit/test_rule_bloat.py tests/unit/test_rule_governance.py tests/integration/test_rule_governance_pipeline.py -q` — **36 passed**.
- `git diff --check` — **clean**.

## Fix Round 2

- Merged caller-supplied `fallbacks` over the complete internal fallback map, so overriding one capability preserves mandatory internal fallbacks for the other capabilities.
- Guarded configured fallback invocation and result normalization; exceptions now return an optional `UNAVAILABLE` `ProviderResult` carrying the failure as a limitation instead of crashing the gateway.
- Added unit regressions for fallback-map merging and both fallback failure paths.
- Preserved the Task9 `rule_bloat` baseline; no changes were made to `engine/rule_bloat.py`.

### Fix Round 2 Verification

- RED: the three new tests failed against the pre-fix gateway (missing defaults and uncaught fallback exceptions).
- GREEN: `python -m pytest tests/unit/test_providers.py tests/integration/test_provider_fallback.py -q` — **29 passed**.
- Full suite: `python -m pytest -q` — **256 passed, 2 skipped** (Windows symlink privilege skips).
- `git diff --check` — **clean**.
