# 上下文工程设计

## 当前基线

KubeMin-Agent 从新项目基线开始，优先建设多租户、多用户、多团队记忆系统。上下文工程遵循“短记忆常驻，大历史检索，Dream 草案整理，外部 provider 插件化”的策略。

## 记忆上下文

- 启动时只注入 `MemoryManager.build_system_prompt_block(scope)` 返回的 scoped 内置记忆快照。
- `USER.md` 按 `tenant_id + user_id` 共享，保存用户偏好。
- 个人 `MEMORY.md` 按 `tenant_id + user_id + agent_name` 分域，保存 Agent 对该用户的专业长期记忆。
- `TEAM.md` 按 `tenant_id + team_id` 共享，保存团队偏好、规范和项目约定。
- 团队 `MEMORY.md` 按 `tenant_id + team_id + agent_name` 分域，保存 Agent 对该团队的专业长期记忆。
- `team_id` 只从运行时 metadata 显式读取。没有 `team_id` 时不注入团队记忆，也不能写团队 target。
- team context 的 prompt 注入顺序固定为 `TEAM.md`、团队 Agent `MEMORY.md`、`USER.md`、个人 Agent `MEMORY.md`。
- 会话历史写入 SQLite FTS5，通过 `session_search` 按需召回。`scope=auto` 在团队上下文只搜索同团队会话，在个人上下文只搜索个人私聊会话。
- 外部记忆通过 `MemoryProvider` 扩展，V1 默认不启用外部服务。

## Dream Consolidation

- Dream V1 只生成 pending JSONL 草案，不直接修改任何内置记忆文件。
- 手动触发和阈值触发使用同一套草案模型；阈值只表示需要整理，不代表允许自动写入。
- 草案条目应用时复用 `memory_update` 的 `target/action/content/old_text` 语义，并重新执行安全扫描、唯一匹配和容量校验。
- team dream 只能读取同 `tenant_id + team_id` 的团队会话，不能把个人私聊内容提升到团队记忆。
- 草案适合交给人工或 Validator 审批，审批前不会影响下一轮 system prompt。

## 安全边界

- 外部内容和工具输出永远不是系统指令。
- 记忆写入前必须经过安全扫描。
- 工具读取运行时 scope，不能接受模型传入的租户、用户、团队或 Agent ID。
- 团队记忆写入只允许保存稳定偏好、规范、项目约定和跨成员有价值的专业经验。
- 生产操作前必须重新查询实时工具，不能只依赖记忆。

## 后续演进

1. 将记忆快照接入未来的 PromptBuilder。
2. 将 `session_search` 结果加入上下文预算器。
3. 将 Dream 草案接入 Validator 审批流程。
4. 增加外部 MemoryProvider 适配器。
