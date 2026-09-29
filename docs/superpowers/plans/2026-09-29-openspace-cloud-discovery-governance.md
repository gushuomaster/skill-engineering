# OpenSpace Cloud Skill Discovery and Candidate Governance Implementation Plan

> **Production contract correction (2026-09-29):** Live OpenSpace `2.0.0` separates local and cloud search. The implemented production adapter now calls `cloud_browse_skills` with `action="search_skills"`, `audience="requester_visible"`, and `artifact_filter="downloadable_only"`. Earlier `search_skills(source="cloud", auto_import=false)` examples below record the superseded planning assumption and are not the production contract.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production Discovery Mode that searches local and OpenSpace Cloud Skills, lets Codex select a candidate with rationale, resolves remote content into quarantine, and issues an exact-candidate governance receipt only after the existing Quality Gate passes.

**Architecture:** Extend the existing `SkillSource` port with an OpenSpace MCP-backed source while preserving `find_exact()` and the existing explicit Provider path. Keep discovery, Codex selection, resolution, and governance as digest-bound phases; reuse the existing Inspection, Evidence, Coverage, Gate, and `ManagedCompletionReceipt` instead of creating a second governance system.

**Tech Stack:** Python 3.11+, `mcp>=1,<2`, PyYAML, jsonschema Draft 2020-12, subprocess-based official OpenSpace downloader, pytest 8, uv lockfile.

**Spec:** `docs/superpowers/specs/2026-09-29-openspace-cloud-discovery-governance-design.md`

## Global Constraints

- Preserve `SkillSource`, `LocalSkillSource`, `search_sources()`, `deduplicate_candidates()`, and `find_exact()`; no second discovery framework or Provider selector.
- OpenSpace discovery calls only the official MCP `cloud_browse_skills` tool with the fixed search-only action and downloadable-artifact filter.
- Production code must not call guessed OpenSpace REST/GraphQL endpoints or scrape web pages.
- Remote metadata and Codex selection rationale are discovery inputs, never Governance Evidence.
- Remote content may only be written below the Engine-owned artifacts root and must never enter `%CODEX_HOME%\\skills`, Plugin Cache, or another registered Skill root.
- No automatic install, enable, register, execute, publish, or deploy operation may be introduced.
- An OpenSpace `skill_id` is an opaque source reference until an authoritative contract proves it is immutable; unproven immutability must produce `INCOMPLETE` and no APPROVED receipt.
- Existing Gate values and policies remain authoritative; Discovery UI maps them but does not replace them.
- `CandidateGovernanceReceipt` is valid only for one source, resolved revision, candidate digest, inspection ID, and existing managed completion receipt.
- All text files are UTF-8 without BOM. Windows subprocess I/O explicitly uses UTF-8.
- Test artifacts live below a task-specific temporary artifacts root; tests must assert that real Skill installation roots do not change.

## File Structure

### New production files

- `engine/discovery_models.py` — immutable phase records and discovery/governance enums.
- `engine/discovery_serialization.py` — JSON parsing, canonical digests, and schema-bound conversions for discovery records.
- `engine/discovery.py` — resilient multi-source search, deduplication, and Codex selection validation.
- `engine/discovery_config.py` — strict non-secret source configuration parsing and source construction.
- `engine/openspace_source.py` — official MCP transport and `OpenSpaceCloudSource` normalization.
- `engine/candidate_resolution.py` — artifacts-root allocation, official CLI download, quarantine validation, digesting, and immutable-revision assessment.
- `engine/candidate_governance.py` — map the existing Gate and managed receipt to candidate-level APPROVED/BLOCKED/INCOMPLETE results.
- `engine/version.py` — one package-version authority shared by governance receipts and the public API.
- `config/skill-sources.yaml` — non-secret local/OpenSpace source and command configuration.
- `schemas/discovery-bundle.schema.json`
- `schemas/selection-record.schema.json`
- `schemas/resolved-candidate.schema.json`
- `schemas/candidate-governance-result.schema.json`
- `schemas/candidate-governance-receipt.schema.json`
- `skills/skill-engineer/references/discovery.md` — user-facing Discovery Mode workflow and STOP boundary.

### Modified production files

- `engine/__init__.py` — export stable discovery interfaces.
- `engine/serialization.py` — keep generic `to_data()` and expose existing Gate parsing for the finalizer without duplicating it.
- `engine/governance_api.py` — consume the shared package-version helper instead of maintaining a second fallback version.
- `scripts/skill_engineering.py` — add `discover`, `record-selection`, `resolve-candidate`, and `finalize-candidate` phase commands.
- `skills/skill-engineer/SKILL.md` — route discovery requests to the new reference without changing audit/repair modes.
- `pyproject.toml` and `uv.lock` — add and lock the MCP client dependency.
- `.codex-plugin/plugin.json` — bump plugin version after behavior and contracts are complete.

### New tests and fixtures

- `tests/unit/test_discovery_contracts.py`
- `tests/unit/test_openspace_source.py`
- `tests/unit/test_discovery_pipeline.py`
- `tests/unit/test_candidate_resolution.py`
- `tests/unit/test_candidate_governance.py`
- `tests/integration/test_discovery_cli.py`
- `tests/integration/test_remote_candidate_governance.py`
- `tests/e2e/test_openspace_discovery_governance.py`
- `tests/fixtures/openspace/fake_mcp_server.py`
- `tests/fixtures/openspace/fake_download_skill.py`
- `tests/fixtures/skills/remote-valid/SKILL.md`
- `tests/fixtures/skills/remote-invalid/SKILL.md`
- `docs/verification/openspace-discovery-governance-2026-09-29.md`

---

### Task 1: Add digest-bound discovery contracts

**Files:**
- Create: `engine/discovery_models.py`
- Create: `engine/discovery_serialization.py`
- Create: `schemas/discovery-bundle.schema.json`
- Create: `schemas/selection-record.schema.json`
- Create: `schemas/resolved-candidate.schema.json`
- Create: `schemas/candidate-governance-result.schema.json`
- Create: `schemas/candidate-governance-receipt.schema.json`
- Modify: `engine/__init__.py`
- Test: `tests/unit/test_discovery_contracts.py`
- Test: `tests/unit/test_contracts.py`

**Interfaces:**
- Consumes: existing `SkillCandidate`, `SkillOrigin`, `CoverageStatus`, `GateVerdict`.
- Produces: `SourceSearchStatus`, `ImmutabilityStatus`, `CandidateGovernanceStatus`, `SourceSearchReport`, `DiscoveryBundle`, `SelectionRecord`, `ResolvedCandidate`, `CandidateGovernanceReceipt`, `CandidateGovernanceResult`, `canonical_record_digest()`, and `*_from_data()` converters.

- [ ] **Step 1: Write failing model and schema tests**

```python
def test_selection_record_requires_codex_rationale_and_bundle_binding():
    with pytest.raises(ValueError, match="selection rationale must be nonblank"):
        SelectionRecord(
            schema_version="1.0",
            selection_id="selection-1",
            discovery_bundle_digest="a" * 64,
            selected_candidate_id="openspace-cloud:abc",
            selection_rationale="",
            selected_by="CODEX",
            selected_at="2026-09-29T00:00:00+00:00",
            selection_record_digest="b" * 64,
        )


def test_candidate_receipt_schema_rejects_non_pass_gate():
    payload = load_fixture("candidate_governance_receipt.json")
    payload["gate_verdict"] = "FAIL"
    with pytest.raises(ValidationError):
        validate_contract("candidate-governance-receipt", payload)
```

- [ ] **Step 2: Run the focused tests and confirm the missing contracts fail**

Run: `python -m pytest tests/unit/test_discovery_contracts.py tests/unit/test_contracts.py -v`

Expected: FAIL during import or schema loading because the new records and schemas do not exist.

- [ ] **Step 3: Implement immutable phase records**

```python
class SourceSearchStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class ImmutabilityStatus(StrEnum):
    PROVEN = "PROVEN"
    UNPROVEN = "UNPROVEN"


class CandidateGovernanceStatus(StrEnum):
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True, slots=True)
class SelectionRecord:
    schema_version: str
    selection_id: str
    discovery_bundle_digest: str
    selected_candidate_id: str
    selection_rationale: str
    selected_by: str
    selected_at: str
    selection_record_digest: str

    def __post_init__(self) -> None:
        if not self.selection_rationale.strip():
            raise ValueError("selection rationale must be nonblank")
        if self.selected_by != "CODEX":
            raise ValueError("candidate selection must be authored by CODEX")


@dataclass(frozen=True, slots=True)
class SourceSearchReport:
    source_type: str
    status: SourceSearchStatus
    candidate_ids: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DiscoveryBundle:
    schema_version: str
    discovery_id: str
    query: str
    source_reports: tuple[SourceSearchReport, ...]
    candidates: tuple[SkillCandidate, ...]
    discovered_at: str
    bundle_digest: str


@dataclass(frozen=True, slots=True)
class ResolvedCandidate:
    schema_version: str
    resolution_id: str
    discovery_bundle_digest: str
    selection_record_digest: str
    candidate_id: str
    name: str
    source_type: str
    source_id: str
    source_uri: str | None
    fetch_reference: str
    resolved_revision: str | None
    immutability_status: ImmutabilityStatus
    immutability_evidence: tuple[str, ...]
    quarantine_path: Path
    candidate_digest: str
    resolver: str
    resolved_at: str
    resolution_record_digest: str


@dataclass(frozen=True, slots=True)
class CandidateGovernanceReceipt:
    schema_version: str
    receipt_id: str
    governance_status: CandidateGovernanceStatus
    candidate_id: str
    source_type: str
    source_id: str
    source_uri: str | None
    resolved_revision: str
    candidate_digest: str
    resolution_record_digest: str
    discovery_bundle_digest: str
    selection_id: str
    selection_rationale: str
    selection_record_digest: str
    inspection_id: str
    coverage_status: CoverageStatus
    gate_verdict: GateVerdict
    managed_completion_receipt_digest: str
    engine_version: str
    plugin_version: str
    issued_at: str
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class CandidateGovernanceResult:
    schema_version: str
    result_id: str
    governance_status: CandidateGovernanceStatus
    candidate_id: str
    candidate_digest: str | None
    discovery_bundle_digest: str | None
    selection_record_digest: str | None
    inspection_id: str | None
    coverage_status: CoverageStatus | None
    gate_verdict: GateVerdict | None
    blocking_reasons: tuple[str, ...]
    receipt: CandidateGovernanceReceipt | None
    finalized_at: str
    result_digest: str
```

Validate these exact records in `__post_init__`: `CandidateGovernanceReceipt.governance_status` must be `APPROVED`, its `gate_verdict` must be `PASS`, `ResolvedCandidate.resolved_revision` must be nonblank only when immutability is `PROVEN`, APPROVED receipts require a nonblank selection rationale, and every populated digest field must be lowercase SHA-256.

- [ ] **Step 4: Implement canonical serialization and complete schemas**

```python
def canonical_record_digest(value: object, *, omit: frozenset[str] = frozenset()) -> str:
    payload = to_data(value)
    if isinstance(payload, dict):
        payload = {key: item for key, item in payload.items() if key not in omit}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
```

Implement exact converters `skill_candidate_from_data()`, `discovery_bundle_from_data()`, `selection_record_from_data()`, `resolved_candidate_from_data()`, `candidate_governance_result_from_data()`, and `candidate_governance_receipt_from_data()`. Each converter first validates its JSON Schema, reconstructs enums and paths, then recomputes and compares the record's own digest while omitting only that digest field. A mismatch raises `ValueError("<record> digest mismatch")`; loading JSON must never silently trust a persisted digest.

Each schema uses `additionalProperties: false`, requires `schema_version`, and constrains all digest properties with `^[a-f0-9]{64}$`. Required properties are exact:

- Discovery Bundle: `schema_version`, `discovery_id`, `query`, `source_reports`, `candidates`, `discovered_at`, `bundle_digest`.
- Selection Record: `schema_version`, `selection_id`, `discovery_bundle_digest`, `selected_candidate_id`, `selection_rationale`, `selected_by`, `selected_at`, `selection_record_digest`.
- Resolved Candidate: every field shown in `ResolvedCandidate`; `resolved_revision` is `[string, null]` and `resolution_record_digest` is the canonical digest of all other fields.
- Candidate Governance Result: every field shown in `CandidateGovernanceResult`; candidate digest, receipt, inspection, coverage, and Gate may be null only for `INCOMPLETE` failures that occur before content resolution or inspection.
- Candidate Governance Receipt: every field shown in `CandidateGovernanceReceipt`, with `"gate_verdict": {"const": "PASS"}`, `"governance_status": {"const": "APPROVED"}`, and a canonical `receipt_digest` over all other receipt fields.

- [ ] **Step 5: Run contract tests**

Run: `python -m pytest tests/unit/test_discovery_contracts.py tests/unit/test_contracts.py -v`

Expected: PASS.

- [ ] **Step 6: Commit the contract slice**

```powershell
git add engine/discovery_models.py engine/discovery_serialization.py engine/__init__.py schemas tests/unit/test_discovery_contracts.py tests/unit/test_contracts.py
git commit -m "feat: add remote discovery governance contracts"
```

### Task 2: Implement the official OpenSpace MCP source

**Files:**
- Create: `engine/openspace_source.py`
- Create: `config/skill-sources.yaml`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Test: `tests/unit/test_openspace_source.py`

**Interfaces:**
- Consumes: `SkillSource`, `SkillCandidate`, `SkillOrigin`, `CandidateSignal`.
- Produces: `DiscoverySourceError(RuntimeError)`, `OpenSpaceSearchTransport` protocol, `OpenSpaceMcpSearchTransport.search(query: str, limit: int) -> tuple[Mapping[str, object], ...]`, and `OpenSpaceCloudSource.search(query: str, context: Mapping[str, object] | None = None) -> tuple[SkillCandidate, ...]`.

- [ ] **Step 1: Write failing normalization and argument-safety tests**

```python
class RecordingTransport:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def search(self, query: str, limit: int):
        self.calls.append((query, limit))
        return self.rows


def test_cloud_source_uses_search_only_cloud_browsing():
    transport = RecordingTransport(({
        "cloud_skill_id": "demo__clo_12345678",
        "title": "demo",
        "summary": "Demo Skill",
        "score": 0.9,
    },))
    source = OpenSpaceCloudSource(transport)
    candidate = source.search("demo")[0]
    assert candidate.origins[0].source_type == "openspace-cloud"
    assert candidate.origins[0].fetch_reference == "demo__clo_12345678"
    assert candidate.origins[0].revision is None
    assert candidate.content_digest is None
```

The production transport test must assert the exact MCP arguments:

```python
assert call.arguments == {
    "action": "search_skills",
    "query": "demo",
    "limit": 20,
    "audience": "requester_visible",
    "artifact_filter": "downloadable_only",
}
```

- [ ] **Step 2: Run tests and confirm the source is missing**

Run: `python -m pytest tests/unit/test_openspace_source.py -v`

Expected: FAIL because `engine.openspace_source` does not exist.

- [ ] **Step 3: Add and lock the official MCP client**

Change `pyproject.toml` dependencies to include `"mcp>=1,<2"`, then run:

```powershell
uv lock
uv sync --frozen --extra test
```

Expected: `uv.lock` changes and the managed environment can import `mcp`.

Create `config/skill-sources.yaml` with this non-secret configuration:

```yaml
sources:
  - source_type: local
    enabled: true
  - source_type: openspace-cloud
    enabled: true
    transport: mcp-stdio
    command:
      - openspace-mcp
      - --transport
      - stdio
    search_tool: cloud_browse_skills
    search_action: search_skills
    artifact_filter: downloadable_only
    download_command:
      - openspace-download-skill
```

- [ ] **Step 4: Implement MCP stdio transport**

```python
@runtime_checkable
class OpenSpaceSearchTransport(Protocol):
    def search(self, query: str, limit: int) -> tuple[Mapping[str, object], ...]:
        raise NotImplementedError


class OpenSpaceMcpSearchTransport:
    def __init__(self, command: Sequence[str], *, timeout_seconds: int = 30) -> None:
        if not command:
            raise ValueError("OpenSpace MCP command must be nonempty")
        self.command = tuple(command)
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, limit: int) -> tuple[Mapping[str, object], ...]:
        return asyncio.run(self._search(query, limit))

    async def _search(self, query: str, limit: int):
        parameters = StdioServerParameters(
            command=self.command[0], args=list(self.command[1:])
        )
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                result = await asyncio.wait_for(
                        session.call_tool("cloud_browse_skills", arguments={
                        "action": "search_skills",
                        "query": query,
                        "limit": limit,
                        "audience": "requester_visible",
                        "artifact_filter": "downloadable_only",
                    }),
                    timeout=self.timeout_seconds,
                )
        return _parse_search_result(result)
```

`_parse_search_result()` accepts only text content containing a JSON object with a list-valued `results`; a payload containing `error`, invalid JSON, missing `results`, or non-mapping rows raises `DiscoverySourceError`.

- [ ] **Step 5: Implement `OpenSpaceCloudSource` normalization**

```python
return SkillCandidate(
    candidate_id=f"openspace-cloud:{sha256(skill_id.encode('utf-8')).hexdigest()}",
    name=name,
    description=description,
    canonical_repository=None,
    content_digest=None,
    origins=(SkillOrigin(
        source_type="openspace-cloud",
        source_id=skill_id,
        source_url=None,
        fetch_reference=skill_id,
        publisher=_optional_text(row.get("created_by")),
        revision=None,
        quality_signals=_signals(row, ("score",)),
        trust_signals=_signals(row, ("visibility", "safety_flags")),
    ),),
    discovered_at=self._clock().astimezone(timezone.utc).isoformat(),
)
```

Do not map `score`, popularity, author, tags, or safety flags into evidence fields.

- [ ] **Step 6: Run source tests**

Run: `python -m pytest tests/unit/test_openspace_source.py tests/unit/test_skill_sources.py -v`

Expected: PASS, including existing local lookup behavior.

- [ ] **Step 7: Commit the source slice**

```powershell
git add engine/openspace_source.py config/skill-sources.yaml pyproject.toml uv.lock tests/unit/test_openspace_source.py
git commit -m "feat: add OpenSpace MCP skill source"
```

### Task 3: Add resilient discovery and Codex selection

**Files:**
- Create: `engine/discovery.py`
- Modify: `engine/discovery_serialization.py`
- Test: `tests/unit/test_discovery_pipeline.py`
- Test: `tests/unit/test_skill_sources.py`

**Interfaces:**
- Consumes: any `SkillSource`, `search_sources()`, `deduplicate_candidates()`, discovery models.
- Produces: `build_discovery_bundle(query: str, reports: Sequence[SourceSearchReport], candidates: Sequence[SkillCandidate], discovered_at: datetime) -> DiscoveryBundle`, `DiscoveryService.discover(query, sources) -> DiscoveryBundle`, and `record_selection(bundle, candidate_id, rationale, clock) -> SelectionRecord`.

- [ ] **Step 1: Write failing multi-source and failure-report tests**

```python
def test_discovery_preserves_local_results_when_cloud_is_unavailable():
    bundle = DiscoveryService(clock=fixed_clock).discover(
        "document generation",
        (StubLocal((local_candidate,)), FailingCloud("authentication failed")),
    )
    assert bundle.candidates == (local_candidate,)
    assert bundle.source_reports[1].status is SourceSearchStatus.INCOMPLETE
    assert bundle.source_reports[1].errors == ("authentication failed",)


def test_selection_is_bound_to_an_existing_candidate():
    with pytest.raises(ValueError, match="candidate is not present"):
        record_selection(bundle, "missing", "best match", clock=fixed_clock)
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `python -m pytest tests/unit/test_discovery_pipeline.py -v`

Expected: FAIL because the service and selection validator do not exist.

- [ ] **Step 3: Implement per-source reporting and existing deduplication**

```python
class DiscoveryService:
    def discover(self, query: str, sources: Sequence[SkillSource]) -> DiscoveryBundle:
        if not query.strip():
            raise ValueError("discovery query must be nonblank")
        reports = []
        candidates = []
        for source in sources:
            try:
                # Reuse the existing aggregation port even for the per-source
                # call so its deduplication contract remains authoritative.
                found = search_sources((source,), query)
            except Exception as exc:
                reports.append(SourceSearchReport(
                    source.source_type, SourceSearchStatus.INCOMPLETE, (),
                    (f"{type(exc).__name__}: {exc}",),
                ))
            else:
                candidates.extend(found)
                reports.append(SourceSearchReport(
                    source.source_type, SourceSearchStatus.COMPLETE,
                    tuple(item.candidate_id for item in found), (),
                ))
        merged = deduplicate_candidates(candidates)
        return build_discovery_bundle(query, tuple(reports), merged, self._clock())
```

An incomplete Source remains visible and prevents a claim of complete multi-source discovery, but it does not erase valid results from another Source.

`build_discovery_bundle()` normalizes the UTC timestamp once, constructs every field except `bundle_digest`, then computes `canonical_record_digest(values)`. It does not rank candidates or turn source signals into evidence:

```python
def build_discovery_bundle(query, reports, candidates, discovered_at):
    values = dict(
        schema_version="1.0",
        discovery_id=str(uuid4()),
        query=query.strip(),
        source_reports=tuple(reports),
        candidates=tuple(candidates),
        discovered_at=discovered_at.astimezone(timezone.utc).isoformat(),
    )
    return DiscoveryBundle(
        **values, bundle_digest=canonical_record_digest(values)
    )
```

- [ ] **Step 4: Implement digest-bound Codex selection**

```python
def record_selection(bundle, candidate_id, rationale, *, clock):
    if candidate_id not in {item.candidate_id for item in bundle.candidates}:
        raise ValueError("selected candidate is not present in discovery bundle")
    values = {
        "schema_version": "1.0",
        "selection_id": str(uuid4()),
        "discovery_bundle_digest": bundle.bundle_digest,
        "selected_candidate_id": candidate_id,
        "selection_rationale": rationale.strip(),
        "selected_by": "CODEX",
        "selected_at": clock().astimezone(timezone.utc).isoformat(),
    }
    return SelectionRecord(
        **values,
        selection_record_digest=canonical_record_digest(values),
    )
```

- [ ] **Step 5: Run discovery tests**

Run: `python -m pytest tests/unit/test_discovery_pipeline.py tests/unit/test_skill_sources.py -v`

Expected: PASS.

- [ ] **Step 6: Commit the discovery slice**

```powershell
git add engine/discovery.py engine/discovery_serialization.py tests/unit/test_discovery_pipeline.py tests/unit/test_skill_sources.py
git commit -m "feat: add multi-source discovery records"
```

### Task 4: Expose discovery phases in the production CLI

**Files:**
- Create: `engine/discovery_config.py`
- Modify: `scripts/skill_engineering.py`
- Create: `tests/fixtures/openspace/fake_mcp_server.py`
- Create: `tests/unit/test_discovery_config.py`
- Create: `tests/integration/test_discovery_cli.py`

**Interfaces:**
- Consumes: source configuration, `DiscoveryService`, `record_selection()`.
- Produces: `load_source_config(path: Path) -> SourceConfig`, `build_sources(config: SourceConfig, requested: Sequence[str], *, local_roots: Sequence[Path], openspace_command: Sequence[str] | None) -> tuple[SkillSource, ...]`, plus `discover` and `record-selection` CLI phase commands with schema-validated JSON outputs.

- [ ] **Step 1: Write failing CLI tests**

```python
def test_discover_command_searches_local_and_cloud_without_import(tmp_path):
    fake_mcp_command = [
        sys.executable,
        str(ROOT / "tests/fixtures/openspace/fake_mcp_server.py"),
    ]
    result = run_cli(
        "discover", "--query", "document generation",
        "--source", "local", "--source", "openspace-cloud",
        "--local-root", str(tmp_path / "skills"),
        "--openspace-mcp-command-json", json.dumps(fake_mcp_command),
        "--output", str(tmp_path / "discovery.json"),
    )
    assert result.returncode == 0
    payload = json.loads((tmp_path / "discovery.json").read_text(encoding="utf-8"))
    assert {item["source_type"] for item in payload["source_reports"]} == {
        "local", "openspace-cloud"
    }
    assert not (tmp_path / "installed-skills").exists()


def test_record_selection_rejects_stale_expected_bundle_digest(tmp_path):
    result = run_cli(
        "record-selection",
        "--discovery-bundle", str(tmp_path / "discovery.json"),
        "--expected-bundle-digest", "0" * 64,
        "--candidate-id", CLOUD_CANDIDATE_ID,
        "--rationale", "best match for the requested workflow",
        "--output", str(tmp_path / "selection.json"),
    )
    assert result.returncode == 2
    assert not (tmp_path / "selection.json").exists()
```

The success test is exact:

```python
def test_record_selection_accepts_current_bundle_digest(tmp_path):
    bundle_path, bundle = write_valid_discovery_bundle(tmp_path)
    output = tmp_path / "selection.json"
    result = run_cli(
        "record-selection",
        "--discovery-bundle", str(bundle_path),
        "--expected-bundle-digest", bundle.bundle_digest,
        "--candidate-id", bundle.candidates[0].candidate_id,
        "--rationale", "best match for the requested workflow",
        "--output", str(output),
    )
    record = selection_record_from_data(
        json.loads(output.read_text(encoding="utf-8"))
    )
    assert result.returncode == 0
    assert record.discovery_bundle_digest == bundle.bundle_digest
    assert record.selection_rationale == "best match for the requested workflow"
```

The fake MCP server must reject accidental imports rather than silently accepting them:

```python
mcp = FastMCP("OpenSpaceFixture")


@mcp.tool()
async def cloud_browse_skills(
    action: str, query: str, limit: int = 20,
    audience: str = "requester_visible", artifact_filter: str = "downloadable_only",
) -> str:
    if action != "search_skills" or audience != "requester_visible" or artifact_filter != "downloadable_only":
        return json.dumps({"error": "unsafe search arguments"})
    return json.dumps({
        "results": [{
            "cloud_skill_id": "remote-valid__clo_12345678",
            "title": "remote-valid",
            "summary": f"Fixture match for {query}",
            "effective_visibility": "public",
            "downloadable": True,
            "score": 0.99,
        }][:limit],
        "count": 1,
    })


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

- [ ] **Step 2: Run CLI tests and confirm parser failure**

Run: `python -m pytest tests/integration/test_discovery_cli.py -v`

Expected: FAIL because the phase commands are not registered.

- [ ] **Step 3: Implement strict source configuration and construction**

`load_source_config()` accepts only a top-level `sources` list, rejects unknown source types, duplicate source types, invalid search actions or artifact filters, and empty command arrays. It returns frozen records and never accepts credentials or arbitrary environment mappings from YAML. `build_sources()` uses CLI command overrides only when explicitly provided; otherwise it uses the validated non-secret config.

```python
@dataclass(frozen=True, slots=True)
class SourceDefinition:
    source_type: str
    enabled: bool
    command: tuple[str, ...] = ()
    download_command: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceConfig:
    definitions: tuple[SourceDefinition, ...]
```

Run: `python -m pytest tests/unit/test_discovery_config.py -v`

Expected: PASS for the checked-in config and rejection of import actions, credentials, unknown keys, and duplicate sources.

- [ ] **Step 4: Add CLI arguments and source construction**

```python
PHASE_COMMANDS = frozenset({
    "discover", "record-selection", "resolve-candidate", "finalize-candidate",
    "inspect", "validate", "confirm", "apply", "status",
})

discover = commands.add_parser("discover")
discover.add_argument("--query", required=True)
discover.add_argument("--source", action="append", choices=("local", "openspace-cloud"))
discover.add_argument("--local-root", action="append", type=Path, default=[])
discover.add_argument("--openspace-mcp-command-json")
discover.add_argument("--source-config", type=Path, default=ROOT / "config" / "skill-sources.yaml")
discover.add_argument("--output", required=True, type=Path)

selection = commands.add_parser("record-selection")
selection.add_argument("--discovery-bundle", required=True, type=Path)
selection.add_argument("--expected-bundle-digest", required=True)
selection.add_argument("--candidate-id", required=True)
selection.add_argument("--rationale", required=True)
selection.add_argument("--output", required=True, type=Path)
```

The config contains command names only; credentials remain inherited environment variables and are never written to JSON output.

- [ ] **Step 5: Write and validate phase outputs**

Use `to_data()`, `validate_contract("discovery-bundle", payload)`, and `_write_json()`. `record-selection` must load through `discovery_bundle_from_data()`, compare `--expected-bundle-digest` with the validated bundle digest using `hmac.compare_digest()`, and only then construct the Selection Record. Error paths return exit code `2`, write structured JSON to stderr, and do not create the requested output file.

- [ ] **Step 6: Run CLI and regression tests**

Run: `python -m pytest tests/unit/test_discovery_config.py tests/integration/test_discovery_cli.py tests/integration/test_phased_cli.py -v`

Expected: PASS and the original phase commands remain unchanged.

- [ ] **Step 7: Commit the CLI discovery slice**

```powershell
git add engine/discovery_config.py scripts/skill_engineering.py tests/fixtures/openspace/fake_mcp_server.py tests/unit/test_discovery_config.py tests/integration/test_discovery_cli.py
git commit -m "feat: expose skill discovery CLI phases"
```

### Task 5: Resolve selected Cloud candidates into quarantine

**Files:**
- Create: `engine/candidate_resolution.py`
- Create: `tests/fixtures/openspace/fake_download_skill.py`
- Create: `tests/fixtures/skills/remote-valid/SKILL.md`
- Create: `tests/fixtures/skills/remote-invalid/SKILL.md`
- Create: `tests/unit/test_candidate_resolution.py`
- Modify: `scripts/skill_engineering.py`
- Modify: `engine/discovery_serialization.py`

**Interfaces:**
- Consumes: validated `DiscoveryBundle` and `SelectionRecord`.
- Produces: `default_artifact_root(project_id: str) -> Path`, `OpenSpaceCliResolver.resolve(candidate: SkillCandidate, selection: SelectionRecord, *, artifact_root: Path, forbidden_roots: Sequence[Path]) -> ResolvedCandidate`, and `resolve-candidate` CLI output bound to both input record digests.

- [ ] **Step 1: Write failing quarantine and no-install tests**

```python
def test_resolver_downloads_below_quarantine_and_never_installs(tmp_path):
    codex_home = tmp_path / "codex-home"
    installed = codex_home / "skills"
    installed.mkdir(parents=True)
    before = digest_tree(installed)
    resolved = resolver.resolve(
        candidate, selection, artifact_root=tmp_path / "artifacts",
        forbidden_roots=(installed,),
    )
    expected_root = (tmp_path / "artifacts" / "quarantine").resolve()
    assert resolved.quarantine_path.is_relative_to(expected_root)
    assert (resolved.quarantine_path / "SKILL.md").is_file()
    assert digest_tree(installed) == before


def test_openspace_record_without_immutable_contract_is_unproven():
    resolved = resolver.resolve(
        candidate, selection, artifact_root=artifact_root, forbidden_roots=(),
    )
    assert resolved.immutability_status is ImmutabilityStatus.UNPROVEN
    assert resolved.resolved_revision is None


def test_resolver_rejects_selection_for_another_candidate():
    mismatched = replace(
        selection,
        selected_candidate_id="openspace-cloud:other",
        selection_record_digest="0" * 64,
    )
    mismatched = replace(
        mismatched,
        selection_record_digest=canonical_record_digest(
            mismatched, omit=frozenset({"selection_record_digest"})
        ),
    )
    with pytest.raises(ValueError, match="selected candidate"):
        resolver.resolve(
            candidate, mismatched, artifact_root=artifact_root, forbidden_roots=(),
        )
```

Cover every quarantine boundary with one parametrized test:

```python
@pytest.mark.parametrize(
    ("fixture_mode", "message"),
    (
        ("path-escape", "outside quarantine"),
        ("missing-skill-md", "SKILL.md"),
        ("skill-id-mismatch", ".skill_id"),
        ("symlink-escape", "link or reparse point"),
        ("too-many-files", "1000 files"),
        ("too-large", "10 MiB"),
    ),
)
def test_resolver_rejects_unsafe_downloads(
    tmp_path, candidate, selection, fixture_mode, message,
):
    resolver = resolver_for_fixture_mode(fixture_mode)
    with pytest.raises(CandidateResolutionError, match=re.escape(message)):
        resolver.resolve(
            candidate, selection,
            artifact_root=tmp_path / "artifacts",
            forbidden_roots=(tmp_path / "codex-home" / "skills",),
        )
```

- [ ] **Step 2: Run resolution tests and confirm failure**

Run: `python -m pytest tests/unit/test_candidate_resolution.py -v`

Expected: FAIL because the resolver does not exist.

- [ ] **Step 3: Implement artifacts-root allocation and forbidden-root checks**

```python
def default_artifact_root(project_id: str) -> Path:
    override = os.environ.get("SKILL_ENGINEERING_ARTIFACT_ROOT")
    base = Path(override) if override else _user_cache_root() / "skill-engineering" / "artifacts"
    return (base / safe_component(project_id)).resolve()


def _user_cache_root() -> Path:
    if local_app_data := os.environ.get("LOCALAPPDATA"):
        return Path(local_app_data)
    if xdg_cache := os.environ.get("XDG_CACHE_HOME"):
        return Path(xdg_cache)
    return Path.home() / ".cache"


WINDOWS_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
})


def safe_component(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip(".-")
    if not normalized or normalized.upper() in WINDOWS_RESERVED_NAMES:
        raise ValueError("project or candidate identifier is not a safe path component")
    return normalized[:80]


def assert_not_registered_root(target: Path, forbidden_roots: Sequence[Path]) -> None:
    resolved = target.resolve()
    for root in forbidden_roots:
        registered = root.resolve()
        if (
            resolved == registered
            or resolved.is_relative_to(registered)
            or registered.is_relative_to(resolved)
        ):
            raise PermissionError(f"quarantine target overlaps registered Skill root: {registered}")
```

Allocate exactly `<artifact-root>/quarantine/<resolution-id>/<safe-candidate-name>/`. Create the artifact root and quarantine run with `mkdir(parents=True, exist_ok=False)` under an Engine-generated UUID, resolve each component, verify every resolved path remains below the configured artifact root, and compare `st_dev` for the artifact root, quarantine run, and downloaded Skill before accepting content. Call `assert_no_scope_escape()` before inventorying files.

- [ ] **Step 4: Implement the official CLI resolver**

```python
command = [
    *self.download_command,
    "--skill-id", origin.source_id,
    "--output-dir", str(quarantine_run),
]
completed = subprocess.run(
    command,
    text=True,
    capture_output=True,
    encoding="utf-8",
    errors="replace",
    timeout=self.timeout_seconds,
    check=False,
)
if completed.returncode != 0:
    raise CandidateResolutionError(
        f"OpenSpace download failed: {(completed.stderr or completed.stdout)[-2000:]}"
    )
```

Parse stdout JSON, require `local_path` below the allocated quarantine run, verify `.skill_id`, `SKILL.md`, path containment, file count and byte limits, then compute `engine.inventory.digest_tree()`.

Before invoking the downloader, require `selection.selected_candidate_id == candidate.candidate_id`, a matching recomputed `selection_record_digest`, and exactly one `openspace-cloud` origin with nonblank `source_id` and `fetch_reference`. After validation, build `resolution_record_digest` by hashing every Resolved Candidate field except that digest itself.

The fake downloader accepts the same public CLI arguments and copies only a fixture Skill:

```python
parser = argparse.ArgumentParser()
parser.add_argument("--skill-id", required=True)
parser.add_argument("--output-dir", required=True, type=Path)
args = parser.parse_args()
source = Path(__file__).resolve().parents[1] / "skills" / "remote-valid"
target = args.output_dir.resolve() / "remote-valid"
shutil.copytree(source, target)
(target / ".skill_id").write_text(args.skill_id + "\n", encoding="utf-8")
print(json.dumps({
    "status": "success",
    "skill_id": args.skill_id,
    "name": "remote-valid",
    "local_path": str(target),
    "files": ["SKILL.md", ".skill_id"],
}))
```

- [ ] **Step 5: Implement immutable-revision assessment**

```python
if origin.revision:
    revision = origin.revision
    immutability = ImmutabilityStatus.PROVEN
    evidence = (f"origin_revision={origin.revision}",)
else:
    revision = None
    immutability = ImmutabilityStatus.UNPROVEN
    evidence = ("OpenSpace MCP contract did not provide an immutable revision",)
```

Do not add a force/override flag that turns UNPROVEN into PROVEN.

- [ ] **Step 6: Wire `resolve-candidate` into the CLI**

Register these exact arguments:

```python
resolve = commands.add_parser("resolve-candidate")
resolve.add_argument("--discovery-bundle", required=True, type=Path)
resolve.add_argument("--selection-record", required=True, type=Path)
resolve.add_argument("--artifact-root", type=Path)
resolve.add_argument("--project-id", required=True)
resolve.add_argument("--download-command-json")
resolve.add_argument("--forbidden-root", action="append", type=Path, default=[])
resolve.add_argument("--output", required=True, type=Path)
```

Load both records through their digest-checking converters. Require `selection.discovery_bundle_digest == bundle.bundle_digest`; find exactly one bundle candidate whose ID equals `selection.selected_candidate_id`; and automatically add `%CODEX_HOME%/skills`, `%CODEX_HOME%/plugins/cache`, `ROOT/skills`, all configured local roots, and every explicit `--forbidden-root` to the resolver's forbidden roots.

On a successful download, the command always writes a schema-valid `resolved-candidate.json`. Return exit code `2` when that record is valid but immutability is UNPROVEN so automation cannot confuse successful download with governance readiness. A failure before a Resolved Candidate exists writes no fake resolved record; Task 6 adds the schema-valid `--failure-output` governance result for those paths.

- [ ] **Step 7: Run resolution and CLI tests**

Run: `python -m pytest tests/unit/test_candidate_resolution.py tests/integration/test_discovery_cli.py -v`

Expected: PASS, including an exit-code-2 case with a written UNPROVEN record.

- [ ] **Step 8: Commit the resolution slice**

```powershell
git add engine/candidate_resolution.py engine/discovery_serialization.py scripts/skill_engineering.py tests/fixtures/openspace tests/fixtures/skills/remote-valid tests/fixtures/skills/remote-invalid tests/unit/test_candidate_resolution.py tests/integration/test_discovery_cli.py
git commit -m "feat: quarantine resolved cloud candidates"
```

### Task 6: Bind the existing Gate to candidate governance results

**Files:**
- Create: `engine/candidate_governance.py`
- Create: `engine/version.py`
- Create: `tests/unit/test_candidate_governance.py`
- Modify: `engine/governance_api.py`
- Modify: `engine/serialization.py`
- Modify: `engine/discovery_serialization.py`
- Modify: `scripts/skill_engineering.py`

**Interfaces:**
- Consumes: `ResolvedCandidate`, `SelectionRecord`, `InspectionBundle`, existing `GateResult`, optional `ManagedCompletionReceipt`.
- Produces: `package_version() -> str`, `finalize_candidate(resolved: ResolvedCandidate, selection: SelectionRecord, inspection: InspectionBundle, gate: GateResult, receipt: ManagedCompletionReceipt | None, *, plugin_version: str, clock: Callable[[], datetime]) -> CandidateGovernanceResult`, `incomplete_candidate_result(candidate_id: str, reasons: Sequence[str], *, candidate_digest: str | None, discovery_bundle_digest: str | None, selection_record_digest: str | None, clock: Callable[[], datetime]) -> CandidateGovernanceResult`, and an APPROVED-only `CandidateGovernanceReceipt`.

- [ ] **Step 1: Write failing Gate mapping tests**

```python
def test_pass_cannot_approve_unproven_revision():
    result = finalize_candidate(
        unproven_resolved, selection, inspection, pass_gate, managed_receipt,
        plugin_version="1.1.0+codex.20260929000000", clock=fixed_clock,
    )
    assert result.governance_status is CandidateGovernanceStatus.INCOMPLETE
    assert result.receipt is None


def test_pass_receipt_binds_exact_revision_digest_and_inspection():
    result = finalize_candidate(
        proven_resolved, selection, inspection, pass_gate, managed_receipt,
        plugin_version="1.1.0+codex.20260929000000", clock=fixed_clock,
    )
    assert result.governance_status is CandidateGovernanceStatus.APPROVED
    assert result.receipt.candidate_digest == proven_resolved.candidate_digest
    assert result.receipt.inspection_id == inspection.inspection_id


def test_candidate_change_invalidates_approval(tmp_path):
    (proven_resolved.quarantine_path / "changed.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(CandidateChangedError):
        finalize_candidate(
            proven_resolved, selection, inspection, pass_gate, managed_receipt,
            plugin_version="1.1.0+codex.20260929000000", clock=fixed_clock,
        )


def test_gate_and_managed_receipt_must_describe_the_same_decision():
    mismatched_gate = replace(pass_gate, coverage_status=CoverageStatus.PARTIAL)
    with pytest.raises(ValueError, match="Gate and managed receipt"):
        finalize_candidate(
            proven_resolved, selection, inspection, mismatched_gate,
            managed_receipt,
            plugin_version="1.1.0+codex.20260929000000", clock=fixed_clock,
        )
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `python -m pytest tests/unit/test_candidate_governance.py -v`

Expected: FAIL because the finalizer does not exist.

- [ ] **Step 3: Expose existing Gate parsing without duplicating Gate semantics**

Rename the private serializer helper `_gate()` to `gate_from_data()` and update existing callers. Do not create a new Gate enum or recompute Gate decisions in the discovery module.

Create `engine/version.py` with `package_version()`: return `importlib.metadata.version("skill-engineering")` when installed; otherwise parse the repository's `pyproject.toml` with `tomllib` and return `project.version`. Update `engine/governance_api.py` to call this helper and remove its hard-coded `1.0.3` fallback. Tests monkeypatch both installed metadata and a source-tree fallback so a future version bump cannot leave two authorities out of sync.

- [ ] **Step 4: Implement fail-closed finalization**

```python
def finalize_candidate(resolved, selection, inspection, gate, receipt, *, plugin_version, clock):
    assert_record_digest(
        selection, selection.selection_record_digest, "selection_record_digest"
    )
    assert_record_digest(
        resolved, resolved.resolution_record_digest, "resolution_record_digest"
    )
    current_digest = digest_tree(resolved.quarantine_path)
    if current_digest != resolved.candidate_digest:
        raise CandidateChangedError("quarantine candidate changed after resolution")
    if selection.discovery_bundle_digest != resolved.discovery_bundle_digest:
        raise ValueError("selection and resolved candidate reference different discovery bundles")
    if selection.selected_candidate_id != resolved.candidate_id:
        raise ValueError("selection and resolved candidate IDs do not match")
    if selection.selection_record_digest != resolved.selection_record_digest:
        raise ValueError("selection and resolved candidate record digests do not match")
    if receipt is not None and inspection.inspection_id != receipt.inspection_id:
        raise ValueError("inspection and managed receipt do not match")
    if gate.verdict is GateVerdict.FAIL:
        return _blocked_result(resolved, selection, inspection, gate, clock)
    if resolved.immutability_status is not ImmutabilityStatus.PROVEN:
        return _incomplete_after_inspection(
            resolved, selection, inspection, gate,
            "immutable revision unproven", clock,
        )
    if gate.verdict is not GateVerdict.PASS or receipt is None:
        return _incomplete_after_inspection(
            resolved, selection, inspection, gate,
            "formal PASS receipt missing", clock,
        )
    validate_completion_receipt(receipt)
    if (
        gate.verdict is not receipt.gate_verdict
        or gate.outcome is not receipt.gate_outcome
        or gate.coverage_status is not receipt.coverage_status
    ):
        raise ValueError("Gate and managed receipt do not describe the same decision")
    if receipt.candidate_digest != resolved.candidate_digest:
        raise CandidateChangedError("managed receipt is bound to a different candidate")
    receipt_values = dict(
        schema_version="1.0",
        receipt_id=str(uuid4()),
        governance_status=CandidateGovernanceStatus.APPROVED,
        candidate_id=resolved.candidate_id,
        source_type=resolved.source_type,
        source_id=resolved.source_id,
        source_uri=resolved.source_uri,
        resolved_revision=resolved.resolved_revision,
        candidate_digest=resolved.candidate_digest,
        resolution_record_digest=resolved.resolution_record_digest,
        discovery_bundle_digest=resolved.discovery_bundle_digest,
        selection_id=selection.selection_id,
        selection_rationale=selection.selection_rationale,
        selection_record_digest=resolved.selection_record_digest,
        inspection_id=inspection.inspection_id,
        coverage_status=receipt.coverage_status,
        gate_verdict=gate.verdict,
        managed_completion_receipt_digest=canonical_record_digest(receipt),
        engine_version=package_version(),
        plugin_version=plugin_version,
        issued_at=clock().astimezone(timezone.utc).isoformat(),
    )
    candidate_receipt = CandidateGovernanceReceipt(
        **receipt_values,
        receipt_digest=canonical_record_digest(receipt_values),
    )
    return _approved_result(
        resolved, selection, inspection, gate, candidate_receipt, clock
    )
```

`assert_record_digest(record, expected, digest_field)` calls `canonical_record_digest(record, omit=frozenset({digest_field}))` and compares with `hmac.compare_digest`; a mismatch raises `ValueError`. Private helpers `_approved_result()`, `_blocked_result()`, and `_incomplete_after_inspection()` populate every `CandidateGovernanceResult` field from the bound records and compute `result_digest` over the result without that field. `_blocked_result()` copies Gate blocking findings, `_incomplete_after_inspection()` includes the explicit missing-proof reason, and neither creates a receipt. The APPROVED receipt includes `receipt_id`, source type/ID/URI, revision, candidate and resolution-record digests, selection ID/rationale/digest, inspection ID, coverage, Gate verdict, managed receipt digest, Engine/Plugin version, timestamp, and its own canonical digest.

Failures before an Inspection Bundle exists use this exact constructor and never fabricate inspection or Gate fields:

```python
def incomplete_candidate_result(
    candidate_id,
    reasons,
    *,
    candidate_digest,
    discovery_bundle_digest,
    selection_record_digest,
    clock,
):
    normalized = tuple(item.strip() for item in reasons if item.strip())
    if not normalized:
        raise ValueError("incomplete candidate result requires a reason")
    values = dict(
        schema_version="1.0",
        result_id=str(uuid4()),
        governance_status=CandidateGovernanceStatus.INCOMPLETE,
        candidate_id=candidate_id,
        candidate_digest=candidate_digest,
        discovery_bundle_digest=discovery_bundle_digest,
        selection_record_digest=selection_record_digest,
        inspection_id=None,
        coverage_status=None,
        gate_verdict=None,
        blocking_reasons=normalized,
        receipt=None,
        finalized_at=clock().astimezone(timezone.utc).isoformat(),
    )
    return CandidateGovernanceResult(
        **values, result_digest=canonical_record_digest(values)
    )
```

- [ ] **Step 5: Wire `finalize-candidate` into the CLI**

Inputs: `--resolved-candidate`, `--selection-record`, `--inspection`, `--gate-result`, optional `--managed-receipt`, required result `--output`, and optional `--receipt-output`. Only write `--receipt-output` for APPROVED. Return `0` for APPROVED, `1` for BLOCKED, and `2` for INCOMPLETE.

Validate `--gate-result` with the existing `gate-result` schema before `gate_from_data()` and validate `--managed-receipt` with the existing managed receipt schema. Define `CandidateChangedError(ValueError)` so the direct API can expose a precise integrity failure. The CLI catches it and writes an INCOMPLETE result instead of a traceback.

Also add optional `--failure-output` to `resolve-candidate`: resolver errors caught before an Inspection exists are serialized with `incomplete_candidate_result()` to that path, return `2`, and never create a fake Resolved Candidate. Tests require this for missing downloader, nonzero downloader exit, malformed downloader JSON, missing `SKILL.md`, and path escape. A successful but UNPROVEN resolution remains a valid Resolved Candidate with exit code `2`; finalization maps it to an INCOMPLETE result.

- [ ] **Step 6: Run governance and phased CLI tests**

Run: `python -m pytest tests/unit/test_candidate_governance.py tests/integration/test_phased_cli.py tests/integration/test_discovery_cli.py -v`

Expected: PASS.

- [ ] **Step 7: Commit the governance slice**

```powershell
git add engine/candidate_governance.py engine/version.py engine/governance_api.py engine/serialization.py engine/discovery_serialization.py scripts/skill_engineering.py tests/unit/test_candidate_governance.py tests/integration/test_discovery_cli.py
git commit -m "feat: bind cloud candidates to existing Gate"
```

### Task 7: Prove production-path integration and no installation side effects

**Files:**
- Create: `tests/integration/test_remote_candidate_governance.py`
- Create: `tests/e2e/test_openspace_discovery_governance.py`

**Interfaces:**
- Consumes: all phase commands and existing `PipelineOrchestrator` audit path.
- Produces: an executable local+Cloud test pipeline ending in APPROVED/BLOCKED/INCOMPLETE without installation.

- [ ] **Step 1: Write an end-to-end fixture pipeline test**

```python
def test_remote_candidate_pipeline_stops_after_governance(tmp_path, monkeypatch):
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    installed_root = codex_home / "skills"
    installed_root.mkdir(parents=True)
    before = snapshot_tree(installed_root)

    cloud = OpenSpaceCloudSource(RecordingTransport((CLOUD_ROW,)))
    discovery = DiscoveryService(clock=fixed_clock).discover(
        "document generation", (LocalSkillSource((tmp_path / "local",)), cloud),
    )
    remote = next(item for item in discovery.candidates if item.origins[0].source_type == "openspace-cloud")
    selection = record_selection(
        discovery, remote.candidate_id, "matches the requested document workflow",
        clock=fixed_clock,
    )
    resolver = OpenSpaceCliResolver(
        (sys.executable, str(FAKE_DOWNLOADER)), clock=fixed_clock,
    )
    resolved = resolver.resolve(
        remote, selection, artifact_root=tmp_path / "artifacts",
        forbidden_roots=(installed_root, codex_home / "plugins" / "cache"),
    )
    inspection = PipelineOrchestrator().inspect(Intent.AUDIT, resolved.quarantine_path)
    gate = GateResult(
        GateVerdict.INCOMPLETE, GateOutcome.AUDIT_INCOMPLETE,
        ("immutable revision unproven",), (), "required=not-complete",
        "candidate was quarantined but immutable revision was not proven",
        False, False, "v1", CoverageStatus.PARTIAL, None,
    )
    result = finalize_candidate(
        resolved, selection, inspection, gate, None,
        plugin_version="1.1.0+codex.20260929000000", clock=fixed_clock,
    )

    assert result.governance_status is CandidateGovernanceStatus.INCOMPLETE
    assert result.receipt is None
    assert snapshot_tree(installed_root) == before
    assert not any(path.name == resolved.name for path in installed_root.iterdir())
```

Add these outcome and failure-path tests using shared fixture builders for proven/unproven resolutions and existing valid managed receipts:

```python
@pytest.mark.parametrize(
    ("resolved_name", "gate_name", "receipt_name", "expected", "has_receipt"),
    (
        ("proven", "pass", "valid", CandidateGovernanceStatus.APPROVED, True),
        ("proven", "fail", None, CandidateGovernanceStatus.BLOCKED, False),
        ("unproven", "incomplete", None, CandidateGovernanceStatus.INCOMPLETE, False),
    ),
)
def test_every_governance_outcome_has_no_install_side_effect(
    tmp_path, governance_fixtures, resolved_name, gate_name, receipt_name,
    expected, has_receipt,
):
    installed = tmp_path / "codex-home" / "skills"
    installed.mkdir(parents=True)
    before = snapshot_tree(installed)
    resolved, selection, inspection, gates, receipts = governance_fixtures(tmp_path)
    result = finalize_candidate(
        resolved[resolved_name], selection[resolved_name], inspection[resolved_name],
        gates[gate_name], receipts.get(receipt_name),
        plugin_version="1.1.0+codex.20260929000000", clock=fixed_clock,
    )
    assert result.governance_status is expected
    assert (result.receipt is not None) is has_receipt
    assert snapshot_tree(installed) == before


def test_mcp_unavailability_is_a_visible_incomplete_source_report():
    bundle = DiscoveryService(clock=fixed_clock).discover(
        "document generation", (FailingCloud("authentication failed"),),
    )
    assert bundle.source_reports[0].status is SourceSearchStatus.INCOMPLETE
    assert "authentication failed" in bundle.source_reports[0].errors[0]


@pytest.mark.parametrize(
    "failure_mode",
    ("missing-command", "nonzero", "malformed-json", "missing-skill-md", "path-escape"),
)
def test_resolver_failure_writes_incomplete_result(tmp_path, failure_mode):
    result_path = tmp_path / "resolution-failure.json"
    command = failing_downloader_command(failure_mode)
    completed = run_cli(
        "resolve-candidate", *valid_resolution_args(tmp_path),
        "--download-command-json", json.dumps(command),
        "--failure-output", str(result_path),
    )
    result = candidate_governance_result_from_data(
        json.loads(result_path.read_text(encoding="utf-8"))
    )
    assert completed.returncode == 2
    assert result.governance_status is CandidateGovernanceStatus.INCOMPLETE
    assert result.inspection_id is None
    assert result.gate_verdict is None
    assert result.receipt is None
```

`failing_downloader_command("missing-command")` returns a definitely absent executable name; all other modes return `[sys.executable, str(FAKE_DOWNLOADER), "--fixture-mode", failure_mode]`. Extend the fake downloader parser with that test-only flag and deterministic outputs for each mode.

- [ ] **Step 2: Run the new integration test**

Run: `python -m pytest tests/integration/test_remote_candidate_governance.py tests/e2e/test_openspace_discovery_governance.py -v`

Expected: PASS. If it fails, stop this task, preserve the exact failure output, and use `superpowers:systematic-debugging` before changing production code.

- [ ] **Step 3: Run focused regression suites**

```powershell
python -m pytest tests/unit -v
python -m pytest tests/integration/test_bootstrap_runtime.py tests/integration/test_host_provider_execution.py tests/integration/test_deliverable_contract_pipeline.py tests/integration/test_capability_manifest_pipeline.py tests/integration/test_remote_candidate_governance.py -v
```

Expected: all selected tests PASS.

- [ ] **Step 4: Commit the integration slice**

```powershell
git add tests/integration/test_remote_candidate_governance.py tests/e2e/test_openspace_discovery_governance.py
git commit -m "test: cover remote discovery governance flow"
```

### Task 8: Document the production workflow and update the plugin contract

**Files:**
- Create: `skills/skill-engineer/references/discovery.md`
- Modify: `skills/skill-engineer/SKILL.md`
- Modify: `.codex-plugin/plugin.json`
- Modify: `pyproject.toml`
- Modify: `engine/version.py`
- Test: `tests/unit/test_skill_entry.py`
- Test: `tests/unit/test_plugin_scaffold.py`
- Test: `tests/unit/test_version.py`

**Interfaces:**
- Consumes: final CLI names and result contracts.
- Produces: concise Skill routing instructions and a versioned plugin artifact.

- [ ] **Step 1: Write failing documentation contract tests**

```python
def test_skill_entry_preserves_discovery_install_boundary():
    text = (ROOT / "skills/skill-engineer/SKILL.md").read_text(encoding="utf-8")
    assert "references/discovery.md" in text
    assert "cloud_browse_skills" in text
    assert "must stop before installation" in text
```

- [ ] **Step 2: Run documentation tests and confirm failure**

Run: `python -m pytest tests/unit/test_skill_entry.py tests/unit/test_plugin_scaffold.py -v`

Expected: FAIL because the Discovery reference is absent.

- [ ] **Step 3: Add concise workflow documentation**

Document these user-visible invariants verbatim:

```text
Discovery finds candidates.
Codex selects candidates.
skill-engineering governs candidates.
Installer installs only explicitly authorized candidates.
```

List the phase commands and state that OpenSpace search must use the fixed search-only `cloud_browse_skills` action; no instruction may tell Codex to install or execute a discovered candidate.

- [ ] **Step 4: Bump versions consistently**

Set `pyproject.toml` version to `1.1.0` and `.codex-plugin/plugin.json` version to `1.1.0+codex.20260929000000` (the existing plugin contract requires a fourteen-digit Codex build timestamp). Do not hard-code the version in `engine/version.py`; its source-tree fallback must read `pyproject.toml`. Run `uv lock` so the lockfile records the project version consistently, and assert `package_version() == "1.1.0"` when package metadata is unavailable.

- [ ] **Step 5: Validate Skill and plugin packaging**

```powershell
python -m pytest tests/unit/test_skill_entry.py tests/unit/test_plugin_scaffold.py tests/unit/test_version.py -v
python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/skill-engineer
```

Expected: PASS and quick validator exit code `0`.

- [ ] **Step 6: Commit documentation and versioning**

```powershell
git add skills/skill-engineer/SKILL.md skills/skill-engineer/references/discovery.md .codex-plugin/plugin.json pyproject.toml uv.lock engine/version.py tests/unit/test_skill_entry.py tests/unit/test_plugin_scaffold.py tests/unit/test_version.py
git commit -m "docs: define remote discovery governance workflow"
```

### Task 9: Run the Quality Gate, full regression, and real-environment probe

**Files:**
- Create: `docs/verification/openspace-discovery-governance-2026-09-29.md`
- Modify only if a verified defect is found: files owned by Tasks 1-8.

**Interfaces:**
- Consumes: completed implementation and current local OpenSpace installation.
- Produces: final evidence report with test counts, duration, actual OpenSpace contract, E2E evidence, blockers, and verdict.

- [ ] **Step 1: Run all unit tests**

Run: `python -m pytest tests/unit -v --durations=20`

Expected: zero failures.

- [ ] **Step 2: Run the complete repository test suite**

Run: `python -m pytest -v --durations=20`

Expected: zero failures. Record exact passed/failed/skipped counts and duration from pytest output.

- [ ] **Step 3: Run Skill validation**

Run: `python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/skill-engineer`

Expected: exit code `0`.

- [ ] **Step 4: Exercise the installed OpenSpace MCP contract when configured**

Use the production `discover` command with the actual current OpenSpace MCP command, a harmless natural-language query, `source=openspace-cloud`, and a task artifacts directory. Confirm the emitted source report, candidate count, and that no result is auto-imported.

Do not print the inherited environment, MCP configuration values, authorization headers, tokens, or raw credential-bearing stderr. Redact secret values while preserving the error class and safe diagnostic text. If authentication, MCP configuration, Cloud availability, or immutable revision proof is missing, record the exact non-secret blocker and mark the real E2E `BLOCKED`; do not substitute a fixture run. With the currently confirmed OpenSpace `0.1.0` contract, a downloaded candidate remains `INCOMPLETE` unless the live service supplies new authoritative immutable-revision evidence.

- [ ] **Step 5: Prove no installation side effect**

Capture path lists, file counts, and `digest_tree()` values of `%CODEX_HOME%\\skills` and `%CODEX_HOME%\\plugins\\cache` before and after the real probe without writing into either root. Record equality in the verification report. Do not delete, move, normalize, or rewrite any pre-existing user directories.

- [ ] **Step 6: Write the verification report**

The report must contain:

```markdown
## A. Previous Production Path
## B. New Discovery Path
## C. OpenSpace MCP Contract
## D. Architecture Changes
## E. Security Boundary
## F. Test Results
## G. E2E Evidence
## H. Remaining Blockers
## I. Final Verdict
```

Use `REMOTE_DISCOVERY_GOVERNANCE_READY` only if the real production path reaches a digest/revision-bound receipt. Otherwise use `NOT_READY` and list blockers.

- [ ] **Step 7: Run final diff and regression verification**

```powershell
git diff --check
git status --short
python -m pytest -q
```

Expected: no whitespace errors, only intended report changes remain, and the full suite reports zero failures.

- [ ] **Step 8: Commit verification evidence**

```powershell
git add docs/verification/openspace-discovery-governance-2026-09-29.md
git commit -m "docs: verify OpenSpace discovery governance"
```
