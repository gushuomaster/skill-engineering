# Audit Immutability and Phased Workflow Validation

> Historical validation record. Provider optionality and Gate verdict semantics in sections 7-9 were superseded by [Required Capability Model](required-capability-model.md): target defects now yield Gate `FAIL`, unavailable required capabilities yield `INCOMPLETE`, and neither can publish.

Date: 2026-09-16

Implementation commit: `6d6703653c4452e1ae88228d884f2e8e0fe984f3`

Validated plugin: `skill-engineering@personal` `1.0.2+codex.20260916071634`

This report is the final local validation record for the reopened P0-P4 architecture review. It does not authorize a remote push or public Plugin publication.

## 1. Original vulnerability reproduction

At baseline `93971f4e5aceecccd8f0174c9a4947549db6517e`, Audit Only passed the real source directory to external runners. A runner could create `runner-write.txt`, return exit code 0, and still obtain `PASS`/`UNCHANGED_VALIDATED` with an empty diff because the workspace comparison read the same mutated path as both sides. The source had changed while the audit result claimed it was trustworthy.

The protected baseline checks also confirmed that commits `3b4a8e2e34c709f9746fda57445de427551017a9` and `93971f4e5aceecccd8f0174c9a4947549db6517e` existed before changes.

## 2. RED evidence

Tests were added before production changes. The first P0 collection failed because `ArtifactAssessment` did not exist. After the P0 contract was introduced, the new real subprocess probes exposed source mutations and the self-comparison defect. The first P1 run then had six failures because `PipelineOrchestrator.inspect()`, `validate()`, phased serialization, and phased CLI commands did not exist.

The final A1-A7 integration suite executes real subprocesses for add, modify, delete, rename, nested write, nonzero exit without write, and concurrent external source mutation. It also covers a runner that returns 0 after mutating its supplied execution directory.

## 3. Root cause

Three mechanisms were missing:

1. `WorkspaceSession` retained only an aggregate digest and did not retain an immutable recursive source snapshot for a later real diff.
2. Audit commands used the source directory as their working artifact, so the Engine exposed an avoidable write surface.
3. The monolithic request required semantic and governance decisions before the detector had produced stable finding IDs, and it allowed confirmation, validation, and Gate computation to occur in one call.

Audit target defects and audit process integrity were also represented by the same Gate failure vocabulary, while Provider advice and deterministic checks shared one evidence collection.

## 4. Audit Only isolation and digest verification

`engine.inventory.snapshot_tree()` now records every recursive entry with relative path, entry type, size, content hash, mode, and an aggregate content-bound digest. `WorkspaceSession` captures that baseline at inspection/session creation.

Audit Only behavior commands run against a copy under the system temporary directory named `skill-engineering-audit-*`. After every external command, before Gate construction, and before returning the result, the Engine recalculates the real source snapshot. The final diff compares the stored baseline snapshot with the new snapshot; it never compares a path with itself.

If the source differs, the result becomes:

```text
audit_execution=INCOMPLETE
artifact_assessment=UNKNOWN
gate.outcome=AUDIT_INCOMPLETE
semantic_confirmed=false
publish_authorized=false
```

The diff carries added, modified, and deleted paths. Renames are represented as delete plus add. The Engine does not restore the source because a restore could overwrite a legitimate concurrent change.

## 5. Formal phased API

The authoritative path is now:

```text
PipelineOrchestrator.inspect()
→ Codex DecisionRecord and GovernanceDecision records
→ PipelineOrchestrator.validate()
→ Codex SemanticConfirmation
→ PipelineOrchestrator.confirm()
→ independent publish()
```

`InspectionBundle` contains the inspection ID, intent, source, baseline manifest and snapshot, baseline digest, signals, findings, stable finding IDs, Provider capabilities/evidence, creation time, schema version, and `INSPECTED` state.

`validate()` rejects stale baselines, unknown or uncovered actionable findings, non-Codex decisions, same-path source/candidate use, candidates in Audit Only, missing candidates for change modes, and candidate findings that were not inspected. It emits a `ValidationBundle` with staged manifest/digest, separate evidence channels, a real diff, evidence fingerprint, and `VALIDATED_PENDING_CONFIRMATION`.

`confirm()` rechecks the source baseline, staged artifact digest, evidence fingerprint, confirmation author, and exact confirmed digest before computing the Gate. `run()` remains a compatibility wrapper over inspect, validate, and confirm and never publishes.

`publish()` is independent. It rechecks source and candidate digests, requires `READY_TO_PUBLISH`, preserves the confirmation binding, creates a recoverable backup before atomic replacement, validates the published digest, and reports recovery-specific failure states.

## 6. CLI calls

The new machine-readable CLI is:

```powershell
python scripts/skill_engineering.py inspect `
  --target <skill> --mode AUDIT_ONLY --output inspection.json

python scripts/skill_engineering.py validate `
  --inspection inspection.json `
  --decision-record decision.json `
  --governance-decisions governance.json `
  --candidate <candidate> `
  --behavior-command-json '<json-array>' `
  --regression-command-json '<json-array>' `
  --output validation.json

python scripts/skill_engineering.py confirm `
  --validation validation.json `
  --semantic-confirmation confirmation.json `
  --output outcome.json

python scripts/skill_engineering.py publish `
  --outcome outcome.json --output publication.json
```

The inspection and validation bundles have JSON Schemas and round-trip loaders. Finding IDs survive the process boundary. The CLI never infers RCA or governance actions from request keywords.

Audit exit codes are 0 for complete and valid, 1 for complete with findings or blocking findings, and 2 for incomplete/system/contract failure.

## 7. Provider phase and evidence split

Inspection records these capabilities before Codex makes a decision:

```text
CREATE_CANDIDATE
AUDIT_SKILL
GOVERN_AGENT_INSTRUCTIONS
CHECK_SKILL_CONFORMANCE
```

Each Provider record contains provider ID, capability, invocation phase, status, summary, `deterministic=false`, and `reproducible=false` unless reproducibility is actually established. Missing Providers are recorded as `NOT_EXECUTED`. A separate Required Capability layer now executes trusted internal validators where available; this is real fallback evidence, not simulated Provider success.

Validation emits `deterministic_evidence` and `advisory_evidence` as separate fields. Providers cannot author final RCA, choose `KEEP/MERGE/MOVE/DELETE`, submit semantic confirmation, change Gate policy, or authorize publication. The `GOVERN_AGENT_INSTRUCTIONS` capability is recorded but not invoked unless `AGENTS.md` or `CLAUDE.md` is genuinely in scope.

## 8. Audit execution and target assessment

The two orthogonal contracts are:

```text
AuditExecution: COMPLETE | INCOMPLETE
ArtifactAssessment: VALID | FINDINGS | BLOCKING_FINDINGS | UNKNOWN
```

A complete audit of a defective Skill returns `COMPLETE/BLOCKING_FINDINGS` with Gate verdict `FAIL` and outcome `AUDIT_COMPLETE_BLOCKING_FINDINGS`. `INCOMPLETE/UNKNOWN` is reserved for an untrustworthy audit, missing required execution, or a changed source baseline; framework failures use Gate `ERROR`.

## 9. State mapping

| Phase/result | Lifecycle state | Gate outcome | Publish result |
|---|---|---|---|
| Inspection emitted | `INSPECTED` | n/a | n/a |
| Checks complete, awaiting Codex | `VALIDATED_PENDING_CONFIRMATION` | n/a | n/a |
| Confirmed, no publish request | `VALIDATED` | `VALIDATED` | n/a |
| Confirmed and explicit publish request | `READY_TO_PUBLISH` | `READY_TO_PUBLISH` | n/a |
| Audit complete, valid | `AUDIT_COMPLETE_VALID` | `AUDIT_COMPLETE_VALID` | n/a |
| Audit complete, findings | `AUDIT_COMPLETE_FINDINGS` | `AUDIT_COMPLETE_FINDINGS` | n/a |
| Audit complete, blocking findings | `AUDIT_COMPLETE_BLOCKING_FINDINGS` | `AUDIT_COMPLETE_BLOCKING_FINDINGS` | n/a |
| Audit not trustworthy | `AUDIT_INCOMPLETE` | `AUDIT_INCOMPLETE` | n/a |
| Publish succeeded | `PUBLISHED` | `READY_TO_PUBLISH` was required | `PUBLISHED` |
| Publish failed, restore succeeded | `PUBLISH_FAILED_RECOVERED` | unchanged | `PUBLISH_FAILED_RECOVERED` |
| Publish and restore failed | `PUBLISH_FAILED_UNRECOVERABLE` | unchanged | `PUBLISH_FAILED_UNRECOVERABLE` |

Legacy states retained for compatibility are documented and are not used as new terminal results. Illegal state transitions are rejected by focused tests.

## 10. Safety probes: expected and actual

| Probe | Expected | Actual |
|---|---|---|
| A1 add file | detect `added`; audit untrusted if real source changes | PASS |
| A2 modify `SKILL.md` | detect content hash change and `modified` | PASS |
| A3 delete reference/script | detect `deleted`; exit 0 cannot mask it | PASS |
| A4 rename | represent as add plus delete | PASS |
| A5 nested write | recursive snapshot and diff detect it | PASS |
| A6 command exits 7, no write | preserve command/stdout/stderr/exit; `INCOMPLETE/UNKNOWN` | PASS |
| A7 concurrent external change | baseline mismatch, real diff, no attribution or restore | PASS |
| Malicious runner returns 0 | mutations stay in disposable snapshot; real source unchanged | PASS |
| Post-validation source race | confirmation invalidated and final B10 evidence replaced with failure | PASS |

The installed-plugin dogfood runner attempted create, modify, delete, rename, nested write, and an escape marker against the absolute execution path it received. All writes landed under `skill-engineering-audit-*`; the real source digest and per-file hashes remained identical and the snapshot was deleted.

A separate external writer deliberately changed the real source while returning 0. Validation recorded `behavioral.audit=PASS` for the process exit and independently recorded `B10=FAIL`; confirmation exited 2 with `AUDIT_INCOMPLETE/UNKNOWN`, a diff of `added=['external-change.txt']` and `modified=['SKILL.md']`, and no automatic restore.

## 11. Automated validation

Final commands and results:

```text
python -m pytest -q
326 passed, 2 skipped in 9.11s

python -m pytest tests/unit -q
233 passed, 2 skipped in 0.97s

python -m pytest tests/integration -q
70 passed in 5.23s

python -m pytest tests/regression -q
6 passed in 0.40s

python -m pytest tests/e2e -q
17 passed in 3.49s

python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/skill-engineer
Skill is valid!

python C:\Users\28320\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py .
Plugin validation passed

git diff --check
exit 0
```

The two skips are the Windows scope-escape symlink cases. The current Windows token returns WinError 1314 because it lacks symbolic-link creation privilege. Equivalent path/reparse protections and all non-symlink inventory tests executed; the skip is an explicit platform limitation, not a test failure.

## 12. Local Plugin reinstall

The official cachebuster script updated the manifest from `1.0.2+codex.20260916014822` to `1.0.2+codex.20260916071634`. The runtime allowlist contains 127 files.

Before dogfooding, the repository runtime set, personal marketplace source at `C:\Users\28320\plugins\skill-engineering`, and installed cache at `C:\Users\28320\.codex\plugins\cache\personal\skill-engineering\1.0.2+codex.20260916071634` were compared by relative path and SHA-256:

```text
repo files=127 digest=194a1a582a7529db312e80de4ea5ed5cea2557d2f579eabbdaef6be8a00a298b
package files=127 digest=194a1a582a7529db312e80de4ea5ed5cea2557d2f579eabbdaef6be8a00a298b
cache files=127 digest=194a1a582a7529db312e80de4ea5ed5cea2557d2f579eabbdaef6be8a00a298b
missing=0 extra=0 changed=0
```

`codex plugin list` reported `skill-engineering@personal installed, enabled` at the expected version. The installed Skill and Plugin validators both passed.

## 13. Real Codex dogfooding

The first desktop-created projectless task `01a0a919-f202-7c31-af47-c4d7574296d6` was stopped by the host before execution because its ChatGPT access token could not refresh after an account sign-out/switch. The fallback was a separate real `codex exec` task, thread `01a0a91f-af64-7ce3-8613-c3869212e674`, authenticated through the local CLI. It completed with Codex exit 0 and imported all Engine/validator modules from the installed cache; `any_module_inside_other_root=false` for `D:\project\skill-engineering`.

The raw task prompt was:

> 必须使用已安装的 `$skill-engineering:skill-engineer` 个人插件执行真实隔离 dogfooding。期望安装版本为 `1.0.2+codex.20260916071634`，必须从安装缓存的实际 CLI/engine 运行，禁止从仓库加载。只在当前 workspace 创建合成 Skill，完成后清理。实际执行 Create、Fix、Audit Only、纯建议负向触发、恶意 runner、并发外部改源、完整 inspect → Codex decisions → validate → Codex confirm → independent publish、跨进程 JSON 往返和安装来源校验。任一必需场景失败就明确列出，不能虚报。

The task also stored these verbatim user-level trigger samples:

```text
Create: 帮我新建一个 Skill，用来把发布说明压缩成五行以内的固定格式摘要。
Fix: 修复 fix-source-skill 的缺陷：scripts/check.py 归一化时返回小写，期望是大写。
Audit Only: 请只审计 audit-clean-skill，保持文件一字不改，告诉我它是否干净、审计过程是否完整。
Advice only: 解释 inspect、validate、confirm、publish 四个阶段，以及为什么 Gate 必须等 Codex 语义确认。
```

Observed results:

- Create inspect/validate/confirm: `0/0/0`, confirmed outcome `VALIDATED`, no publication.
- Fix inspect/validate/confirm: `0/0/0`; source defect reproduced with exit 1; staged behavior and B07 both passed.
- Clean Audit Only inspect/validate/confirm: `0/0/0`, `COMPLETE/VALID`, source digest unchanged.
- Broken target Audit Only: confirmation exit 1, `COMPLETE/BLOCKING_FINDINGS`, Gate verdict `FAIL`.
- Advice-only legacy invocation: exit 2 for missing explicit intent/decision, no writes and no publication.
- Malicious snapshot runner: exit 0, six mutations confined to the snapshot, source unchanged.
- Concurrent source writer: process exit 0, confirm exit 2, `INCOMPLETE/UNKNOWN`, B10 failure and real diff.
- `publish_requested=false`: confirm produced `VALIDATED`, `publish_authorized=false`; an attempted publish was refused with exit 2.
- Explicit publication rehearsal: a separate validation with `publish_requested=true` produced `READY_TO_PUBLISH`; post-confirm tampering was refused; the clean independent publish exited 0 with matching candidate/published digest.
- Existing-target publication preserved the former target as `.backup` before replacement. The backup digest matched the old target and the new published digest matched the confirmed candidate.
- Inspection, validation, confirmation payloads, nested decisions/governance, and publication JSON passed semantic and whole-document process-boundary round trips.

The `publish_requested=false` and successful publish checks are intentionally separate. A false request must stop at `VALIDATED`; successful independent publication requires an explicit true request, a new validation, and a matching Codex confirmation.

## 14. Temporary cleanup

The real Codex task recorded 169 temporary entries before cleanup, including all synthetic Skills, candidates, five staging directories, the backup, and the temporary published target. After cleanup:

```text
dogfood_exists=False
workspace_children=[]
workspace_is_empty=True
workspace_file_count_recursive=0
temp_audit_snapshots_from_this_session=[]
temp_escape_marker_exists=False
temp_stray_files=[]
```

After the evidence above was copied into this report, the exact harness root `skill-engineering-codex-dogfood-20260916153020` was also deleted and verified absent. No repository artifact, real user Skill, or global `AGENTS.md` was changed by dogfooding. The installed cache had no `__pycache__` or `.pyc` side effects.

## 15. Git record

Implementation, tests, schemas, Skill instructions, cachebuster manifest, and authoritative architecture documentation were committed locally as:

```text
6d6703653c4452e1ae88228d884f2e8e0fe984f3
fix: enforce staged inspection and audit immutability
```

The staged diff was shown before commit: 29 project files, 1,856 insertions, and 443 deletions; `git diff --cached --check` exited 0. No push or public publication was performed.

## 16. Remaining limitations and risks

1. The two Windows symlink tests remain skipped when the process token lacks WinError 1314 privilege. This is the only automated coverage limitation.
2. The Engine minimizes runner access by passing an isolated snapshot, but it cannot stop a separately privileged process that already knows an absolute real-source path. The durable control is detection: any such change yields `INCOMPLETE/UNKNOWN`, invalidates confirmation, blocks publication, and is never silently restored.
3. `publish_requested=false` cannot be reused for a successful publish by design. A later publish requires an explicit publication request and a fresh current validation/confirmation.
4. The desktop task launcher had a stale ChatGPT refresh token. The independent CLI Codex task completed all requested dogfood scenarios using the installed Plugin cache; desktop account reauthentication is outside this repository.

All repository acceptance conditions are satisfied despite the explicitly skipped Windows privilege cases: Audit Only changes cannot remain undetected, signals precede Codex decisions, governance crosses the CLI boundary, confirmation follows validation, evidence channels are separate, audit execution and target assessment are independent, state transitions match runtime behavior, the full suite passes, the local Plugin is reinstalled, and a new real Codex session completed dogfooding.
