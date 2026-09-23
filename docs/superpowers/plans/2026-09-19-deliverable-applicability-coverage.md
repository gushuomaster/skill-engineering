# Deliverable Applicability and Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent absent deliverable inspection from being represented as a full successful audit by separating applicability, validation, and coverage.

**Architecture:** Codex supplies deliverable-contract applicability through inspection context. Capability preflight materializes that semantic choice even when no Provider or contract exists; deterministic validation derives coverage and structured provenance, while the existing Gate remains the sole advancement authority.

**Tech Stack:** Python 3.11+, dataclasses, JSON Schema 2020-12, pytest.

**Spec:** `C:\Users\28320\.codex\attachments\f5eacb6d-1ce5-42db-a0c1-09bfafbfd5d7\pasted-text.txt`

## Global Constraints

- Modify only `D:\project\skill-engineering`.
- Do not invoke the `skill-engineering` Skill under review.
- Do not infer applicability from keywords, filenames, or document-domain identifiers.
- Preserve legacy APIs and schemas with optional fields and an explicit compatibility default.
- Preserve Provider availability, selection, and execution as distinct facts.
- Do not modify the real target Skill during Audit Only validation.

---

### Task 1: Lock the state matrix with failing tests

**Files:**
- Modify: `tests/integration/test_deliverable_contract_pipeline.py`
- Modify: `tests/unit/test_deliverable_contract.py`
- Modify: `tests/unit/test_contracts.py`

**Interfaces:**
- Consumes existing `PipelineOrchestrator.inspect`, Provider Gateway, and contract validator.
- Produces regression expectations for applicability, coverage, provenance, Gate outcome, and legacy mode.

- [x] Add REQUIRED missing/unexecuted, OPTIONAL missing, NOT_REQUIRED missing, valid, stale, path escape, partial-output, and legacy compatibility tests.
- [x] Run the focused tests and verify failures identify absent applicability/coverage/provenance fields and incorrect complete-audit mapping.

### Task 2: Add typed applicability, coverage, and provenance

**Files:**
- Modify: `engine/models.py`
- Modify: `engine/serialization.py`
- Modify: `schemas/inspection-bundle.schema.json`
- Modify: `schemas/validation-bundle.schema.json`
- Modify: `schemas/gate-result.schema.json`

**Interfaces:**
- Produces `DeliverableContractApplicability`, `CoverageStatus`, and structured deliverable provenance records.
- Legacy deserialization defaults applicability and coverage to `COMPATIBILITY`.

- [x] Add minimal immutable enums and provenance record.
- [x] Add optional schema properties and compatibility defaults.
- [x] Run contract serialization tests.

### Task 3: Make applicability drive capability resolution

**Files:**
- Modify: `engine/capabilities.py`
- Modify: `engine/orchestrator.py`
- Modify: `engine/deliverable_contract.py`

**Interfaces:**
- `build_capability_preflight(..., deliverable_contract_applicability=...)` always materializes the dimension.
- Required missing evidence becomes required `NOT_EXECUTED`; optional missing evidence remains optional; not-required evidence is explicitly not applicable.

- [x] Pass applicability into Provider requests and capability preflight.
- [x] Derive structured Provider/contract provenance without conflating selected and executed.
- [x] Emit declared/verified/missing deliverable counts.
- [x] Run focused state-matrix tests.

### Task 4: Separate validation from coverage at the Gate

**Files:**
- Modify: `engine/quality_gate.py`
- Modify: `engine/orchestrator.py`
- Modify: `schemas/gate-result.schema.json`

**Interfaces:**
- Gate results expose coverage independently from verdict.
- `AUDIT_COMPLETE_VALID` requires `CoverageStatus.FULL`.
- Required non-full coverage cannot authorize apply/publication.

- [x] Derive `FULL`, `PARTIAL`, or `COMPATIBILITY` from applicability and verified contract evidence.
- [x] Prevent partial/compatibility successful audit results from using `AUDIT_COMPLETE_VALID`.
- [x] Add defense-in-depth advancement blocking for required non-full coverage.
- [x] Run Gate and workflow tests.

### Task 5: Expose context through CLI and verify

**Files:**
- Modify: `scripts/skill_engineering.py`
- Modify: `skills/skill-engineer/references/pipeline.md`
- Modify: `skills/skill-engineer/references/required-capabilities.md`

**Interfaces:**
- Adds optional `--deliverable-contract-applicability` to inspection and legacy execution.
- Omission selects explicit compatibility mode.

- [x] Add CLI parsing and round-trip tests.
- [x] Run focused tests, the full suite, and Skill validation.
- [x] Run two real read-only scenarios and confirm target digest stability.
