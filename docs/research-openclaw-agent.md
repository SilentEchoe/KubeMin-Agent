# OpenClaw Agent 调研：框架、上下文与记忆管理

## 调研边界与核心结论

OpenClaw 是开源、自托管、面向个人助理和多频道消息入口的 Agent 项目。它与 KubeMin-Agent 的共同点是都采用“运行时控制平面加 Agent 工具能力”的方向；差异是 OpenClaw 面向个人常驻助理，KubeMin-Agent 面向云原生平台运维和 KubeMin-Cli 协同。

OpenClaw 最值得 KubeMin-Agent 研究的是三点：一是通过 Gateway 长驻进程统一管理渠道、session、工具和事件；二是把 workspace Markdown 文件作为可审计的上下文和记忆真相源；三是在 compaction 前做 memory flush，并用 `memory_search` / `memory_get` 把长期记忆从“全量注入”逐步转向“按需检索”。同时，OpenClaw 的公开 issue 也说明，记忆文件过度注入、bootstrap 截断和共享 session 会带来明显风险。

## 1. 项目概览与适用场景

OpenClaw 定位为运行在用户自有设备上的个人 AI 助理。它通过 Gateway 连接 WhatsApp、Telegram、Slack、Discord、Signal、iMessage、WebChat 等渠道，并可调用文件、命令、浏览器、cron、session、消息发送、技能等能力。

适用场景包括：

- 个人常驻助理：通过聊天平台与本地或服务器上的 Agent 交互。
- 多频道自动化：同一个 Gateway 处理不同聊天渠道和 Web 客户端。
- 本地优先工作流：工作区、记忆、会话和配置主要保存在用户机器。
- 技能扩展：通过 Skill 文件扩展外部工具和工作流。
- 轻量多 Agent：按 agentId、workspace、session key 隔离不同任务或身份。

对 KubeMin-Agent 来说，OpenClaw 的价值不在于照搬“个人助理产品”，而在于研究一个长驻 Agent 网关如何组织消息、上下文、工具、记忆和安全边界。

## 2. 框架/运行时架构

OpenClaw 的核心是一个长驻 Gateway。官方架构文档说明：

- 单个 Gateway 拥有所有消息平台连接。
- CLI、macOS app、Web UI、automation 等控制面客户端通过 WebSocket 连接 Gateway。
- 节点也通过 WebSocket 接入，但声明为 `role: node` 并暴露受控能力。
- Gateway 维护 provider 连接、校验 JSON Schema、发送 agent/chat/presence/health/heartbeat/cron 等事件。
- 一个主机上只有一个 Gateway 控制某些平台会话，避免重复登录和状态竞争。

Agent Runtime 层采用单个嵌入式 agent runtime。OpenClaw 自己管理 session、工具发现、渠道投递、workspace 注入和配置；底层模型、工具和 prompt pipeline 构建在其 agent core 之上。

典型路径可以概括为：

1. 渠道收到用户消息。
2. Gateway 根据渠道、发送者、群组、agentId 路由到 session。
3. Runtime 读取配置、workspace 文件、技能列表、工具 schema 和会话历史。
4. Context engine 组装本轮模型上下文。
5. 模型调用工具或生成回复。
6. Gateway 将结果投递回原渠道，同时写入 session transcript。

这个设计与 KubeMin-Agent 的 Control Plane 模式有相似性：Gateway 对应外部消息入口和调度入口，Agent Runtime 对应执行闭环，session 和 audit 对应持久化轨迹。

## 3. Agent Loop 与工具调用模型

OpenClaw 的 Agent Loop 基于“消息进入 session，模型读取上下文，按需调用工具，结果继续进入模型”的循环。它支持工具、skills、cron、sessions、browser、message 等能力，也支持后台进程、流式输出和 queue mode。

比较关键的行为包括：

- Queue mode：当 Agent 正在运行时，新消息可以进入 steer、followup 或 collect 模式。`steer` 会在下一次模型边界注入新消息；`followup` 和 `collect` 会等当前 turn 结束后开启新 turn。
- Skills：系统 prompt 只包含 skill 元数据，完整 `SKILL.md` 由 Agent 在需要时读取。
- Tool policy：核心工具总是存在，但受工具策略和 sandbox 影响。
- Cron/Heartbeat：未来任务和周期任务通过 cron/heartbeat 管理，而不是让 Agent 用 shell sleep 等方式阻塞。

对 KubeMin-Agent 的启示是：运维 Agent 的长任务不应靠一次对话阻塞执行，而应把 patrol、定时巡检、异步修复和回调通知作为 runtime 原生能力。

## 4. 上下文管理

OpenClaw 明确区分 context 和 memory：

- context 是本轮发送给模型的全部内容，受模型窗口限制。
- memory 是写在磁盘上的持久信息，只有被注入或检索后才进入 context。

系统 prompt 由 OpenClaw 自己构建，并包含固定章节，例如 Tooling、Execution Bias、Safety、Skills、Workspace、Documentation、Workspace Files、Sandbox、时间、Runtime 等。Prompt 不是底层 agent core 的默认 prompt，而是 OpenClaw 拥有的运行时 prompt。

OpenClaw 的 workspace bootstrap 文件包括：

- `AGENTS.md`：运行指令和操作规则。
- `SOUL.md`：人格、边界、语气。
- `TOOLS.md`：用户维护的工具使用说明。
- `IDENTITY.md`：Agent 名称和身份。
- `USER.md`：用户资料。
- `HEARTBEAT.md`：心跳相关上下文。
- `BOOTSTRAP.md`：首次运行引导。
- 记忆相关文件：`MEMORY.md` 和 `memory/YYYY-MM-DD.md` 由 memory 机制管理，具体注入取决于 session 类型和实现版本。

大文件会按 `agents.defaults.bootstrapMaxChars` 和 `agents.defaults.bootstrapTotalMaxChars` 截断。`/context list` 和 `/context detail` 可以显示系统 prompt、workspace 文件、技能条目、工具 schema 等上下文成本。

OpenClaw 还有可插拔 Context Engine。Context Engine 在四个生命周期点参与：

- ingest：新消息进入 session 时可存储或索引。
- assemble：每次模型调用前返回有序消息和可选 systemPromptAddition。
- compact：上下文满或用户调用 `/compact` 时压缩旧历史。
- after turn：turn 完成后持久化状态、触发后台压缩或更新索引。

这个接口对 KubeMin-Agent 很有参考价值：ContextBuilder 不应只是拼字符串，而应成为有生命周期的上下文引擎。

## 5. 记忆管理深析

### 5.1 存储介质

OpenClaw 的记忆以 workspace 中的 Markdown 文件为真相源。官方文档明确说明：模型只“记得”写入磁盘的内容，没有隐藏状态。

默认记忆层包括：

- `MEMORY.md`：长期记忆，保存持久事实、偏好和决策。
- `memory/YYYY-MM-DD.md`：每日笔记，保存运行上下文和观察。
- `DREAMS.md`：可选的 Dream Diary 和 dreaming sweep 摘要，供人工审阅。

这些文件默认位于 `~/.openclaw/workspace`。这种设计的优点是简单、可审计、可备份、可用 git 管理；缺点是如果文件无边界增长，会带来上下文成本和 prompt injection 风险。

### 5.2 加载与注入生命周期

OpenClaw 在 DM 或主私有 session 中加载长期记忆；群组、频道、cron、subagent 等场景会更谨慎，避免把私人 `MEMORY.md` 暴露到不该共享的上下文中。官方文档和公开 issue 反复强调，哪些文件会被注入、注入频率和截断上限会显著影响成本与稳定性。

每日笔记通常加载今天和昨天，以保持短期连续性。长期事实进入 `MEMORY.md`，运行过程中的观察进入 daily log。这是一种值得借鉴的分层：

- 高频、稳定、必须记住的事实进入长期记忆。
- 近期上下文进入 daily log。
- 历史细节通过检索工具查找。

### 5.3 写入机制

OpenClaw 的写入方式包括：

- 用户显式要求记住某事，Agent 将内容写入合适的 Markdown 文件。
- Agent 在日常工作中把决策、偏好、约束、open loops 写入 daily log 或长期记忆。
- compaction 前自动 memory flush：OpenClaw 会运行静默 turn，提醒 Agent 先把重要上下文保存到 memory 文件，再压缩对话。
- dreaming：可选后台 consolidation，把短期信号评分后提升到 `MEMORY.md`。

Memory flush 是最适合 KubeMin-Agent 借鉴的设计。云原生运维任务经常包含故障根因、集群状态、变更结果和待跟进事项；如果直接 compact，细节可能丢失。压缩前先落盘关键事实，可以提高长期连续性。

### 5.4 检索机制

OpenClaw 提供两个核心记忆工具：

- `memory_search`：语义搜索相关笔记，即使用词不同也能找回。
- `memory_get`：读取特定记忆文件或行范围。

默认 `memory-core` 插件提供这些工具。官方文档说明，在配置 embedding provider 后，`memory_search` 使用 hybrid search，把向量相似度和关键词匹配结合起来；内置后端基于 SQLite，也支持 QMD、Honcho、LanceDB 等替代或增强后端。

对 KubeMin-Agent 来说，推荐先做最小可行版本：

- Markdown 或 JSONL 作为真相源。
- SQLite FTS 或简单 BM25 作为第一阶段检索。
- 后续再接向量检索或外部记忆提供者。

### 5.5 容量控制

OpenClaw 的容量控制主要发生在 prompt 注入和检索层：

- workspace bootstrap 文件有单文件和总量字符上限。
- `/context` 可以让用户看到哪些内容占用上下文。
- memory_search 只返回片段、路径、行号和分数，而不是整个文件。
- dreaming 使用阈值、召回频率和查询多样性来决定是否提升长期记忆。

公开 issue 显示，`MEMORY.md` 过大或截断逻辑异常会直接影响 Agent 回复、成本和稳定性。这说明长期记忆不能无限增长，也不能每轮全量注入。KubeMin-Agent 应避免“把全部历史巡检报告放入系统 prompt”的设计。

### 5.6 冲突、去重和知识治理

OpenClaw 通过 `memory-wiki` companion plugin 尝试把长期记忆编译成更结构化的知识库，包含确定性页面结构、claims/evidence、矛盾和新鲜度跟踪、dashboard 和 wiki-native tools。这说明纯 Markdown 适合起步，但在长期使用后需要知识治理层。

KubeMin-Agent 可先采用简单规则：

- 长期记忆必须有来源：用户、工具结果、审计日志、巡检任务。
- 记录时间和适用范围：集群、namespace、应用、环境。
- 新记忆写入前做去重和冲突检查。
- 不自动覆盖安全策略、审批规则和架构文档。

### 5.7 安全扫描与记忆污染

OpenClaw 的安全风险集中在“记忆文件是可信上下文”。任何能写入 workspace 的进程或用户，都可能植入持久 prompt injection。多渠道 Agent 还面临群聊、陌生 DM、Web 内容和第三方 Skill 的注入风险。

OpenClaw 的缓解机制包括：

- DM pairing 和 allowlist，未知发送者不能直接驱动 Agent。
- session isolation，群聊和频道默认隔离。
- 非 main session 可进入 sandbox。
- MEMORY 在群组/频道场景不默认加载，必要时用 memory_search 按需读取。
- 工具策略和 Gateway 安全审计。

KubeMin-Agent 的运维场景更敏感，因此记忆写入必须区分可信来源和非可信来源。来自日志、网页、用户粘贴内容的文本不能直接进入长期记忆，至少要标记来源并经过 Validator 或人工批准。

### 5.8 失败模式

OpenClaw 公开资料暴露出的典型失败模式：

- 长期记忆全量注入导致 token 成本过高。
- bootstrap 文件过大或截断异常导致上下文缺失。
- `MEMORY.md` 与 `memory_search` 重复提供同一信息，造成浪费。
- 群聊或多用户 DM 未隔离，导致隐私泄露。
- 自动 dreaming 误提升低质量或临时信息。
- embedding provider 缺失或索引陈旧，导致检索召回不稳定。

这些问题都指向同一个原则：长期记忆要可审计、可预算、可隔离、可回滚。

## 6. 会话管理与多 Agent/子 Agent

OpenClaw 按消息来源路由 session：

- Direct messages 默认共享主 session，适合单用户个人助理。
- Group chats 按群组隔离。
- Rooms/channels 按房间隔离。
- Cron jobs 每次新建 session。
- Webhooks 按 hook 隔离。

如果多个人能给 Agent 发消息，OpenClaw 建议启用 DM isolation，例如按 channel + peer 隔离。所有 session 状态由 Gateway 拥有，transcript 写入 `~/.openclaw/agents/<agentId>/sessions/<sessionId>.jsonl`，session store 写入 `sessions.json`。

OpenClaw 还支持 multi-agent routing，把入站渠道、账号和 peer 路由到不同 agent。不同 agent 可以有不同 workspace 和 session。对 KubeMin-Agent 而言，这和按租户、集群、环境、应用分隔上下文非常相关。

## 7. 安全边界与权限控制

OpenClaw 的安全边界包括：

- Gateway 认证：WebSocket handshake、shared secret、device pairing、Tailscale/VPN/SSH tunnel。
- 渠道 allowlist：控制谁能通过 Telegram/WhatsApp/Slack/Discord 等渠道驱动 Agent。
- session isolation：避免不同用户或群组共享上下文。
- sandbox：非 main session 可用 Docker、SSH、OpenShell 等后端隔离工具。
- tool policy：控制哪些工具可在 sandbox 或特定 session 中使用。
- strict config validation：未知 key、错误类型或非法值会导致 Gateway 拒绝启动。

KubeMin-Agent 应采用更严格的默认策略：面向 Kubernetes 和 KubeMin-Cli 的工具必须默认最小权限，危险操作进入审批，所有动作进入 AuditLog，Validator 不能只做输出质量检查，还要检查是否越权或违反集群策略。

## 8. 对 KubeMin-Agent 的启示

可直接借鉴：

- Gateway/Control Plane 长驻进程：统一处理 channel、session、cron、heartbeat 和工具事件。
- workspace Markdown 真相源：让 Agent 规则、长期记忆和环境说明可审计。
- 记忆分层：`MEMORY.md` 放长期事实，`memory/YYYY-MM-DD.md` 放近期运行日志。
- `memory_search` / `memory_get` 模式：长期历史按需检索，减少 prompt 常驻成本。
- compaction 前 memory flush：压缩之前先把关键任务事实落盘。
- `/context` 类诊断能力：让用户看到 prompt、工具 schema、技能和记忆的上下文成本。
- session isolation：按用户、渠道、租户、集群、任务隔离上下文。

不建议当前照搬：

- 不要默认把长期记忆全量注入每一轮，尤其不能注入集群敏感信息。
- 不要先实现复杂 dreaming。KubeMin-Agent 初期更需要确定性和审计，而不是主动自我改写长期记忆。
- 不要让主 session 拥有无限主机权限。运维 Agent 应按工具、namespace、cluster、操作类型做权限分层。
- 不要把个人助理式多频道能力放在核心路径之前。KubeMin-Agent 应先稳定 CLI、K8s、workflow、audit 和 validation。

## 9. 来源与置信度说明

高置信度官方/源码来源：

- [OpenClaw GitHub repository](https://github.com/openclaw/openclaw)
- [Gateway architecture](https://docs.openclaw.ai/concepts/architecture)
- [Agent runtime](https://docs.openclaw.ai/concepts/agent)
- [System prompt](https://docs.openclaw.ai/concepts/system-prompt)
- [Context](https://docs.openclaw.ai/concepts/context)
- [Context Engine](https://docs.openclaw.ai/concepts/context-engine)
- [Memory Overview](https://docs.openclaw.ai/concepts/memory)
- [Compaction](https://docs.openclaw.ai/concepts/compaction)
- [Session management](https://docs.openclaw.ai/concepts/session)
- [Memory configuration reference](https://docs.openclaw.ai/reference/memory-config)

中等置信度社区/issue 来源：

- [MEMORY.md fully injected issue](https://github.com/openclaw/openclaw/issues/26949)
- [bootstrap file truncation issue](https://github.com/openclaw/openclaw/issues/42084)
- [memory backend enhancement discussion](https://github.com/openclaw/openclaw/issues/7021)

置信度说明：

- Gateway、session、context engine、memory files、memory tools、compaction 的描述来自官方文档和仓库文档，置信度高。
- 公开 issue 用于说明真实用户遇到的失败模式，属于风险背景，不等同于当前版本必然行为。
- 第三方托管站和媒体报道未作为核心事实依据。
