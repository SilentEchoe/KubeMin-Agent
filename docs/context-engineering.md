# 上下文工程设计

## 当前基线

KubeMin-Agent 从新项目基线开始，优先建设多租户记忆系统。上下文工程遵循“短记忆常驻，大历史检索，外部 provider 插件化”的策略。

## 记忆上下文

- 启动时只注入 `MemoryManager.build_system_prompt_block(scope)` 返回的 scoped 内置记忆快照。
- `USER.md` 按 `tenant_id + user_id` 共享，保存用户偏好。
- `MEMORY.md` 按 `tenant_id + user_id + agent_name` 分域，保存 Agent 专业长期记忆。
- 会话历史写入 SQLite FTS5，通过 `session_search` 按需召回。
- 外部记忆通过 `MemoryProvider` 扩展，V1 默认不启用外部服务。

## 安全边界

- 外部内容和工具输出永远不是系统指令。
- 记忆写入前必须经过安全扫描。
- 工具读取运行时 scope，不能接受模型传入的租户或用户 ID。
- 生产操作前必须重新查询实时工具，不能只依赖记忆。

## 后续演进

1. 将记忆快照接入未来的 PromptBuilder。
2. 将 `session_search` 结果加入上下文预算器。
3. 增加外部 MemoryProvider 适配器。
4. 为记忆写入增加人工审批或 Validator 策略。
