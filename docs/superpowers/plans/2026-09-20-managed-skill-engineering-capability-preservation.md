# Managed Skill Engineering and Capability Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every formal skill-engineering operation inspection-backed, extract baseline and candidate capability manifests through a default read-only Provider, block unauthorized capability regression, and issue verifiable completion receipts.

**Architecture:** A bundled semantic Provider extracts evidence-bound Capability Manifests for baseline and candidate artifacts. Deterministic engine modules validate and digest those manifests, compute a structured capability diff, verify Codex-authored decisions and user authorization, and feed preservation state into Coverage, Quality Gate, managed completion, and Apply. The plugin cannot intercept arbitrary writes, so unmanaged work is reported explicitly rather than represented as a completed audit.

**Tech Stack:** Python 3.11+, frozen dataclasses and `StrEnum`, JSON Schema draft 2020-12, PyYAML, pytest, Codex `exec` Provider adapter, PowerShell validation commands.

**Spec:** `docs/superpowers/specs/2026-09-20-managed-skill-engineering-capability-preservation-design.md`

## Global Constraints

- Codex owns semantic intent, change classification, rationale, and authorization interpretation.
- Providers return typed semantic evidence only; they never return Gate, Apply, publication, or lifecycle decisions.
- Deterministic code must not infer capabilities from filenames, keyword counts, or a fixed document/domain catalog.
- Preserve current user changes in the dirty worktree; do not reset, discard, or overwrite unrelated edits.
- Do not modify any real `gjb438c-document-engineering` directory; use repository fixtures and temporary copies only.
- Do not weaken Required Capability, Provider execution, evidence provenance, Coverage, or Gate assertions.
- Do not commit, push, tag, release, publish, or install during this plan unless the user separately authorizes it.
- Use UTF-8 explicitly for all Windows text I/O.
- Use `apply_patch` for repository edits.

---

## File Map

- `engine/models.py`: capability, diff, authorization, preservation, managed-status, and receipt records.
- `engine/capability_manifest.py`: manifest validation, canonical digest, evidence-bound deserialization.
- `engine/capability_diff.py`: deterministic semantic comparison and preservation assessment.
- `engine/providers.py`: typed Provider payload support for Capability Manifests.
- `engine/host_adapters.py`: bundled Provider discovery and read-only invocation.
- `engine/applicability.py`: explicit mode/audit-dimension applicability policy.
- `engine/orchestrator.py`: baseline/candidate Provider execution and managed phase binding.
- `engine/workspace.py`: semantic workspace diff and immutable baseline retention.
- `engine/quality_gate.py`: capability-preservation and managed-operation Gate enforcement.
- `engine/serialization.py`: backward-compatible bundle and receipt serialization.
- `scripts/skill_engineering.py`: default Provider loading, structured audit dimensions, status, and receipt CLI.
- `providers/capability-contract-provider/SKILL.md`: bundled read-only evidence extraction profile.
- `config/providers.yaml`: default `CAPABILITY_CONTRACT` and `DELIVERABLE_CONTRACT` Provider mappings.
- `schemas/*.schema.json`: manifest, diff, decision, inspection, validation, Provider, and completion contracts.
- `skills/skill-engineer/SKILL.md` and references: managed-result boundary and required engine workflow.
- `tests/fixtures/skills/capability-preservation-*`: five-output baseline and self-consistent one-output candidate.
- `tests/unit`, `tests/integration`, `tests/e2e`, `tests/regression`: focused TDD coverage.

### Task 1: Capability Manifest Models and Schemas

**Files:**
- Modify: `engine/models.py`
- Create: `schemas/capability-manifest.schema.json`
- Create: `tests/unit/test_capability_manifest_models.py`
- Modify: `tests/unit/test_contracts.py`

**Interfaces:**
- Produces: `ArtifactRole`, `CapabilityEvidenceState`, `CapabilityRecord`, `CapabilityManifest`.
- Produces: schema contract name `capability-manifest` loadable by `engine.contracts.validate_contract`.

- [ ] **Step 1: Write failing model and schema tests**

```python
def test_capability_manifest_schema_requires_digest_bound_provider_identity() -> None:
    payload = complete_capability_manifest_payload()
    payload.pop("artifact_digest")
    with pytest.raises(ValueError):
        validate_contract("capability-manifest", payload)


def test_capability_record_keeps_public_scope_as_structured_sets() -> None:
    record = CapabilityRecord(
        capability_id="document-generation",
        public_name="Document generation",
        capability_type="deliverable_set",
        declared_status="implemented",
        implementation_status="implemented",
        entrypoints=("cli:generate",),
        supported_profiles=("profile-a", "profile-b"),
        supported_deliverables=("A", "B"),
        templates=("template-a", "template-b"),
        schemas=("schema-a",),
        validation_coverage=("test:A", "test:B"),
        public_claim_sources=("file=SKILL.md;line=10",),
        implementation_evidence=("file=scripts/run.py;line=20",),
        confidence=1.0,
        evidence_state=CapabilityEvidenceState.COMPLETE,
    )
    assert record.supported_deliverables == ("A", "B")
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_capability_manifest_models.py tests/unit/test_contracts.py -v`

Expected: collection or import failure because the new models and schema do not exist.

- [ ] **Step 3: Add minimal immutable records**

```python
class ArtifactRole(StrEnum):
    BASELINE = "BASELINE"
    CANDIDATE = "CANDIDATE"


class CapabilityEvidenceState(StrEnum):
    COMPLETE = "COMPLETE"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True)
class CapabilityRecord:
    capability_id: str
    public_name: str
    capability_type: str
    declared_status: str
    implementation_status: str
    entrypoints: tuple[str, ...]
    supported_profiles: tuple[str, ...]
    supported_deliverables: tuple[str, ...]
    templates: tuple[str, ...]
    schemas: tuple[str, ...]
    validation_coverage: tuple[str, ...]
    public_claim_sources: tuple[str, ...]
    implementation_evidence: tuple[str, ...]
    confidence: float
    evidence_state: CapabilityEvidenceState


@dataclass(frozen=True)
class CapabilityManifest:
    schema_version: str
    inspection_id: str
    inspection_nonce: str
    artifact_role: ArtifactRole
    artifact_digest: str
    provider_identity: str
    capabilities: tuple[CapabilityRecord, ...]
    public_output_contract_status: str
    public_output_contract_evidence: tuple[str, ...]
    evidence_origin: str = "provider"
```

Add a strict JSON Schema with `additionalProperties: false`, SHA-256 digest patterns, unique `capability_id` enforcement in deterministic validation, evidence arrays, numeric confidence range `0..1`, and enums for artifact role/evidence state.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest tests/unit/test_capability_manifest_models.py tests/unit/test_contracts.py -v`

Expected: PASS.

- [ ] **Step 5: Record a no-commit checkpoint**

Run: `git diff --check -- engine/models.py schemas/capability-manifest.schema.json tests/unit/test_capability_manifest_models.py tests/unit/test_contracts.py`

Expected: no output; do not commit.

### Task 2: Manifest Validation and Canonical Digest

**Files:**
- Create: `engine/capability_manifest.py`
- Create: `validators/capability_manifest.py`
- Create: `tests/unit/test_capability_manifest.py`
- Modify: `engine/contracts.py`

**Interfaces:**
- Consumes: `CapabilityManifest`, `ArtifactManifest`, `ProviderExecution`.
- Produces: `capability_manifest_from_data(payload) -> CapabilityManifest`.
- Produces: `capability_manifest_digest(manifest) -> str`.
- Produces: `validate_capability_manifest(...) -> CheckResult`.

- [ ] **Step 1: Write failing provenance, boundary, duplicate-ID, and digest tests**

```python
def test_manifest_rejects_wrong_artifact_role(tmp_path: Path) -> None:
    result = validate_capability_manifest(
        manifest(role=ArtifactRole.BASELINE),
        artifact_manifest(tmp_path),
        inspection_id="inspection-1",
        inspection_nonce="nonce-1",
        provider_id="bundled.capability-contract",
        provider_execution=ProviderExecution.EXECUTED,
        expected_role=ArtifactRole.CANDIDATE,
    )
    assert result.status is CheckStatus.NOT_EXECUTED
    assert "CAPABILITY_MANIFEST_ROLE_MISMATCH" in result.evidence


def test_manifest_digest_is_order_stable() -> None:
    left = manifest_with_capabilities((record("b"), record("a")))
    right = manifest_with_capabilities((record("a"), record("b")))
    assert capability_manifest_digest(left) == capability_manifest_digest(right)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_capability_manifest.py -v`

Expected: import failure for `engine.capability_manifest`.

- [ ] **Step 3: Implement deterministic validation**

```python
def capability_manifest_digest(manifest: CapabilityManifest) -> str:
    payload = to_canonical_manifest_data(manifest)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_capability_manifest(
    manifest: CapabilityManifest,
    artifact: ArtifactManifest,
    *,
    inspection_id: str,
    inspection_nonce: str,
    provider_id: str,
    provider_execution: ProviderExecution,
    expected_role: ArtifactRole,
) -> CheckResult:
    # Validate execution, identity, nonce, artifact digest, role, origin,
    # unique stable IDs, evidence paths, and evidence completeness in this order.
```

Register the schema in `engine/contracts.py`. Evidence paths must resolve inside `artifact.files`; absolute paths and `..` are rejected. Provider confidence is recorded but never converted into semantic truth by a numeric threshold.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m pytest tests/unit/test_capability_manifest.py tests/unit/test_contracts.py -v`

Expected: PASS.

- [ ] **Step 5: Run existing deliverable validation tests**

Run: `python -m pytest tests/unit/test_deliverable_contract.py -v`

Expected: PASS with unchanged deliverable findings.

### Task 3: Deterministic Capability Diff

**Files:**
- Create: `engine/capability_diff.py`
- Create: `schemas/capability-diff.schema.json`
- Create: `tests/unit/test_capability_diff.py`

**Interfaces:**
- Consumes: validated baseline and candidate `CapabilityManifest` values.
- Produces: `CapabilityChangeKind`, `CapabilityChange`, `CapabilityDiff`, `compare_capability_manifests()`.

- [ ] **Step 1: Write failing classification tests**

```python
@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ((), CapabilityChangeKind.REMOVED),
        ((record("docs", deliverables=("SRS",)),), CapabilityChangeKind.NARROWED),
        ((record("docs", implementation_status="missing"),), CapabilityChangeKind.BROKEN),
        ((record("docs", evidence_state=CapabilityEvidenceState.UNVERIFIABLE),), CapabilityChangeKind.UNVERIFIABLE),
    ],
)
def test_capability_change_classification(candidate, expected) -> None:
    diff = compare_capability_manifests(
        manifest_with_capabilities((record("docs", deliverables=("SRS", "STD", "STP", "STR", "SDD_DETAIL")),)),
        manifest_with_capabilities(candidate, role=ArtifactRole.CANDIDATE),
    )
    assert diff.changes[0].kind is expected
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_capability_diff.py -v`

Expected: import failure for `engine.capability_diff`.

- [ ] **Step 3: Implement set-based structured comparison**

```python
class CapabilityChangeKind(StrEnum):
    ADDED = "ADDED"
    PRESERVED = "PRESERVED"
    MODIFIED = "MODIFIED"
    REMOVED = "REMOVED"
    NARROWED = "NARROWED"
    BROKEN = "BROKEN"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True)
class CapabilityChange:
    capability_id: str
    kind: CapabilityChangeKind
    changed_fields: tuple[str, ...]
    baseline_values: tuple[str, ...]
    candidate_values: tuple[str, ...]


@dataclass(frozen=True)
class CapabilityDiff:
    baseline_manifest_digest: str
    candidate_manifest_digest: str
    changes: tuple[CapabilityChange, ...]


PUBLIC_SCOPE_FIELDS = (
    "entrypoints",
    "supported_profiles",
    "supported_deliverables",
    "templates",
    "schemas",
)


def compare_capability_manifests(
    baseline: CapabilityManifest,
    candidate: CapabilityManifest,
) -> CapabilityDiff:
    baseline_by_id = {item.capability_id: item for item in baseline.capabilities}
    candidate_by_id = {item.capability_id: item for item in candidate.capabilities}
    changes = classify_capability_ids(baseline_by_id, candidate_by_id)
    return CapabilityDiff(
        capability_manifest_digest(baseline),
        capability_manifest_digest(candidate),
        tuple(changes),
    )
```

The diff record stores both manifest digests and exact before/after structured values for every changed field. Coordinated removal of declarations, implementation, entrypoints, and tests is still `REMOVED` because the baseline index is immutable.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/unit/test_capability_diff.py -v`

Expected: PASS for removed, narrowed, broken, unverifiable, preserved, modified, and added cases.

### Task 4: DecisionRecord Capability Decisions and Authorization

**Files:**
- Modify: `engine/models.py`
- Modify: `schemas/decision-record.schema.json`
- Modify: `engine/serialization.py`
- Modify: `tests/support.py`
- Create: `tests/unit/test_capability_decisions.py`
- Modify: `tests/unit/test_contracts.py`

**Interfaces:**
- Consumes: `CapabilityDiff`.
- Produces: `CapabilityDecisionKind`, `AuthorizationStatus`, `CapabilityChangeDecision`.
- Produces: `validate_capability_change_decision(diff, decision) -> CheckResult`.

- [ ] **Step 1: Write failing authorization coverage tests**

```python
def test_unapproved_removed_capabilities_require_authorization() -> None:
    result = validate_capability_change_decision(
        removed_four_diff(),
        capability_decision(
            removed_ids=("SDD_DETAIL", "STP", "STD", "STR"),
            authorization_status=AuthorizationStatus.MISSING,
        ),
    )
    assert result.status is CheckStatus.FAIL
    assert "CAPABILITY_REMOVAL_NOT_AUTHORIZED" in result.evidence


def test_authorization_must_match_exact_change_ids() -> None:
    result = validate_capability_change_decision(
        removed_four_diff(),
        authorized_decision(removed_ids=("STD",)),
    )
    assert result.status is CheckStatus.FAIL
    assert "CAPABILITY_AUTHORIZATION_SCOPE_MISMATCH" in result.evidence
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_capability_decisions.py tests/unit/test_contracts.py -v`

Expected: missing decision types and schema fields.

- [ ] **Step 3: Add structured decision records**

```python
class CapabilityDecisionKind(StrEnum):
    BUG_FIX = "BUG_FIX"
    IMPLEMENTATION_COMPLETION = "IMPLEMENTATION_COMPLETION"
    DECLARATION_CORRECTION = "DECLARATION_CORRECTION"
    CAPABILITY_REMOVAL = "CAPABILITY_REMOVAL"
    CAPABILITY_NARROWING = "CAPABILITY_NARROWING"
    INTENTIONAL_BREAKING_CHANGE = "INTENTIONAL_BREAKING_CHANGE"


class AuthorizationStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    REQUIRED = "REQUIRED"
    AUTHORIZED = "AUTHORIZED"
    DENIED = "DENIED"
    MISSING = "MISSING"


@dataclass(frozen=True)
class CapabilityChangeDecision:
    baseline_capability_digest: str
    candidate_capability_digest: str
    capability_changes: tuple[tuple[str, CapabilityDecisionKind], ...]
    removed_capability_ids: tuple[str, ...]
    narrowed_capability_ids: tuple[str, ...]
    change_rationale: str
    user_authorization_required: bool
    user_authorization_status: AuthorizationStatus
    authorization_evidence: tuple[str, ...]
    compatibility_impact: str
    migration_plan: str | None
    deprecation_plan: str | None
```

Add a frozen `CapabilityChangeDecision` with both manifest digests, per-change decisions, removed/narrowed IDs, rationale, authorization status/evidence, compatibility impact, migration plan, and deprecation plan. Add it to `DecisionRecord` as an optional compatibility field, but require it at Gate time for mutating managed operations.

- [ ] **Step 4: Preserve legacy deserialization without preserving legacy Apply**

`decision_from_data()` accepts a missing capability decision as `None`. Validation converts this to incomplete evidence for mutating flows; it must not authorize Apply.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `python -m pytest tests/unit/test_capability_decisions.py tests/unit/test_contracts.py tests/unit/test_diagnostics.py -v`

Expected: PASS.

### Task 5: Bundled Default Capability Provider

**Files:**
- Create: `providers/capability-contract-provider/SKILL.md`
- Modify: `config/providers.yaml`
- Modify: `engine/host_adapters.py`
- Modify: `engine/providers.py`
- Modify: `schemas/provider-result.schema.json`
- Create: `tests/unit/test_bundled_provider.py`
- Modify: `tests/unit/test_providers.py`
- Modify: `tests/integration/test_host_provider_execution.py`

**Interfaces:**
- Produces default Provider IDs `bundled.capability-contract` and `bundled.deliverable-contract`.
- Extends `ProviderResult` and `ProviderEvidence` with `capability_manifest: CapabilityManifest | None`.
- Produces `build_default_provider_adapters(plugin_root, executor=...)`.

- [ ] **Step 1: Write failing default discovery and typed-output tests**

```python
def test_default_provider_is_packaged_and_selected_without_cli_override() -> None:
    adapters = build_default_provider_adapters(PROJECT_ROOT)
    assert {item.descriptor.capability for item in adapters} >= {
        "CAPABILITY_CONTRACT",
        "DELIVERABLE_CONTRACT",
    }


def test_provider_cannot_return_gate_or_authorization_fields() -> None:
    payload = provider_payload(capability_manifest=manifest_payload())
    payload["apply_authorization"] = True
    with pytest.raises(ValueError):
        normalize_provider_result(payload, capability="CAPABILITY_CONTRACT")
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_bundled_provider.py tests/unit/test_providers.py -v`

Expected: default adapter and `capability_manifest` field are absent.

- [ ] **Step 3: Add the bundled read-only Provider profile**

The Provider instructions require exhaustive cross-file evidence for public claims, entrypoints, dispatch, implementation, templates, schemas, and per-capability tests. They require stable capability IDs and `UNVERIFIABLE` when evidence is insufficient. They explicitly forbid repair suggestions, Gate verdicts, authorization decisions, and file modification.

- [ ] **Step 4: Add explicit bundled Provider configuration**

```yaml
- provider_id: bundled.capability-contract
  capability: CAPABILITY_CONTRACT
  source_identity: bundled-provider:capability-contract-provider
  resource_path: providers/capability-contract-provider
  availability: packaged
  invocation_adapter: codex-exec
  optional: false
- provider_id: bundled.deliverable-contract
  capability: DELIVERABLE_CONTRACT
  source_identity: bundled-provider:capability-contract-provider
  resource_path: providers/capability-contract-provider
  availability: packaged
  invocation_adapter: codex-exec
  optional: false
```

Resolve `resource_path` relative to the installed plugin root and bind its `SKILL.md` digest into Provider evidence.

- [ ] **Step 5: Extend Provider normalization and prompt binding**

The adapter request includes `artifact_role`, artifact digest, inspection ID, and nonce. The provider-result schema accepts `capability_manifest` only for `CAPABILITY_CONTRACT`; existing `deliverable_contract` behavior remains.

- [ ] **Step 6: Run Provider tests and verify GREEN**

Run: `python -m pytest tests/unit/test_bundled_provider.py tests/unit/test_providers.py tests/integration/test_host_provider_execution.py -v`

Expected: PASS, including missing resource, crash, timeout, invalid schema, wrong nonce, and wrong digest cases.

Run: `python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py providers/capability-contract-provider`

Expected: `Skill is valid!` for the bundled Provider profile.

### Task 6: Explicit Applicability and Requiredness Policy

**Files:**
- Create: `engine/applicability.py`
- Modify: `engine/models.py`
- Modify: `engine/capabilities.py`
- Modify: `scripts/skill_engineering.py`
- Create: `tests/unit/test_applicability.py`
- Modify: `tests/integration/test_deliverable_contract_pipeline.py`

**Interfaces:**
- Produces: `AuditDimension` and `resolve_deliverable_applicability()`.
- Consumes: canonical mode, structured audit dimensions, validated manifest public-output status, and explicit not-required evidence.

- [ ] **Step 1: Write the failing mode matrix**

```python
@pytest.mark.parametrize(
    ("mode", "dimensions", "public_status", "expected"),
    [
        (Intent.AUDIT_REPAIR, (), "present", DeliverableContractApplicability.REQUIRED),
        (Intent.TARGETED_REPAIR, (), "unknown", DeliverableContractApplicability.REQUIRED),
        (Intent.CREATE, (), "present", DeliverableContractApplicability.REQUIRED),
        (Intent.AUDIT, (AuditDimension.DELIVERABLES,), "absent", DeliverableContractApplicability.REQUIRED),
        (Intent.AUDIT, (AuditDimension.STRUCTURE,), "absent", DeliverableContractApplicability.NOT_REQUIRED),
    ],
)
def test_applicability_matrix(mode, dimensions, public_status, expected) -> None:
    assert resolve_deliverable_applicability(mode, dimensions, public_status).applicability is expected
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_applicability.py -v`

Expected: missing applicability module and audit-dimension enum.

- [ ] **Step 3: Implement deterministic policy from structured state**

```python
class AuditDimension(StrEnum):
    FULL = "FULL"
    STRUCTURE = "STRUCTURE"
    CAPABILITIES = "CAPABILITIES"
    DELIVERABLES = "DELIVERABLES"
    ENTRYPOINTS = "ENTRYPOINTS"
    TEMPLATES = "TEMPLATES"
    PROFILES = "PROFILES"
    OUTPUT_COVERAGE = "OUTPUT_COVERAGE"
```

`COMPATIBILITY` remains only for callers that omit the new structured fields. It never produces complete managed coverage. Explicit `NOT_REQUIRED` is accepted only when the requested audit dimensions exclude output truthfulness and the validated Provider fact is `absent`; `unknown` is incomplete.

- [ ] **Step 4: Update CLI input**

Add repeatable `--audit-dimension` choices and `--deliverable-not-required-rationale`. Do not parse free-text requirements or target file contents in the CLI.

- [ ] **Step 5: Run applicability and existing coverage tests**

Run: `python -m pytest tests/unit/test_applicability.py tests/integration/test_deliverable_contract_pipeline.py -v`

Expected: PASS, including existing five-declared/one-verified behavior.

### Task 7: Baseline and Candidate Provider Execution

**Files:**
- Modify: `engine/orchestrator.py`
- Modify: `engine/serialization.py`
- Modify: `schemas/inspection-bundle.schema.json`
- Modify: `schemas/validation-bundle.schema.json`
- Modify: `scripts/skill_engineering.py`
- Create: `tests/integration/test_capability_manifest_pipeline.py`
- Modify: `tests/integration/test_phased_cli.py`
- Modify: `tests/integration/test_phased_workflow.py`

**Interfaces:**
- `InspectionBundle` stores validated baseline manifest, its digest, selected Provider identities, audit dimensions, and managed status.
- `ValidationBundle` stores candidate manifest, manifest digest, capability diff, preservation result, and Provider execution for the candidate phase.
- `PipelineOrchestrator.validate()` executes the same selected default Provider against the engine-staged candidate.

- [ ] **Step 1: Write failing two-phase Provider tests**

```python
def test_modify_runs_capability_provider_for_baseline_and_staged_candidate(tmp_path: Path) -> None:
    executor = RecordingCapabilityProviderExecutor()
    orchestrator = orchestrator_with_default_provider(executor)
    inspection = orchestrator.inspect(Intent.TARGETED_REPAIR, five_output_source(tmp_path))
    validation = orchestrator.validate(
        inspection,
        preservation_decision(inspection),
        (),
        candidate=one_output_candidate(tmp_path),
        target_parent=tmp_path / "stage",
        authorized_to_modify=True,
    )
    assert [call.artifact_role for call in executor.calls] == ["BASELINE", "CANDIDATE"]
    assert validation.capability_diff.removed_capability_ids == ("SDD_DETAIL", "STD", "STP", "STR")
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/integration/test_capability_manifest_pipeline.py tests/integration/test_phased_cli.py -v`

Expected: candidate Provider execution and bundle fields are absent.

- [ ] **Step 3: Add baseline extraction to inspect**

Run `CAPABILITY_CONTRACT` first, validate its manifest, resolve deliverable applicability, then run `DELIVERABLE_CONTRACT` when required. Persist selected default Provider descriptors and baseline manifest identity in the inspection bundle.

- [ ] **Step 4: Add candidate extraction to validate**

After `session.stage_candidate()`, invoke the persisted Provider identity against `execution_artifact` with `artifact_role=CANDIDATE`. Validate the candidate manifest, compute the diff, validate the Codex capability decision, and add deterministic checks before ordinary Gate evidence aggregation.

- [ ] **Step 5: Restore Provider execution in phased CLI validate**

`validate` constructs the default gateway from installed plugin resources and verifies that its Provider IDs/resource digests match the inspection. A different Provider resource cannot satisfy the original inspection.

- [ ] **Step 6: Run phased workflow tests and verify GREEN**

Run: `python -m pytest tests/integration/test_capability_manifest_pipeline.py tests/integration/test_phased_cli.py tests/integration/test_phased_workflow.py -v`

Expected: PASS; baseline and candidate evidence remain distinct and digest-bound.

### Task 8: Semantic Workspace Evidence and Preservation Gate

**Files:**
- Modify: `engine/workspace.py`
- Modify: `engine/quality_gate.py`
- Modify: `engine/orchestrator.py`
- Modify: `schemas/gate-result.schema.json`
- Modify: `schemas/validation-bundle.schema.json`
- Create: `tests/unit/test_semantic_workspace_diff.py`
- Modify: `tests/unit/test_quality_gate.py`
- Create: `tests/integration/test_capability_preservation_gate.py`

**Interfaces:**
- Produces: `SemanticWorkspaceDiff` and `CapabilityPreservationStatus`.
- Extends `GateContext` and `GateResult` with preservation and managed-operation state.

- [ ] **Step 1: Write failing Gate tests**

```python
def test_unapproved_removed_capability_blocks_apply() -> None:
    result = adjudicate(
        gate_context(
            coverage_status=CoverageStatus.FULL,
            capability_preservation=CapabilityPreservationStatus.AUTHORIZATION_REQUIRED,
        ),
        passing_evidence(),
    )
    assert result.verdict is GateVerdict.FAIL
    assert result.apply_authorized is False
    assert any("capability regression requires authorization" in item for item in result.blocking_findings)


def test_broken_capability_blocks_even_when_authorized() -> None:
    result = adjudicate(
        gate_context(capability_preservation=CapabilityPreservationStatus.CAPABILITY_REGRESSION),
        passing_evidence(),
    )
    assert result.verdict is GateVerdict.FAIL
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_semantic_workspace_diff.py tests/unit/test_quality_gate.py tests/integration/test_capability_preservation_gate.py -v`

Expected: preservation fields and semantic workspace diff are absent.

- [ ] **Step 3: Add semantic workspace record**

```python
class CapabilityPreservationStatus(StrEnum):
    CAPABILITY_PRESERVED = "CAPABILITY_PRESERVED"
    CAPABILITY_REGRESSION = "CAPABILITY_REGRESSION"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    CAPABILITY_UNVERIFIABLE = "CAPABILITY_UNVERIFIABLE"


@dataclass(frozen=True)
class SemanticWorkspaceDiff:
    file_changes: WorkspaceDiff
    declaration_changes: tuple[str, ...]
    entrypoint_changes: tuple[str, ...]
    schema_changes: tuple[str, ...]
    template_changes: tuple[str, ...]
    test_coverage_changes: tuple[str, ...]
    capability_changes: tuple[CapabilityChange, ...]
```

Populate semantic categories only from the validated structured diff, not from file paths or keywords.

- [ ] **Step 4: Add preservation policy to Gate**

Map no regression to `CAPABILITY_PRESERVED`, authorized removed/narrowed changes to `CAPABILITY_PRESERVED` with warnings, unauthorized removed/narrowed changes to `AUTHORIZATION_REQUIRED`, broken changes to `CAPABILITY_REGRESSION`, and unknown evidence to `CAPABILITY_UNVERIFIABLE` plus incomplete coverage.

- [ ] **Step 5: Run Gate tests and verify GREEN**

Run: `python -m pytest tests/unit/test_quality_gate.py tests/unit/test_semantic_workspace_diff.py tests/integration/test_capability_preservation_gate.py -v`

Expected: PASS; validation success alone cannot authorize Apply.

### Task 9: Managed Completion Receipt, Unmanaged Status, and Apply Binding

**Files:**
- Modify: `engine/models.py`
- Modify: `engine/orchestrator.py`
- Modify: `engine/workspace.py`
- Modify: `engine/serialization.py`
- Modify: `scripts/skill_engineering.py`
- Create: `schemas/managed-completion-receipt.schema.json`
- Create: `tests/unit/test_managed_completion.py`
- Create: `tests/integration/test_managed_apply.py`
- Modify: `tests/integration/test_atomic_publish.py`

**Interfaces:**
- Produces: `ManagedOperationStatus`, `ManagedCompletionReceipt`, `completion_receipt(outcome)`.
- Adds CLI command `status --target PATH [--receipt PATH] --output PATH`.
- Strengthens `apply` to consume a valid completion receipt bound to the outcome.

- [ ] **Step 1: Write failing unmanaged and stale-Apply tests**

```python
def test_status_without_inspection_receipt_is_unmanaged_change(tmp_path: Path) -> None:
    result = managed_status(tmp_path, receipt=None)
    assert result.status is ManagedOperationStatus.UNMANAGED_CHANGE
    assert result.formal_completion is False


def test_target_pytest_pass_cannot_replace_gate(tmp_path: Path) -> None:
    receipt = completion_receipt_from_target_test_only(exit_code=0)
    with pytest.raises(ValueError, match="formal inspection and Gate evidence are required"):
        validate_completion_receipt(receipt)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_managed_completion.py tests/integration/test_managed_apply.py -v`

Expected: managed completion types and receipt validator are absent.

- [ ] **Step 3: Add digest-chained completion receipt**

```python
class ManagedOperationStatus(StrEnum):
    MANAGED = "MANAGED"
    AUDIT_INCOMPLETE = "AUDIT_INCOMPLETE"
    UNMANAGED_CHANGE = "UNMANAGED_CHANGE"
    APPLY_BLOCKED = "APPLY_BLOCKED"


@dataclass(frozen=True)
class ManagedCompletionReceipt:
    inspection_id: str
    operation_mode: Intent
    source_digest: str | None
    candidate_digest: str
    baseline_capability_digest: str | None
    candidate_capability_digest: str
    validation_bundle_digest: str
    semantic_confirmation_digest: str
    coverage_status: CoverageStatus
    capability_preservation: CapabilityPreservationStatus
    gate_verdict: GateVerdict
    gate_outcome: GateOutcome
    formal_completion: bool
```

Canonicalize and hash the validation bundle and confirmation. The receipt schema forbids extra fields and requires the same inspection ID and artifact digests as the outcome.

- [ ] **Step 4: Add unmanaged status command**

`status` with no receipt, invalid receipt, or a receipt bound to another target returns structured `UNMANAGED_CHANGE`/`AUDIT_INCOMPLETE` and exit code 2. It never reads target-owned `validation.json` as formal evidence.

- [ ] **Step 5: Require receipt validation in Apply**

Before filesystem replacement, verify source digest, staged candidate digest, both capability digests, full required coverage, semantic confirmation, preservation state, and `PASS / READY_TO_APPLY`. Retain current concurrent-source and recovery protections.

- [ ] **Step 6: Run Apply tests and verify GREEN**

Run: `python -m pytest tests/unit/test_managed_completion.py tests/integration/test_managed_apply.py tests/integration/test_atomic_publish.py -v`

Expected: PASS for managed Apply; missing/stale/forged receipts are rejected.

### Task 10: Skill Instructions and Provider Discipline Tests

**Files:**
- Modify: `skills/skill-engineer/SKILL.md`
- Modify: `skills/skill-engineer/references/pipeline.md`
- Modify: `skills/skill-engineer/references/provider-contracts.md`
- Modify: `skills/skill-engineer/references/quality-gate.md`
- Modify: `skills/skill-engineer/references/required-capabilities.md`
- Modify: `tests/unit/test_skill_entry.py`
- Modify: `tests/unit/test_reference_integrity.py`
- Create: `tests/regression/test_managed_workflow_instructions.py`

**Interfaces:**
- Documents the engine-produced receipt as the only formal completion shape.
- Documents `UNMANAGED_CHANGE` without claiming platform-level write interception.

- [ ] **Step 1: Write failing instruction-contract tests**

```python
def test_skill_requires_engine_receipt_before_completion_claim() -> None:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    assert "ManagedCompletionReceipt" in skill
    assert "UNMANAGED_CHANGE" in skill
    assert "target pytest cannot replace the Quality Gate" in skill


def test_skill_does_not_claim_platform_write_interception() -> None:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    assert "cannot intercept every out-of-band write" in skill
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_skill_entry.py tests/unit/test_reference_integrity.py tests/regression/test_managed_workflow_instructions.py -v`

Expected: missing managed-receipt language.

- [ ] **Step 3: Update instructions minimally**

Keep `SKILL.md` concise. Put phase details, Provider contracts, and Gate truth table in existing references. Replace prompt-only completion language with a positive output contract: a completed formal result contains inspection ID, receipt path, Gate verdict, coverage, and capability-preservation status.

- [ ] **Step 4: Run instruction tests and quick validation**

Run: `python -m pytest tests/unit/test_skill_entry.py tests/unit/test_reference_integrity.py tests/regression/test_managed_workflow_instructions.py -v`

Run: `python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/skill-engineer`

Expected: tests PASS and `Skill is valid!`.

### Task 11: Five-to-One Capability Regression Dogfooding Fixture

**Files:**
- Create: `tests/fixtures/skills/capability-preservation-baseline/SKILL.md`
- Create: `tests/fixtures/skills/capability-preservation-baseline/scripts/run.py`
- Create: `tests/fixtures/skills/capability-preservation-baseline/tests/test_outputs.py`
- Create: `tests/fixtures/skills/capability-preservation-candidate/SKILL.md`
- Create: `tests/fixtures/skills/capability-preservation-candidate/scripts/run.py`
- Create: `tests/fixtures/skills/capability-preservation-candidate/tests/test_outputs.py`
- Create: `tests/e2e/test_capability_preservation_dogfood.py`

**Interfaces:**
- Baseline exposes `SRS`, `SDD_DETAIL`, `STP`, `STD`, and `STR` through generic fixture data.
- Candidate exposes only `SRS`, is internally consistent, and passes its own pytest.

- [ ] **Step 1: Add the failing end-to-end test before production wiring is complete**

```python
def test_self_consistent_five_to_one_repair_is_blocked_without_authorization(tmp_path: Path) -> None:
    source, candidate = copy_dogfood_pair(tmp_path)
    assert run_target_tests(candidate).returncode == 0
    outcome = run_managed_repair(source, candidate, decision=unapproved_removal_decision())
    assert outcome.capability_diff.removed_capability_ids == (
        "SDD_DETAIL", "STD", "STP", "STR",
    )
    assert outcome.gate_result.verdict is GateVerdict.FAIL
    assert outcome.gate_result.apply_authorized is False
    assert outcome.lifecycle_state is not LifecycleState.AUDIT_COMPLETE_VALID
```

- [ ] **Step 2: Run dogfooding test and verify RED**

Run: `python -m pytest tests/e2e/test_capability_preservation_dogfood.py -v`

Expected: fail until the full Provider/manifest/diff/Gate chain is wired.

- [ ] **Step 3: Add authorized counterpart**

The authorized DecisionRecord names the exact four capability IDs, includes non-empty authorization evidence, compatibility impact, migration plan, and deprecation plan. Assert that authorization permits Gate evaluation but does not override unrelated validation, coverage, or broken-capability failures.

- [ ] **Step 4: Run end-to-end dogfooding and verify GREEN**

Run: `python -m pytest tests/e2e/test_capability_preservation_dogfood.py -v`

Expected: unauthorized candidate blocked; authorized, otherwise valid candidate may reach `READY_TO_APPLY`; neither test modifies a real external Skill.

### Task 12: Full Regression, Packaging Integrity, and Final Evidence

**Files:**
- Modify only if failures reveal defects in files already named by this plan.
- Create: `docs/verification/managed-capability-preservation-2026-09-20.md`

**Interfaces:**
- Produces a verification report with commands, counts, dogfooding results, known limits, Git diff/stat, and installation status.

- [ ] **Step 1: Run focused capability suites**

Run:

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python -m pytest tests/unit/test_capability_manifest_models.py tests/unit/test_capability_manifest.py tests/unit/test_capability_diff.py tests/unit/test_capability_decisions.py tests/unit/test_applicability.py tests/unit/test_quality_gate.py -v
python -m pytest tests/integration/test_capability_manifest_pipeline.py tests/integration/test_capability_preservation_gate.py tests/integration/test_managed_apply.py tests/integration/test_deliverable_contract_pipeline.py -v
python -m pytest tests/e2e/test_capability_preservation_dogfood.py -v
```

Expected: all pass.

- [ ] **Step 2: Run project unit tests**

Run: `python -m pytest tests/unit -v`

Expected: PASS with no new skips.

- [ ] **Step 3: Run full regression**

Run: `python -m pytest -v`

Expected: all tests pass; only previously documented Windows symlink skips remain.

- [ ] **Step 4: Validate schemas and Skill packaging**

Run:

```powershell
python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/skill-engineer
python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py providers/capability-contract-provider
git diff --check
```

Expected: both Skill directories report `Skill is valid!` and no diff errors.

- [ ] **Step 5: Verify real target immutability without running it**

Compute the recursive SHA-256 inventory of `D:\project\skills\test3\.hypercode\skills\gjb438c-document-engineering` before and after all tests. Do not execute dogfooding against that directory. Expected: identical aggregate digest.

- [ ] **Step 6: Write verification report**

Record Root Cause, Architecture Change, changed files, Capability Manifest/diff structures, DecisionRecord fields, applicability matrix, Gate truth table, tests, fixture dogfooding, platform limitation, `git diff --stat`, and whether installation occurred. State explicitly that no platform-level write hook was implemented.

- [ ] **Step 7: Preserve installation boundary**

Do not install automatically. Report repository verification as complete and installation as not performed unless the user separately authorizes installation. If later authorized, use the plugin development installation workflow and verify repository/package/cache/loaded version hashes.
