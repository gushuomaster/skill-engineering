# OpenSpace Cloud Skill Discovery 与 Candidate Governance 设计

## 1. 目标与边界

第一期把 OpenSpace Cloud Discovery 接入现有 `SkillSource` 体系，让用户需求可以产生本地与 Cloud 的候选 Skill，并让选中的远程候选在进入 `skill-engineering` Inspection、Evidence、Coverage 和 Gate 前始终处于 Engine 管理的隔离目录中。

本期生产链路固定为：

```text
User Query
  -> Local + OpenSpace Cloud Discovery
  -> SkillCandidate[]
  -> Deduplicate
  -> Codex Selection + Rationale
  -> Resolve to immutable revision
  -> Quarantine / Staging
  -> Existing Inspection
  -> Provider Evidence
  -> Coverage
  -> Existing Gate
  -> APPROVED / BLOCKED / INCOMPLETE
  -> Candidate Governance Receipt (only when APPROVED)
  -> STOP
```

`skill-engineering` 本期不负责安装、启用、部署、发布或自动执行远程 Skill。Gate 通过也不会写入 `%CODEX_HOME%\\skills`、正式 Plugin Cache 或其他运行时注册目录。未来独立 Installer 必须在用户明确授权后重新核验 Receipt、revision 和 digest。

## 2. 已确认的 OpenSpace Contract

当前本机 OpenSpace 源码版本为 `0.1.0`，工作树提交为 `d1e367d`。已确认：

- MCP 暴露 `execute_task`、`search_skills`、`fix_skill`、`upload_skill`。
- 不存在 `cloud_browse_skills`。
- `search_skills(query, source, limit, auto_import)` 是正式 Discovery tool。
- Cloud 查询使用 `source="cloud"`。
- `auto_import` 默认值为 `true`，生产适配必须显式使用 `auto_import=false`。
- 搜索结果至少可提供 `skill_id`、`name`、`description`、`source`、`score`，并可能带有 `visibility`、`created_by`、`origin`、`tags` 和安全信号。
- 官方 `openspace-download-skill --skill-id <id> --output-dir <dir>` 可下载到指定目录。
- 当前 Contract 没有明确声明 `skill_id` 是不可变 revision，也没有向搜索结果保证 content digest。

因此本期不猜测内部 REST endpoint，不抓取网页，不把 `skill_id` 或 `latest/main` 自动当作不可变 revision。若无法取得 OpenSpace 对不可变性的证明，候选可以被发现和暂存，但必须以 `INCOMPLETE` 停止，不能签发 `APPROVED`。

## 3. 架构组件

### 3.1 现有组件保留

- `SkillSource`：现有 discovery port。
- `LocalSkillSource`：继续扫描 `%CODEX_HOME%\\skills` 和 `%CODEX_HOME%\\plugins\\cache`。
- `search_sources()`：继续聚合并去重多个 Source。
- `find_exact()`：继续支持明确 Skill 名、Bundled Provider、确定性重放和既有 `--provider-skill` 路径。
- `PipelineOrchestrator`、Provider、Evidence、Coverage、Quality Gate 和 `ManagedCompletionReceipt`：继续作为治理权威。

### 3.2 新增组件

#### `OpenSpaceCloudSource`

实现现有 `SkillSource`，职责仅限于调用 OpenSpace MCP `search_skills` 并把结果规范化为 `SkillCandidate`。它不下载、不安装、不执行、不生成治理结论。

生产调用必须满足：

```text
source="cloud"
auto_import=false
```

MCP 结果中的评分、作者、下载量、标签、安全标记等均保存为 discovery signals，不得转换为 Evidence 或 Gate 输入。

#### `OpenSpaceMcpSearchTransport`

隔离 MCP 调用协议和结果解析。Transport 负责 timeout、认证错误、工具缺失、返回值解析和结构错误；Source 负责候选模型映射。Transport 不暴露 OpenSpace 内部 HTTP client。

#### `DiscoveryService`

以 query 调用 Local 与 Cloud Source，执行现有 `search_sources()` 和 `deduplicate_candidates()`，生成带 source 状态和 bundle digest 的 Discovery Bundle。单个 Source 失败时保留其他 Source 的结果，同时把失败记录为可见的 `INCOMPLETE` 原因。

#### `SelectionRecord`

由 Codex 产生，必须绑定 Discovery Bundle digest、选中的 candidate ID 和非空 selection rationale。它只表达“选择哪个候选进入审计”，不表达可信、合规、可安装或 Gate 通过。

#### `OpenSpaceCliResolver`

调用官方 `openspace-download-skill`，目标目录必须是 Engine 创建的 quarantine/staging 目录。解析器必须拒绝把目标目录设为 `%CODEX_HOME%\\skills`、Plugin Cache、工作区正式 Skill 目录或其他已注册目录。

#### `CandidateGovernanceReceipt`

新增外层凭证，至少绑定 `receipt_id`、具体 candidate、source ID/URI、OpenSpace skill ID、resolved revision、candidate digest、inspection ID、coverage、Gate 结果、Selection 摘要、Engine/Plugin 版本和时间。它不替代现有 `ManagedCompletionReceipt`，而是引用其摘要或 digest。第一期 Receipt 属于本机 Engine 信任边界内的凭证，不宣称具备跨机器签名认证能力；未来 Installer 若跨越该边界，必须增加独立的签名或可信 Receipt Registry。

## 4. 分阶段生产入口

新增 Discovery Mode，同时保持 Explicit Mode 兼容。

### Explicit Mode

```text
--provider-skill NAME
  -> find_exact(NAME)
  -> 既有 Provider 路径
```

此路径行为不变。

### Discovery Mode

建议将 CLI 拆成以下可重放阶段，每阶段只接受前一阶段的结构化 JSON：

```text
discover
  -> discovery-bundle.json

record-selection
  -> validate and persist Codex-authored selection-record.json

resolve
  -> quarantine/
  -> resolved-candidate.json

inspect / validate / confirm
  -> 复用现有治理流水线

finalize-candidate
  -> candidate-governance-result.json
  -> candidate-governance-receipt.json (仅 APPROVED)
```

阶段文件必须包含版本、输入 digest、输出 digest 和结构化错误，保证失败可重放、可审计，避免把搜索、选择、下载和治理隐藏在一个不可解释的命令中。

## 5. Candidate 生命周期与完整性

Candidate 经过以下逻辑状态：

```text
DISCOVERED -> SELECTED -> RESOLVED -> QUARANTINED -> INSPECTED -> GOVERNED
```

其中：

- `DISCOVERED` 只有元数据和来源 provenance。
- `SELECTED` 需要 Codex rationale。
- `RESOLVED` 必须有官方 resolver 结果和来源引用。
- `QUARANTINED` 必须有 Engine 计算的完整目录 SHA-256 digest。
- `INSPECTED` 必须连接现有 inspection ID、Evidence 和 Coverage。
- `GOVERNED` 只有现有 Gate 给出 `PASS` 且 revision/digest 绑定仍有效时才能标记 `APPROVED`。

不可变性规则：

1. `skill_id` 只作为 OpenSpace opaque source reference，不能未经证明充当 revision。
2. `latest`、`main`、`master`、网页 URL 或没有版本证明的可变标签不能作为 resolved revision。
3. 若 OpenSpace 返回明确不可变 revision，则记录其来源字段及证明材料。
4. 若不能证明不可变 revision，结果为 `INCOMPLETE`，不得生成 APPROVED Receipt。
5. finalize 前重新计算 quarantine digest；任何内容、revision、source 或 inspection 变化都会使旧结果失效。

## 6. Governance 与 Gate 规则

Discovery metadata、server score、author、popularity、quality、safety flags 和 selection rationale 都不是 Governance Evidence。

正式 Evidence 只能来自：

- 对 quarantine candidate 的现有 inventory/reference/structure 检查；
- 适用的真实行为、契约和回归检查；
- 已配置且实际执行的 Provider；
- 现有 Coverage 计算和 Quality Gate。

结果映射：

```text
PASS + FULL coverage + immutable revision proven + digest unchanged
  -> APPROVED + CandidateGovernanceReceipt

FAIL
  -> BLOCKED

INCOMPLETE / ERROR / MCP unavailable / resolver failure /
immutable proof missing / candidate changed
  -> INCOMPLETE or BLOCKED
```

任何状态都不得触发安装或正式注册。

## 7. 安全失败与错误处理

以下情况必须结构化记录并安全失败：

- OpenSpace MCP 未配置或工具不存在；
- 认证失败、超时、Cloud 不可用；
- MCP 返回 malformed JSON 或 schema 不匹配；
- 搜索返回空结果；
- 选择记录缺少 rationale 或引用错误 bundle digest；
- resolver CLI 不存在、退出失败或下载内容不完整；
- 下载内容没有 `SKILL.md`、路径逃逸或包含越界文件；
- revision 不可证明不可变；
- quarantine candidate 在治理前后 digest 不一致。

失败不能回退到未经治理的本地安装、自动执行、伪造 candidate、伪造 PASS 或复用旧 Receipt。

## 8. Quarantine 约束

所有远程内容写入项目统一产物目录下的任务专用 quarantine 子目录。产物根目录可由 `SKILL_ENGINEERING_ARTIFACT_ROOT` 显式配置；未配置时使用操作系统用户缓存下的 `skill-engineering/artifacts/<project-id>`，不得默认写入仓库：

```text
<project-artifacts>/quarantine/<run-id>/<candidate-name>/
```

不得直接写入项目父目录、`%CODEX_HOME%\\skills` 或 Plugin Cache。暂存目录由 Engine 创建并校验绝对路径、所属任务和同文件系统约束。测试产生的日志和中间 JSON 也写入统一 artifacts/diagnostics 目录，完成后只保留最终证据和必要诊断。

## 9. 测试设计

必须保留并扩展现有完整回归测试，新增至少覆盖：

1. Local-only query 返回 Candidate。
2. Cloud-only query 通过 MCP adapter 返回 Candidate，且调用参数强制 `auto_import=false`。
3. Local + Cloud 聚合、排序输入和去重。
4. 相同 repository/revision/digest 的不同来源合并且保留 provenance。
5. 相同 name 但不同内容保持独立。
6. Selection rationale 非空且绑定 bundle digest。
7. Cloud `skill_id` 无 immutable proof 时为 `INCOMPLETE`。
8. 官方 CLI 下载到 quarantine，且正式 Skill 目录没有副作用。
9. quarantine 内容 digest 改变后旧结果失效。
10. staged candidate 能进入现有 Inspection、Evidence、Coverage 和 Gate。
11. 缺陷候选产生正式 `FAIL/BLOCKED`，不异常崩溃。
12. MCP 不可用、认证失败、超时、invalid schema 和下载失败安全失败。
13. PASS、FAIL、INCOMPLETE 三种结果都验证没有安装副作用。
14. 现有 bootstrap、Provider ownership、deliverable contract、capability manifest、EvidenceCollector、Coverage、Gate、Receipt 回归保持通过。

真实 E2E 只有在当前环境有可用 OpenSpace MCP、有效认证、可调用 Cloud Search 且能证明 immutable revision 时才执行。否则报告明确为 `NOT_READY`，不得用 mock 冒充真实 E2E PASS。

## 10. 分阶段实施顺序

1. 先增加数据模型和 JSON Schema，覆盖 Discovery Bundle、Selection Record、Resolved Candidate 和 Candidate Governance Receipt。
2. 实现 MCP Transport 与 `OpenSpaceCloudSource`，用 fake transport 完成契约测试。
3. 接入 Discovery Mode CLI，同时保留 Explicit Mode。
4. 实现官方 CLI quarantine resolver 和完整性校验。
5. 把 resolved quarantine candidate 接入现有 Inspection/Governance 流程。
6. 实现 finalize Receipt 和候选变更失效检查。
7. 运行完整测试套件，再尝试真实 E2E；根据实际 OpenSpace contract 决定是否标记 `REMOTE_DISCOVERY_GOVERNANCE_READY`。

## 11. 完成判定

只有以下条件同时满足，才可声称第一期生产就绪：

- Discovery Mode 已进入生产 CLI；
- Local + OpenSpace Cloud 搜索真实接入；
- `auto_import=false` 和 quarantine 边界由代码强制；
- 远程候选不会绕过现有 Evidence、Coverage 或 Gate；
- APPROVED Receipt 绑定具体 source、immutable revision、digest 和 inspection；
- 任意失败都安全收敛为 BLOCKED/INCOMPLETE；
- 完整测试套件通过；
- 真实 E2E 具备有效 OpenSpace 认证和 immutable revision 证据，或明确报告为 `NOT_READY`。

核心不变量：

```text
Discovery finds candidates.
Codex selects candidates.
skill-engineering governs candidates.
Installer installs only explicitly authorized candidates.
```
