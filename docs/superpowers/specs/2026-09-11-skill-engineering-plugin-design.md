# Skill Engineering Plugin — V1 Architecture Baseline

| Field | Value |
|---|---|
| Status | **Final / Frozen** |
| Baseline version | V1 Architecture Baseline |
| Date | 2026-09-11 |
| Scope | Architecture and design only |
| Implementation status | Not started |
| Authority | This document is the sole architecture baseline for the implementation plan |

## Contract Revision Record

**2026-09-14 — Final/Frozen amendment**

- The Gate entry point is `adjudicate(context, evidence, *, policy: Mapping[str, object] | None = None)`; if a formal `GatePolicy` type is introduced later, this mapping type may converge on it.
- `policy=None` uses the core policy. Project policy is read, validated, and merged by the upper-layer loader before adjudication.
- `adjudicate` accepts only the effective policy supplied by its caller; it does not search configuration or use global policy state.
- Project policy may only make the core policy stricter or add blocking/warning rules; it cannot weaken or disable `B01–B12`.
- `GateResult.policy_version` records the version of the effective policy actually used for the decision.

## 1. Problem Statement

Skill maintenance often follows a harmful loop:

```text
Failure
  → add a case-specific instruction
  → encounter another edge case
  → add another instruction
  → accumulate exceptions, workarounds, and conflicts
```

Over time, `SKILL.md` and `AGENTS.md` become historical bug ledgers rather than stable capability contracts. Reliability remains dependent on the model remembering an expanding set of rules, while root causes, deterministic enforcement, and regression protection remain unaddressed.

The Skill Engineering Plugin exists to replace this default behavior with an engineering governance pipeline. It manages the creation, modification, repair, audit, optimization, validation, and release of Skills while moving reliability toward implementation, schemas, validators, tests, environment detection, tooling, and workflow controls.

### 1.1 Why a Plugin

A single Skill is insufficient because the system needs more than an instruction workflow. It requires:

- a stable orchestration boundary;
- deterministic scripts and validators;
- schemas for internal evidence and decisions;
- isolated workspace control;
- regression execution;
- external Provider adapters;
- an internal Quality Gate with release authority.

A Plugin is the packaging and distribution boundary for these coordinated capabilities. The Plugin is not itself the governance logic; the governance logic belongs to the Internal Core.

### 1.2 Why `AGENTS.md` Is Insufficient

`AGENTS.md` loads broad, persistent instructions. Using it as the primary enforcement mechanism would merely move rule inflation from `SKILL.md` into another prompt file. It cannot reliably provide atomic publication, schema validation, filesystem isolation, test execution, evidence integrity, or reproducible gate decisions.

Within this design, `AGENTS.md` contains only a small set of stable, cross-Skill governance invariants.

## 2. Goals

The V1 system must:

1. Prefer mechanisms over instructions.
2. Diagnose root causes before changing persistent Skill instructions.
3. Classify issues across three independent dimensions.
4. Select the correct engineering layer before applying changes.
5. Treat new Prompt Rules as a last resort.
6. Convert reproducible historical failures into regression protection.
7. Detect rule inflation without allowing heuristics to directly block delivery.
8. isolate every Modify and Fix operation.
9. preserve read-only semantics for Audit Only.
10. aggregate all evidence through one internal Quality Gate.
11. release or replace a Skill only after Gate PASS.
12. return complete, coherent Skill artifacts rather than patches.
13. reuse mature external Skills as replaceable capability Providers.
14. remain operational when every external Provider is absent.

## 3. Non-Goals

V1 does not:

- understand every business domain handled by target Skills;
- prohibit all Prompt Rules;
- convert every instruction into a test;
- provide a Web UI;
- provide an MCP server;
- build a remote Provider execution platform;
- maintain a database or multi-version history system;
- automatically search a Skill marketplace;
- automatically install third-party Skills;
- vendor third-party Skills into this Plugin;
- provide a multi-model evaluation matrix;
- build complex hooks;
- use raw line counts or keyword counts as direct failure thresholds;
- force every generated Skill to contain scripts, validators, schemas, or tests;
- expose internal diagnosis and governance reports as the primary product output.

## 4. Final Design Principles

### 4.1 Mechanism over Instruction — Final

Behavior that can be enforced by implementation, schema, validator, test, tooling, environment detection, or workflow control must not primarily depend on Prompt Rules.

### 4.2 Root Cause over Patch — Final

A demonstrated failure must be diagnosed and classified before persistent instructions are changed. `INSUFFICIENT_EVIDENCE` cannot be converted into a permanent Prompt Rule.

### 4.3 Regression over Memory — Final

Reproducible historical failures should normally be preserved as regression protection for their failure family, not as case-specific prompt memory.

### 4.4 Internal Governance Authority — Final

Root Cause Analysis, Issue Classification, Mechanism Selection, Rule Inflation Governance, Pipeline orchestration, and final Quality Gate adjudication are internal capabilities. No external Skill owns these decisions.

### 4.5 Provider Replaceability — Final

External Skills are replaceable Providers behind stable capability ports. Provider identity, availability, or invocation method cannot define or alter internal governance semantics.

### 4.6 Safe Publication — Final

Modify and Fix always operate in isolated working copies. Only the Internal Quality Gate can authorize atomic publication.

## 5. Top-Level Input and Output Contract

### 5.1 Input — Final

```text
Input
├── User Requirement
├── Existing Skill?       optional
└── Failure Evidence?     optional
```

Users do not need to provide an operation parameter. The system detects `Create`, `Modify`, `Fix`, `Audit Only`, or `Audit + Optimize` from intent and authorization.

### 5.2 Legal Output Type A — Final

```text
Validated Complete Skill
```

Applicable to:

- Create;
- Modify;
- Fix;
- Audit + Optimize;
- Audit Only when the unchanged Skill passes the Gate.

The output is a complete Skill directory. It may be unchanged when no changes are necessary.

### 5.3 Legal Output Type B — Final

```text
Unchanged Skill + Minimal Blocking Findings
```

This result is legal only when all conditions hold:

- the operation is Audit Only;
- the original Skill receives Gate FAIL;
- the user has not authorized modification.

The external findings contain only:

- finding ID;
- affected path;
- blocking reason;
- required next action.

Internal similarity scores, complete Provider information, `DecisionRecord`, and full governance state remain private by default.

Audit Only never auto-upgrades to Audit + Optimize. Audit completion does not turn an internal Gate FAIL into PASS. If the user later authorizes repair, a new Audit + Optimize flow begins and creates an isolated working copy.

## 6. System Invariants — Final

| ID | Invariant |
|---|---|
| `I01` | Only the Internal Quality Gate emits the final `PASS` or `FAIL` verdict. |
| `I02` | Validators, tests, detectors, and external checkers emit evidence or check results only. |
| `I03` | Modify and Fix never mutate the source Skill before Gate PASS. |
| `I04` | Audit Only is read-only and never auto-upgrades. |
| `I05` | Audit + Optimize creates isolation only after read-only audit confirms a modification is needed. |
| `I06` | Gate FAIL never authorizes publication. |
| `I07` | PASS is required before atomic replacement or delivery of a new Skill. |
| `I08` | Every external Provider is optional and replaceable. |
| `I09` | Required capabilities have internal fallbacks; no external Provider is a hard dependency. |
| `I10` | `INSUFFICIENT_EVIDENCE` never creates a permanent Prompt Rule. |
| `I11` | `TASK_LOCAL_PREFERENCE` is not persisted into the Skill. |
| `I12` | Rule Bloat Detection cannot directly fail the Gate. |
| `I13` | A new Prompt Rule requires a stable capability-invariant classification and justification. |
| `I14` | Missing optional Provider evidence cannot independently fail the Gate. |
| `I15` | Required evidence must be valid, trustworthy, and reproducible. |
| `I16` | Publication uses same-filesystem staging and atomic replacement only. |
| `I17` | V1 retains one previous-version backup for publication recovery. |
| `I18` | Project policy may strengthen but never weaken core `B01–B12`. |

## 7. Overall Architecture

```text
User Request
  + Existing Skill?
  + Failure Evidence?
          │
          ▼
┌─────────────────────────────┐
│ skill-engineer Entry Skill  │
│ Intent and authorization    │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ Pipeline Orchestrator       │
│ Sole control plane          │
└───────┬───────────┬─────────┘
        │           │
        ▼           ▼
┌──────────────┐  ┌─────────────────────┐
│ Internal Core│  │ Provider Gateway    │
│ governance   │  │ ports + adapters    │
└──────┬───────┘  └──────────┬──────────┘
       │                      ├── external Provider, optional
       │                      └── internal fallback, mandatory minimum
       ▼
┌─────────────────────────────┐
│ Workspace / Mechanisms      │
│ scripts · schema · tests    │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ Rule Governance Engine      │
│ KEEP · MERGE · MOVE · DELETE│
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ Evidence Collector          │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ Internal Quality Gate       │
│ Sole final adjudicator      │
└───────┬─────────────────────┘
        ├── PASS → atomic publish / complete output
        └── FAIL → remediation or Audit Only exception
```

## 8. Component Responsibilities

### 8.1 `AGENTS.md` Governance Layer — Final

Contains only stable, high-level, cross-Skill governance principles:

- prefer mechanisms over instructions;
- diagnose before changing instructions;
- prefer implementation, test, validator/schema, tooling, and workflow over Prompt Rules;
- preserve historical failures through regression where appropriate;
- consolidate overlapping rules;
- require the internal engineering Quality Gate.

It does not contain specific bugs, environment workarounds, classifier tables, Provider details, or Gate implementation rules.

### 8.2 `skill-engineer` Entry Skill — Final

A single public entry avoids operation parameters and routing conflicts among multiple internal Skills. It remains a thin routing and workflow layer.

It owns:

- input discovery;
- intent and authorization recognition;
- progressive disclosure into relevant governance references;
- invocation of the Pipeline Orchestrator;
- presentation of one of the two legal external result types.

It does not own:

- filesystem mutation mechanics;
- deterministic validation;
- detailed classification logic;
- Provider-specific invocation;
- Gate adjudication.

### 8.3 Pipeline Orchestrator — Final

The sole control plane:

- normalizes input;
- selects the operation flow;
- controls state transitions;
- calls Internal Core modules and Provider ports;
- enforces stopping conditions;
- routes Gate failures to the responsible stage;
- requests publication only after Gate PASS.

### 8.4 Workspace Controller — Final

Responsible for:

- read-only source inventory;
- isolated staging;
- source and candidate digests;
- same-filesystem verification;
- source-change detection before publication;
- one-generation backup;
- atomic replacement and recovery.

### 8.5 Diagnostic Core — Final

Responsible for Root Cause Analysis when applicable, three-dimensional issue classification, requirement-versus-preference distinction, and creation of `DecisionRecord`.

RCA applicability:

- Create: capability, boundary, and risk analysis; not artificial RCA.
- Modify: requirement classification; RCA only when a failure is also present.
- Fix: RCA required.
- Audit: RCA only after an actual issue is found.

### 8.6 Mechanism Selector — Final

Chooses one or more mechanisms and records rejected alternatives.

Default preference:

```text
1. Implementation Fix
2. Regression Test
3. Schema / Validator
4. Environment Detection / Tooling
5. Workflow Refactor
6. Merge / Generalize Existing Invariant
7. Add New SKILL.md Rule
```

### 8.7 Rule Governance Engine — Final

Adjudicates rule findings using `KEEP`, `MERGE`, `MOVE`, and `DELETE`. Detectors and external auditors may recommend actions, but only this internal engine creates governance decisions.

### 8.8 Provider Gateway — Final

Owns Provider discovery, compatibility checks, invocation adapters, output normalization, limitations, and fallback selection. The core depends on capability ports, not concrete Provider identities.

### 8.9 Evidence Collector — Final

Validates and normalizes `CheckResult`, Provider evidence, regression results, governance decisions, artifact references, reproducibility, and required/optional status.

### 8.10 Internal Quality Gate — Final

The only component authorized to emit final `PASS` or `FAIL`. It evaluates internal policy against normalized evidence and sets `publish_authorized`.

## 9. Internal Pipeline

### 9.1 Shared Pipeline

```text
Load Context
→ Detect Intent and Authorization
→ Select Workspace Mode
→ Analyze / Diagnose
→ Three-Dimensional Classification
→ Mechanism Selection
→ Apply Candidate Changes when authorized
→ Skill Audit
→ Rule Bloat Detection
→ Validation and Regression
→ Evidence Collection
→ Internal Quality Gate
→ PASS: Publish or return complete Skill
→ FAIL: Return to responsible stage or use Audit Only exception
```

### 9.2 Create

Creates staging immediately, performs capability and risk analysis, optionally invokes the Create Provider, falls back internally when needed, generates a complete candidate Skill, and runs the complete audit and Gate.

### 9.3 Modify

Always creates an isolated copy. It first distinguishes a stable capability change from `TASK_LOCAL_PREFERENCE`. A local preference is not persisted and does not trigger replacement.

### 9.4 Fix

Always creates an isolated copy. It requires RCA, three-dimensional classification, mechanism selection, and `Regression Disposition`. It never treats a new Prompt Rule as the unknown-problem fallback.

### 9.5 Audit Only

Runs read-only without copying. If the Skill passes, it returns `Validated Complete Skill` unchanged. If it fails, it returns `Unchanged Skill + Minimal Blocking Findings`; it never modifies or auto-upgrades.

### 9.6 Audit + Optimize

Begins with read-only audit. If no change is needed, it returns the unchanged validated Skill. If optimization is needed and authorized, it creates an isolated copy before any edit.

## 10. State Model and Transitions — Final

### 10.1 States

```text
DISCOVERED
CLASSIFIED
MECHANISM_SELECTED
STAGED
AUDITED
VALIDATED
GATE_FAILED
GATE_PASSED
PUBLISHED
UNCHANGED_VALIDATED
UNCHANGED_BLOCKED
```

These are lifecycle milestones, not a mandatory linear sequence. Operation mode, authorization, evidence availability, and the remediation target determine the path.

### 10.2 Valid Transitions

| From | To | Guard |
|---|---|---|
| `DISCOVERED` | `STAGED` | Create establishes an empty same-filesystem workspace, or Modify/Fix creates an isolated source copy before diagnostics. |
| `DISCOVERED` | `AUDITED` | Audit Only enters the read-only audit path and never enters `STAGED`. |
| `DISCOVERED` | `CLASSIFIED` | A read-only requirement or audit finding can be classified without staging. |
| `STAGED` | `CLASSIFIED` | Create/Modify/Fix diagnostics and three-dimensional classification run against the staged context. |
| `AUDITED` | `STAGED` | Audit + Optimize found a necessary change and modification is authorized; Audit Only cannot use this transition. |
| `AUDITED` | `CLASSIFIED` | A read-only audit found an actual defect that requires classification before optimization. |
| `CLASSIFIED` | `MECHANISM_SELECTED` | Required analysis is complete; conditional `root_cause` requirements are satisfied. |
| `MECHANISM_SELECTED` | `STAGED` | A read-only classification now has authorized candidate work, or an existing staged workspace remains the mutation target. |
| `MECHANISM_SELECTED` | `AUDITED` | No persistent change is authorized or required; the classified read-only result returns to governance audit without staging. |
| `STAGED` | `AUDITED` | Candidate changes are complete and ready for governance audit. |
| `AUDITED` | `VALIDATED` | Governance decisions are resolved. |
| `VALIDATED` | `AUDITED` | A validation/evidence-level remediation has completed and the current remediation cycle must be re-audited before revalidation. |
| `VALIDATED` | `GATE_PASSED` | Internal Gate verdict is PASS. |
| `VALIDATED` | `GATE_FAILED` | Internal Gate verdict is FAIL. |
| `GATE_PASSED` | `PUBLISHED` | Same-filesystem atomic publication succeeds. |
| `GATE_PASSED` | `UNCHANGED_VALIDATED` | Audit Only or Audit + Optimize requires no modification. |
| `GATE_FAILED` | `UNCHANGED_BLOCKED` | Audit Only and no modification authorization. |
| `GATE_FAILED` | `CLASSIFIED` | Failure requires corrected diagnosis or classification. |
| `GATE_FAILED` | `MECHANISM_SELECTED` | Failure requires a different engineering mechanism. |
| `GATE_FAILED` | `STAGED` | Failure requires candidate implementation changes in the existing isolated workspace. |
| `GATE_FAILED` | `AUDITED` | Failure requires renewed governance decisions. |
| `GATE_FAILED` | `VALIDATED` | Failure is corrected at validation/evidence level without changing the candidate. |

After any remediation transition, the flow must pass through `AUDITED`, `VALIDATED`, and a fresh Gate adjudication before publication. Audit, validation, and Gate evidence must belong to the same current remediation cycle; stale evidence from an earlier failed cycle cannot satisfy a later transition. The state machine permits loops; it does not encode `DISCOVERED → CLASSIFIED → MECHANISM_SELECTED → STAGED` as a universal sequence.

### 10.3 Forbidden Transitions

- `STAGED → PUBLISHED` without Gate PASS;
- `GATE_FAILED → PUBLISHED`;
- `AUDITED → UNCHANGED_VALIDATED` without Gate PASS;
- `Audit Only → STAGED` within the same read-only operation;
- any external Provider result → final Gate verdict;
- `TASK_LOCAL_PREFERENCE → STAGED` for persistent Skill changes;
- `INSUFFICIENT_EVIDENCE → new Prompt Rule`.

After remediation, all applicable required checks run again. Passing only the previously failed check is insufficient for publication. A later user authorization starts Audit + Optimize as a new operation; it does not mutate the prior Audit Only state path.

## 11. Three-Dimensional Issue Classification — Final

### 11.1 Primary Issue Class

| Value | Meaning |
|---|---|
| `IMPLEMENTATION_DEFECT` | Executable or implementation behavior is wrong. |
| `ENVIRONMENT_COMPATIBILITY` | OS, shell, encoding, dependency, or runtime variance. |
| `WORKFLOW_DESIGN_DEFECT` | Stage order, responsibility, or data-flow defect. |
| `CONTRACT_ENFORCEMENT_GAP` | Input/output, schema, or mechanical validation gap. |
| `CAPABILITY_INVARIANT_CHANGE` | Stable Skill capability contract changes. |
| `TASK_LOCAL_PREFERENCE` | One request or output preference; never persisted. |
| `DOCUMENTATION_GAP` | Knowledge needed by an Agent or human but not mechanically enforced. |
| `NO_DEFECT` | No repair is necessary. |
| `INSUFFICIENT_EVIDENCE` | Evidence cannot support a trustworthy root cause. |

### 11.2 Control Gap

```text
IMPLEMENTATION_GAP
SCHEMA_MISSING
VALIDATOR_MISSING
ENV_DETECTION_MISSING
REGRESSION_MISSING
WORKFLOW_CONTROL_MISSING
INSTRUCTION_GAP
NONE
```

Multiple control gaps may apply.

### 11.3 Regression Disposition

```text
REQUIRED
RECOMMENDED
NOT_APPLICABLE
```

These dimensions remain independent. A root cause, missing control, and regression treatment are not collapsed into one flat enum.

## 12. Mechanism Selection — Final

The selector produces a `DecisionRecord` with selected and rejected mechanisms:

```text
DecisionRecord
├── intent
├── primary_issue_class
├── control_gaps[]
├── regression_disposition
├── root_cause?                 conditional; see Section 21.2
├── evidence_limitations[]
├── selected_mechanisms[]
├── rejected_mechanisms[]
└── prompt_rule_justification?
```

| Primary class | Default mechanisms |
|---|---|
| `IMPLEMENTATION_DEFECT` | Implementation fix plus regression. |
| `ENVIRONMENT_COMPATIBILITY` | Environment detection/tooling plus regression. |
| `WORKFLOW_DESIGN_DEFECT` | Workflow refactor plus integration test. |
| `CONTRACT_ENFORCEMENT_GAP` | Schema/validator plus contract test. |
| `CAPABILITY_INVARIANT_CHANGE` | Merge/generalize existing invariant; add a rule only when necessary. |
| `TASK_LOCAL_PREFERENCE` | Do not persist. |
| `DOCUMENTATION_GAP` | Reference or concise instruction. |
| `NO_DEFECT` | No change; continue validation. |
| `INSUFFICIENT_EVIDENCE` | Gather evidence or report limitation; no permanent patch. |

A new Prompt Rule requires all of:

- stable, long-term capability contract;
- material effect on Agent decisions;
- unreliable or impossible mechanical enforcement;
- no adequate existing invariant to merge into;
- not a task-local preference;
- documented rejection of higher-priority mechanisms.

## 13. Skill Governance Model — Final

| Action | Decision condition |
|---|---|
| `KEEP` | Stable, necessary, decision-relevant, and correctly placed. |
| `MERGE` | Semantically overlaps another invariant or is only a special case. |
| `MOVE` | Belongs in implementation, validator, schema, test, tooling, workflow, or on-demand reference. |
| `DELETE` | Obsolete, duplicate, unproven, case-specific, or fully superseded by a mechanism. |

Provider findings are advisory inputs. The Rule Governance Engine owns the final governance action.

## 14. Rule Bloat Detection

### 14.1 Role — Final

Rule Bloat Detection produces findings and evidence only. It never emits Gate FAIL and never directly modifies rules.

### 14.2 `RuleUnit`

```text
RuleUnit
├── id
├── source_location
├── normalized_meaning
├── modality
├── condition
├── exception
├── scope
├── environment_qualifier
├── referenced_mechanism
└── history_metadata?
```

### 14.3 Detection Dimensions

- directive pressure;
- conditional and exception complexity;
- exact and near-semantic redundancy;
- conflict candidates;
- case-specific patch smell;
- environment leakage;
- substitution for implementation/schema/validator/test;
- obsolete paths, commands, versions, or resources;
- cross-layer duplication;
- historical rule growth when Git history is available.

No fixed number of `Must`, `Never`, branches, rules, or lines directly causes failure.

### 14.4 `RuleFinding`

```text
RuleFinding
├── finding_id
├── affected_rule_units[]
├── signals[]
├── confidence
├── risk
├── rationale
├── candidate_action
├── candidate_target_layer?
├── evidence_refs[]
└── limitations[]
```

### 14.5 Governance Chain — Final

```text
Rule Bloat Detector
  → RuleFinding
  → Rule Governance Engine
  → governance decision
  → Evidence Collector
  → Internal Quality Gate
```

### 14.6 Missing Git History — Final

Historical growth checks produce `SKIP/WARN` by default. They affect the Gate only when a schema-valid project policy explicitly declares them required.

## 15. Regression Strategy

### 15.1 Regression Unit — Final

Regression protection is organized by independent root-cause or failure family, not by the number of bug reports. Similar reports become parameters or fixtures for one test family.

### 15.2 Regression Candidates

Regression is normally appropriate for:

- reproducible implementation defects;
- environment compatibility failures;
- schema and workflow enforcement gaps;
- failures that previously allowed a bad artifact to ship;
- removal of a Prompt Rule after mechanism coverage replaces it.

Regression is normally inappropriate for:

- task-local preference;
- subjective style preference;
- uncontrollable external live state;
- assertions about exact generated wording;
- speculative cases without a defined failure mode.

### 15.3 Test Levels

| Level | V1 status |
|---|---|
| Structure contract | Required |
| Unit tests for deterministic mechanisms | Required |
| Critical artifact execution | Required |
| Workspace and Gate integration | Required |
| Target Skill regression | According to disposition |
| Routing/behavioral evaluation | Execute when runner exists |
| Cross-model matrix | V2 |

### 15.4 Behavioral Evaluation — Final

V1 defines scenario schema, result records, and a runner interface.

- When a runner exists, the scenario executes and records evidence.
- Without a runner, status is `NOT_EXECUTED` with a limitation.
- An unexecuted scenario cannot be marked PASS.
- Multi-model evaluation belongs to V2.

## 16. Provider Architecture

### 16.1 Capability Ports — Final

```text
CREATE_CANDIDATE
AUDIT_SKILL
GOVERN_AGENT_INSTRUCTIONS
CHECK_SKILL_CONFORMANCE
```

V1 core does not bind to `$skill-name`, CLI, delegation, or a future Skill API. Actual host invocation belongs entirely to Adapter implementations.

### 16.2 Provider Contract

```text
ProviderDescriptor
├── provider_id
├── source_identity
├── revision_or_version
├── capability
├── availability
├── invocation_adapter
├── limitations[]
└── fallback_provider
```

```text
ProviderResult
├── provider_id
├── capability
├── provider_status
├── findings[]
├── candidate_changes[]
├── evidence[]
├── limitations[]
└── fallback_used
```

Forbidden Provider output authority:

```text
final_gate_verdict
publish_authorization
replace_original_skill
pipeline_state_transition
```

### 16.3 Candidate Provider Allocation — Final

| External Provider | Reused capability | Adapter restriction | Internal fallback |
|---|---|---|---|
| OpenAI `skill-creator` | Candidate Skill structure, naming, progressive disclosure, resource selection, basic validation guidance | staging only; cannot publish or control Modify/Fix | minimal internal creation path |
| `agent-skills-creator` | audit dimensions, capability delta, routing evaluation, simplification analysis | advisory audit only; no direct rewrite, installation, README shipping, or final score authority | Rule Governance Engine plus internal audit |
| `agents-md` | AGENTS/CLAUDE placement, duplicate-source checks, command/link validation, reduction guidance | invoked only when agent-instruction files are in scope; Audit Only remains read-only | minimal internal AGENTS governance checks |
| `validate-skills` | external conformance checklist | evidence only; no final PASS; host-specific assumptions filtered | internal deterministic structure validators |

`validate-skills` identifies a capability, not an unambiguous package identity. A concrete source and revision must be configured before formal use.

### 16.4 Provider Source Policy — Final

- Local development may use discovered Providers marked `unpinned/degraded`.
- CI, formal runs, and publication require pinned source and revision/version.
- Provider identity changes cannot alter internal governance semantics.
- An unpinned Provider result cannot replace required internal evidence.

### 16.5 Provider Status and Fallback

```text
AVAILABLE
UNAVAILABLE
INVALID_OUTPUT
TIMEOUT
INCOMPATIBLE
DEGRADED
```

| Provider condition | Required handling |
|---|---|
| Missing | Use fallback. |
| Timeout | Use fallback and record warning. |
| Invalid output | Reject output, use fallback, record warning. |
| Internal-policy conflict | Preserve as disagreement evidence; internal policy decides. |
| Partial artifact | Complete internally or fail due to missing required evidence. |
| Version mismatch | Mark incompatible/degraded according to configured policy. |
| Optional checker error | Warning only unless required capability remains unsatisfied. |
| Fallback failure | Trigger `B08` only when required evidence/check cannot be satisfied. |

Required capability does not imply required external Provider. For example, structure validation is required, but `validate-skills` is optional because the internal validator supplies the required capability.

## 17. Evidence Model

### 17.1 `CheckResult`

```text
CheckResult
├── check_id
├── source
├── subject
├── required
├── status: PASS | WARN | FAIL | SKIP | ERROR | NOT_EXECUTED
├── deterministic
├── reproducible
├── confidence
├── evidence
├── remediation_stage
└── artifact_reference?
```

### 17.2 Evidence Rules — Final

- `PASS` describes one check, not the final delivery verdict.
- `SKIP` and `NOT_EXECUTED` require reasons.
- A required check cannot satisfy the Gate with `SKIP`, `ERROR`, or `NOT_EXECUTED` unless the Gate policy explicitly defines an equivalent trusted check.
- Optional evidence may enrich findings but cannot be the sole basis for required assurance.
- External evidence retains source identity and limitations.
- Invalid or malformed evidence is not silently ignored.

## 18. Internal Quality Gate

### 18.1 Authority — Final

The Internal Quality Gate is the unique final adjudicator. All other components provide evidence or governance decisions.

### 18.2 Blocking Policies — Final

| ID | Blocking condition |
|---|---|
| `B01` | Modify/Fix mutates the source or isolation cannot be confirmed. |
| `B02` | Candidate is not a complete Skill, contains placeholders, or has unresolved required references. |
| `B03` | Frontmatter, name, directory, or required structure violates supported internal contracts. |
| `B04` | Applicable existing tests, validators, or newly required tests fail. |
| `B05` | Unresolved rule conflict, critical duplication, or inconsistent capability contract remains. |
| `B06` | A Prompt Rule is added without `CAPABILITY_INVARIANT_CHANGE` and complete justification. |
| `B07` | Regression disposition is `REQUIRED`, but the regression is absent or does not pass. |
| `B08` | Required evidence is missing/invalid; a required check errors; or a required result is not trustworthy and reproducible. |
| `B09` | Candidate modifications exceed user authorization. |
| `B10` | The source Skill changed before safe atomic replacement. |
| `B11` | A critical executable, schema, required dependency, or runtime-critical reference is not verified. |
| `B12` | External evidence identifies an issue that maps to an internal blocking policy and remains unresolved. |

`B08` never applies solely because an optional Provider or checker fails. `B11` does not apply to optional documentation or non-critical links.

### 18.3 Warning Policies — Final

Warnings include:

- elevated absolute or branch density without a confirmed defect;
- low-confidence semantic duplicate candidates;
- missing Git history for default-optional growth trends;
- optional Provider failure with successful fallback;
- unavailable behavioral runner when evaluation is not required;
- disagreement among optional checkers;
- unverifiable optional documentation or non-critical links;
- Skill growth supported by valid mechanism decisions but worth monitoring.

Warnings do not become FAIL based only on count.

### 18.4 Gate Result

```text
GateResult
├── verdict: PASS | FAIL
├── outcome: READY_TO_PUBLISH | UNCHANGED_VALIDATED | UNCHANGED_BLOCKED | REMEDIATION_REQUIRED
├── blocking_findings[]
├── warnings[]
├── required_checks_summary
├── evidence_summary
├── publish_authorized: true | false
└── policy_version
```

The adjudication contract is:

```python
def adjudicate(
    context: GateContext,
    evidence: tuple[CheckResult, ...],
    *,
    policy: Mapping[str, object] | None = None,
) -> GateResult: ...
```

When `policy` is `None`, adjudication uses the immutable core policy. The caller supplies an already effective policy for project-specific decisions; adjudication does not load or search project configuration and does not consult global policy state. `GateResult.policy_version` is the version of that effective policy.

`verdict` answers whether the Skill satisfies the quality policy. `publish_authorized` answers whether the Workspace Controller may execute publication or replacement; these are separate contracts.

- Create/Modify/Fix/Audit + Optimize with PASS and a candidate requiring delivery: `publish_authorized = true`.
- For that publishable candidate, Gate outcome is `READY_TO_PUBLISH`; lifecycle state becomes `PUBLISHED` only after Workspace Controller completes atomic publication.
- Audit Only with PASS: `verdict = PASS`, `publish_authorized = false`, `outcome = UNCHANGED_VALIDATED`.
- Audit + Optimize with no necessary change and PASS: `publish_authorized = false`, `outcome = UNCHANGED_VALIDATED`.
- Any FAIL: `publish_authorized = false`.

PASS is necessary but not sufficient for publication authority. Publication also requires an authorized operation, a publishable staged candidate, and satisfied Workspace Controller preconditions.

### 18.5 Project Policy Extension — Final

- Project policy may add blocking or warning rules.
- It may strengthen but cannot disable or weaken `B01–B12`.
- Custom policy must be schema-valid.
- The upper-layer loader reads, validates, and merges project policy into an effective policy before calling the Gate.
- The effective policy version actually used is recorded in `GateResult.policy_version`.

## 19. Atomic Publication — Final

V1 supports only same-filesystem staging and replacement.

Publication sequence:

```text
Verify Gate PASS and publish_authorized = true
→ verify staging and target share a filesystem
→ compare current source digest with audited source digest
→ move current source to one-generation backup
→ atomically move candidate into target path
→ verify target digest and loadability
→ on failure, restore backup
```

Cross-volume publication fails. V1 retains one prior backup and does not maintain multi-version history. File-lock or replacement errors preserve or restore the source rather than reporting success.

## 20. Configuration Boundaries

### 20.1 Configuration Categories — Final

```text
Provider Configuration
Gate Policy
Runtime Input
```

These categories remain separate.

### 20.2 Provider Configuration

Contains Provider capability, source, revision/version, adapter, optional status, compatibility, and fallback. It does not contain Gate rules, historical bug patches, business-domain rules, or user task preferences.

### 20.3 Gate Policy

Contains stable required-check applicability and blocking/warning policies. It does not contain Skill-name special cases, historical bug IDs, or environment-specific patch rules.

### 20.4 Runtime Input

Contains the current user requirement, target Skill, evidence, authorization, requested policy additions, and environment facts. Runtime input never silently mutates stable Provider or Gate configuration.

## 21. Schema Boundaries

V1 defines:

```text
schemas/
├── artifact-manifest.schema.json
├── decision-record.schema.json
├── provider-result.schema.json
├── check-result.schema.json
├── regression-case.schema.json
├── behavioral-scenario.schema.json
├── behavioral-result.schema.json
├── gate-policy.schema.json
└── gate-result.schema.json
```

### 21.1 Ownership

| Schema | Owns | Does not own |
|---|---|---|
| Artifact manifest | Skill inventory, critical assets, digests | Quality verdict |
| Decision record | classification and mechanism reasoning | Provider execution |
| Provider result | normalized Provider output | final verdict or publication |
| Check result | individual evidence status | final verdict |
| Regression case | failure family and observable contract | Prompt wording |
| Behavioral scenario/result | runner-neutral task and observed result | multi-model scheduling |
| Gate policy | required checks and policy extension | case-specific bugs |
| Gate result | final verdict and publish authorization | filesystem mutation implementation |

Schemas constrain exchange data. They do not determine root cause, governance action, or Gate policy meaning.

The Artifact Manifest contract includes:

```text
ArtifactManifest
├── intent
├── artifact_root
├── skill_name
├── source_revision?            conditional; see Section 21.2
├── source_digest?              required for existing-source flows
├── files[]
├── executable_assets[]
├── required_references[]
├── test_inventory[]
└── content_digest
```

### 21.2 Conditional Field Contracts — Final

#### `ArtifactManifest.source_revision/source_digest`

- Create: both fields are nullable or explicitly not applicable because no source Skill exists.
- Modify/Fix/Audit Only/Audit + Optimize: `source_digest` is required and non-empty; `source_revision` is recorded when a trustworthy VCS or source revision is available and is otherwise nullable.
- Modify/Fix/Audit + Optimize use the digest, plus revision when available, for race detection before atomic publication.
- Audit Only uses the same source identity fields for traceability of the read-only result.

#### `DecisionRecord.root_cause`

- Fix and any defect-related flow: required and non-empty.
- Defect-related classes are `IMPLEMENTATION_DEFECT`, `ENVIRONMENT_COMPATIBILITY`, `WORKFLOW_DESIGN_DEFECT`, `CONTRACT_ENFORCEMENT_GAP`, and an evidenced `DOCUMENTATION_GAP`.
- Create: nullable or explicitly not applicable; capability and risk analysis is not represented as a false root cause.
- Modify that represents only a requirement or `CAPABILITY_INVARIANT_CHANGE`: nullable.
- Audit: required only after an actual defect is found; otherwise nullable.
- `INSUFFICIENT_EVIDENCE` records the evidence limitation and cannot fabricate a root cause.

#### `GateResult.publish_authorized`

- Boolean and always present.
- It authorizes Workspace Controller mutation; it does not restate the quality verdict.
- Audit Only always sets it to `false`, including Gate PASS.
- Gate FAIL always sets it to `false`.
- Gate PASS sets it to `true` only for an authorized publishable candidate whose workspace preconditions are satisfied; that Gate result uses `outcome = READY_TO_PUBLISH` until publication succeeds.

## 22. V1 Directory Structure — Final

```text
skill-engineering-plugin/
├── .codex-plugin/
│   └── plugin.json
├── AGENTS.md
├── skills/
│   └── skill-engineer/
│       ├── SKILL.md
│       └── references/
│           ├── pipeline.md
│           ├── issue-classification.md
│           ├── mechanism-selection.md
│           ├── rule-governance.md
│           ├── provider-contracts.md
│           └── quality-gate.md
├── engine/
│   ├── workspace.py
│   ├── inventory.py
│   ├── diagnostics.py
│   ├── mechanism_selection.py
│   ├── rule_governance.py
│   ├── rule_bloat.py
│   ├── providers.py
│   ├── evidence.py
│   └── quality_gate.py
├── scripts/
│   └── skill_engineering.py
├── validators/
│   ├── skill_structure.py
│   └── reference_integrity.py
├── schemas/
│   └── [schemas listed in Section 21]
├── config/
│   ├── gate-policy.yaml
│   └── providers.yaml
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── regression/
│   └── fixtures/
└── docs/
    └── architecture/
```

The directory structure is a responsibility map, not a mandate to create empty placeholder files. Implementation may keep closely related V1 logic together when that produces clearer, smaller units without altering boundaries.

## 23. V1 Scope Freeze — Final

### 23.1 Required V1 Capabilities

- one public `skill-engineer` entry;
- intent and authorization recognition;
- Create, Modify, Fix, Audit Only, and Audit + Optimize flows;
- isolated Modify/Fix workspace;
- delayed isolation for Audit + Optimize;
- read-only Audit Only;
- three-dimensional classification;
- mechanism selection and Prompt Rule justification;
- internal `KEEP/MERGE/MOVE/DELETE` governance;
- basic rule bloat findings;
- Provider ports, adapters, pinned/degraded identity, and fallback;
- deterministic structure and reference validation;
- evidence normalization;
- regression case execution;
- behavioral scenario schema and runner interface;
- internal Quality Gate;
- same-filesystem atomic publication with one backup;
- Plugin self-tests.

### 23.2 Minimal Rule Bloat Capability

- exact duplicate detection;
- near-duplicate candidates;
- directive and branch structure signals;
- environment-specific instruction concentration;
- workaround and historical-patch candidates;
- conflict candidates;
- change summary when history exists;
- cross-layer mechanism duplication candidates.

### 23.3 Explicitly Deferred to V2

- multi-model behavioral evaluation matrix;
- more sophisticated semantic and historical analysis;
- optional hooks for detecting manual bypasses;
- expanded Provider ecosystem and host adapters;
- richer regression-family consolidation tooling;
- enhanced metrics dashboards or longitudinal reporting;
- additional formal validators proven necessary by V1 use.

### 23.4 Explicitly Outside Current Roadmap

- remote orchestration service;
- database-backed governance platform;
- generalized business-domain validation;
- automatic marketplace crawling and installation;
- UI-first workflow;
- copying all third-party capabilities into internal fallback.

## 24. Plugin Self-Test Strategy

### 24.1 Unit Tests

- three-dimensional classification combinations;
- `TASK_LOCAL_PREFERENCE` non-persistence;
- `INSUFFICIENT_EVIDENCE` Prompt Rule prohibition;
- mechanism mapping and rejected-mechanism record;
- RuleUnit normalization and candidate findings;
- `B08/B11` applicability;
- Gate policy extension and non-weakening;
- Provider status normalization;
- evidence integrity.

### 24.2 Workspace Integration Tests

- Modify/Fix cannot alter source before PASS;
- Audit Only creates no copy;
- Audit + Optimize creates a copy only after need and authorization;
- source digest changes trigger `B10`;
- FAIL preserves the original;
- PASS performs same-filesystem atomic replacement;
- replacement failure restores the one-generation backup;
- cross-volume publication fails;
- Windows Unicode paths and file-lock behavior.

### 24.3 Intent Flow Tests

- Create with and without external creator;
- Modify stable invariant;
- Modify task-local preference;
- Fix reproducible environment bug;
- Fix with insufficient evidence;
- Audit Only pass;
- Audit Only fail and minimal findings;
- Audit + Optimize pass;
- Audit + Optimize remediation failure.

### 24.4 Provider Contract Tests

Every adapter uses fixtures for valid output, empty output, malformed output, timeout, incompatible version, conflicting finding, partial artifact, and fallback.

### 24.5 Governance Regression Families

At minimum:

```text
accidental-in-place-write
provider-pass-bypasses-gate
audit-only-auto-upgrades
optional-provider-causes-fail
missing-required-evidence-passes
non-critical-link-blocks-gate
prompt-rule-added-for-unknown-cause
source-changed-before-publish
cross-volume-publish-succeeds
project-policy-weakens-core-gate
```

### 24.6 Safety Properties

- user paths cannot escape staging scope;
- symlinks or Windows reparse points cannot redirect mutation outside scope;
- malformed Provider output cannot alter Gate state;
- every Gate FAIL forbids publication;
- no publication event occurs before Gate PASS;
- optional Provider failure cannot erase a required capability;
- external PASS cannot satisfy the internal Gate by itself.

Tests assert observable artifacts, state transitions, evidence integrity, governance decisions, and publication safety—not fixed Prompt wording.

## 25. Acceptance Criteria — Final

### 25.1 Independence

- All external Providers can be disabled while the V1 pipeline remains functional.
- Each required capability has an internal fallback.
- Replacing a Provider does not change Internal Core or Gate semantics.

### 25.2 Isolation and Authorization

- Modify and Fix cannot publish without isolated staging and PASS.
- Audit Only never writes or auto-upgrades.
- Audit + Optimize does not stage before need and authorization are established.
- Candidate scope remains within user authorization.

### 25.3 Classification and Mechanisms

- Applicable operations produce all three classification dimensions.
- Local preferences never persist.
- Insufficient evidence never creates permanent rules.
- New Prompt Rules satisfy all justification requirements.

### 25.4 Evidence and Gate

- Every applicable required check has a trustworthy result.
- Optional Provider errors do not independently fail the Gate.
- Critical assets receive required verification; optional references generate warnings when unverifiable.
- Rule bloat findings pass through governance and evidence before Gate consideration.
- Only Internal Quality Gate emits final PASS/FAIL.

### 25.5 Outputs and Publication

- Normal successful operations deliver a complete Skill.
- Audit Only failure delivers the unchanged Skill plus only minimal blocking findings.
- Gate FAIL never mutates or publishes the source.
- Gate PASS is required for atomic publish.
- The published artifact can be loaded and revalidated independently.

### 25.6 Provider Contracts

- Every adapter passes contract tests.
- Formal publication uses pinned Provider identities.
- Local unpinned Providers are visibly degraded.
- Provider results contain no final-verdict or publication authority.

## 26. Success Metrics

Metrics are governance indicators, not trading-style signals or automatic release decisions.

| Metric | Definition |
|---|---|
| Rule Growth Rate | Persistent instruction growth over comparable changes. |
| Case-Specific Rule Count | Confirmed rules tied to individual historical symptoms. |
| Duplicate Rule Count | Governance-confirmed duplicates, not raw similarity candidates. |
| Prompt Rules per Failure Family | Permanent rules added per independent root cause. |
| Regression Coverage | Covered failure families divided by applicable failure families. |
| Skill Size Trend | Instruction and reference growth interpreted alongside capability growth. |
| Quality Gate Failure Rate | Gate failures by blocking policy and remediation stage. |
| Rules Moved to Mechanisms | Rules replaced by implementation, schema, validator, test, tooling, or workflow. |
| Provider Fallback Rate | External Provider degradation frequency and successful fallback rate. |
| Unchanged Audit Rate | Audits correctly resulting in no modification. |

No single metric directly determines quality. The central outcome is that historical failures predominantly produce mechanisms and regression protection, with only a small number producing true new invariants.

## 27. Example End-to-End Flows

### 27.1 Windows Encoding Fix

```text
Failure evidence
→ isolated copy
→ reproduce encoding failure
→ Primary: ENVIRONMENT_COMPATIBILITY
→ Control Gaps: IMPLEMENTATION_GAP + ENV_DETECTION_MISSING + REGRESSION_MISSING
→ Regression: REQUIRED
→ implementation and environment-detection fix
→ one parameterized encoding failure-family regression
→ inspect old encoding Prompt Rule
→ MOVE/DELETE when mechanism coverage is complete
→ required validation
→ Gate PASS
→ same-filesystem atomic replacement
```

### 27.2 Modify Request That Is Only a Preference

```text
"For this task, do not show faces"
→ Modify intent candidate
→ Primary: TASK_LOCAL_PREFERENCE
→ no persistent mechanism selected
→ original Skill remains unchanged
→ no replacement
```

### 27.3 Audit Only Pass

```text
Read source
→ inventory and bloat findings
→ Rule Governance
→ required validation
→ Gate PASS
→ UNCHANGED_VALIDATED
→ return Validated Complete Skill unchanged
```

### 27.4 Audit Only Fail

```text
Read source
→ blocking issue found
→ Gate FAIL
→ no copy, no modification, no upgrade
→ UNCHANGED_BLOCKED
→ return original Skill + minimal blocking findings
```

### 27.5 Optional Provider Failure

```text
External Provider TIMEOUT
→ record optional warning
→ invoke internal fallback
→ fallback supplies required capability and evidence
→ continue Gate evaluation
```

If the fallback cannot supply a required result, Gate failure is caused by `B08`—not by the external Provider's status itself.

## 28. Risks and Trade-offs

| Risk | Mitigation / accepted trade-off |
|---|---|
| Entry Skill becomes a super-Skill | Keep it as a thin router; use references and engine modules. |
| Provider drift | Pin formal runs; normalize results; keep internal semantics stable. |
| No stable Skill-to-Skill API | Adapter owns invocation; core owns capability port only. |
| Semantic bloat false positives | Findings are advisory until internally governed. |
| Gate creates false confidence | Required-check applicability derives from classification and mechanisms. |
| Workspace race | Source digest check before publication. |
| Windows replacement failure | Same-volume staging, one backup, verified recovery. |
| Test inflation | Organize by failure family and parameterize fixtures. |
| Fallback duplicates external Skills | Fallback supplies only minimum required correctness. |
| `AGENTS.md` inflation | Keep cases in mechanisms, tests, and on-demand references. |
| Gate policy inflation | Each core blocking rule must represent a cross-case risk and have tests. |
| External standards conflict | Preserve provenance; internal policy determines applicability. |
| Audit Only cannot always deliver a validated Skill | Legal exception preserves authorization and truthful Gate FAIL. |

## 29. Implementation-Time Open Questions

No architectural decisions remain open. The following implementation facts must be discovered before or during planning and do not change the baseline:

1. Which Provider invocation mechanisms are actually available in each target host at implementation time, so the corresponding adapters can be selected.
2. Which exact source and revision will be configured for each optional external Provider, especially the ambiguous `validate-skills` capability.
3. Which Python runtime and dependency versions are supported by the target Codex Plugin environment.
4. Which filesystem primitives provide the required same-filesystem atomic directory replacement semantics on supported Windows and Unix environments.
5. Which behavioral runner, if any, is available in the initial implementation environment.

If an implementation fact would require changing an invariant, state transition, Provider authority boundary, Gate authority, output contract, or V1/V2 boundary, implementation must stop and request an architecture-baseline revision.

## 30. Final Decision Record

The following are **Final** for V1:

- one internal governance Pipeline;
- one thin public `skill-engineer` entry;
- three-dimensional issue classification;
- mechanism selection before persistent change;
- isolated Modify and Fix;
- read-only Audit Only with a truthful failure exception;
- delayed staging for Audit + Optimize;
- Provider ports and replaceable adapters;
- internal fallbacks for required capabilities;
- pinned Providers for CI/formal publication;
- rule detectors as evidence producers only;
- Internal Quality Gate as sole final adjudicator;
- same-filesystem atomic publication with one backup;
- two legal external output types;
- V1 scope and V2 deferrals in Section 23.

The next allowed artifact is a separate Implementation Plan and Task Breakdown derived from this document. No implementation should begin before that plan is reviewed.
