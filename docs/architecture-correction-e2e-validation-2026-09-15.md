# 架构纠偏最终端到端验收报告

## 验收结论

```text
ARCHITECTURE_CORRECTED_AND_END_TO_END_VALIDATED
```

本轮用独立的测试 Skill、真实子进程检查、真实临时文件系统替换和受控失败注入完成 Create、Modify、Audit Only、Gate 与显式发布链路。所有 required 场景均符合预期；未发布、竞争失败、摘要失效、检查失败和恢复场景都没有覆盖测试源以外的任何 Skill。

## 验收范围与 Git 基线

- 仓库：`D:\project\skill-engineering`
- 分支：`master`
- 基线提交：`e8fe2312aec68da720cd73c3e1434604b13b73ea`
- 本轮开始时工作树已包含上一轮架构纠偏：50 个 tracked 文件有修改，另有 4 个 untracked 路径。它们均被保留，没有 reset、checkout、commit 或覆盖。
- 本轮没有修改用户级或系统级 `AGENTS.md`，没有执行 Plugin 安装、市场发布、`git commit` 或 `git push`。
- 所有可写验收对象都由 pytest `tmp_path` 创建在系统测试临时目录；仓库下的 fixtures 只作为只读输入。没有发布、覆盖或删除真实用户 Skill。

## 真实实现入口与调用关系

| 能力 | 实现位置 | 实际调用关系 |
|---|---|---|
| `DecisionRecord` | `engine/models.py:24` | Codex/CLI 构造；`PipelineOrchestrator.run()` 先经分类与机制完整性校验，再交给 Gate。 |
| `SemanticConfirmation` | `engine/models.py:27`、`schemas/semantic-confirmation.schema.json` | Codex 提供 rationale 和 artifact digest；`run()` 校验 schema、`confirmed_by=CODEX` 与当前 manifest digest。 |
| CLI `--publish` | `scripts/skill_engineering.py:46` | 映射为 `EngineeringRequest.publish_requested`；`run()` 返回后才调用独立的 `publish(outcome)`。 |
| CLI behavior/regression | `scripts/skill_engineering.py:44-45,76` | JSON 字符串数组进入 `_command_runner()`；以 staging artifact 为 cwd 真实执行并记录 command、exit code、stdout、stderr。 |
| `PipelineOrchestrator.run()` | `engine/orchestrator.py:117` | 显式输入校验 → source baseline → staging → manifest/diff → structure/reference/behavior/regression → signals/治理证据 → semantic digest 校验 → Gate；函数自身不移动正式目标。 |
| artifact digest | `engine/inventory.py:48,73` | `digest_tree()` 对相对路径、大小和内容做 SHA-256；`build_artifact_manifest()` 将结果写入 `content_digest`。 |
| source baseline digest | `engine/workspace.py::WorkspaceSession.for_existing()` | 会话创建时固定 `source_digest`；staging 前和 publish 前分别复核。 |
| staging | `engine/workspace.py:124` | `stage_candidate()` 将 Codex 完整候选复制到目标文件系统上的 `.skill-engineering-*` 隔离目录，保留候选名。 |
| confirmed digest binding | `engine/workspace.py:179` | Gate PASS 后把当前 staging artifact 与确认摘要绑定；任何发布前变化触发 `CandidateChangedError(B12)`。 |
| `publish(outcome)` | `engine/orchestrator.py:225` | 只接受带 publication-ready session 的 outcome，然后调用 `publish_atomic()`。 |
| backup / atomic replace | `engine/workspace.py:222,246,248` | 先复核 Gate、确认摘要、source baseline 和同文件系统；已有目标用 `os.replace()` 移到 `.backup`，候选再用 `os.replace()` 替换目标。 |
| recovery | `engine/workspace.py:257-286` | 发布后 loadability/digest 失败或 move 异常时删除不完整目标并将 backup 原子移回；异常携带状态、摘要、diff 和 backup 路径。 |

```text
CLI / Codex inputs
  -> EngineeringRequest(intent, decision, candidate, confirmation,
                        behavior runner, regression runner, publish_requested)
  -> PipelineOrchestrator.run()
  -> WorkspaceSession.stage_candidate()
  -> CheckResult Evidence + SemanticConfirmation digest match
  -> Quality Gate
  -> EngineeringOutcome
  -> [only when explicitly requested] publish(outcome)
  -> publish_atomic(): digest preflight -> backup -> replace -> verify -> record/recover
```

## 临时测试对象

| 对象 | 仓库 fixture | 固定内容摘要 |
|---|---|---|
| Modify 源 Skill | `tests/e2e/fixtures/source-skill/` | `b73d534d5785d1afbdb314ce6f18cf4aa5dba4bb8783ea6742647d842d365efa` |
| Modify 候选 | `tests/e2e/fixtures/modify-candidate/source-skill/` | `e8b54616db855d6e1be7e2b3615b45cda7b16eea484d1519c026d6ee2c2b5da2` |
| Create 候选 | `tests/e2e/fixtures/create-candidate/candidate-skill/` | `97f862f90e73ed3ae41c02a7cf0cc5e13f9c782b5ddae8f030ae498ca8f3ebc8` |

Modify 候选把真实执行行为从 trim + lowercase 改为 trim + uppercase；Create 候选包含完整 `SKILL.md`、被引用的 `references/behavior.md` 和被工作流引用并真实执行的 `scripts/check.py`。目录名与 metadata 分别保持 `source-skill` 和 `candidate-skill`，没有生成 `staged-skill`。

## Codex 决策记录摘要

| 流程 | Intent | Primary issue | Regression | Selected mechanism | 语义主体 |
|---|---|---|---|---|---|
| M1-M7 | `MODIFY` | `CAPABILITY_INVARIANT_CHANGE` | `REQUIRED` | `implementation_fix` | `decided_by=CODEX`；其余已知机制逐项 rejected |
| C1-C2 | `CREATE` | `CAPABILITY_INVARIANT_CHANGE` | `REQUIRED` | `reference_or_instruction` | `decided_by=CODEX`；其余已知机制逐项 rejected |
| Audit Only | `AUDIT_ONLY` | `NO_DEFECT` | `NOT_APPLICABLE` | 无 selected；全部已知机制明确 rejected | `decided_by=CODEX` |

每次成功 Gate 都使用与当次候选 digest 完全一致、`confirmed_by=CODEX` 且 rationale 非空的 `SemanticConfirmation`。Provider PASS 场景故意不提供该确认，结果仍由 B12 阻止。

## 实际 behavior 与 regression 证据

本机 `sys.executable` 为 `C:\Users\28320\AppData\Local\Python\pythoncore-3.14-64\python.exe`。命令由生产 CLI runner 执行，cwd 是 Engine staging 内的候选目录。

| 用途 | 实际命令 | Exit | stdout 摘要 | stderr 摘要 |
|---|---|---:|---|---|
| Modify behavior | `...python.exe scripts/check.py --value " Example " --expect EXAMPLE` | 0 | `actual=EXAMPLE` | 空 |
| Modify regression | `...python.exe scripts/check.py --value " stable " --expect STABLE` | 0 | `actual=STABLE` | 空 |
| Create behavior | `...python.exe scripts/check.py --topic release` | 0 | `Topic: release / Scope / Validation / Rollback` | 空 |
| Create regression | `...python.exe scripts/check.py --topic upgrade` | 0 | `Topic: upgrade / Scope / Validation / Rollback` | 空 |
| M5 failing behavior | `...python.exe scripts/check.py --value Example --expect WRONG` | 1 | `actual=EXAMPLE` | 空 |
| M6 未提供 regression | 未提供 | `NOT_EXECUTED` | 不适用 | `Required regression command was not supplied` |
| M6 工具不存在 | `missing-skill-engineering-e2e-tool` | `NOT_STARTED` / `ERROR` | 空 | `FileNotFoundError` 与实际 OS 错误 |
| M6 命令无法启动 | 将 staging candidate 的 `scripts/` 目录作为 executable | `NOT_STARTED` / `ERROR` | 空 | Windows `PermissionError` 与实际 OS 错误 |

`CheckResult.evidence` 和 CLI JSON 现在分别保留 `command=...`、`exit_code=...`、`stdout=...`、`stderr=...`。M5/M6 的 required 结果均进入 blocking findings，没有降级为 warning 或 PASS。

## 场景结果与发布证据

### M1：Modify 无显式发布

- 输入：独立 source/candidate，真实 behavior + regression，匹配候选的 SemanticConfirmation，`publish_requested=False`。
- Gate：`PASS`，`semantic_confirmed=True`，`publish_authorized=False`，没有调用 `publish()`。
- 结果：source digest 保持 `b73d...65efa`；staging digest 为 `e8b5...b5da2`；diff 精确列出 `SKILL.md`、`references/behavior.md`、`scripts/check.py` 三个 modified 文件；无 backup、无正式覆盖。

### M2：Modify 显式发布

- 输入与 M1 相同，但 `publish_requested=True`，并在 Gate PASS 后实际调用 `publish(outcome)`。
- 发布前 source digest：`b73d534d5785d1afbdb314ce6f18cf4aa5dba4bb8783ea6742647d842d365efa`。
- candidate digest：`e8b54616db855d6e1be7e2b3615b45cda7b16eea484d1519c026d6ee2c2b5da2`。
- 发布后 digest：`e8b54616db855d6e1be7e2b3615b45cda7b16eea484d1519c026d6ee2c2b5da2`。
- 记录：`status=PUBLISHED`，backup 为临时发布父目录下 `source-skill.backup`，其 digest 等于发布前 source；record diff 与 Gate 前 diff 一致。哨兵文件 `unrelated.txt` 内容保持不变。

### M3：源摘要竞争保护

- `run()` PASS 后在临时 source 新增 `external-change.txt`，使当前 source digest 与 session baseline 不同。
- 实际调用 `publish()` 后抛出 `SourceChangedError(B10)`；没有创建 backup，外部内容保持，staging candidate 和 Gate evidence 仍存在，未产生发布成功记录。

### M4：候选摘要失效

- `run()` PASS 并确认原 staging digest 后，向 staging script 加入一次可执行但会改变 digest 的内容。
- 旧 outcome 调用 `publish()` 时在任何 move 前抛出 `CandidateChangedError(B12)`，source 未改变。
- 用变化后的 candidate 重新生成 SemanticConfirmation 并重新运行 Gate 后，新的显式 publish 成功；旧确认没有被沿用。

### M5：行为测试失败

- behavior 真实退出 1，证据保留完整命令、`exit_code=1`、`stdout=actual=EXAMPLE`、空 stderr。
- required `behavioral.modify=FAIL` 映射为 B04；Gate `FAIL`、`publish_authorized=False`，即使 `publish_requested=True` 也没有生成可发布 outcome。source digest 不变，无 backup。

### M6：回归未执行与启动失败

- 未提供 required runner：生成显式 `B07=NOT_EXECUTED`，Gate FAIL。
- 工具不存在及目录不可执行：生产 `_command_runner()` 捕获真实 `OSError`，生成 `B07=ERROR`、`exit_code=NOT_STARTED` 与 stderr，Gate FAIL。
- 三个分支都没有 backup、正式覆盖或伪造 PASS。

### M7：发布失败恢复

- 在临时目录内只对第二次 `os.replace()`（候选替换目标）注入 `OSError("controlled E2E failure injection")`。
- 第一次 replace 已建立 backup；恢复路径实际执行第三次 replace 将 backup 移回 source。
- 异常记录：`status=RECOVERED`、`restored_after_failure=True`、source-before digest `b73d...65efa`、candidate digest `e8b5...b5da2`、最终 published/source digest `b73d...65efa`，并保留 backup 路径与 workspace diff。
- 恢复后 backup 路径本身不存在，因为它已被原子移回 source；staging candidate 仍可审查。最终 source 是完整旧版本，没有混合状态，也没有成功发布标记。

### C1：Create 无显式发布

- 完整候选通过 structure、reference、真实 behavior、真实 regression 和 digest-bound SemanticConfirmation。
- Gate `PASS`、`publish_authorized=False`；候选留在 staging，正式 `candidate-skill` 不存在，无 backup，也不存在 `staged-skill`。

### C2：Create 显式发布

- 通过真实 CLI `--publish` 执行。发布前目标不存在；Gate PASS 后 CLI 实际调用 `publish(outcome)`。
- 发布后 `candidate-skill` digest 为 `97f862f90e73ed3ae41c02a7cf0cc5e13f9c782b5ddae8f030ae498ca8f3ebc8`，与确认候选一致。
- CLI JSON 含 structure、behavior、regression evidence 及 `publication_result(status=PUBLISHED, backup_path=null, candidate_digest=published_digest)`；没有错误重命名。

### Audit Only 回归

- API 和真实 CLI `--publish` 两条路径都已验证。
- 无 staging、无 candidate、无 backup、无 atomic replace，source digest 不变；Gate PASS 仍为 `publish_authorized=False`。
- 对 API outcome 调用 `publish()` 被拒；CLI 带 `--publish` 返回退出码 1 和 `no publication-ready workspace`，signals/evidence 仍正常生成。

## Codex 主体地位

自动化用例验证 Engine 不会补全以下输入：

- `Intent` 与 `DecisionRecord` 是 CLI required 参数；非 `CODEX` 的 decision 被契约拒绝。
- 缺少 RCA 的 defect flow、缺少问题分类维度或不完整的 mechanism selected/rejected 集合被明确拒绝。
- Create/Modify/Fix 缺少完整独立 candidate 被拒绝；Engine 不生成模板或 `staged-skill`。
- actionable rule signals 缺少 Codex `KEEP / MERGE / MOVE / DELETE` 决策时，`governance.coverage=FAIL` 并阻止候选。检测器结果只以 optional `rule-signal.*` evidence 出现，不带 action 或 target。
- 缺少当前 digest 的 Codex SemanticConfirmation 时，即使 Provider 返回可用证据，Gate 仍以 B12 FAIL。
- publication request 只来自 `publish_requested` / CLI `--publish`；Engine 不从关键词或 Provider 输出推断。

## E2E 发现与生产修复

本轮先增加失败复现，再实施最小修复：

1. **M4 旧确认可发布已变化 candidate**：修复前聚焦测试实际失败为 `DID NOT RAISE`。根因是 publish 只比较发布前后同一份 candidate，没有保留 Gate 确认摘要。修复为 session digest binding，并在文件移动前校验；新增 `CandidateChangedError(B12)`。
2. **无 `--publish` 仍得到 `publish_authorized=True`**：根因是 Gate 将 modification authorization 与 publication request 混用。增加默认 false 的 `publish_requested`，CLI 只由 `--publish` 设置；M1/C1 现为 PASS 但不可发布。
3. **普通 required `FAIL` 被降为 warning**：E2E 首轮 16 项中 M5 和治理 coverage 两项出现 `DID NOT RAISE`。根因是 Gate 只无条件阻塞 required 的 `ERROR/SKIP/NOT_EXECUTED`，required `FAIL` 仍依赖来源映射。修复为普通 required FAIL 统一 B04 阻塞，同时保留 `rule-bloat`/`rule-signal` advisory 例外。

为满足可审计发布证据，`EngineeringOutcome`/`PipelineBlockedError` 公开 evidence，`PublishResult` 增加 source-before/candidate/published digest、diff 和 status，`PublishRecoveryError` 携带恢复 result，CLI JSON 增加 `evidence` 与 `publication_result`。现有 CLI 字段保留；直接 API 调用者若要发布，需要显式设置 `publish_requested=True`，低层 `publish_atomic()` 调用者需要先绑定确认摘要。这是有意强化的公开契约。

## 新增或修改的验收文件

- `tests/e2e/fixtures/source-skill/**`
- `tests/e2e/fixtures/modify-candidate/source-skill/**`
- `tests/e2e/fixtures/create-candidate/candidate-skill/**`
- `tests/e2e/test_architecture_correction_flows.py`
- `tests/e2e/test_publish_digest_binding.py`
- `tests/unit/test_quality_gate.py`
- `tests/integration/test_atomic_publish.py`
- `tests/integration/test_cli.py`
- `tests/integration/test_end_to_end_flows.py`
- `tests/integration/test_minimal_pipeline.py`
- `tests/regression/test_governance_invariants.py`

生产修复位于 `engine/orchestrator.py`、`engine/quality_gate.py`、`engine/workspace.py` 和 `scripts/skill_engineering.py`；当前契约说明同步更新于 `skills/skill-engineer/references/pipeline.md`、`skills/skill-engineer/references/quality-gate.md` 与架构纠偏文档。

## 实际验证命令

| 命令 | Exit | 实际结果 |
|---|---:|---|
| `python -m pytest -q` | 0 | `303 passed, 2 skipped in 5.28s` |
| `python -m pytest tests/unit -v` | 0 | `227 passed, 2 skipped in 0.82s` |
| `python -m pytest tests/integration -v` | 0 | `53 passed in 1.72s` |
| `python -m pytest tests/regression -v` | 0 | `6 passed in 0.24s` |
| `python -m pytest tests/e2e -v` | 0 | `17 passed in 3.21s` |
| `python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/skill-engineer` | 0 | `Skill is valid!` |
| `python C:\Users\28320\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py .` | 0 | `Plugin validation passed: D:\project\skill-engineering` |
| `python -c <临时 DecisionRecord 驱动的当前 Skill Quality Gate>` | 0 | digest `f4db3042...b346eaa`；`PASS / UNCHANGED_VALIDATED`；9 required、0 missing、0 blocking；`semantic_confirmed=true`、`publish_authorized=false` |
| `git diff --check` | 0 | 最终报告写入后执行；无 whitespace error。 |

仓库内没有 `scripts/quick_validate.py` 或 `scripts/validate_plugin.py`，因此按实际工具位置调用系统 `skill-creator` 和 `plugin-creator` 校验脚本。

最终只读 Quality Gate 使用临时目录中的完整 `AUDIT_ONLY` DecisionRecord 和当前入口 Skill digest `f4db3042d0ffe86b33a22327f75176fc9eaed06238fb312b5cec75136b346eaa`。临时 decision 文件由 `TemporaryDirectory` 自动清理；Gate 共收集 16 条有效 evidence，唯一 warning 是缺少 Git 历史输入的 advisory `rule-signal.history`，没有 blocking finding。

## Windows skip 与剩余限制

- 两个 skip 均来自 `tests/unit/test_inventory.py:81,95`：当前 Windows 进程缺少创建符号链接所需的 `WinError 1314` 权限。测试明确报告 `symlinks unavailable`，没有改权限，也没有扩大范围。
- symlink 逃逸保护在具备 symlink 权限的环境才会执行对应动态创建用例；现有代码仍拒绝 symlink 和 reparse point。
- 原子发布要求 staging 与目标在同一文件系统；跨文件系统路径按设计拒绝。
- M7 使用受控 monkeypatch 只让临时目录中的第二次 `os.replace()` 失败；真实备份、恢复与 digest 验证仍由生产文件系统代码完成。
- 测试临时对象由 pytest `tmp_path` 管理；仓库与用户 Skill 目录没有残留测试发布对象。

## 最终验收矩阵

| 场景 | Gate | Publish requested | Source changed | Backup | 预期 | 实际 |
|---|---|---:|---:|---:|---|---|
| M1 无显式发布 | PASS | 否 | 否 | 否 | 阻止覆盖 | PASS；仅 staging，`publish_authorized=false` |
| M2 显式发布 | PASS | 是 | 是 | 是 | 原子发布 | PASS；摘要一致，原始版本可由 backup 验证 |
| M3 源摘要竞争 | PASS 后 publish BLOCK | 是 | 否（外部改动保留） | 否 | 拒绝发布 | `SourceChangedError(B10)`，无覆盖 |
| M4 候选摘要失效 | PASS 后 publish BLOCK | 是 | 否 | 否 | 拒绝旧确认 | `CandidateChangedError(B12)`；重新确认后才可继续 |
| M5 行为测试失败 | FAIL | 是 | 否 | 否 | 拒绝发布 | required FAIL/B04，命令四项证据齐全 |
| M6 验证未执行 | FAIL | 是 | 否 | 否 | 拒绝发布 | `NOT_EXECUTED`/`ERROR`，无伪 PASS |
| M7 发布失败恢复 | PASS 后 RECOVERED | 是 | 否 | 是 | 完整恢复 | `status=RECOVERED`，最终 digest 等于旧版本 |
| C1 Create 不发布 | PASS | 否 | 否 | 否 | 仅保留候选 | 完整候选仅在 staging，`publish_authorized=false` |
| C2 Create 显式发布 | PASS | 是 | 是 | 否 | 创建完整 Skill | CLI 发布成功，名称与 digest 一致 |
| Audit Only | PASS | 否；另测强制请求 | 否 | 否 | 严格只读 | API/CLI 均无法进入 atomic replace |
