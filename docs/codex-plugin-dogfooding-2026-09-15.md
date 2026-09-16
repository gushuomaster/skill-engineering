# Skill Engineering 本地 Plugin 安装与 Codex Dogfooding 验收

## 结论

最终状态：`LOCAL_PLUGIN_INSTALLED_AND_CODEX_DOGFOOD_VALIDATED`

本轮在 2026-09-15 至 2026-09-16（Asia/Shanghai）完成了安全基线提交、打包前验证、个人 Marketplace 安装、五个独立 Codex 新会话黑盒场景、Dogfooding 缺陷修复、cachebuster 更新、重新安装及受影响场景复测。测试对象全部位于临时目录，没有修改真实用户 Skill、全局 `AGENTS.md` 或公开 Marketplace，也没有执行 `git push`。

## Git 安全基线

安装前基线如下：

- 仓库：`D:\project\skill-engineering`
- 分支：`master`
- 安装前 HEAD：`e8fe2312aec68da720cd73c3e1434604b13b73ea`
- 工作树包含架构纠偏成果：50 个已跟踪修改和 6 组未跟踪路径；检查后均属于本项目的架构纠偏、测试、Plugin 包装或验收文档，没有发现无关用户修改。
- 安装前 diff 规模：66 个文件，2318 行新增，965 行删除。
- `git diff --check`：通过；仅有 Git 的 LF/CRLF 工作树转换提示。

安全基线提交：

```text
3b4a8e2e34c709f9746fda57445de427551017a9
feat: restore Codex-led skill engineering workflow
```

Dogfooding 缺陷修复及本报告由第二个本地提交承载，提交标题为：

```text
fix: address plugin dogfooding findings
```

最终仓库仅比 `origin/master` 领先这两个本地提交，工作树干净；没有 push。

## 打包前与修复后验证

安全基线提交前：

```powershell
python -m pytest -q
python C:\Users\28320\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills/skill-engineer
python C:\Users\28320\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py .
git diff --check
```

结果：303 passed、2 skipped；Skill quick validation、Plugin validation 和 diff check 全部通过。两个 skip 都来自 Windows 当前账户无符号链接权限（`WinError 1314`），与产品逻辑无关。

Dogfooding 修复后增加了两个回归检查：Codex host 的 `defaultPrompt` 长度上限，以及 Audit/Advice 模式禁止目标目录出现任何瞬时写入。最终结果：

```text
305 passed, 2 skipped
Skill quick validation: PASS
Plugin validation: PASS
git diff --check: PASS
```

## 本地打包与安装

使用 `plugin-creator` 的个人 Marketplace 流程。Marketplace 文件及最终源目录：

```text
C:\Users\28320\.agents\plugins\marketplace.json
C:\Users\28320\plugins\skill-engineering
```

Marketplace 名称为 `personal`，entry 的 source 为 `./plugins/skill-engineering`，policy 为 `installation=AVAILABLE`、`authentication=ON_INSTALL`，category 为 `Productivity`。

打包范围由 Git 跟踪文件确定：

```powershell
git ls-files -- .codex-plugin config engine schemas scripts skills tests validators pyproject.toml
```

上述 120 个文件被逐字节同步到 `C:\Users\28320\plugins\skill-engineering`。未打包 `docs`、项目 `AGENTS.md`、缓存、临时文件、私钥或开发机绝对路径。

验证、cachebuster 和安装命令：

```powershell
python C:\Users\28320\.codex\skills\.system\plugin-creator\scripts\validate_plugin.py C:\Users\28320\plugins\skill-engineering
python C:\Users\28320\.codex\skills\.system\plugin-creator\scripts\read_marketplace_name.py
python C:\Users\28320\.codex\skills\.system\plugin-creator\scripts\update_plugin_cachebuster.py D:\project\skill-engineering
codex plugin add skill-engineering@personal
codex plugin list
```

第一次安装前，包曾被放到 `C:\Users\28320\.agents\plugins\plugins\skill-engineering`；Codex 按个人 Marketplace 规则把 source 解析到 `C:\Users\28320\plugins\skill-engineering`，因此安装真实失败。该新建错误包已安全移除，随后按官方默认布局重新打包和安装，没有修改现有用户文件。

最终安装信息：

- Plugin ID：`skill-engineering@personal`
- 状态：`installed, enabled`
- 基础版本：`1.0.2`
- cachebuster：`codex.20260916014822`
- 完整版本：`1.0.2+codex.20260916014822`
- 安装路径：`C:\Users\28320\.codex\plugins\cache\personal\skill-engineering\1.0.2+codex.20260916014822`
- 最终安装时间：2026-09-16 09:57:53 CST（2026-09-16 01:57:53 UTC）
- Plugin 聚合 digest：`f913c848473277afa03d2dd111f2eeb604a188bc56e479279eb7f9ba665a3ece`
- `.codex-plugin/plugin.json` SHA-256：`bf23e846a5332a3b6b45cdeea3ea73a0409c320941ea0d8b896c6787d70f999a`

最终包目录与安装 cache 均为 120 个文件，路径集合、文件内容和聚合 digest 完全一致；包中的每个文件也与仓库对应文件逐字节一致。

## Dogfooding 方法

所有场景均通过 `codex exec` 启动独立新会话，从原始自然语言请求开始。每个会话在独立临时工作目录中运行，使用 `workspace-write` sandbox，并由新 Codex 自己识别模式、读取已安装的 `skill-engineer`、生成决策、创作或审计候选、运行 Engine、评估 Gate 和决定是否发布。父会话没有用直接调用 Python Engine 代替这些黑盒会话。

临时测试根目录：

```text
C:\Users\28320\AppData\Local\Temp\skill-engineering-codex-dogfood-g0i09iv3
```

由于已安装的无关 `superpowers@openai-api-curated` Plugin 在第一次 D1 尝试中抢先要求重复确认，正式场景对它使用会话级配置 `plugins."superpowers@openai-api-curated".enabled=false`。这只隔离无关 Plugin，不关闭或绕过 `skill-engineering@personal`。新会话日志均显示从个人安装 cache 读取 `skill-engineer`，证明 Plugin 可发现并真实触发。

## D1：Create

原始提示：

> 请使用 Skill Engineering 能力创建一个用于检查 Markdown 文件标题层级的测试 Skill。它只用于临时验收，必须包含完整 SKILL.md、必要 reference、一个可执行检查脚本以及真实行为测试。先在候选目录完成验证，不要发布到任何真实 Skills 目录。

- 触发：是，新会话自动读取已安装 `skill-engineer`。
- Intent / RCA / DecisionRecord：`CREATE`；没有既有缺陷需要修复，Codex 将需求视为新能力不变量，选择完整 Skill、reference、可执行实现和行为测试作为机制，并自行创建候选。
- 产物：`markdown-heading-check`，包含 `SKILL.md`、`references/heading-rules.md`、`scripts/check_headings.py` 和 `tests/test_behavior.py`。
- 行为命令：`python tests/test_behavior.py`，exit 0，3 个测试通过。
- Codex 在首轮行为检查中发现 Setext 标题解析缺陷，修正实现后重新测试通过。
- SemanticConfirmation：绑定 digest `637024773903d1c845af8aeaf203170c0b528374e4fb35bd134d8ac81970972f`，确认标题层级、围栏代码、Setext、JSON 和 UTF-8 行为满足请求。
- Gate：`PASS`；9 项必需结构检查、引用完整性及行为检查通过。
- 发布：未请求；`publish_authorized=false`。
- 变化：只创建临时候选和 Gate staging；没有真实 Skills 目录变化，没有 backup。

## D2：Fix

原始提示：

> 请使用 Skill Engineering 能力诊断并修复这个临时 Skill。先复现问题、完成 RCA 和机制选择，在隔离候选中实施最小修复，运行行为及回归测试。验证通过后只发布到该临时测试目标，不得处理任何真实用户 Skill。

- 触发：是，新会话自动读取已安装 `skill-engineer`。
- Intent：`FIX`。
- RCA：临时源的 `scripts/check.py` 使用 `lower()`，与“trim 后 uppercase”的契约相反；同时存在重复 MUST 规则和过时描述。
- DecisionRecord：分类为 implementation defect；选择 implementation fix、regression test、合并重复不变量和更新权威 reference；没有新增案例特化 Prompt Rule，也没有修改 `AGENTS.md`。
- 复现：输入 `Example` 时得到 `actual=example`，exit 1。
- 行为命令：`python scripts/check.py --value Example --expect EXAMPLE`，修复后 exit 0。
- 回归命令：`python scripts/check.py --value "  eXaMpLe  " --expect EXAMPLE`，exit 0。
- 首次 Gate：行为、回归和治理检查均通过，但因尚无精确候选 digest 的 SemanticConfirmation，被 `B12` 正确阻止。
- SemanticConfirmation：绑定 digest `19496b40b738ee7a0a68f02e8cd5b6fb2687197af25c5bad88e9667da6b06d2b`，确认 `strip().upper()` 与契约及两类测试一致。
- 最终 Gate：`PASS / READY_TO_PUBLISH`，`publish_authorized=true`。
- 发布：原始提示明确授权仅发布到临时目标，因此执行原子替换；状态 `PUBLISHED`。
- 源 digest：`29feeea635cc3b397fc0d1bf09da859bcb2f3ca2fc7d4b39caad49f9a7d083c7`。
- 发布后 digest：`19496b40b738ee7a0a68f02e8cd5b6fb2687197af25c5bad88e9667da6b06d2b`。
- diff：修改 `SKILL.md`、`references/behavior.md`、`scripts/check.py`；无新增或删除。
- backup：`d2-fix\broken-skill.backup`；没有恢复失败。
- 变化边界：只修改临时测试目标，未接触真实用户 Skill。

## D3：Audit Only

原始提示：

> 请使用 Skill Engineering 能力只读审计这个临时 Skill，检查规则膨胀、重复、冲突、作用域和验证覆盖。只输出证据、问题和建议，禁止创建发布候选，禁止修改任何文件。

- 触发：是。
- Intent：`AUDIT_ONLY`。
- RCA / DecisionRecord：Codex 将问题分类为 contract enforcement gap，识别重复指令和缺少回归覆盖；选择 regression test、merge invariant 和 reference/instruction 作为建议机制。历史增长因临时目录无 Git 历史而标记为证据限制。
- 治理：detector 只给出 `exact-1` 重复信号；Codex 决定 `MERGE`，并把 history 缺失保留为 `KEEP` 限制，signals 与治理建议未混同。
- 只读行为/回归：通过 `python -B` 在不写缓存的条件下覆盖普通文本、首尾空白、Unicode、全空白及错误预期；各 case 的实际 exit 与预期 exit 一致，runner 为 PASS。
- SemanticConfirmation：绑定审计前 source digest，确认精确源的行为可运行，同时保留重复规则和覆盖不足结论。
- Gate：`UNCHANGED_BLOCKED`；唯一阻塞项是重复规则，`publish_authorized=false`。
- 发布：未请求、未执行。
- 变化：workspace diff 为空；审计前后 3 个文件 SHA-256 一致；没有候选、staging、backup 或缓存。

## D4：负向触发

原始提示：

> 解释 Python 列表和元组的区别，不要修改任何文件。

- Skill Engineering 触发：否。
- Intent / RCA / DecisionRecord / SemanticConfirmation：不适用。
- 行为或回归命令：未执行。
- Gate / staging / publish：未执行。
- 变化：无文件创建或修改。
- 结果：新会话直接解释 list 与 tuple 的可变性、语法、用途、哈希能力及单元素 tuple 语法。

## D5：仅分析、不授权修改

原始提示：

> 请分析这个临时 Skill 可能有哪些改进方向，但不要修改文件。

- 触发：是，按边界请求进入只读审计。
- Intent / DecisionRecord：`AUDIT_ONLY`，`authorized_to_modify=false`，无发布请求；核心行为无既有 defect，改进项作为建议而非自动 Fix。
- 只读行为命令：使用显式解释器、`PYTHONDONTWRITEBYTECODE=1` 和 `python -B` 验证 `Example`、首尾空白、Unicode 及中英文混合输入，均 exit 0。
- SemanticConfirmation：绑定精确 source digest，确认 trim + uppercase 核心行为符合临时夹具契约，同时指出说明和验证覆盖仍可改善。
- Gate：`PASS / UNCHANGED_VALIDATED`；9 项必需检查通过，只有临时目录缺少 Git 历史的非阻塞警告。
- 发布：未请求；`publish_authorized=false`，`publication_ready=false`。
- 变化：审计前后 `SKILL.md`、`references/behavior.md`、`scripts/check.py` 的 SHA-256 完全一致；没有 `__pycache__`、`.pyc`、候选、backup 或发布文件。

## 验收矩阵

| 场景 | 应触发 Plugin | 应修改 | 应发布 | 实际结果 |
| --- | ---: | ---: | ---: | --- |
| Create | 是 | 仅候选 | 否 | 通过；候选完整、行为测试和 Gate PASS，未发布 |
| Fix | 是 | 是 | 仅临时目标 | 通过；先复现并修复，精确 digest 确认后原子发布到临时目标 |
| Audit Only | 是 | 否 | 否 | 通过；UNCHANGED_BLOCKED，源哈希不变，无候选或 backup |
| 普通 Python 问题 | 否 | 否 | 否 | 通过；未触发 Plugin、Gate 或文件操作 |
| 仅分析不修改 | 可触发审计 | 否 | 否 | 通过；按 Audit Only 运行，PASS / UNCHANGED_VALIDATED，全程无目标写入 |

## Dogfooding 发现及修复

### 1. Plugin defaultPrompt 超出 Codex host 上限

首次新会话发出 `defaultPrompt` 超过 128 字符并被忽略的警告。先添加失败测试 `test_plugin_default_prompt_respects_codex_host_limit`，确认修复前失败，再缩短 prompt；同时让版本测试接受官方 `+codex.<timestamp>` cachebuster metadata。相关测试和全量测试通过后更新 cachebuster 并重新安装。

### 2. Audit/Advice 允许瞬时写入

D5 首轮虽在结束时恢复了原 digest，但过程中执行 `py_compile`，生成后再删除 `__pycache__`。这违反“不要修改文件”的全过程授权边界。先添加失败测试 `test_audit_guidance_forbids_transient_target_writes`，再把稳定不变量写入 `skill-engineer`：Audit Only 和 advice 必须在整个运行期保持目标树逐字节不变；Python 检查使用 `python -B` 与 `PYTHONDONTWRITEBYTECODE=1`；禁止 `py_compile`、cache、coverage 或目标内临时产物；无法只读执行的检查应报告证据限制。

修复后更新 cachebuster 至 `codex.20260916014822` 并重新安装。第一次 D5 复测已遵守零写入，但最终响应阶段遇到连续服务端限流/stream disconnect，属于外部基础设施失败；目标哈希仍不变。第二个全新 D5 会话完整通过，确认目标全程无生成物。

### 3. 安装布局纠正

首次包位置与个人 Marketplace 的 source 解析规则不一致，安装真实失败。纠正为 `C:\Users\28320\plugins\skill-engineering` 后验证及安装成功。该问题属于本地安装布局，不是 Engine 或 Gate 功能缺陷。

## 外部噪声与限制

- 新会话启动期间，远端 curated Plugin 同步出现 401/403、Git 不在 trusted installation directories 等警告；本地 curated snapshot 和个人 Plugin cache 可用，未影响测试。
- 两条 icon `..` 路径警告来自其他已安装 Plugin；`skill-engineering` manifest 没有 icon 字段。
- 个别会话发生临时 capacity limit / stream reconnect；完成的 D1-D5 场景均有终态日志，D5 对基础设施失败另起新会话重试。
- 临时测试目录不是 Git 仓库，因此 rule history 检查只能报告证据限制。
- Windows 无符号链接权限导致全量测试中的 2 个预期 skip。

这些限制均未掩盖功能失败，也没有被包装成 Dogfooding 成功依据。

## 证据与清理状态

主要日志：

```text
d1-events.jsonl / d1-final.txt
d2-events.jsonl / d2-final.txt
d3-events.jsonl / d3-final.txt
d4-events.jsonl / d4-final.txt
d5-events.jsonl / d5-final.txt
d5-retry-events.jsonl
d5-retry2-events.jsonl / d5-retry2-final.txt
```

这些文件均位于临时测试根目录。为保留本轮可复核的完整自然语言会话、命令、Gate 输出和修复前后证据，最终验收时暂未删除该临时目录。它不在仓库和任何真实 Skills 目录中，可在验收证据不再需要后整体清理。

未执行步骤：`git push`、公开 Plugin 发布、真实用户 Skill 修改、全局 `AGENTS.md` 修改。不存在需要人工接力的安装或 Dogfooding 阻塞。
