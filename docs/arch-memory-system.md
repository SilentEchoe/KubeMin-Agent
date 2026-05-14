# 多租户记忆系统架构文档

## 设计理念

KubeMin-Agent 的记忆系统采用 Hermes Agent 的三层思路：短小高信号的内置记忆、大容量会话搜索、可插拔外部 MemoryProvider。系统从第一版开始面向多租户、多用户，并进一步支持团队作用域。任何记忆读写都必须显式绑定运行时 scope，避免不同用户、团队、租户、Agent 之间发生上下文泄漏。

核心原则：

- `USER.md` 保存用户偏好和沟通习惯，按 `tenant_id + user_id` 共享。
- `MEMORY.md` 保存 Agent 专业长期记忆，按 `tenant_id + user_id + agent_name` 分域。
- `TEAM.md` 保存团队偏好、规范和项目约定，按 `tenant_id + team_id` 共享。
- 团队 `MEMORY.md` 保存某个 Agent 面向该团队的专业长期记忆，按 `tenant_id + team_id + agent_name` 分域。
- 会话历史进入 SQLite FTS5 索引，按需检索，不常驻 prompt。
- `team_id` 只从 `InboundMessage.metadata["team_id"]` 显式读取。没有 `team_id` 时视为个人上下文，不加载也不写入团队记忆。
- Dream consolidation V1 只生成可审批草案，不自动落盘。
- 外部 provider 通过接口扩展，V1 只允许一个 active provider，默认 `none`。
- 记忆是辅助上下文，不是实时状态。涉及集群、工作流、生产操作前必须重新调用工具验证。

## 架构

```mermaid
flowchart TB
  MSG["InboundMessage"] --> SCOPE["MemoryScope tenant/user/team/agent"]
  SCOPE --> BUILTIN["BuiltinMemoryStore"]
  SCOPE --> INDEX["SessionSearchIndex SQLite FTS5"]
  SCOPE --> DREAM["MemoryDreamService pending drafts"]
  SCOPE --> PROVIDER["MemoryProvider (single active)"]

  BUILTIN --> USER["USER.md tenant/user"]
  BUILTIN --> PMEM["Personal MEMORY.md tenant/user/agent"]
  BUILTIN --> TEAM["TEAM.md tenant/team"]
  BUILTIN --> TMEM["Team MEMORY.md tenant/team/agent"]
  INDEX --> DB["session_search.sqlite3"]
  DREAM --> DRAFT["memory/dreams/pending/*.jsonl"]
  PROVIDER --> EXT["External provider (future)"]

  TOOLS["memory_update / session_search"] --> CTX["contextvars active scope"]
  CTX --> BUILTIN
  CTX --> INDEX
```

## 功能清单

| 功能 | 状态 |
|---|---|
| `MemoryScope(tenant_id, user_id, agent_name, team_id)` | 已实现 |
| `USER.md` 按租户和用户隔离 | 已实现 |
| `MEMORY.md` 按租户、用户、Agent 隔离 | 已实现 |
| `TEAM.md` 按租户和团队隔离 | 已实现 |
| 团队 `MEMORY.md` 按租户、团队、Agent 隔离 | 已实现 |
| `add/replace/remove` 内置记忆操作 | 已实现 |
| 重复记忆幂等 | 已实现 |
| 硬字符上限与 80% 整理提醒 | 已实现 |
| prompt injection、凭据、控制字符安全扫描 | 已实现 |
| SQLite FTS5 会话搜索 | 已实现 |
| scoped personal/team 会话搜索 | 已实现 |
| Dream consolidation 草案生成与 apply | 已实现 |
| scoped `memory_update` / `session_search` 工具 | 已实现 |
| 外部 `MemoryProvider` 抽象 | 已实现 |
| Honcho/Mem0/Supermemory 适配器 | 规划中 |

## 安全约束

- 工具不能从模型参数接收 `tenant_id`、`user_id`、`team_id`、`agent_name`，只能读取运行时 `MemoryScope`。
- 记忆写入必须通过安全扫描；命中风险内容时 fail-fast，不静默保存。
- FTS 查询必须按 scope 强制过滤：个人上下文只读 `tenant_id + user_id + team_id=""`，团队上下文只读 `tenant_id + team_id`。
- `USER.md`、`TEAM.md` 与两类 `MEMORY.md` 有硬字符上限，超过上限直接失败。
- 团队记忆只能在 active scope 存在 `team_id` 时写入。
- Dream 只保存 pending draft；只有显式 apply draft item 时才更新内置记忆。
- 当前集群状态不得作为长期记忆直接信任，操作前必须重新查询工具。

## 工具集

- `memory_update`
  - `target`: `user`、`memory`、`team` 或 `team_memory`
  - `action`: `add`、`replace`、`remove`
  - `content`: 新增或替换内容
  - `old_text`: 替换或删除时的唯一匹配子串
- `session_search`
  - `query`: 搜索词
  - `scope`: `auto`、`personal` 或 `team`
  - `top_k`: 返回数量
  - `agent_name/session_key/request_id`: 可选过滤条件
- `MemoryDreamService`
  - `check_dream_due(scope)`: 检查 scoped 记忆容量和会话轮次是否达到整理阈值。
  - `create_dream_draft(scope, target_scope, source)`: 生成 pending JSONL 草案。
  - `apply_dream_draft_item(draft_id, item_id)`: 按草案条目应用到内置记忆。

## 技术取舍

- 使用 Markdown 保存短记忆：可审计、可手工修正、适合 docs-first；不适合作为大容量历史库。
- 团队记忆独立于个人记忆：团队规范可复用，个人偏好不泄漏给团队。
- 使用 SQLite FTS5 保存会话搜索：无外部依赖、可本地部署、强作用域过滤；语义搜索可后续通过 provider 扩展。
- 使用 `contextvars` 传递工具 scope：避免模型伪造租户或用户 ID。
- Dream V1 不直接写入：先让系统生成草案，保留人工或 Validator 审批空间，降低团队记忆污染风险。
- V1 不接外部 provider：先稳定本地契约，再接 Honcho、Mem0、Supermemory 等服务。

## 变更日志

| 日期 | 变更 | 原因 |
|---|---|---|
| 2026-05-14 | 增加团队作用域记忆与 Dream 草案机制 | 支持团队服务场景，并降低自动记忆污染风险 |
| 2026-05-12 | 新增 Hermes 风格多租户三层记忆系统 | 从新项目基线开始搭建记忆模块 |
