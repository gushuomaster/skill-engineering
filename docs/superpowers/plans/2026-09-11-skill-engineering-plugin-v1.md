# Skill Engineering Plugin V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the frozen V1 Skill Engineering Plugin as a minimal, independently testable governance pipeline that safely creates, modifies, fixes, audits, validates, and publishes complete Skills.

**Architecture:** A thin `skill-engineer` entry routes user intent into an internal Python orchestration core. The core owns state, diagnostics, three-dimensional classification, mechanism selection, rule governance, evidence collection, the sole Quality Gate, and safe publication; external Skills attach only through replaceable Provider adapters with internal fallbacks.

**Tech Stack:** Python 3.11+, standard-library dataclasses/enums/pathlib/hashlib/shutil, PyYAML 6.x, jsonschema 4.x, pytest 8.x, Codex Plugin manifest and Skill format.

**Spec:** `docs/superpowers/specs/2026-09-11-skill-engineering-plugin-design.md`

## Global Constraints

- The design document is **Final / Frozen** and is the sole architecture authority.
- Do not add V1 features, new control layers, MCP, UI, remote orchestration, databases, automatic Provider installation, or multi-model evaluation.
- Only the Internal Quality Gate emits final `PASS` or `FAIL`.
- Validators, tests, rule detectors, and external checkers return evidence only.
- Modify and Fix always use an isolated same-filesystem working copy.
- Audit Only is read-only and never enters `STAGED`.
- Audit + Optimize creates staging only after a read-only audit finds necessary work and authorization exists.
- `TASK_LOCAL_PREFERENCE` is never persisted.
- `INSUFFICIENT_EVIDENCE` never produces a permanent Prompt Rule.
- Rule Bloat Detection cannot directly fail the Gate.
- Gate PASS does not imply `publish_authorized = true`; Audit Only PASS remains unchanged and non-publishable.
- Publication requires same-filesystem staging, `publish_authorized = true`, a validated candidate digest, and an unchanged source digest for existing-source flows.
- V1 retains exactly one previous-version backup.
- Project policy may strengthen but never disable or weaken `B01–B12`.
- External Providers are optional; formal/CI publication requires pinned Provider identities.
- Use UTF-8 without BOM for all project text files.
- Implement with TDD: failing test, observed failure, minimal implementation, observed pass.
- Execution prerequisite: run this plan in a Git repository or initialize one before Task 1 so each task can end in a reviewable commit.

---

## File and Responsibility Map

| Area | Files | Responsibility |
|---|---|---|
| Plugin package | `.codex-plugin/plugin.json`, `AGENTS.md`, `skills/skill-engineer/**` | Distribution, stable governance, thin user entry |
| Project tooling | `pyproject.toml` | Runtime dependencies and pytest configuration |
| Contracts | `engine/models.py`, `engine/contracts.py`, `schemas/*.schema.json` | Typed internal records and boundary validation |
| State | `engine/state_machine.py` | Legal milestone transitions and remediation loops |
| Workspace | `engine/workspace.py`, `engine/inventory.py` | Isolation, digests, manifests, atomic publication |
| Diagnosis | `engine/diagnostics.py`, `engine/mechanism_selection.py` | Conditional RCA, three-dimensional classification, mechanism choices |
| Governance | `engine/rule_governance.py`, `engine/rule_bloat.py` | Rule findings and internal KEEP/MERGE/MOVE/DELETE decisions |
| Validation | `validators/skill_structure.py`, `validators/reference_integrity.py` | Deterministic `CheckResult` producers |
| Evidence/Gate | `engine/evidence.py`, `engine/quality_gate.py`, `config/gate-policy.yaml` | Evidence integrity and sole final verdict |
| Regression | `engine/regression.py`, `engine/behavioral.py` | Failure-family execution and runner-neutral behavioral scenarios |
| Providers | `engine/providers.py`, `config/providers.yaml` | Capability ports, adapter registry, identity policy, fallback |
| Orchestration | `engine/orchestrator.py`, `engine/output.py`, `scripts/skill_engineering.py` | End-to-end modes, legal outputs, CLI |
| Tests | `tests/unit/**`, `tests/integration/**`, `tests/regression/**`, `tests/fixtures/**` | Contract, flow, safety, and governance proof |

## Dependency and Parallelism Map

```text
Task 1  Plugin + test scaffold
  ↓
Task 2  Contracts + schemas
  ├──────────────┬──────────────┐
  ↓              ↓              ↓
Task 3 State   Task 4 Workspace Task 5 Diagnostics
  └──────────────┴──────┬───────┘
                        ↓
Task 6 Validators + Evidence
                        ↓
Task 7 Quality Gate
                        ↓
Task 8 Minimal runnable pipeline + CLI
  ├────────────────┬────────────────┐
  ↓                ↓                ↓
Task 9 Rule       Task 10          Task 11 Provider
Governance/Bloat  Regression       Gateway/Fallback
  └────────────────┴───────┬────────┘
                           ↓
Task 12 Atomic publication
                           ↓
Task 13 Skill entry + configuration
                           ↓
Task 14 Full V1 integration and packaging
```

Parallel rules:

- Tasks 3, 4, and 5 may run in parallel after Task 2; they touch separate modules.
- Tasks 9, 10, and 11 may run in parallel after Task 8.
- Task 6 waits for Task 4 because validators consume `ArtifactManifest` inventory.
- Task 7 waits for Task 6 because the Gate consumes normalized evidence.
- Task 8 waits for Tasks 3–7 and is the first minimal runnable closed-loop milestone.
- Task 12 waits for Tasks 4, 7, 8, 9, 10, and 11.
- Tasks 13 and 14 remain serial integration tasks.

## Frozen-Spec Coverage Matrix

| Design sections | Implemented or verified by |
|---|---|
| 1–4 Problem, goals, non-goals, principles | Global Constraints; Tasks 1, 8, 13, 14 |
| 5 Top-level contract | Tasks 2, 8, 14 |
| 6 Invariants | Tasks 2–14; governance regression matrix in Task 14 |
| 7–9 Architecture, responsibilities, Pipeline | Tasks 1, 3–13 |
| 10 State model | Tasks 3, 8, 14 |
| 11–12 Classification and mechanisms | Tasks 2, 5, 8, 14 |
| 13–14 Skill/rule governance | Tasks 9, 13, 14 |
| 15 Regression strategy | Tasks 10, 14 |
| 16 Provider architecture | Tasks 2, 11, 14 |
| 17 Evidence model | Tasks 2, 6, 7, 14 |
| 18 Quality Gate | Tasks 2, 7, 8, 14 |
| 19 Atomic publication | Tasks 4, 7, 12, 14 |
| 20–21 Configuration and schemas | Tasks 2, 7, 11, 13 |
| 22–23 Directory and V1 scope | Tasks 1, 13, 14 |
| 24 Self-test strategy | Tests in every task; full verification in Task 14 |
| 25 Acceptance criteria | Per-task acceptance criteria; V1 Definition of Done |
| 26 Success metrics | Task 14 verification report |
| 27 End-to-end flows | Tasks 8, 10, 12, 14 |
| 28 Risks/trade-offs | Global Constraints; safety tests in Tasks 4, 7, 11, 12, 14 |
| 29 Implementation facts | Checked at Tasks 1, 11, 12, and 14; baseline revision required if an invariant would change |
| 30 Final decisions | Global Constraints and final Definition of Done |

---

### Task 1: Establish the Plugin and Python Test Scaffold

**Inputs:** Frozen design Sections 3, 7, 22, and 23; empty implementation workspace; installed `plugin-creator` scaffold script.

**Outputs:** A valid plugin manifest, Python package skeleton, dependency declaration, and a passing smoke test.

**Dependencies:** None.

**Parallelism:** Serial foundation task.

**Tests:** `tests/unit/test_plugin_scaffold.py` plus bundled Plugin manifest validation.

**Files:**

- Create: `.codex-plugin/plugin.json`
- Create: `pyproject.toml`
- Create: `engine/__init__.py`
- Create: `validators/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/test_plugin_scaffold.py`

**Interfaces:**

- Consumes: no internal interfaces.
- Produces: importable `engine` and `validators` packages; pytest command; plugin name `skill-engineering`.

- [ ] **Step 1: Generate only the supported plugin scaffold**

Run from `D:\project\skill-engineering`:

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
python C:\Users\28320\.codex\skills\.system\plugin-creator\scripts\create_basic_plugin.py skill-engineering --path D:\project --with-skills --with-scripts
```

Expected: `.codex-plugin/plugin.json`, `skills/`, and `scripts/` exist; no marketplace, MCP, app, hook, or asset files are created.

- [ ] **Step 2: Write the failing scaffold test**

```python
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_plugin_manifest_exposes_only_skill_component() -> None:
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "skill-engineering"
    assert manifest["version"] == "0.1.0"
    assert manifest["skills"] == "./skills/"
    assert "mcpServers" not in manifest
    assert "apps" not in manifest
    assert "hooks" not in manifest
```

- [ ] **Step 3: Run the test and observe the expected metadata mismatch**

Run:

```powershell
python -m pytest tests/unit/test_plugin_scaffold.py -v
```

Expected: FAIL until the generated manifest metadata is specialized for Skill Engineering.

- [ ] **Step 4: Add project metadata and dependency configuration**

Create `pyproject.toml` with:

```toml
[project]
name = "skill-engineering"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "jsonschema>=4.23,<5",
  "PyYAML>=6,<7",
]

[project.optional-dependencies]
test = ["pytest>=8,<9"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
```

Update `plugin.json` to keep `author.name = "Local developer"` and use:

```json
{
  "name": "skill-engineering",
  "version": "0.1.0",
  "description": "Governed creation, repair, audit, validation, and release of Codex Skills.",
  "author": { "name": "Local developer" },
  "skills": "./skills/",
  "interface": {
    "displayName": "Skill Engineering",
    "shortDescription": "Engineer and validate maintainable Skills.",
    "longDescription": "Applies root-cause analysis, mechanism selection, rule governance, regression checks, and an internal quality gate to complete Skills.",
    "developerName": "Local developer",
    "category": "Productivity",
    "capabilities": ["Write"],
    "defaultPrompt": "Create, repair, or audit this Skill through the engineering quality gate."
  }
}
```

- [ ] **Step 5: Install test dependencies and run the smoke test**

Run:

```powershell
python -m pip install -e ".[test]"
python -m pytest tests/unit/test_plugin_scaffold.py -v
```

Expected: PASS.

- [ ] **Step 6: Validate the plugin manifest**

Run:

```powershell
python C:\Users\28320\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py D:\project\skill-engineering
```

Expected: plugin validation succeeds without placeholders or unsupported fields.

- [ ] **Step 7: Commit the scaffold**

```powershell
git add .codex-plugin pyproject.toml engine validators tests/unit/test_plugin_scaffold.py tests/conftest.py
git commit -m "chore: scaffold skill engineering plugin"
```

**Acceptance Criteria:** Plugin validation passes; pytest can import project packages; the manifest advertises Skills only; no deferred V1 components are scaffolded.

---

### Task 2: Implement Contract Models and JSON Schemas

**Inputs:** Frozen design Sections 5, 10, 11, 16, 17, 18, and 21.

**Outputs:** Complete machine-valid schemas and typed Python records with conditional contracts.

**Dependencies:** Task 1.

**Parallelism:** Serial contract foundation; Tasks 3–5 branch after completion.

**Tests:** `tests/unit/test_contracts.py` against positive and invalid fixtures for all nine schemas.

**Files:**

- Create: `engine/models.py`
- Create: `engine/contracts.py`
- Create: `schemas/artifact-manifest.schema.json`
- Create: `schemas/decision-record.schema.json`
- Create: `schemas/provider-result.schema.json`
- Create: `schemas/check-result.schema.json`
- Create: `schemas/regression-case.schema.json`
- Create: `schemas/behavioral-scenario.schema.json`
- Create: `schemas/behavioral-result.schema.json`
- Create: `schemas/gate-policy.schema.json`
- Create: `schemas/gate-result.schema.json`
- Create: `tests/unit/test_contracts.py`
- Create: `tests/fixtures/contracts/*.json`

**Interfaces:**

- Consumes: `jsonschema.Draft202012Validator`.
- Produces:

```python
def validate_contract(schema_name: str, payload: dict[str, object]) -> None: ...
def load_schema(schema_name: str) -> dict[str, object]: ...
```

And immutable records/enums:

```python
Intent
LifecycleState
PrimaryIssueClass
ControlGap
RegressionDisposition
CheckStatus
GateVerdict
GateOutcome
ProviderStatus
ArtifactManifest
DecisionRecord
ProviderDescriptor
ProviderResult
CheckResult
GateResult
```

- [ ] **Step 1: Write failing conditional-contract tests**

```python
import pytest
from jsonschema import ValidationError

from engine.contracts import validate_contract


def test_create_manifest_allows_null_source_revision() -> None:
    payload = load_fixture("contracts/artifact_manifest_create.json")
    validate_contract("artifact-manifest", payload)


def test_modify_manifest_requires_source_digest() -> None:
    payload = load_fixture("contracts/artifact_manifest_modify_missing_digest.json")
    with pytest.raises(ValidationError):
        validate_contract("artifact-manifest", payload)


def test_fix_decision_requires_root_cause() -> None:
    payload = load_fixture("contracts/decision_fix_missing_root_cause.json")
    with pytest.raises(ValidationError):
        validate_contract("decision-record", payload)


def test_audit_pass_is_not_publish_authorized() -> None:
    payload = load_fixture("contracts/gate_audit_pass.json")
    validate_contract("gate-result", payload)
    assert payload["verdict"] == "PASS"
    assert payload["publish_authorized"] is False
    assert payload["outcome"] == "UNCHANGED_VALIDATED"
```

- [ ] **Step 2: Run tests and observe missing contract modules**

Run:

```powershell
python -m pytest tests/unit/test_contracts.py -v
```

Expected: FAIL because `engine.contracts` and schemas do not exist.

- [ ] **Step 3: Define exact enums and dataclasses**

Use string enums matching the frozen spec. Define conditional fields explicitly:

```python
@dataclass(frozen=True)
class ArtifactManifest:
    intent: Intent
    artifact_root: str
    skill_name: str
    source_revision: str | None
    source_digest: str | None
    files: tuple[str, ...]
    executable_assets: tuple[str, ...]
    required_references: tuple[str, ...]
    test_inventory: tuple[str, ...]
    content_digest: str


@dataclass(frozen=True)
class DecisionRecord:
    intent: Intent
    primary_issue_class: PrimaryIssueClass
    control_gaps: tuple[ControlGap, ...]
    regression_disposition: RegressionDisposition
    root_cause: str | None
    evidence_limitations: tuple[str, ...]
    selected_mechanisms: tuple[str, ...]
    rejected_mechanisms: tuple[str, ...]
    prompt_rule_justification: str | None
```

- [ ] **Step 4: Write all Draft 2020-12 schemas**

Encode these conditional rules with `if/then`:

- Create permits null `source_revision` and `source_digest`.
- Modify, Fix, Audit Only, and Audit + Optimize require a non-empty source digest.
- Fix requires non-empty `root_cause`.
- Create and non-defect Modify permit null `root_cause`.
- Audit requires root cause only when `primary_issue_class` is a defect class.
- Defect classes are `IMPLEMENTATION_DEFECT`, `ENVIRONMENT_COMPATIBILITY`, `WORKFLOW_DESIGN_DEFECT`, `CONTRACT_ENFORCEMENT_GAP`, and an evidenced `DOCUMENTATION_GAP`.
- `publish_authorized = true` requires `verdict = PASS` and `outcome = READY_TO_PUBLISH`; lifecycle state becomes `PUBLISHED` only after atomic publication succeeds.
- `UNCHANGED_VALIDATED` requires `publish_authorized = false`.
- `FAIL` requires `publish_authorized = false`.
- Provider result schema excludes final verdict, publication, replacement, and state-transition fields through `additionalProperties: false`.

- [ ] **Step 5: Implement schema loading and validation**

```python
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"


@lru_cache(maxsize=None)
def load_schema(schema_name: str) -> dict[str, object]:
    path = SCHEMA_ROOT / f"{schema_name}.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def validate_contract(schema_name: str, payload: dict[str, object]) -> None:
    Draft202012Validator(load_schema(schema_name)).validate(payload)
```

- [ ] **Step 6: Run contract tests**

Run:

```powershell
python -m pytest tests/unit/test_contracts.py -v
```

Expected: every positive fixture passes and every invalid conditional fixture raises `ValidationError`.

- [ ] **Step 7: Commit the contract layer**

```powershell
git add engine/models.py engine/contracts.py schemas tests/unit/test_contracts.py tests/fixtures/contracts
git commit -m "feat: define skill engineering contracts"
```

**Acceptance Criteria:** All nine schemas validate their positive fixtures; conditional `root_cause`, `source_revision/source_digest`, and `publish_authorized` behavior is enforced; forbidden Provider authority fields are rejected.

---

### Task 3: Implement the Non-Linear Lifecycle State Machine

**Inputs:** Frozen design Section 10 and contract enums from Task 2.

**Outputs:** A pure state-transition engine that supports staging-first flows and remediation loops.

**Dependencies:** Task 2.

**Parallelism:** May run in parallel with Tasks 4 and 5.

**Tests:** `tests/unit/test_state_machine.py`, covering staging-first, Audit Only, remediation-loop, stale-cycle, and forbidden transitions.

**Files:**

- Create: `engine/state_machine.py`
- Create: `tests/unit/test_state_machine.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class TransitionContext:
    intent: Intent
    authorized_to_modify: bool
    defect_found: bool
    staging_exists: bool
    remediation_cycle: int = 0
    audit_cycle: int | None = None
    validation_cycle: int | None = None


def allowed_targets(state: LifecycleState, context: TransitionContext) -> frozenset[LifecycleState]: ...
def transition(state: LifecycleState, target: LifecycleState, context: TransitionContext) -> LifecycleState: ...
```

- [ ] **Step 1: Write tests for staging-first and read-only paths**

```python
def test_fix_can_stage_before_classification() -> None:
    context = TransitionContext(Intent.FIX, True, True, True)
    assert transition(DISCOVERED, STAGED, context) is STAGED
    assert transition(STAGED, CLASSIFIED, context) is CLASSIFIED


def test_create_can_stage_first() -> None:
    context = TransitionContext(Intent.CREATE, True, False, True)
    assert transition(DISCOVERED, STAGED, context) is STAGED


def test_audit_only_cannot_enter_staged() -> None:
    context = TransitionContext(Intent.AUDIT_ONLY, False, True, False)
    with pytest.raises(InvalidTransition):
        transition(DISCOVERED, STAGED, context)


def test_audit_only_defect_returns_to_audit_without_staging() -> None:
    context = TransitionContext(Intent.AUDIT_ONLY, False, True, False)
    assert transition(DISCOVERED, AUDITED, context) is AUDITED
    assert transition(AUDITED, CLASSIFIED, context) is CLASSIFIED
    assert transition(CLASSIFIED, MECHANISM_SELECTED, context) is MECHANISM_SELECTED
    assert transition(MECHANISM_SELECTED, AUDITED, context) is AUDITED
```

- [ ] **Step 2: Write remediation-loop tests**

```python
@pytest.mark.parametrize("target", [CLASSIFIED, MECHANISM_SELECTED, STAGED, AUDITED, VALIDATED])
def test_gate_failure_can_return_to_responsible_stage(target: LifecycleState) -> None:
    context = TransitionContext(Intent.FIX, True, True, True)
    assert transition(GATE_FAILED, target, context) is target


def test_remediated_candidate_must_reaudit_before_publish() -> None:
    context = TransitionContext(Intent.FIX, True, True, True)
    with pytest.raises(InvalidTransition):
        transition(STAGED, PUBLISHED, context)


def test_stale_audit_cycle_cannot_reenter_gate() -> None:
    context = TransitionContext(
        Intent.FIX,
        True,
        True,
        True,
        remediation_cycle=2,
        audit_cycle=1,
        validation_cycle=2,
    )
    with pytest.raises(InvalidTransition):
        transition(VALIDATED, GATE_PASSED, context)
```

- [ ] **Step 3: Run tests and observe missing implementation**

Run:

```powershell
python -m pytest tests/unit/test_state_machine.py -v
```

Expected: FAIL with missing module or transition definitions.

- [ ] **Step 4: Implement guarded adjacency rules**

Implement the complete transition table from frozen design Section 10, including:

```python
BASE_TRANSITIONS = {
    DISCOVERED: {STAGED, AUDITED, CLASSIFIED},
    STAGED: {CLASSIFIED, AUDITED},
    AUDITED: {STAGED, CLASSIFIED, VALIDATED},
    CLASSIFIED: {MECHANISM_SELECTED},
    MECHANISM_SELECTED: {STAGED, AUDITED},
    VALIDATED: {AUDITED, GATE_PASSED, GATE_FAILED},
    GATE_PASSED: {PUBLISHED, UNCHANGED_VALIDATED},
    GATE_FAILED: {CLASSIFIED, MECHANISM_SELECTED, STAGED, AUDITED, VALIDATED, UNCHANGED_BLOCKED},
}
```

Add guards for Audit Only, authorization, staging existence, outcome legality, and remediation-cycle freshness. `VALIDATED → GATE_*` is legal only when `audit_cycle == validation_cycle == remediation_cycle`; after Gate failure the orchestrator increments the remediation cycle before returning to the responsible stage.

- [ ] **Step 5: Run the full state tests**

Run:

```powershell
python -m pytest tests/unit/test_state_machine.py -v
```

Expected: PASS, including all forbidden transitions.

- [ ] **Step 6: Commit the state machine**

```powershell
git add engine/state_machine.py tests/unit/test_state_machine.py
git commit -m "feat: add non-linear pipeline state machine"
```

**Acceptance Criteria:** Create/Modify/Fix can stage first; Audit Only never stages and can finish a classified defect audit without staging; Gate remediation can return to the responsible stage; every publication path requires audit, validation, and Gate evidence from the same fresh remediation cycle.

---

### Task 4: Implement Inventory and Isolated Workspace Control

**Inputs:** Frozen design Sections 6, 8.4, 19, and 21.2; Task 2 contracts.

**Outputs:** Read-only inventory, content digests, and safe same-filesystem staging without publication.

**Dependencies:** Task 2.

**Parallelism:** May run in parallel with Tasks 3 and 5.

**Tests:** `tests/unit/test_inventory.py` and `tests/integration/test_workspace_isolation.py`, including Unicode paths and source immutability.

**Files:**

- Create: `engine/inventory.py`
- Create: `engine/workspace.py`
- Create: `tests/unit/test_inventory.py`
- Create: `tests/integration/test_workspace_isolation.py`
- Create: `tests/fixtures/skills/minimal-valid/SKILL.md`
- Create: `tests/fixtures/skills/with-unicode/技能说明.md`

**Interfaces:**

```python
def digest_tree(root: Path) -> str: ...
def build_artifact_manifest(root: Path, intent: Intent, source_revision: str | None) -> ArtifactManifest: ...
def assert_no_scope_escape(root: Path) -> None: ...


@dataclass
class WorkspaceSession:
    intent: Intent
    source: Path | None
    staging: Path | None
    source_digest: str | None

    def prepare(self, target_parent: Path) -> None: ...
    def verify_source_unchanged(self) -> bool: ...
```

- [ ] **Step 1: Write deterministic inventory tests**

```python
def test_digest_is_path_order_independent(tmp_path: Path) -> None:
    write_tree(tmp_path, {"b.txt": "二", "a.txt": "一"})
    first = digest_tree(tmp_path)
    rewrite_in_reverse_order(tmp_path)
    assert digest_tree(tmp_path) == first


def test_existing_source_manifest_requires_digest(skill_fixture: Path) -> None:
    manifest = build_artifact_manifest(skill_fixture, Intent.MODIFY, "rev-1")
    assert manifest.source_revision == "rev-1"
    assert manifest.source_digest
```

- [ ] **Step 2: Write isolation and Audit Only tests**

```python
def test_modify_copies_source_without_mutating_it(skill_fixture: Path, tmp_path: Path) -> None:
    session = WorkspaceSession.for_existing(Intent.MODIFY, skill_fixture)
    session.prepare(tmp_path)
    (session.staging / "SKILL.md").write_text("changed", encoding="utf-8")
    assert (skill_fixture / "SKILL.md").read_text(encoding="utf-8") != "changed"


def test_audit_only_has_no_staging(skill_fixture: Path, tmp_path: Path) -> None:
    session = WorkspaceSession.for_existing(Intent.AUDIT_ONLY, skill_fixture)
    session.prepare(tmp_path)
    assert session.staging is None
```

- [ ] **Step 3: Run tests and observe missing workspace behavior**

Run:

```powershell
python -m pytest tests/unit/test_inventory.py tests/integration/test_workspace_isolation.py -v
```

Expected: FAIL.

- [ ] **Step 4: Implement UTF-8-safe inventory and digests**

Hash relative POSIX paths, a null separator, file length, and file bytes in sorted order. Exclude transient staging state only when it lies outside the Skill root; do not silently omit Skill files.

- [ ] **Step 5: Implement staging safety guards**

Use `Path.resolve(strict=False)` containment checks. Reject symlinks and Windows reparse points that redirect outside the source or staging root. Verify staging and target parent share `os.stat(...).st_dev`; on Windows also require matching resolved drive roots.

- [ ] **Step 6: Implement operation-specific preparation**

- Create: allocate empty staging under the target filesystem.
- Modify/Fix: copy source into staging and record source digest/revision.
- Audit Only: retain read-only source and no staging.
- Audit + Optimize: expose `prepare_optimization()` only after the caller supplies `modification_needed=True` and `authorized_to_modify=True`.

- [ ] **Step 7: Run workspace tests**

Run:

```powershell
python -m pytest tests/unit/test_inventory.py tests/integration/test_workspace_isolation.py -v
```

Expected: PASS on Unicode paths and source immutability assertions.

- [ ] **Step 8: Commit workspace control**

```powershell
git add engine/inventory.py engine/workspace.py tests/unit/test_inventory.py tests/integration/test_workspace_isolation.py tests/fixtures/skills
git commit -m "feat: add isolated skill workspaces"
```

**Acceptance Criteria:** Audit Only performs no copy; Modify/Fix always isolate; Create stages on the target filesystem; manifests satisfy conditional source fields; scope-escape paths are rejected.

---

### Task 5: Implement Diagnostics and Mechanism Selection

**Inputs:** Frozen design Sections 8.5, 8.6, 11, and 12; Task 2 contracts.

**Outputs:** Deterministic validation of classification records and an explicit mechanism decision service.

**Dependencies:** Task 2.

**Parallelism:** May run in parallel with Tasks 3 and 4.

**Tests:** `tests/unit/test_diagnostics.py` and `tests/unit/test_mechanism_selection.py` for conditional RCA and persistence guards.

**Files:**

- Create: `engine/diagnostics.py`
- Create: `engine/mechanism_selection.py`
- Create: `tests/unit/test_diagnostics.py`
- Create: `tests/unit/test_mechanism_selection.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class DiagnosticInput:
    intent: Intent
    requirement: str
    failure_evidence: tuple[str, ...]
    defect_found: bool


def validate_classification(record: DecisionRecord) -> None: ...
def select_mechanisms(record: DecisionRecord) -> DecisionRecord: ...
def prompt_rule_allowed(record: DecisionRecord) -> bool: ...
```

- [ ] **Step 1: Write conditional RCA tests**

```python
def test_fix_requires_root_cause() -> None:
    record = decision(intent=Intent.FIX, root_cause=None)
    with pytest.raises(InvalidDecisionRecord):
        validate_classification(record)


def test_create_accepts_no_root_cause() -> None:
    record = decision(intent=Intent.CREATE, root_cause=None)
    validate_classification(record)


def test_invariant_only_modify_accepts_no_root_cause() -> None:
    record = decision(
        intent=Intent.MODIFY,
        primary=PrimaryIssueClass.CAPABILITY_INVARIANT_CHANGE,
        root_cause=None,
    )
    validate_classification(record)
```

- [ ] **Step 2: Write hard-principle tests**

```python
def test_task_local_preference_selects_no_persistent_mechanism() -> None:
    result = select_mechanisms(decision(primary=PrimaryIssueClass.TASK_LOCAL_PREFERENCE))
    assert result.selected_mechanisms == ()


def test_insufficient_evidence_cannot_select_prompt_rule() -> None:
    record = decision(primary=PrimaryIssueClass.INSUFFICIENT_EVIDENCE)
    assert prompt_rule_allowed(record) is False
```

- [ ] **Step 3: Run tests and observe missing services**

Run:

```powershell
python -m pytest tests/unit/test_diagnostics.py tests/unit/test_mechanism_selection.py -v
```

Expected: FAIL.

- [ ] **Step 4: Implement classification invariants**

Enforce all three dimensions, conditional root cause, non-empty evidence limitation for `INSUFFICIENT_EVIDENCE`, and no persistence for `TASK_LOCAL_PREFERENCE`.

- [ ] **Step 5: Implement the frozen mechanism mapping**

Return ordered mechanism identifiers:

```python
IMPLEMENTATION_FIX = "implementation_fix"
REGRESSION_TEST = "regression_test"
SCHEMA_VALIDATOR = "schema_validator"
ENVIRONMENT_TOOLING = "environment_tooling"
WORKFLOW_REFACTOR = "workflow_refactor"
MERGE_INVARIANT = "merge_invariant"
PROMPT_RULE = "prompt_rule"
```

Record every considered but rejected mechanism and require a non-empty `prompt_rule_justification` before selecting `PROMPT_RULE`.

- [ ] **Step 6: Run diagnostics tests**

Run:

```powershell
python -m pytest tests/unit/test_diagnostics.py tests/unit/test_mechanism_selection.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit diagnostic services**

```powershell
git add engine/diagnostics.py engine/mechanism_selection.py tests/unit/test_diagnostics.py tests/unit/test_mechanism_selection.py
git commit -m "feat: add issue classification and mechanism selection"
```

**Acceptance Criteria:** Conditional RCA rules hold; the three dimensions remain independent; local preference and insufficient evidence protections are executable; Prompt Rule selection requires complete justification.

---

### Task 6: Implement Deterministic Validators and Evidence Collection

**Inputs:** Frozen design Sections 17, 18.2, 18.3, and 21; Tasks 2 and 4.

**Outputs:** Deterministic structure/reference checks and an Evidence Collector that distinguishes required and optional results.

**Dependencies:** Tasks 2 and 4.

**Parallelism:** Serial before Task 7.

**Tests:** Structure, reference-integrity, and Evidence Collector unit tests with critical/optional fixtures.

**Files:**

- Create: `validators/skill_structure.py`
- Create: `validators/reference_integrity.py`
- Create: `engine/evidence.py`
- Create: `tests/unit/test_structure_validator.py`
- Create: `tests/unit/test_reference_integrity.py`
- Create: `tests/unit/test_evidence.py`
- Create: `tests/fixtures/skills/invalid-frontmatter/SKILL.md`
- Create: `tests/fixtures/skills/broken-critical-reference/SKILL.md`
- Create: `tests/fixtures/skills/broken-optional-reference/SKILL.md`

**Interfaces:**

```python
def validate_skill_structure(manifest: ArtifactManifest) -> tuple[CheckResult, ...]: ...
def validate_references(manifest: ArtifactManifest) -> tuple[CheckResult, ...]: ...


class EvidenceCollector:
    def add(self, result: CheckResult) -> None: ...
    def required_results(self) -> tuple[CheckResult, ...]: ...
    def optional_results(self) -> tuple[CheckResult, ...]: ...
    def snapshot(self) -> tuple[CheckResult, ...]: ...
```

- [ ] **Step 1: Write validator tests**

```python
def test_missing_skill_md_is_required_failure(tmp_path: Path) -> None:
    manifest = build_artifact_manifest(tmp_path, Intent.CREATE, None)
    results = validate_skill_structure(manifest)
    assert check(results, "skill.structure.skill_md").status is CheckStatus.FAIL
    assert check(results, "skill.structure.skill_md").required is True


def test_optional_broken_link_is_warning(optional_reference_fixture: Path) -> None:
    results = validate_references(manifest_for(optional_reference_fixture))
    assert check(results, "reference.optional.exists").status is CheckStatus.WARN
```

- [ ] **Step 2: Write Evidence Collector tests**

```python
def test_optional_provider_error_is_not_required() -> None:
    collector = EvidenceCollector()
    collector.add(check_result(required=False, status=CheckStatus.ERROR))
    assert collector.required_results() == ()


def test_malformed_result_is_rejected() -> None:
    collector = EvidenceCollector()
    with pytest.raises(InvalidEvidence):
        collector.add(check_result(check_id="", evidence=""))
```

- [ ] **Step 3: Run tests and observe failures**

Run:

```powershell
python -m pytest tests/unit/test_structure_validator.py tests/unit/test_reference_integrity.py tests/unit/test_evidence.py -v
```

Expected: FAIL.

- [ ] **Step 4: Implement structure checks**

Return separate `CheckResult` records for `SKILL.md`, frontmatter syntax, name format, directory/name agreement, placeholders, critical assets, schema files, executables, and required dependencies. Do not produce a Gate verdict.

- [ ] **Step 5: Implement reference checks**

Resolve Markdown links relative to their source file. Classify links listed in `ArtifactManifest.required_references` as required; classify other documentation links as optional unless the Skill declares them runtime-critical.

- [ ] **Step 6: Implement Evidence Collector validation and deduplication**

Validate every serialized result against `check-result.schema.json`, reject duplicate `check_id + subject` pairs with conflicting values, retain provenance, and preserve `SKIP/NOT_EXECUTED` reasons.

- [ ] **Step 7: Run validation/evidence tests**

Run:

```powershell
python -m pytest tests/unit/test_structure_validator.py tests/unit/test_reference_integrity.py tests/unit/test_evidence.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit validation and evidence**

```powershell
git add validators engine/evidence.py tests/unit tests/fixtures/skills
git commit -m "feat: collect deterministic skill evidence"
```

**Acceptance Criteria:** Critical and optional references differ correctly; validators emit only `CheckResult`; malformed or contradictory evidence cannot enter the Gate.

---

### Task 7: Implement the Internal Quality Gate

**Inputs:** Frozen design Sections 6, 18, and 25; Tasks 2 and 6.

**Outputs:** Versioned core Gate policy and sole final verdict implementation.

**Dependencies:** Tasks 2 and 6.

**Parallelism:** Serial before the minimal pipeline.

**Tests:** `tests/unit/test_quality_gate.py` and `tests/unit/test_gate_policy.py` for `B01–B12`, warnings, authority, and policy extension.

**Files:**

- Create: `config/gate-policy.yaml`
- Create: `engine/quality_gate.py`
- Create: `tests/unit/test_quality_gate.py`
- Create: `tests/unit/test_gate_policy.py`
- Create: `tests/fixtures/policies/valid-stricter-policy.yaml`
- Create: `tests/fixtures/policies/invalid-weakened-policy.yaml`

**Interfaces:**

```python
@dataclass(frozen=True)
class GateContext:
    intent: Intent
    state: LifecycleState
    authorized_to_modify: bool
    candidate_requires_publish: bool
    workspace_publishable: bool
    decision: DecisionRecord | None


def load_gate_policy(project_policy: Path | None = None) -> dict[str, object]: ...
def adjudicate(context: GateContext, evidence: tuple[CheckResult, ...]) -> GateResult: ...
```

- [ ] **Step 1: Write B08 and B11 tests**

```python
def test_required_check_error_triggers_b08() -> None:
    result = adjudicate(context(Intent.FIX), (check(required=True, status=ERROR),))
    assert result.verdict is GateVerdict.FAIL
    assert "B08" in ids(result.blocking_findings)


def test_optional_provider_error_is_warning() -> None:
    result = adjudicate(context(Intent.AUDIT_ONLY), passing_required() + (provider_error(required=False),))
    assert "optional_provider_error" in result.warnings
    assert "B08" not in ids(result.blocking_findings)


def test_noncritical_link_is_warning_not_b11() -> None:
    result = adjudicate(context(Intent.AUDIT_ONLY), passing_required() + (optional_link_warning(),))
    assert "B11" not in ids(result.blocking_findings)
```

- [ ] **Step 2: Write verdict-versus-publication tests**

```python
def test_audit_only_pass_has_no_publish_authority() -> None:
    result = adjudicate(context(Intent.AUDIT_ONLY, publish=False), passing_required())
    assert result.verdict is GateVerdict.PASS
    assert result.outcome is GateOutcome.UNCHANGED_VALIDATED
    assert result.publish_authorized is False


def test_candidate_pass_requires_workspace_preconditions_for_publish() -> None:
    result = adjudicate(context(Intent.MODIFY, publish=True, workspace_publishable=False), passing_required())
    assert result.publish_authorized is False


def test_publishable_candidate_is_ready_but_not_yet_published() -> None:
    result = adjudicate(context(Intent.MODIFY, publish=True, workspace_publishable=True), passing_required())
    assert result.publish_authorized is True
    assert result.outcome is GateOutcome.READY_TO_PUBLISH
```

- [ ] **Step 3: Write policy-extension tests**

```python
def test_project_policy_can_add_blocking_rule(valid_stricter_policy: Path) -> None:
    policy = load_gate_policy(valid_stricter_policy)
    assert "PROJECT_B01" in policy["blocking"]


def test_project_policy_cannot_disable_core_rule(invalid_weakened_policy: Path) -> None:
    with pytest.raises(PolicyWeakeningError):
        load_gate_policy(invalid_weakened_policy)
```

- [ ] **Step 4: Run tests and observe missing Gate**

Run:

```powershell
python -m pytest tests/unit/test_quality_gate.py tests/unit/test_gate_policy.py -v
```

Expected: FAIL.

- [ ] **Step 5: Encode core B01–B12 in `gate-policy.yaml`**

Assign applicability, required evidence identifiers, and remediation stages. Do not encode Skill names, OS special cases, or historical bug IDs.

- [ ] **Step 6: Implement policy merge and adjudication**

Core rules are immutable. Project rules append or strengthen requirements. Compute quality verdict before publication authority; then set:

```python
publish_authorized = (
    verdict is GateVerdict.PASS
    and context.candidate_requires_publish
    and context.authorized_to_modify
    and context.workspace_publishable
)
```

- [ ] **Step 7: Run all Gate tests**

Run:

```powershell
python -m pytest tests/unit/test_quality_gate.py tests/unit/test_gate_policy.py -v
```

Expected: PASS for B01–B12, warning behavior, policy non-weakening, and Audit Only PASS semantics.

- [ ] **Step 8: Commit the Quality Gate**

```powershell
git add config/gate-policy.yaml engine/quality_gate.py tests/unit/test_quality_gate.py tests/unit/test_gate_policy.py tests/fixtures/policies
git commit -m "feat: add internal skill quality gate"
```

**Acceptance Criteria:** Only `adjudicate()` returns final verdict; optional Provider errors do not directly fail; B08/B11 match the frozen contract; PASS and publish authority remain independent.

---

### Task 8: Deliver the Minimal Runnable Governance Loop

**Inputs:** Tasks 3–7 and frozen top-level input/output contract.

**Outputs:** A CLI that runs internal-only Create, Modify, Fix, Audit Only, and Audit + Optimize through classification, validation, and Gate without Rule Bloat or external Provider enhancements.

**Dependencies:** Tasks 3, 4, 5, 6, and 7.

**Parallelism:** Serial integration milestone.

**Tests:** `tests/integration/test_minimal_pipeline.py`, `tests/integration/test_cli.py`, then the complete Tasks 1–8 suite.

**Files:**

- Create: `engine/orchestrator.py`
- Create: `engine/output.py`
- Create: `scripts/skill_engineering.py`
- Create: `tests/integration/test_minimal_pipeline.py`
- Create: `tests/integration/test_cli.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class EngineeringRequest:
    requirement: str
    intent: Intent | None
    source: Path | None
    failure_evidence: tuple[str, ...]
    authorized_to_modify: bool
    target_parent: Path


@dataclass(frozen=True)
class EngineeringOutcome:
    outcome_type: str
    artifact_path: Path
    gate_result: GateResult
    minimal_blocking_findings: tuple[dict[str, str], ...]


class PipelineOrchestrator:
    def run(self, request: EngineeringRequest) -> EngineeringOutcome: ...


class PipelineBlockedError(RuntimeError):
    gate_result: GateResult
```

- [ ] **Step 1: Write minimal end-to-end tests**

```python
def test_audit_only_valid_skill_returns_unchanged_validated(skill_fixture: Path) -> None:
    outcome = orchestrator().run(audit_only_request(skill_fixture))
    assert outcome.outcome_type == "Validated Complete Skill"
    assert outcome.artifact_path == skill_fixture
    assert outcome.gate_result.publish_authorized is False


def test_audit_only_invalid_skill_returns_minimal_findings(invalid_skill: Path) -> None:
    outcome = orchestrator().run(audit_only_request(invalid_skill))
    assert outcome.outcome_type == "Unchanged Skill + Minimal Blocking Findings"
    assert outcome.gate_result.verdict is GateVerdict.FAIL
    assert set(outcome.minimal_blocking_findings[0]) == {
        "finding_id", "affected_path", "blocking_reason", "required_next_action"
    }
```

- [ ] **Step 2: Write staging tests for Modify/Fix/Create**

```python
@pytest.mark.parametrize("intent", [Intent.MODIFY, Intent.FIX])
def test_mutating_flows_stage_before_classification(intent: Intent, skill_fixture: Path) -> None:
    trace = orchestrator_with_trace().run(existing_request(intent, skill_fixture))
    assert trace.index(STAGED) < trace.index(CLASSIFIED)


def test_create_stages_empty_workspace_before_candidate_generation(tmp_path: Path) -> None:
    trace = orchestrator_with_trace().run(create_request(tmp_path))
    assert trace[1] is STAGED
```

- [ ] **Step 3: Run tests and observe missing orchestration**

Run:

```powershell
python -m pytest tests/integration/test_minimal_pipeline.py tests/integration/test_cli.py -v
```

Expected: FAIL.

- [ ] **Step 4: Implement explicit intent input before heuristic detection**

The Python API accepts `intent=None`; the internal detector then derives the mode from source presence, failure evidence, read-only authorization, and requirement wording. The CLI exposes no required operation flag, but tests may pass explicit intent to isolate flow behavior.

- [ ] **Step 5: Implement legal output projection**

`engine/output.py` must expose only complete artifact paths and the four minimal Audit Only blocking fields. A non-Audit operation that cannot reach a legal result raises `PipelineBlockedError` and delivers no `EngineeringOutcome` or artifact. The output layer must not serialize complete `DecisionRecord`, similarity scores, Provider internals, or the entire evidence store.

- [ ] **Step 6: Implement the internal-only pipeline**

Use internal candidate generation sufficient for test fixtures. Call state machine, workspace, diagnostics, mechanism selector, validators, Evidence Collector, and Quality Gate. Do not add Rule Bloat or external Provider behavior yet.

- [ ] **Step 7: Add the CLI contract**

```text
python scripts/skill_engineering.py <requirement>
  [--source PATH]
  [--failure-evidence PATH]
  [--read-only]
  [--authorize-optimize]
  [--target-parent PATH]
  [--json]
```

The CLI must infer operation and return exit code `0` for PASS, `2` for the legal Audit Only unchanged/blocked result, and `1` for other blocked operations. Exit code `1` does not create a third legal output type and must not report an artifact as delivered.

- [ ] **Step 8: Run minimal pipeline and CLI tests**

Run:

```powershell
python -m pytest tests/integration/test_minimal_pipeline.py tests/integration/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 9: Run all tests for the first closed-loop milestone**

Run:

```powershell
python -m pytest -v
```

Expected: all Tasks 1–8 tests pass with no external Provider installed.

- [ ] **Step 10: Commit the minimal runnable loop**

```powershell
git add engine/orchestrator.py engine/output.py scripts/skill_engineering.py tests/integration
git commit -m "feat: run minimal skill governance pipeline"
```

**Acceptance Criteria:** All five operation modes execute without external Providers; Audit Only produces exactly the two legal outcomes; staging-first transitions are visible; the internal Gate is the only final verdict source.

---

### Task 9: Add Rule Governance and Rule Bloat Findings

**Inputs:** Frozen design Sections 13 and 14; minimal pipeline from Task 8.

**Outputs:** Rule extraction, bounded bloat findings, and internal governance decisions integrated as evidence.

**Dependencies:** Task 8.

**Parallelism:** May run in parallel with Tasks 10 and 11.

**Tests:** Rule detector/governance unit tests plus `tests/integration/test_rule_governance_pipeline.py`.

**Files:**

- Create: `engine/rule_bloat.py`
- Create: `engine/rule_governance.py`
- Create: `tests/unit/test_rule_bloat.py`
- Create: `tests/unit/test_rule_governance.py`
- Create: `tests/integration/test_rule_governance_pipeline.py`
- Create: `tests/fixtures/rules/*.md`

**Interfaces:**

```python
def extract_rule_units(skill_root: Path) -> tuple[RuleUnit, ...]: ...
def detect_rule_bloat(units: tuple[RuleUnit, ...], history: RuleHistory | None) -> tuple[RuleFinding, ...]: ...
def govern_findings(findings: tuple[RuleFinding, ...], mechanisms: tuple[str, ...]) -> tuple[GovernanceDecision, ...]: ...
def governance_evidence(decisions: tuple[GovernanceDecision, ...]) -> tuple[CheckResult, ...]: ...
```

- [ ] **Step 1: Write candidate-only detector tests**

```python
def test_keyword_density_never_returns_gate_verdict(rule_fixture: Path) -> None:
    findings = detect_rule_bloat(extract_rule_units(rule_fixture), history=None)
    assert all(not hasattr(finding, "verdict") for finding in findings)


def test_similar_rules_are_candidates_not_automatic_duplicates(similar_rules: Path) -> None:
    finding = find(findings_for(similar_rules), "semantic_similarity")
    assert finding.candidate_action is GovernanceAction.MERGE
    assert finding.confidence < 1.0
```

- [ ] **Step 2: Write governance-chain tests**

```python
def test_detector_finding_reaches_gate_only_through_governance() -> None:
    findings = (rule_finding(candidate_action=GovernanceAction.DELETE),)
    decisions = govern_findings(findings, mechanisms=("regression_test",))
    evidence = governance_evidence(decisions)
    assert evidence[0].source == "rule_governance"
```

- [ ] **Step 3: Run tests and observe missing rule services**

Run:

```powershell
python -m pytest tests/unit/test_rule_bloat.py tests/unit/test_rule_governance.py tests/integration/test_rule_governance_pipeline.py -v
```

Expected: FAIL.

- [ ] **Step 4: Implement bounded `RuleUnit` extraction**

Extract Markdown directives from `SKILL.md`, instruction-bearing references, and in-scope `AGENTS.md`. Record modality, conditions, scope, environment qualifiers, and mechanism references. Do not treat tests, assets, or ordinary reference prose as rules.

- [ ] **Step 5: Implement V1 detection signals**

Implement exact duplicates, token/Jaccard near-duplicate candidates, directive pressure, branch depth, environment concentration, workaround language, conflict candidates, cross-layer mechanism duplication, and optional Git growth summaries. Missing history yields `SKIP/WARN` evidence.

- [ ] **Step 6: Implement governance decisions**

Require rationale and evidence references for `KEEP/MERGE/MOVE/DELETE`. A conflict or critical duplicate can become blocking evidence only after internal governance confirms it.

- [ ] **Step 7: Integrate the governance chain into the orchestrator**

Insert:

```text
Detector → RuleFinding → Rule Governance → CheckResult → Evidence Collector → Quality Gate
```

- [ ] **Step 8: Run rule and full pipeline tests**

Run:

```powershell
python -m pytest tests/unit/test_rule_bloat.py tests/unit/test_rule_governance.py tests/integration/test_rule_governance_pipeline.py tests/integration/test_minimal_pipeline.py -v
```

Expected: PASS; no detector method can directly fail the Gate.

- [ ] **Step 9: Commit rule governance**

```powershell
git add engine/rule_bloat.py engine/rule_governance.py tests/unit tests/integration/test_rule_governance_pipeline.py tests/fixtures/rules
git commit -m "feat: govern skill rule inflation findings"
```

**Acceptance Criteria:** All frozen V1 signals exist; false-positive-prone signals remain findings; governance owns action; Gate receives normalized evidence only.

---

### Task 10: Add Regression Families and Behavioral Runner Contracts

**Inputs:** Frozen design Section 15; Task 8 pipeline.

**Outputs:** Failure-family regression execution and behavioral scenario/result records with `NOT_EXECUTED` support.

**Dependencies:** Tasks 2, 6, and 8.

**Parallelism:** May run in parallel with Tasks 9 and 11.

**Tests:** Regression and behavioral unit tests plus `tests/integration/test_required_regression_gate.py`.

**Files:**

- Create: `engine/regression.py`
- Create: `engine/behavioral.py`
- Create: `tests/unit/test_regression.py`
- Create: `tests/unit/test_behavioral.py`
- Create: `tests/integration/test_required_regression_gate.py`
- Create: `tests/fixtures/regression/windows-encoding/**`

**Interfaces:**

```python
class RegressionRunner(Protocol):
    def run(self, case: RegressionCase, artifact_root: Path) -> CheckResult: ...


class BehavioralRunner(Protocol):
    def run(self, scenario: BehavioralScenario, artifact_root: Path) -> BehavioralResult: ...


def run_regressions(cases: tuple[RegressionCase, ...], runner: RegressionRunner, root: Path) -> tuple[CheckResult, ...]: ...
def evaluate_behavior(scenario: BehavioralScenario, runner: BehavioralRunner | None, root: Path) -> BehavioralResult: ...
```

- [ ] **Step 1: Write failure-family tests**

```python
def test_same_failure_family_uses_one_parameterized_case() -> None:
    case = load_case("windows-encoding")
    assert case.failure_family_id == "windows-encoding"
    assert len(case.fixtures) >= 2


def test_required_regression_failure_blocks_gate() -> None:
    result = run_gate_with(required_regression(CheckStatus.FAIL))
    assert "B07" in ids(result.blocking_findings)
```

- [ ] **Step 2: Write behavioral runner absence test**

```python
def test_missing_behavioral_runner_is_not_executed() -> None:
    result = evaluate_behavior(scenario(), runner=None, root=Path("skill"))
    assert result.status is CheckStatus.NOT_EXECUTED
    assert result.limitation
```

- [ ] **Step 3: Run tests and observe missing runner contracts**

Run:

```powershell
python -m pytest tests/unit/test_regression.py tests/unit/test_behavioral.py tests/integration/test_required_regression_gate.py -v
```

Expected: FAIL.

- [ ] **Step 4: Implement regression case loading and execution**

Validate cases against `regression-case.schema.json`, group by `failure_family_id`, reject duplicate independent cases for the same family, and return one result with per-fixture evidence.

- [ ] **Step 5: Implement behavioral runner-neutral records**

When runner is absent, return `NOT_EXECUTED`; never map absence to PASS. When present, retain runner identity, artifact digest, observed assertions, and limitations.

- [ ] **Step 6: Integrate regression disposition**

- `REQUIRED`: missing, failing, error, or untrustworthy result feeds `B07/B08`.
- `RECOMMENDED`: missing runner produces warning.
- `NOT_APPLICABLE`: no synthetic regression result.

- [ ] **Step 7: Run regression and Gate integration tests**

Run:

```powershell
python -m pytest tests/unit/test_regression.py tests/unit/test_behavioral.py tests/integration/test_required_regression_gate.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit regression support**

```powershell
git add engine/regression.py engine/behavioral.py tests/unit tests/integration/test_required_regression_gate.py tests/fixtures/regression
git commit -m "feat: add failure-family regression checks"
```

**Acceptance Criteria:** Regressions are organized by failure family; required disposition blocks correctly; missing behavioral runner records `NOT_EXECUTED`; no multi-model scheduler is introduced.

---

### Task 11: Add Provider Ports, Identity Policy, and Internal Fallbacks

**Inputs:** Frozen design Section 16; Tasks 2 and 8.

**Outputs:** Provider Gateway independent of invocation mechanism, with pinned/degraded identity handling and four internal fallback capabilities.

**Dependencies:** Tasks 2 and 8.

**Parallelism:** May run in parallel with Tasks 9 and 10.

**Tests:** Provider authority/pinning unit tests plus `tests/integration/test_provider_fallback.py` with all external Providers disabled.

**Files:**

- Create: `engine/providers.py`
- Create: `config/providers.yaml`
- Create: `tests/unit/test_providers.py`
- Create: `tests/integration/test_provider_fallback.py`
- Create: `tests/fixtures/providers/*.json`

**Interfaces:**

```python
class ProviderAdapter(Protocol):
    descriptor: ProviderDescriptor

    def invoke(self, capability: str, request: dict[str, object]) -> ProviderResult: ...


class ProviderGateway:
    def register(self, adapter: ProviderAdapter) -> None: ...
    def invoke(self, capability: str, request: dict[str, object], formal_run: bool) -> ProviderResult: ...
```

Capabilities:

```text
CREATE_CANDIDATE
AUDIT_SKILL
GOVERN_AGENT_INSTRUCTIONS
CHECK_SKILL_CONFORMANCE
```

- [ ] **Step 1: Write authority-boundary tests**

```python
def test_provider_result_rejects_final_verdict() -> None:
    payload = fixture("providers/illegal-final-verdict.json")
    with pytest.raises(ValidationError):
        validate_contract("provider-result", payload)


def test_provider_identity_does_not_change_governance_semantics() -> None:
    first = gateway(provider("alpha", audit_findings())).invoke(AUDIT_SKILL, request(), formal_run=False)
    second = gateway(provider("beta", audit_findings())).invoke(AUDIT_SKILL, request(), formal_run=False)
    assert normalize_findings(first) == normalize_findings(second)
```

- [ ] **Step 2: Write fallback and pinning tests**

```python
@pytest.mark.parametrize("status", [UNAVAILABLE, INVALID_OUTPUT, TIMEOUT, INCOMPATIBLE])
def test_external_failure_uses_internal_fallback(status: ProviderStatus) -> None:
    result = gateway(failing_provider(status), internal_fallback()).invoke(CREATE_CANDIDATE, request(), False)
    assert result.fallback_used is True


def test_formal_run_skips_unpinned_provider_and_uses_fallback() -> None:
    result = gateway(unpinned_provider(), internal_fallback()).invoke(
        AUDIT_SKILL,
        request(),
        formal_run=True,
    )
    assert result.fallback_used is True
    assert result.provider_id == "internal.audit.v1"
```

- [ ] **Step 3: Run tests and observe missing Provider Gateway**

Run:

```powershell
python -m pytest tests/unit/test_providers.py tests/integration/test_provider_fallback.py -v
```

Expected: FAIL.

- [ ] **Step 4: Implement invocation-neutral ports**

The Gateway calls only `ProviderAdapter.invoke()`. Do not include `$skill-name`, CLI commands, delegation APIs, or host-specific Skill APIs in core logic.

- [ ] **Step 5: Implement identity and formal-run policy**

Local discovered Providers without revision are `DEGRADED` and permitted only when `formal_run=False`. CI/formal publication rejects them and uses a pinned alternative or internal fallback.

- [ ] **Step 6: Implement four internal fallbacks**

- `internal.create.v1`: minimal complete Skill candidate creation.
- `internal.audit.v1`: structure and governance audit.
- `internal.agents-governance.v1`: minimal AGENTS/CLAUDE scope checks.
- `internal.structure-validator.v1`: deterministic conformance results.

Fallbacks implement only frozen V1 correctness, not feature parity with external Providers.

- [ ] **Step 7: Configure candidate external identities without enabling unavailable adapters**

`providers.yaml` records OpenAI `skill-creator`, `mblode/agent-skills` `agent-skills-creator`, `mblode/agent-skills` `agents-md`, and an explicitly selected `validate-skills` source. Each entry includes capability, source, revision/version, optional flag, adapter key, and fallback. If no host adapter is available, set availability to false rather than inventing an invocation path.

- [ ] **Step 8: Integrate Provider evidence into the orchestrator**

Normalize Provider output, record limitations, and pass evidence through `EvidenceCollector`. Never accept Provider verdict or publication fields.

- [ ] **Step 9: Run Provider and minimal pipeline tests**

Run:

```powershell
python -m pytest tests/unit/test_providers.py tests/integration/test_provider_fallback.py tests/integration/test_minimal_pipeline.py -v
```

Expected: PASS with every external Provider disabled.

- [ ] **Step 10: Commit Provider abstraction**

```powershell
git add engine/providers.py config/providers.yaml tests/unit/test_providers.py tests/integration/test_provider_fallback.py tests/fixtures/providers
git commit -m "feat: add replaceable skill providers"
```

**Acceptance Criteria:** Core contains no host invocation syntax; formal runs require pinned identity or fallback; four capabilities remain available with all external Providers disabled; Provider output cannot control Gate or publication.

---

### Task 12: Implement Atomic Publication and Recovery

**Inputs:** Frozen design Section 19; workspace from Task 4; Gate from Task 7; orchestrator from Task 8; required evidence from Tasks 10 and 11.

**Outputs:** Same-filesystem atomic replacement with source-race detection and one recoverable backup.

**Dependencies:** Tasks 4, 7, 8, 9, 10, and 11.

**Parallelism:** Serial safety-critical task.

**Tests:** `tests/integration/test_atomic_publish.py` and `tests/regression/test_publication_invariants.py`, including race, cross-volume, and recovery paths.

**Files:**

- Modify: `engine/workspace.py`
- Modify: `engine/orchestrator.py`
- Create: `tests/integration/test_atomic_publish.py`
- Create: `tests/regression/test_publication_invariants.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class PublishResult:
    published_path: Path
    backup_path: Path | None
    restored_after_failure: bool


def publish_atomic(session: WorkspaceSession, gate: GateResult) -> PublishResult: ...
```

- [ ] **Step 1: Write publication authorization tests**

```python
def test_gate_pass_without_publish_authority_does_not_publish(session: WorkspaceSession) -> None:
    gate = gate_result(verdict=PASS, publish_authorized=False, outcome=UNCHANGED_VALIDATED)
    with pytest.raises(PublishNotAuthorized):
        publish_atomic(session, gate)


def test_gate_failure_never_publishes(session: WorkspaceSession) -> None:
    with pytest.raises(PublishNotAuthorized):
        publish_atomic(session, gate_result(verdict=FAIL, publish_authorized=False))
```

- [ ] **Step 2: Write race, cross-volume, and recovery tests**

```python
def test_source_digest_change_blocks_replacement(session: WorkspaceSession) -> None:
    mutate_source_after_staging(session)
    with pytest.raises(SourceChangedError):
        publish_atomic(session, publishable_gate())


def test_cross_volume_publish_fails(session_on_other_volume: WorkspaceSession) -> None:
    with pytest.raises(CrossFilesystemPublishError):
        publish_atomic(session_on_other_volume, publishable_gate())


def test_failed_candidate_move_restores_one_backup(session: WorkspaceSession, monkeypatch: pytest.MonkeyPatch) -> None:
    inject_candidate_move_failure(monkeypatch)
    with pytest.raises(PublishRecoveryError):
        publish_atomic(session, publishable_gate())
    assert_source_restored(session)
    assert_exactly_one_backup(session)
```

- [ ] **Step 3: Run tests and observe missing publication implementation**

Run:

```powershell
python -m pytest tests/integration/test_atomic_publish.py tests/regression/test_publication_invariants.py -v
```

Expected: FAIL.

- [ ] **Step 4: Implement publication preflight**

Require `verdict=PASS`, `outcome=READY_TO_PUBLISH`, `publish_authorized=true`, a staged candidate, same filesystem, unchanged source digest for existing-source flows, and a validated candidate digest.

- [ ] **Step 5: Implement one-generation backup and atomic moves**

Use filesystem rename/replace primitives only within the same filesystem. Remove or replace the prior backup only after exact target paths have been resolved and verified inside the target parent. Never use broad recursive deletion.

- [ ] **Step 6: Implement recovery verification**

After publication, rebuild the manifest and verify content digest/loadability. On failure, atomically restore the backup and report failure; never return a successful `PublishResult` after recovery.

- [ ] **Step 7: Run publication and full safety tests**

Run:

```powershell
python -m pytest tests/integration/test_atomic_publish.py tests/regression/test_publication_invariants.py tests/integration/test_workspace_isolation.py -v
```

Expected: PASS on the current platform; platform-specific skips must include an explicit reason and cannot cover the core same-filesystem path.

- [ ] **Step 8: Commit atomic publication**

```powershell
git add engine/workspace.py engine/orchestrator.py tests/integration/test_atomic_publish.py tests/regression/test_publication_invariants.py
git commit -m "feat: publish validated skills atomically"
```

**Acceptance Criteria:** Audit Only PASS cannot publish; cross-volume publication fails; source races block replacement; one backup exists; failed publication restores the original.

---

### Task 13: Add the Thin Skill Entry, Governance Instructions, and Runtime Configuration

**Inputs:** Frozen design Sections 8.1, 8.2, 20, 22, and 23; stable interfaces from Tasks 2–12.

**Outputs:** Final Plugin-facing Skill instructions, concise `AGENTS.md`, progressive-disclosure references, and schema-valid configuration.

**Dependencies:** Tasks 5, 7, 9, 10, 11, and 12.

**Parallelism:** Serial after interfaces stabilize.

**Tests:** `tests/unit/test_skill_entry.py`, `tests/unit/test_configuration.py`, bundled Skill validation, and Plugin-facing reference checks.

**Files:**

- Create: `AGENTS.md`
- Create: `skills/skill-engineer/SKILL.md`
- Create: `skills/skill-engineer/agents/openai.yaml`
- Create: `skills/skill-engineer/references/pipeline.md`
- Create: `skills/skill-engineer/references/issue-classification.md`
- Create: `skills/skill-engineer/references/mechanism-selection.md`
- Create: `skills/skill-engineer/references/rule-governance.md`
- Create: `skills/skill-engineer/references/provider-contracts.md`
- Create: `skills/skill-engineer/references/quality-gate.md`
- Modify: `config/gate-policy.yaml`
- Modify: `config/providers.yaml`
- Create: `tests/unit/test_skill_entry.py`
- Create: `tests/unit/test_configuration.py`

**Interfaces:**

- Consumes: CLI contract, schemas, Provider capability names, Gate policy IDs.
- Produces: discoverable `skill-engineer` Skill and validated runtime configuration.

- [ ] **Step 1: Write Skill-entry tests**

```python
def test_skill_entry_is_thin_and_routes_every_mode() -> None:
    body = read_skill("skills/skill-engineer")
    assert all(mode in body for mode in ["Create", "Modify", "Fix", "Audit Only", "Audit + Optimize"])
    assert len(body.splitlines()) < 220


def test_every_reference_is_directly_linked_from_skill_md() -> None:
    assert unlinked_references("skills/skill-engineer") == set()
```

- [ ] **Step 2: Write governance and config tests**

```python
def test_agents_md_contains_no_case_specific_bug_rules() -> None:
    content = Path("AGENTS.md").read_text(encoding="utf-8")
    assert "Windows encoding bug" not in content
    assert len(content.splitlines()) <= 40


def test_project_policy_cannot_weaken_core_rules() -> None:
    policy = load_gate_policy(Path("config/gate-policy.yaml"))
    assert set(CORE_BLOCKING_IDS).issubset(policy["blocking"])
```

- [ ] **Step 3: Run tests and observe missing Plugin-facing files**

Run:

```powershell
python -m pytest tests/unit/test_skill_entry.py tests/unit/test_configuration.py -v
```

Expected: FAIL.

- [ ] **Step 4: Write concise `AGENTS.md`**

Keep only the stable governance principles and commands required to test the Plugin. Do not duplicate detailed classifier tables, Gate rules, Provider configuration, or historical cases.

- [ ] **Step 5: Write the thin `SKILL.md` entry**

The entry defines trigger scope, input contract, legal outputs, mode selection, authorization boundary, and reference routing. It invokes `scripts/skill_engineering.py` rather than reimplementing engine behavior in prompt instructions.

- [ ] **Step 6: Write focused references**

Each reference documents exactly one frozen contract and is loaded only when its phase applies. Do not duplicate the same invariant across references.

- [ ] **Step 7: Generate and validate `agents/openai.yaml`**

Run the bundled generator with interface metadata, then verify implicit invocation remains enabled and values match the Skill:

```powershell
python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\generate_openai_yaml.py D:\project\skill-engineering\skills\skill-engineer --interface display_name="Skill Engineer" --interface short_description="Create, repair, audit, and validate maintainable Skills." --interface default_prompt="Engineer this Skill through root-cause analysis and the internal quality gate."
```

- [ ] **Step 8: Validate Skill and configuration**

Run:

```powershell
python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py D:\project\skill-engineering\skills\skill-engineer
python -m pytest tests/unit/test_skill_entry.py tests/unit/test_configuration.py -v
```

Expected: both commands pass.

- [ ] **Step 9: Commit Plugin-facing contracts**

```powershell
git add AGENTS.md skills config tests/unit/test_skill_entry.py tests/unit/test_configuration.py
git commit -m "feat: expose skill engineering workflow"
```

**Acceptance Criteria:** `AGENTS.md` stays concise; `SKILL.md` is a thin entry; references are directly discoverable; configuration is schema-valid; no implementation logic is duplicated as Prompt Rules.

---

### Task 14: Verify the Complete V1 Contract and Package

**Inputs:** All preceding tasks and the frozen design acceptance criteria.

**Outputs:** Complete V1 test evidence, packaging validation, and traceable Definition of Done report.

**Dependencies:** Tasks 1–13.

**Parallelism:** Final serial verification task.

**Tests:** Full intent-flow matrix, governance regressions, complete pytest suite, bundled validators, and Windows UTF-8 smoke test.

**Files:**

- Create: `tests/integration/test_end_to_end_flows.py`
- Create: `tests/regression/test_governance_invariants.py`
- Create: `tests/fixtures/end_to_end/**`
- Create: `docs/verification/v1-verification.md`

**Interfaces:**

- Consumes: public CLI and all frozen contracts.
- Produces: end-to-end evidence for V1 Definition of Done.

- [ ] **Step 1: Write the full intent-flow matrix**

```python
@pytest.mark.parametrize(
    ("case", "expected_outcome", "expected_publish"),
    [
        ("create-internal-fallback", "Validated Complete Skill", True),
        ("modify-stable-invariant", "Validated Complete Skill", True),
        ("modify-task-local-preference", "Validated Complete Skill", False),
        ("fix-environment-bug", "Validated Complete Skill", True),
        ("audit-only-pass", "Validated Complete Skill", False),
        ("audit-only-fail", "Unchanged Skill + Minimal Blocking Findings", False),
        ("audit-optimize-pass", "Validated Complete Skill", True),
    ],
)
def test_frozen_v1_flows(case: str, expected_outcome: str, expected_publish: bool) -> None:
    result = run_case(case)
    assert result.outcome_type == expected_outcome
    assert result.gate_result.publish_authorized is expected_publish


def test_non_audit_insufficient_evidence_delivers_no_third_output() -> None:
    with pytest.raises(PipelineBlockedError) as caught:
        run_case("fix-insufficient-evidence")
    assert caught.value.gate_result.verdict is GateVerdict.FAIL
```

- [ ] **Step 2: Write governance regression tests**

Cover these named failure families:

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

- [ ] **Step 3: Run focused end-to-end tests and observe any integration failures**

Run:

```powershell
python -m pytest tests/integration/test_end_to_end_flows.py tests/regression/test_governance_invariants.py -v
```

Expected: failures identify integration gaps only; fix each gap in its owning module without changing architecture.

- [ ] **Step 4: Fix only contract-integration gaps**

For each failure, update the owning implementation and retain the failing case as a regression. Do not add new modes, policies, Providers, or output types.

- [ ] **Step 5: Run the full test suite**

Run:

```powershell
python -m pytest -v
```

Expected: zero failures; skips are limited to unavailable platform-specific runners and carry reasons.

- [ ] **Step 6: Run Skill and Plugin validators**

Run:

```powershell
python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py D:\project\skill-engineering\skills\skill-engineer
python C:\Users\28320\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py D:\project\skill-engineering
```

Expected: both validations pass.

- [ ] **Step 7: Run a UTF-8 Windows smoke test**

Run:

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$probe = Join-Path $env:TEMP 'skill-engineering-中文-smoke'
python scripts/skill_engineering.py '只读审计此 Skill' --source tests/fixtures/skills/with-unicode --read-only --target-parent $probe --json
```

Expected: valid UTF-8 JSON, no replacement characters, and no mutation to the fixture.

- [ ] **Step 8: Record verification evidence**

Write `docs/verification/v1-verification.md` with exact commands, exit codes, test counts, skips and reasons, validator versions, Python version, OS, and the tested Git revision. Do not copy internal Audit Only governance details into user-facing examples.

- [ ] **Step 9: Review the final diff against the frozen design**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors and only intended implementation, tests, configuration, and verification files.

- [ ] **Step 10: Commit V1 verification**

```powershell
git add tests docs/verification
git commit -m "test: verify skill engineering v1"
```

**Acceptance Criteria:** Every V1 flow and governance regression passes; Plugin and Skill validators pass; UTF-8 smoke test passes; verification evidence is tied to the tested revision; no V2 component exists.

---

## V1 Definition of Done

V1 is done only when all statements below have fresh evidence:

- [ ] The Design Document remains `Final / Frozen` and implementation matches it.
- [ ] The Plugin manifest and `skill-engineer` Skill pass bundled validators.
- [ ] All five operation modes execute through the internal Pipeline.
- [ ] Modify/Fix stage before diagnostics and never mutate source before publication.
- [ ] Create can establish staging before classification.
- [ ] Audit Only never enters staging or auto-upgrades.
- [ ] Gate remediation loops return to responsible stages and repeat audit, validation, and Gate.
- [ ] `DecisionRecord.root_cause` follows its conditional contract.
- [ ] `ArtifactManifest.source_revision/source_digest` follows its conditional contract.
- [ ] Audit Only PASS produces `UNCHANGED_VALIDATED` with `publish_authorized=false`.
- [ ] Only Internal Quality Gate emits final PASS/FAIL.
- [ ] Every applicable required check has valid, trustworthy, reproducible evidence.
- [ ] Optional Provider/checker failures use fallback or warnings and do not directly fail the Gate.
- [ ] Rule Bloat Detection produces findings only.
- [ ] Rule Governance owns `KEEP/MERGE/MOVE/DELETE` decisions.
- [ ] `TASK_LOCAL_PREFERENCE` never persists.
- [ ] `INSUFFICIENT_EVIDENCE` never adds a permanent Prompt Rule.
- [ ] All four Provider capabilities work through internal fallback with external Providers disabled.
- [ ] Formal runs reject unpinned external Provider identity.
- [ ] Regression cases are grouped by failure family.
- [ ] Missing behavioral runner records `NOT_EXECUTED`, never PASS.
- [ ] Project policy can strengthen but cannot weaken `B01–B12`.
- [ ] Atomic publication requires PASS plus explicit publication authority.
- [ ] Cross-volume publication fails.
- [ ] Source races block replacement.
- [ ] Failed publication restores the one-generation backup.
- [ ] The two legal external output types are enforced.
- [ ] Blocked non-Audit operations deliver no artifact and do not create a third output type.
- [ ] Full pytest suite passes.
- [ ] Windows UTF-8 and Unicode-path smoke test passes.
- [ ] Verification evidence records commands, environment, results, and tested revision.
- [ ] No MCP, UI, remote orchestration, database, marketplace automation, complex hooks, or multi-model matrix is introduced.

## Execution Checkpoints

1. **Checkpoint A — Contracts:** after Task 2, review schemas and conditional fields before parallel work.
2. **Checkpoint B — Core Safety:** after Tasks 3–7, review state, workspace, evidence, and Gate before orchestration.
3. **Checkpoint C — Minimal Loop:** after Task 8, verify the internal-only end-to-end pipeline before enhancements.
4. **Checkpoint D — Enhancements:** review Tasks 9–11 independently; each may be accepted or corrected without blocking the others.
5. **Checkpoint E — Publication:** review Task 12 as a safety-critical change before Plugin-facing documentation.
6. **Checkpoint F — V1 Release Candidate:** after Task 14, compare fresh evidence to the Definition of Done.
