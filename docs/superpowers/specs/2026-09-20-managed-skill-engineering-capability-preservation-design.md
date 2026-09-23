# Managed Skill Engineering and Capability Preservation Design

## 1. Problem Statement

The installed plugin can be invoked as a prompt-level Skill while its engineering engine remains optional in practice. A Codex task can directly edit a target Skill, run the target's own tests, and report completion without producing an inspection, validation bundle, semantic confirmation, coverage result, or Quality Gate result.

The current deliverable contract protects a single inspected artifact when the capability is explicitly selected and executed. It does not establish a semantic baseline for a repair, compare the baseline with the candidate, or require authorization when public capabilities are removed or narrowed. A candidate can therefore become internally consistent by deleting declarations, entrypoints, implementation, and tests together.

This design makes formal skill-engineering results engine-managed, adds evidence-backed capability baselines and semantic diffs, and blocks unapproved capability regressions. It does not claim to provide a platform-level filesystem interception hook.

## 2. Design Principles

1. Codex remains the semantic decision authority for intent, issue classification, change rationale, and authorization interpretation.
2. Providers extract semantic facts and evidence. They do not decide Gate verdicts, authorization, publication, or apply.
3. The deterministic engine validates schemas, identity, digests, evidence boundaries, lifecycle state, capability diffs, authorization records, and Gate policy.
4. A target Skill's own tests are behavioral evidence only. They cannot substitute for a skill-engineering inspection or Gate.
5. No capability is inferred from filenames, keyword counts, or a fixed domain catalog.
6. A capability may be removed or narrowed only after Codex records the change and binds explicit user authorization to the exact capability diff.
7. Backward compatibility may preserve read-only API use, but it cannot produce a formal complete audit or authorize apply.

## 3. Platform Boundary

The Codex plugin manifest exposes a Skill, not a mandatory write interception hook. The plugin cannot prevent every possible shell command or direct file edit made outside its engine.

The strongest enforceable contract is therefore:

- only the engine can produce a formal skill-engineering completion receipt;
- every formal completion receipt contains a verified inspection ID and digest-bound Gate evidence;
- direct or out-of-band changes are reported as `UNMANAGED_CHANGE` or `AUDIT_INCOMPLETE`;
- the Skill instructions must never describe unmanaged work as a completed skill-engineering audit or repair;
- `apply` remains the only engine-supported source replacement path.

The implementation must not claim platform-wide prevention of unmanaged writes.

## 4. Managed Operation Protocol

### 4.1 Canonical modes

The engine continues to use the canonical modes:

- `CREATE`
- `AUDIT`
- `AUDIT_REPAIR`
- `TARGETED_REPAIR`

Legacy Modify/Fix labels remain compatibility aliases only.

### 4.2 Required phase chain

Every formal operation starts with `inspect` and receives an `inspection_id`.

Mutating flows use:

```text
source
  -> inspect baseline
  -> create isolated candidate
  -> inspect candidate semantics
  -> validate
  -> confirm
  -> apply
```

Audit uses an engine-owned disposable snapshot and never accepts a candidate.

Create has no source baseline but still establishes an inspection, candidate manifest, capability records, validation bundle, semantic confirmation, and Gate result.

### 4.3 Formal operation record

A persisted managed operation record binds:

- `inspection_id`
- `operation_mode`
- source path and source snapshot digest when applicable
- candidate path and candidate snapshot digest when applicable
- `DecisionRecord`
- Provider discovery, selection, execution, and result records
- baseline and candidate Capability Manifests
- Capability Diff
- validation bundle digest
- semantic confirmation digest
- coverage status
- capability preservation result
- Quality Gate result
- apply result when requested

Each phase consumes the previous phase's serialized record and verifies its schema and digest chain. Missing or stale state cannot be reconstructed from the current directory and cannot authorize apply.

### 4.4 Managed completion receipt

The engine emits a final completion receipt only after `confirm`. It includes the inspection ID, target digests, required capability execution summary, coverage, capability preservation, Gate verdict, and final lifecycle state.

Without this receipt, the only valid result classifications are:

- `UNMANAGED_CHANGE`
- `AUDIT_INCOMPLETE`
- `APPLY_BLOCKED`

## 5. Default Semantic Provider

The plugin ships a dedicated read-only `capability-contract-provider` profile. It is a bundled Provider resource, not the skill-engineer workflow itself and not a user-facing repair authority.

The Provider runs in a read-only isolated Codex session and returns typed evidence for:

- public capabilities;
- deliverables and profiles;
- user entrypoints;
- implementation and dispatch paths;
- templates and schemas;
- validation coverage;
- public claim sources;
- confidence and unresolved facts.

The Provider result is bound to:

- `inspection_id`
- inspection nonce
- artifact role: `baseline` or `candidate`
- artifact digest
- Provider identity and Provider resource digest

Provider absence, non-selection, non-execution, crash, timeout, schema failure, stale evidence, or path escape becomes an explicit required-capability execution gap.

## 6. Applicability and Requiredness

Applicability is determined from explicit operation state and evidence-backed Provider facts, never from keyword matching.

### 6.1 Capability manifest extraction

Capability manifest extraction is required for every formal mutating operation because preservation cannot be proven without a baseline and candidate manifest.

For read-only audit, Codex supplies structured audit dimensions. A full audit includes capability and deliverable truthfulness by default. A targeted audit may exclude it only through an explicit `NOT_REQUIRED` decision with rationale and evidence.

### 6.2 Deliverable contract rules

- `AUDIT_REPAIR` and `TARGETED_REPAIR`: `DELIVERABLE_CONTRACT` is `REQUIRED` when the baseline Provider reports public deliverables, profiles, formats, commands, or output contracts. `UNKNOWN` is incomplete.
- `CREATE`: it is `REQUIRED` when the candidate Provider reports public deliverables or output contracts. `UNKNOWN` is incomplete.
- `AUDIT`: it is `REQUIRED` when structured audit dimensions include capabilities, deliverables, CLI/API entrypoints, templates, profiles, formats, or output coverage. A full audit includes these dimensions.
- `NOT_REQUIRED` requires an explicit Codex decision plus Provider evidence that no relevant public output contract exists in scope.
- `COMPATIBILITY` is accepted only for legacy read-only calls and never produces complete formal coverage or apply authorization.

The engine applies these deterministic rules to typed facts. The Provider supplies the facts but does not select the Gate outcome.

## 7. Capability Manifest

### 7.1 Capability record

Each manifest contains stable capability records with at least:

```text
capability_id
public_name
capability_type
declared_status
implementation_status
entrypoints
supported_profiles
supported_deliverables
templates
schemas
validation_coverage
public_claim_sources
implementation_evidence
confidence
```

Every semantic field is accompanied by evidence references inside the inspected artifact. The deterministic validator checks evidence paths, line references where available, artifact role, inspection identity, Provider identity, and artifact digest.

### 7.2 Manifest identity

The manifest digest is computed from a canonical serialization of validated capability records plus the inspected artifact digest. Provider-supplied digest values are not trusted until recomputed by the engine.

The inspection stores:

- `baseline_capabilities` and `baseline_capability_digest` for an existing source;
- `candidate_capabilities` and `candidate_capability_digest` for a candidate or created Skill.

## 8. Capability Diff

The engine compares validated manifests using stable capability IDs and structured fields. It does not reinterpret business meaning.

The diff contains:

- `added_capabilities`
- `preserved_capabilities`
- `modified_capabilities`
- `removed_capabilities`
- `narrowed_capabilities`
- `broken_capabilities`
- `unverifiable_capabilities`

Classification rules:

- baseline ID absent from candidate: `REMOVED`;
- supported deliverables, profiles, formats, entrypoints, schemas, templates, or public scope is a strict subset: `NARROWED`;
- declaration remains but implementation or required validation disappears: `BROKEN`;
- identity or preservation cannot be proven from valid evidence: `UNVERIFIABLE`;
- all public and implementation dimensions are retained: `PRESERVED`;
- a new candidate-only ID: `ADDED`;
- other evidence-backed changes without scope reduction: `MODIFIED`.

Deleting declarations, implementation, entrypoints, and tests together still produces `REMOVED` because the baseline manifest is immutable and independently retained.

## 9. DecisionRecord Extension

`DecisionRecord` gains a structured capability-change decision containing:

```text
baseline_capability_digest
candidate_capability_digest
capability_changes
removed_capability_ids
narrowed_capability_ids
change_rationale
user_authorization_required
user_authorization_status
authorization_evidence
compatibility_impact
migration_plan
deprecation_plan
```

Each change is classified by Codex as one of:

- bug fix;
- implementation completion;
- declaration correction;
- capability removal;
- capability narrowing;
- intentional breaking change.

The engine verifies that the DecisionRecord covers every diff item and matches the two manifest digests. It does not invent missing decisions.

Removal, narrowing, and intentional breaking changes require authorization bound to the exact affected capability IDs. Authorization evidence must reference the user-approved change. Migration and deprecation plans are required when compatibility impact is not `NONE`.

If a baseline declares five deliverables while only one is implemented, Codex must explicitly record one of:

1. complete the missing implementation;
2. prove with evidence that the other declarations were never valid public capabilities;
3. request and record user authorization for capability reduction.

The engine never defaults to option 3.

## 10. Workspace Evidence

The existing file-level `WorkspaceDiff` remains. A new semantic workspace record adds:

- `file_changes`
- `declaration_changes`
- `entrypoint_changes`
- `schema_changes`
- `template_changes`
- `test_coverage_changes`
- `capability_changes`

The source snapshot and baseline Capability Manifest are captured before candidate authoring. Candidate extraction occurs only from the engine-staged candidate. Evidence from sibling copies, previous outputs, or another candidate cannot satisfy the current inspection because artifact role and digest binding differ.

Source and candidate digest checks run at staging, validation, confirmation, and apply. Any change after its bound phase invalidates downstream state.

## 11. Quality Gate and Apply

### 11.1 Capability preservation result

The engine produces one of:

- `CAPABILITY_PRESERVED`
- `CAPABILITY_REGRESSION`
- `AUTHORIZATION_REQUIRED`
- `CAPABILITY_UNVERIFIABLE`

### 11.2 Gate requirements

`AUDIT_COMPLETE_VALID` requires all of:

- formal inspection exists;
- required Providers executed with valid evidence;
- required coverage is complete;
- deterministic validation passes;
- semantic confirmation matches the current artifact digest;
- capability preservation passes or every intentional regression is explicitly authorized;
- Quality Gate verdict is `PASS`.

Any unmanaged modification, missing baseline, stale digest, invalid Provider evidence, uncovered required capability, broken capability, or unauthorized removal/narrowing blocks formal completion.

### 11.3 Apply requirements

`apply` requires a valid managed operation record and verifies:

- inspection ID and phase chain;
- unchanged source digest;
- unchanged staged candidate digest;
- matching baseline and candidate capability digests;
- complete DecisionRecord coverage;
- required Provider execution;
- complete required coverage;
- semantic confirmation;
- `PASS` Gate result;
- no unauthorized capability regression.

A target project's own test result can contribute behavioral evidence but cannot satisfy these conditions by itself.

## 12. State Model

The public result distinguishes execution, validation, coverage, capability preservation, authorization, Gate, and apply.

Required observable states include:

- `VALIDATION_PASS`
- `VALIDATION_FAIL`
- `COVERAGE_COMPLETE`
- `COVERAGE_INCOMPLETE`
- `CAPABILITY_PRESERVED`
- `CAPABILITY_REGRESSION`
- `AUTHORIZATION_REQUIRED`
- `AUDIT_COMPLETE_VALID`
- `AUDIT_COMPLETE_INVALID`
- `AUDIT_INCOMPLETE`
- `UNMANAGED_CHANGE`
- `APPLY_BLOCKED`

These may be represented by orthogonal enums and an aggregate outcome rather than one overloaded enum.

## 13. Gate Truth Table

| Inspection | Required Providers | Coverage | Capability Diff | Authorization | Gate / Apply |
| --- | --- | --- | --- | --- | --- |
| absent | unknown | unknown | unknown | unknown | `UNMANAGED_CHANGE`, blocked |
| valid | missing or not executed | incomplete | unknown | n/a | `AUDIT_INCOMPLETE`, blocked |
| valid | executed | complete | preserved | n/a | may pass |
| valid | executed | complete | removed/narrowed | absent | `AUTHORIZATION_REQUIRED`, blocked |
| valid | executed | complete | removed/narrowed | valid and exact | may continue to Gate |
| valid | executed | complete | broken | any | invalid, blocked |
| valid | executed | incomplete | any | any | incomplete, blocked |
| valid | executed | complete | unverifiable | any | incomplete, blocked |
| stale source or candidate digest | any | any | any | any | `APPLY_BLOCKED` |

## 14. Test Strategy

Implementation follows test-first development.

### 14.1 Unit tests

- Capability Manifest schema and canonical digest;
- evidence boundary and provenance validation;
- semantic diff classification;
- DecisionRecord coverage and authorization binding;
- applicability and requiredness matrix;
- Gate mapping and unmanaged completion states.

### 14.2 Integration tests

- baseline five deliverables to candidate one deliverable blocks without authorization;
- complete preservation passes;
- authorized removal with migration and deprecation records may continue;
- declaration-only deletion is narrowed/inconsistent;
- implementation-only deletion is broken;
- coordinated deletion remains removed;
- Provider missing, not selected, not executed, invalid, or stale blocks required coverage;
- target tests passing without formal Gate cannot produce formal completion;
- source and candidate digest changes block apply;
- Create, Audit, Audit Repair, and Targeted Repair applicability behavior;
- existing five-declared/one-verified coverage regression remains enforced.

### 14.3 End-to-end dogfooding

A repository fixture models a five-document Skill. A fully self-consistent one-document candidate removes four capabilities and passes its own tests.

Expected unmanaged/unauthorized result:

- four removed or narrowed capabilities;
- authorization required;
- Gate blocked;
- apply rejected;
- no `AUDIT_COMPLETE_VALID`.

The authorized variant binds exact capability IDs, compatibility impact, migration plan, deprecation plan, and user authorization evidence before Gate evaluation.

No test or dogfooding run modifies the real `gjb438c-document-engineering` directory.

## 15. Migration and Compatibility

- Existing serialized records without capability manifests remain readable only in legacy compatibility mode.
- Legacy records cannot authorize apply or claim complete formal audit coverage.
- Existing phased CLI commands remain, with new required fields for mutating formal flows.
- A high-level managed status/report command may summarize the phase chain, but it cannot fabricate missing phases.
- Existing `COMPATIBILITY` behavior remains observable for old read-only callers and is never promoted to complete coverage.

## 16. Installation and Release Boundary

Repository implementation and verification do not automatically install or publish the plugin. Installation is a separate explicit step after tests and repository review. The final implementation report must state whether installation occurred and, if so, verify repository, package, cache, and loaded version consistency.

No Git commit, push, tag, release, or installation is performed without explicit authorization.

## 17. Expected File Areas

The implementation is expected to touch:

- `.codex-plugin/plugin.json` only if packaged Provider resources require manifest metadata;
- `config/providers.yaml`;
- `engine/models.py`;
- new capability manifest/diff modules;
- `engine/orchestrator.py`;
- `engine/workspace.py`;
- `engine/quality_gate.py`;
- `engine/serialization.py` and schemas;
- `engine/host_adapters.py` and Provider contracts;
- `scripts/skill_engineering.py`;
- `skills/skill-engineer/SKILL.md` and focused references;
- bundled read-only Provider resources;
- unit, integration, end-to-end, and regression tests.

The implementation must consolidate overlapping rules and preserve the existing architecture: Codex owns semantics, Providers own typed evidence, and the deterministic engine owns integrity and Gate enforcement.
