# Deliverable Contract Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make declared deliverables a first-class, evidence-bound Required Capability so cross-layer output contradictions cannot receive a complete audit PASS.

**Architecture:** A Codex-selected Provider returns a typed deliverable-contract payload bound to the current inspection, nonce, and target digest. Deterministic Core validates schema, identity, paths, freshness, and per-deliverable behavioral evidence; the Quality Gate adjudicates the resulting capability without interpreting business semantics. Existing behavioral and regression runners remain reusable, while a contract runner validates independently declared output coverage.

**Tech Stack:** Python 3.11+, dataclasses, JSON Schema 2020-12, pytest, existing Provider Gateway and Quality Gate.

**Spec:** `C:\Users\28320\.codex\attachments\8c8715a3-44e5-425f-ac6b-eaef2a604dc6\pasted-text.txt`

## Global Constraints

- Modify only `D:\project\skill-engineering`.
- Preserve existing user changes and do not commit, push, tag, install, or publish.
- Do not hard-code the target document names or add keyword-driven document detection.
- Provider owns semantic contract extraction; Core owns typed evidence, paths, digests, execution, aggregation, and Gate decisions.
- Audit Only executes only in an isolated snapshot and proves source digest immutability.
- Target self-reports remain advisory and cannot substitute for plugin provenance.

---

### Task 1: Add failing contract-model and evidence tests

**Files:**
- Create: `tests/unit/test_deliverable_contract.py`
- Create: `tests/integration/test_deliverable_contract.py`
- Modify: `tests/unit/test_contracts.py`

**Interfaces:**
- Define the expected typed contract payload and finding codes in tests before implementation.
- Cover valid single/multi-output contracts, stale digest, nonce mismatch, invalid provider execution, escaped evidence paths, missing behavioral proof, self-report-only evidence, and explicit not-applicable evidence.

- [ ] Write tests that construct a Provider result with `deliverables`, target digest, inspection nonce, and provider identity.
- [ ] Add tests proving `implemented` outputs require declaration, exposure, implementation, artifact, and behavioral proof.
- [ ] Add tests proving missing execution evidence yields `INCOMPLETE`, while a verified contradiction yields `FAIL`.
- [ ] Run the focused tests and confirm they fail because the contract types and validator do not exist.

### Task 2: Implement typed deliverable-contract schema and models

**Files:**
- Create: `schemas/deliverable-contract.schema.json`
- Modify: `schemas/provider-result.schema.json`
- Modify: `engine/models.py`
- Modify: `engine/contracts.py`
- Modify: `engine/providers.py`
- Modify: `engine/serialization.py`

**Interfaces:**
- Add immutable records for contract evidence, deliverable status, exposure, implementation, behavioral proof, applicability, and scope conflicts.
- Extend normalized Provider results with optional contract payload while preserving existing Provider authority restrictions.
- Validate `inspection_id`, `target_digest`, `inspection_nonce`, provider identity, and contract payload through the existing schema loader.

- [ ] Add enums and dataclasses with explicit status values and no target-specific identifiers.
- [ ] Extend Provider normalization to reject malformed or authority-bearing contract fields.
- [ ] Add serialization/deserialization and schema fixtures for valid and invalid contract evidence.
- [ ] Run focused model/schema tests and confirm they pass.

### Task 3: Add deterministic contract validator and contract runner

**Files:**
- Create: `validators/deliverable_contract.py`
- Create: `engine/contract_runner.py`
- Modify: `engine/evidence.py`

**Interfaces:**
- `validate_deliverable_contract(contract, manifest, inspection_context, provider_context, command_results)` returns typed `CheckResult` records.
- `run_contract_checks(plan, artifact, runner)` executes only declared commands in an isolated artifact and verifies expected artifacts.

- [ ] Validate schema, provider execution, identity, nonce, digest, path scope, and evidence freshness.
- [ ] Emit stable finding codes for conflicts, missing exposure, dispatch, generation, behavioral proof, stale evidence, and self-report-only evidence.
- [ ] Treat a generic test command as insufficient unless its evidence names every covered deliverable.
- [ ] Return `NOT_EXECUTED`/`INCOMPLETE` when no safe contract command is supplied; never guess commands.
- [ ] Run focused validator and isolation tests.

### Task 4: Register the Required Capability and prove fallback equivalence

**Files:**
- Modify: `engine/capabilities.py`
- Modify: `engine/equivalence_contracts.py`
- Modify: `validators/capability_fallbacks.py`
- Modify: `config/gate-policy.yaml`
- Modify: `tests/unit/test_capabilities.py`
- Modify: `tests/unit/test_equivalence_contracts.py`

**Interfaces:**
- Add `DELIVERABLE_CONTRACT` as a Required Capability for full audits when a contract is evidenced or applicability is unresolved.
- Add an explicit Provider port and fallback-equivalence dimensions for declaration, exposure, implementation, artifacts, behavior, conflict, and provenance.

- [ ] Ensure unproven legacy FULL declarations are downgraded to PARTIAL/NONE automatically.
- [ ] Ensure provider unavailable/not executed and unknown applicability produce `INCOMPLETE`.
- [ ] Ensure only evidence-backed `NOT_APPLICABLE` can pass this capability.
- [ ] Run capability and equivalence tests.

### Task 5: Bind the capability into inspect, validate, confirm, and provenance

**Files:**
- Modify: `engine/orchestrator.py`
- Modify: `engine/quality_gate.py`
- Modify: `engine/state_machine.py`
- Modify: `schemas/inspection-bundle.schema.json`
- Modify: `schemas/validation-bundle.schema.json`
- Modify: `schemas/gate-result.schema.json`
- Modify: `scripts/skill_engineering.py`

**Interfaces:**
- Generate and persist an inspection nonce and engine provenance at inspect time.
- Pass the exact inspection context and target digest into Provider requests and deterministic validation.
- Store executed phases, available/selected/executed Providers, required capabilities, capability results, and contract evidence in inspection and validation bundles.

- [ ] Add `contract_runner` as an optional explicit runner without changing existing runner semantics.
- [ ] Make full audit fail closed when the required contract capability is FAIL or INCOMPLETE.
- [ ] Keep target self-reported files advisory and identify them as `target_self_report`.
- [ ] Verify Audit Only source digest before and after isolated execution.
- [ ] Run orchestrator, provenance, Gate, and Audit Only tests.

### Task 6: Add generic regression fixtures and real read-only dogfooding

**Files:**
- Create: `tests/fixtures/skills/deliverable-contract-*` fixtures as needed
- Modify: `tests/integration/test_product_semantics.py`
- Create: `tests/integration/test_deliverable_contract_pipeline.py`

**Interfaces:**
- Test generic names such as `alpha`, `beta`, and `gamma`, never the real document identifiers.
- Exercise declaration/exposure/dispatch/artifact/behavior mismatches, stale provider evidence, self-reported validation output, and complete single/multi-output contracts.

- [ ] Run the new focused and integration tests.
- [ ] Run the full suite and record skipped tests with reasons.
- [ ] Run Audit Only against `D:\project\skills\test3\.hypercode\skills\gjb438c-document-engineering` without modifying it.
- [ ] Record inspection ID, target digest, Provider execution, capability state, findings, Gate result, and before/after digest.
- [ ] Run `git status --short` and `git diff --stat`; confirm no target or unrelated repository changes.
