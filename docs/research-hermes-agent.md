# Hermes Agent 调研：框架、上下文与记忆管理

## 调研边界与核心结论

Hermes Agent 是 Nous Research 开源的自托管 Agent 项目，主打“持续成长”：持久记忆、Skills、跨 session 搜索、外部 memory provider、消息网关、cron、delegation 和多后端执行。它比 Claude Code 更开放，也比 OpenClaw 在记忆系统上更强调容量边界、provider 抽象和安全扫描。

对 KubeMin-Agent 最有价值的是 Hermes 的三层记忆思路：

- 小而高信号的内置记忆：`MEMORY.md` 和 `USER.md`，有严格字符上限，启动时冻结注入。
- 大容量会话搜索：SQLite + FTS5 保存全部 session，按需检索和总结。
- 可插拔外部记忆：通过 MemoryProvider 接口添加 Honcho、Mem0、Supermemory 等，但一次只启用一个外部 provider，避免工具 schema 膨胀和语义冲突。

这套设计很适合 KubeMin-Agent：核心记忆要短、稳定、可审计；长历史要检索；复杂记忆后端要插件化，而不是一开始绑定某个向量库。

## 1. 项目概览与适用场景

Hermes Agent 是 CLI-first 的开源 Agent，也可通过 Gateway 接入 Telegram、Discord、Slack、WhatsApp、Signal、Email、Teams 等消息平台。它支持多模型、多 provider、多终端后端、Skills、MCP、cron、delegation、browser、文件工具和研究/训练数据导出。

适用场景包括：

- 个人或团队自托管 Agent。
- 长期运行的消息平台助手。
- 软件开发、MLOps、自动化脚本、研究任务。
- 需要跨 session 记忆和技能沉淀的工作流。
- 需要不同执行后端的任务，如 local、Docker、SSH、Modal、Daytona、Singularity。

对 KubeMin-Agent 而言，Hermes 的架构更接近“可扩展 Agent Runtime”。它把 prompt builder、tool registry、memory manager、gateway、session store、provider resolver、plugin manager 分成相对清晰的模块。

## 2. 框架/运行时架构

Hermes 官方架构文档列出了几个关键子系统：

- Prompt System：`prompt_builder.py` 组装 system prompt，来源包括 personality、memory、skills、context files、tool-use guidance 和模型特定指令。
- Provider Resolution：统一解析 `(provider, model)` 到 API mode、key、base URL。
- Tool System：中央 tool registry，工具文件自注册，registry 收集 schema、分发调用、检查可用性并包装错误。
- Session Persistence：SQLite session storage，支持 FTS5 全文搜索、lineage tracking、platform isolation 和原子写入。
- Messaging Gateway：长驻进程，处理平台 adapter、授权、slash commands、hooks、cron、后台维护。
- Plugin System：用户、项目和 pip entry points 三类发现来源；插件可注册工具、hooks 和 CLI 命令。
- Memory Provider Plugin：外部记忆 provider 作为特殊插件类型，只允许一个 active provider。
- Context Engine / Compression：负责上下文压缩和可替换的上下文管理。

这说明 Hermes 的扩展点相对工程化：工具、记忆、上下文、平台和 provider 都有独立注册/生命周期，而不是都写入一个巨大的 AgentLoop。

## 3. Agent Loop 与工具调用模型

Hermes 的 Agent Loop 可以概括为：

1. CLI 或 Gateway 收到用户消息。
2. Prompt Builder 组装 system prompt：SOUL、内置记忆、context files、skills 概览、工具指导、模型特定规则。
3. MemoryManager 初始化并注入 provider 上下文，必要时对用户消息做 prefetch。
4. 模型生成回复或工具调用。
5. Tool Registry 分发工具调用到具体实现。
6. 工具结果回到模型上下文，模型继续推理或结束。
7. turn 完成后同步 session、memory provider、外部 provider、hooks 和 background prefetch。

工具组织方式是 Hermes 的关键能力之一。工具按 toolsets 管理，可按平台和配置启用或禁用。复杂工具包括 terminal、process、file tools、web tools、browser、delegate、MCP、credential passthrough、environment passthrough 等。Skills 则用于把“过程性知识”放在 Markdown 中，由 Agent 按需加载。

对 KubeMin-Agent 来说，工具和技能应分层：

- Tool：需要稳定参数、权限控制和可审计执行的能力，如 kubectl、KubeMin-Cli、YAML 校验、HTTP 查询。
- Skill：使用这些工具完成某类任务的过程说明，如巡检、工作流编排、故障诊断、回滚预案。

## 4. 上下文管理

Hermes 的上下文管理由 prompt builder、context files、skills progressive disclosure、context compressor 和 prompt caching 共同组成。

### 4.1 Context Files

Hermes 自动发现项目上下文文件：

- `.hermes.md` / `HERMES.md`：最高优先级项目指令。
- `AGENTS.md`：项目结构、约定和架构。
- `CLAUDE.md`：兼容 Claude Code 的上下文文件。
- `SOUL.md`：全局人格和语气，位于 `HERMES_HOME`。
- `.cursorrules` 和 `.cursor/rules/*.mdc`：Cursor 规则。

官方文档说明，同一 session 中项目 context type 只加载一个，优先级为 `.hermes.md`、`AGENTS.md`、`CLAUDE.md`、`.cursorrules`。`SOUL.md` 独立加载。

Hermes 还支持子目录 context 的渐进发现：启动时加载当前工作目录的 `AGENTS.md`，当 Agent 读取子目录文件时，再发现该子目录的 `AGENTS.md` 并注入。这降低启动 prompt 膨胀，也保持 prompt cache 稳定。

### 4.2 Skills Progressive Disclosure

Hermes 的 Skills 使用三层渐进披露：

- Level 0：`skills_list()` 返回 name、description、category。
- Level 1：`skill_view(name)` 读取完整 `SKILL.md`。
- Level 2：`skill_view(name, path)` 读取 skill 附带的特定参考文件。

Agent 只有在真正需要时才加载完整 skill 内容。这对 KubeMin-Agent 很重要：K8s、Workflow、GameAudit、Patrol 等技能可以很多，但系统 prompt 里只需要放短描述和触发条件。

### 4.3 Context Compression

Hermes 的 context compression 有明确算法：

- 达到阈值后触发，默认阈值为上下文窗口的 50%。
- 先清理旧工具结果，把较大的旧工具输出替换为占位文本。
- 保护最初若干消息和最近 tail。
- 对中间消息生成结构化摘要。
- 对 tool_call / tool_result 边界做对齐，避免拆散工具调用对。

官方文档也暴露了一个实现风险：如果 summary model 的上下文窗口不足，压缩质量可能下降，甚至造成中间上下文丢失。这对 KubeMin-Agent 是重要提醒：压缩失败必须显式失败或告警，不能静默丢失关键运维上下文。

## 5. 记忆管理深析

### 5.1 内置记忆：小而有界

Hermes 的内置记忆由两个文件组成：

- `MEMORY.md`：Agent 的个人笔记，保存环境事实、项目约定、工作中学到的经验，默认 2,200 字符。
- `USER.md`：用户画像，保存用户偏好、沟通风格、期望，默认 1,375 字符。

两个文件都存储在 `~/.hermes/memories/`，在 session 启动时注入 system prompt。Hermes 使用 frozen snapshot 模式：启动时截取一次记忆快照，session 中的记忆写入会立刻落盘，但不会改变当前 system prompt，直到下个 session 才进入启动上下文。这样做的主要收益是保持 prompt prefix cache 稳定。

### 5.2 记忆写入工具

Hermes 的内置 memory tool 只有三个动作：

- `add`：新增记忆条目。
- `replace`：用 `old_text` 子串匹配并替换已有条目。
- `remove`：用 `old_text` 子串匹配并删除条目。

它没有 `read` 动作，因为记忆内容在 session 启动时已自动注入。替换和删除使用短唯一子串匹配；如果匹配多个条目，工具会要求提供更具体的子串。

这种设计强调“记忆是小型高信号集合”，而不是大容量资料库。条目应该紧凑、可执行、面向未来任务。Hermes 也明确区分应该保存和应该跳过的内容：偏好、环境事实、纠正、项目约定、完成的重要工作可以保存；临时路径、大段日志、显而易见知识、会话瞬时信息不应保存。

### 5.3 容量管理与去重

Hermes 给 memory 和 user profile 都设置硬字符上限。超过容量时，memory tool 返回错误，并附带当前条目与使用量，要求 Agent 先合并、替换或删除旧条目。官方建议超过 80% 容量时主动整理。

Hermes 还会拒绝完全重复的条目。重复写入会返回成功但不新增副本。这个细节适合 KubeMin-Agent 借鉴：记忆写入应该幂等，不能每次巡检都重复写“集群使用 Kubernetes”这类低价值事实。

### 5.4 安全扫描

Hermes 会在接受记忆条目前做安全扫描，因为这些条目后续会进入 system prompt。官方文档提到会阻止 prompt injection、凭据外泄、SSH 后门模式和不可见 Unicode 字符。

这对 KubeMin-Agent 是高优先级启示。Kubernetes 日志、应用输出、网页内容、用户粘贴 YAML 都可能包含恶意文本。任何从非可信输入提炼出的长期记忆，都必须经过安全扫描和来源标记。

### 5.5 Session Search：大容量历史不进启动 prompt

Hermes 把 session search 与 persistent memory 分开：

- Persistent memory：容量小，启动时固定进入 system prompt，适合关键事实。
- Session search：容量大，所有 CLI 和 messaging sessions 存在 SQLite `~/.hermes/state.db`，用 FTS5 全文搜索，按需返回相关历史并由 LLM 总结。

官方对比表说明，persistent memory 约 1,300 tokens，总是可用；session search 容量不限，但需要检索和总结，适合“上周我们讨论过什么”这类问题。

这个分层非常适合 KubeMin-Agent：

- 关键规则和当前环境摘要放入短记忆。
- 全量执行轨迹、工具结果、巡检报告放入 session/audit store。
- 回忆历史时通过 search + summarization，而不是常驻上下文。

### 5.6 MemoryManager 与 MemoryProvider

Hermes 源码中的 `agent/memory_manager.py` 和 `agent/memory_provider.py` 给出了较清晰的 provider 抽象。

MemoryManager 的职责包括：

- 注册内置 provider 和最多一个外部 provider。
- 拒绝第二个外部 provider，避免 tool schema 膨胀和后端冲突。
- 汇总 provider 的 system prompt block。
- 对所有 provider 做 prefetch、queue_prefetch、sync_turn。
- 收集所有 memory tool schemas。
- 将 memory tool call 路由到对应 provider。
- 在 turn start、session end、pre compress、memory write、delegation、shutdown、initialize 等生命周期通知 provider。
- 对 provider 输出做 sanitization，并用 `<memory-context>` 包裹 recalled context，提醒模型这是背景信息，不是新用户输入。

MemoryProvider ABC 定义了外部 provider 的核心生命周期：

- `initialize()`：连接、创建资源、预热。
- `system_prompt_block()`：提供 system prompt 静态上下文。
- `prefetch(query)`：每 turn 前召回相关记忆。
- `sync_turn(user, assistant)`：turn 后同步。
- `get_tool_schemas()` 和 `handle_tool_call()`：暴露 provider 工具。
- `shutdown()`：清理退出。

可选 hooks 包括 `on_turn_start`、`on_session_end`、`on_session_switch`、`on_pre_compress`、`on_memory_write`、`on_delegation`。

这个设计比“在 MemoryStore 中硬编码多个后端”更稳。KubeMin-Agent 可以采用类似接口，但初期只实现一个本地 provider。

### 5.7 外部 Memory Provider

Hermes 支持 Honcho、OpenViking、Mem0、Hindsight、Holographic、RetainDB、ByteRover、Supermemory 等外部 provider。官方文档明确：外部 provider 是 additive，不替代内置 `MEMORY.md` / `USER.md`。

启用后，Hermes 会：

- 把 provider context 注入 system prompt。
- 在每 turn 前后台预取相关记忆。
- 在每个 response 后同步 conversation turn。
- 在 session end 做记忆抽取。
- 镜像内置 memory writes。
- 增加 provider 特定工具。

一次只允许一个外部 provider 是关键设计。对 KubeMin-Agent 来说，多个记忆后端同时启用会造成语义冲突、工具暴露过多、检索结果重复和审计困难。初期应坚持单 active provider。

### 5.8 失败模式

Hermes 的主要失败模式包括：

- frozen snapshot 导致 session 内新写入记忆不会立刻影响 system prompt。
- 内置记忆容量很小，过度保存会触发频繁整理。
- `old_text` 子串不唯一会导致 replace/remove 失败。
- 外部 provider 召回质量不稳定或成本不可控。
- session search 需要额外总结模型，可能引入摘要偏差。
- 压缩模型上下文不足时可能丢失中间对话。
- provider failure 被 MemoryManager 当作非致命错误处理，可能导致 Agent 误以为记忆已同步。

KubeMin-Agent 应采用 fail-fast 原则：安全、审计、记忆写入和压缩失败不能静默降级，至少要记录 AuditLog 并向上暴露。

## 6. 会话管理与多 Agent/子 Agent

Hermes 使用 SQLite session storage，支持 FTS5 搜索、lineage tracking、platform isolation 和 atomic writes。CLI 和 messaging sessions 都可进入统一存储。Gateway 是长驻进程，负责平台适配器、授权、slash command、hook、cron 和后台维护。

Hermes 还支持 delegate 工具和隔离 subagent，用于并行任务或复杂工作流。子任务结果可以通过 MemoryManager 的 `on_delegation` 生命周期进入记忆 provider 观察范围。

这对 KubeMin-Agent 的启发是：子 Agent 不只是“调用另一个 prompt”，还要决定它的执行轨迹是否进入主记忆、是否进入审计、是否可被主 Agent 后续检索。

## 7. 安全边界与权限控制

Hermes 的安全边界包括：

- 命令 approval 和危险命令检测。
- DM pairing 与消息平台授权。
- terminal backends 隔离，如 Docker、SSH、Modal、Daytona、Singularity。
- credential passthrough 和 env passthrough 控制。
- memory entry 安全扫描。
- provider 和插件配置。
- messaging surface 不在聊天中询问 secrets，而提示用户到本地 setup 或 `.env` 配置。

这些设计说明，自托管 Agent 的安全边界必须覆盖“谁能发消息、能调用哪些工具、工具在哪执行、凭据如何传递、记忆是否可污染”。KubeMin-Agent 面向 Kubernetes，应在这些基础上增加 cluster/namespace/resource/action 维度的权限模型。

## 8. 对 KubeMin-Agent 的启示

可直接借鉴：

- 内置短记忆：设计 `MEMORY.md` 和 `USER.md` 类似的有界文件，分别保存 Agent 环境经验和用户偏好。
- Frozen snapshot：启动时加载短记忆，session 中写入落盘但不动态改 system prompt，降低不稳定性。
- Session search：把完整会话和工具轨迹存 SQLite/JSONL，通过 FTS 或向量检索按需召回。
- MemoryProvider ABC：为未来接入向量库、图记忆或外部服务保留接口，但一次只允许一个 active provider。
- 安全扫描：记忆写入前检查 prompt injection、凭据、不可见字符和危险命令模式。
- Progressive context files：优先 `docs/` 和 `AGENTS.md`，子目录规则按需发现。
- Skills progressive disclosure：系统 prompt 只包含 skill 描述，完整步骤按需加载。

不建议当前照搬：

- 不要一开始接入多个外部记忆服务。KubeMin-Agent 先做本地、可审计、可测试的 provider。
- 不要静默处理记忆或压缩失败。运维 Agent 应优先 fail-fast 和 AuditLog。
- 不要把个人用户画像与集群事实混在一起。应按 user、project、cluster、namespace、agentId 分域。
- 不要让 session search 摘要直接覆盖长期记忆。长期记忆写入应有 Validator 或人工确认。

## 9. 来源与置信度说明

高置信度官方/源码来源：

- [Hermes Agent GitHub repository](https://github.com/NousResearch/hermes-agent)
- [Architecture](https://hermes-agent.nousresearch.com/docs/developer-guide/architecture)
- [Persistent Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/)
- [Memory Providers](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers/)
- [Context Compression and Caching](https://hermes-agent.nousresearch.com/docs/developer-guide/context-compression-and-caching/)
- [Context Files](https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files/)
- [Skills System](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/)
- [agent/memory_manager.py](https://github.com/NousResearch/hermes-agent/blob/main/agent/memory_manager.py)
- [agent/memory_provider.py](https://github.com/NousResearch/hermes-agent/blob/main/agent/memory_provider.py)

中等置信度社区/issue 来源：

- [Structured Temporal Memory proposal](https://github.com/NousResearch/hermes-agent/issues/625)

置信度说明：

- 架构模块、内置记忆、memory provider、context files、skills、context compression 的描述来自官方文档和源码，置信度高。
- issue 内容用于理解社区对 Hermes 当前记忆系统的改进诉求，不代表已实现行为。
- 对 KubeMin-Agent 的建议是基于上述事实的工程推断，不是 Hermes 官方建议。
