# Claude Code Agent 调研：框架、上下文与记忆管理

## 调研边界与核心结论

本文只把 Claude Code 的官方公开文档作为事实来源。Claude Code 的 CLI 实现并非正式开源项目，网络上存在泄露源码、逆向分析和二手解读；这些材料不作为本文的实现事实依据。本文可确认的是 Claude Code 对外暴露的 Agent 运行模型、上下文机制、记忆机制、子 Agent、权限与扩展接口。

Claude Code 的核心设计不是“单轮问答”，而是一个围绕代码仓库运行的 Agent Harness：模型负责推理，工具负责行动，运行时负责把项目文件、会话、记忆、权限、扩展和上下文压缩组织成可持续工作的闭环。对 KubeMin-Agent 最有价值的启示是：把长期规则、自动学习记忆、会话历史、工具权限和子任务上下文分开治理，不要把所有内容混成一个无限增长的 prompt。

## 1. 项目概览与适用场景

Claude Code 是 Anthropic 面向软件工程任务的 Agentic Coding Tool，可运行在终端、IDE、桌面端、Web、Slack 和 CI/CD 等环境。官方文档将它描述为能读取代码库、编辑文件、运行命令、搜索 Web、连接外部工具并验证结果的编码代理。

适用场景包括：

- 新功能开发：读取代码库、制定修改方案、编辑多文件、运行测试。
- 缺陷修复：复现错误、搜索相关实现、修改代码、回归验证。
- 代码库理解：通过读取、搜索、子 Agent 探索来回答架构问题。
- 自动化开发工作流：通过 Hooks、MCP、Skills、Slash Commands 扩展本地工作流程。

从 KubeMin-Agent 的角度看，Claude Code 更像“面向代码仓库的本地/云端执行代理”，而不是多频道个人助理。它的设计重点是代码上下文、可恢复会话、权限控制和任务执行闭环。

## 2. 框架/运行时架构

Claude Code 的官方架构可以概括为五层：

- 模型层：Claude 模型负责理解任务、规划、选择工具、解释结果和调整策略。
- Agent Harness：Claude Code 为模型提供工具、上下文管理和执行环境，让模型从文本生成器变成可行动的代理。
- 工具层：内置文件操作、搜索、命令执行、Web、代码智能、子 Agent、任务管理等工具；外部能力通过 MCP、Skills 和插件扩展。
- 会话层：每次对话是一个 session，消息、工具调用和结果写入本地 JSONL，可 resume、fork、跨 worktree 管理。
- 配置与安全层：通过 settings、permissions、hooks、managed policies、checkpoints 控制 Agent 可访问内容和可执行动作。

官方文档把 Agent Loop 描述为“收集上下文、采取行动、验证结果”的循环。这个循环不是固定阶段机，而是根据工具反馈不断调整：测试失败时继续读取错误，发现缺失依赖时搜索配置，修改后再次验证。

Claude Code 支持三类执行环境：

- Local：代码和命令在用户本机执行，默认模式。
- Cloud：Anthropic 管理的虚拟机环境，适合把任务交给云端执行。
- Remote Control：通过 Web 控制本机环境，代码仍在用户机器上执行。

## 3. Agent Loop 与工具调用模型

Claude Code 的工具调用模型强调“模型选择工具，工具结果反哺下一步”。官方列出的工具能力可以归纳为：

- 文件操作：读取、编辑、创建、移动和整理文件。
- 搜索：按文件名、路径、正则和符号搜索代码库。
- 执行：运行 shell 命令、构建、测试、git 操作、本地脚本。
- Web：搜索文档、抓取网页、查询外部信息。
- 代码智能：在 IDE 场景中读取类型错误、跳转定义和引用。
- 编排工具：子 Agent、Todo、询问用户、Slash Commands 等。

这个模型的关键是“行动后验证”。例如修复测试失败时，Claude Code 会先运行测试，读取失败信息，搜索相关文件，编辑代码，再次运行测试。对 KubeMin-Agent 而言，这对应云原生运维中的“观测、诊断、操作、验证”闭环：不能只生成建议，还要在受控权限下调用 kubectl、KubeMin-Cli、日志查询和验证工具。

Claude Code 还支持中断与转向。用户可以在运行中打断 Agent，给出新的约束或纠正方向。这个机制对长任务很重要，因为 Agent 的计划会随着工具结果改变，用户需要可介入的控制面。

## 4. 上下文管理

Claude Code 的上下文窗口包含：系统指令、用户消息、助手消息、文件内容、命令输出、工具结果、CLAUDE.md、auto memory、已加载 Skills、MCP 工具信息等。官方强调“context”和“memory”不同：context 是当前模型窗口里的内容，memory 是跨 session 存在于磁盘上的内容，只有被加载后才进入 context。

启动时自动进入上下文的内容包括：

- CLAUDE.md 及相关项目/用户/组织指令。
- auto memory 的启动摘要，具体为 `MEMORY.md` 的前 200 行或 25KB，取较小者。
- MCP 工具名称或可搜索的工具描述。
- Skills 描述，但不是完整 Skill 内容。
- 输出风格、追加系统 prompt 等配置。

运行中动态进入上下文的内容包括：

- Agent 读取的文件内容。
- 命令输出和工具结果。
- 与路径匹配的 path-scoped rules。
- 被显式加载的 Skill 正文。
- 子 Agent 返回的摘要。

上下文膨胀后，Claude Code 会先清理旧工具输出，再按需总结对话。用户可以用 `/compact` 手动压缩，也可以在 CLAUDE.md 中加入 compaction 关注点。官方也说明，早期对话中的详细指令可能在压缩后丢失，因此长期规则应放入 CLAUDE.md，而不是依赖聊天历史。

Claude Code 的两个重要节省策略：

- Skills 按需加载：启动时只暴露描述，完整 Skill 仅在使用时加载。
- 子 Agent 隔离上下文：探索任务可以在独立上下文中完成，只把摘要返回主会话，避免主上下文被大量文件读取污染。

## 5. 记忆管理深析

### 5.1 记忆类型与存储介质

Claude Code 有两类互补记忆：

- CLAUDE.md：用户、团队或组织编写的持久指令与项目背景。
- auto memory：Claude Code 自己在工作过程中写下的经验、偏好、调试发现和项目模式。

CLAUDE.md 的范围分层包括：

- 管理策略：组织级文件，部署在系统级路径，由 IT/DevOps 管理。
- 项目指令：`./CLAUDE.md` 或 `./.claude/CLAUDE.md`，可提交到版本控制。
- 用户指令：`~/.claude/CLAUDE.md`，只影响个人。
- 本地指令：`./CLAUDE.local.md`，个人项目偏好，通常 gitignore。

auto memory 存在于本机的 `~/.claude/projects/<project>/memory/`。项目路径由 git 仓库派生，同一仓库的 worktree 和子目录共享同一个 auto memory 目录。它是机器本地的，不自动跨机器或云环境同步。

### 5.2 读写生命周期

CLAUDE.md 在 session 启动时加载。官方说明，Claude Code 会从当前目录向上查找相关 CLAUDE.md，并在读取子树文件时发现嵌套的 CLAUDE.md。这让大型单仓库可以把规则拆到子目录。

auto memory 默认开启。Claude Code 在工作中根据用户纠正、项目发现、构建命令、调试结论等自动决定是否写入。启动时只加载 `MEMORY.md` 的前 200 行或 25KB；更详细的 topic 文件不会自动加载，而是在需要时通过普通文件工具读取。

这是一种“索引加详情”的设计：`MEMORY.md` 保持简洁，记录有哪些主题和核心事实；详细内容分散到 topic 文件中，按需读取。该设计避免所有历史经验每次都进入上下文。

### 5.3 检索机制

Claude Code 官方文档没有把 auto memory 描述为外部向量数据库或图数据库，而是明确说明其记忆文件是普通 Markdown，可通过 `/memory` 浏览、审计、编辑或删除。Topic 文件按需读取，意味着检索依赖 Agent 对当前任务的判断和标准文件工具。

CLAUDE.md 支持 `@path/to/import` 导入其他文件，且有递归深度限制。这个机制可把团队规则、工作流、命令清单拆成多个文件，同时仍由 CLAUDE.md 作为入口。

### 5.4 容量控制与压缩关系

auto memory 有明确启动加载上限：前 200 行或 25KB。CLAUDE.md 则会完整加载，但官方建议保持简洁，因为它越长，模型越难稳定遵循。上下文压缩不会替代记忆管理；当对话被 compact 后，启动记忆和 CLAUDE.md 仍是恢复长期规则的主要机制。

Claude Code 的经验对 KubeMin-Agent 很直接：长期记忆必须有启动预算和分层策略。否则 `MemoryStore` 一旦把所有历史巡检、对话、命令输出都塞入 prompt，就会快速污染上下文并提高成本。

### 5.5 去重、冲突与安全

官方公开文档没有给出 auto memory 的具体去重算法，但提供了治理入口：用户可通过 `/memory` 查看、打开、编辑和删除记忆。Claude Code 也强调 CLAUDE.md 和 auto memory 是“上下文”，不是强制配置；如果内容模糊、冲突或过长，模型可能无法稳定遵守。

安全上，持久记忆本身可能成为 prompt injection 的载体。Claude Code 通过权限系统、settings.deny、MCP 管理、敏感文件排除、工具审批和 managed policies 降低风险，但记忆内容一旦被加载进入上下文，仍需要用户定期审计。

### 5.6 失败模式

主要失败模式包括：

- 把长期规则写在聊天历史里，compact 后丢失。
- CLAUDE.md 过长或规则互相冲突，导致模型遵循不稳定。
- auto memory 写入错误结论，后续 session 反复继承。
- 本机 auto memory 不跨机器同步，云端/本地行为不一致。
- 记忆中保存敏感信息或外部注入内容，形成持久 prompt injection。
- Topic 文件没有被按需读取，导致 Agent “有记忆但没想起来”。

## 6. 会话管理与多 Agent/子 Agent

Claude Code 的 session 会写入 `~/.claude/projects/` 下的 plaintext JSONL 文件，支持 resume、continue 和 fork。Session 与当前目录、worktree 和项目相关联；切换 branch 后，Agent 看到新的文件状态，但会话历史仍然存在。

子 Agent 是 Claude Code 上下文管理的重要机制。每个 subagent：

- 有独立上下文窗口。
- 有自己的系统 prompt。
- 可限制工具权限。
- 可配置在用户级 `~/.claude/agents/` 或项目级 `.claude/agents/`。
- 以 Markdown 加 YAML frontmatter 定义。

官方文档强调，子 Agent 可避免主会话上下文被复杂探索任务污染。Claude Code 还包含内置的探索、计划、通用任务等辅助 Agent。对 KubeMin-Agent 而言，这与当前“Control Plane 调度 K8sAgent / WorkflowAgent / GeneralAgent”的方向一致，但应进一步明确每个子 Agent 的工具边界、上下文窗口和记忆写入权限。

## 7. 安全边界与权限控制

Claude Code 的安全机制主要包括：

- Permission modes：默认询问、自动接受编辑、计划模式、Auto mode 等。
- settings.json 分层：managed、user、project、local，不同层级有不同优先级。
- permissions.allow / ask / deny：允许、询问或拒绝具体工具和命令。
- sensitive file deny：让 `.env`、secrets、credentials 等对 Claude Code 不可见。
- hooks：在工具调用前后、session 事件、compact 事件等时机执行自定义检查或自动化。
- checkpoints：文件编辑前创建本地快照，可回滚文件变化。
- MCP scope：MCP server 有 local、project、user 等安装范围，便于控制共享和私密工具。

这些机制说明，Agent 的安全不能只靠 prompt。KubeMin-Agent 应把安全边界落到工具注册、命令审批、沙箱、配置验证和审计日志上，prompt 只作为行为引导。

## 8. 对 KubeMin-Agent 的启示

可直接借鉴：

- 用 Markdown 作为项目指令入口：保留 `AGENTS.md` / `docs/` 作为项目事实源，并支持子目录规则。
- 区分“人工规则”和“自动记忆”：人工维护的架构约束、工具说明、审批规则应与 Agent 自动写入的经验分开。
- 为自动记忆设启动预算：例如只加载 Memory Index，详情通过 `memory_get` 或检索工具按需读取。
- 子 Agent 独立上下文：K8sAgent、WorkflowAgent、GeneralAgent 不应共享完整 tool trace，只返回结构化结果给 Control Plane。
- 把 compact 和 memory flush 结合：压缩前先让 Agent 把关键事实落盘，避免上下文总结遗漏。
- 给用户可审计入口：提供 `kubemin-agent memory list/edit/prune` 或文档化的 memory 文件结构。

不建议当前照搬：

- 不要把“记忆”当作强制策略。安全策略必须在工具层、Validator、Sandbox 和 AuditLog 中强制执行。
- 不要过早实现复杂自动学习。KubeMin-Agent 先做可审计、可回滚、容量受控的记忆，再考虑自动提炼。
- 不要默认跨频道/跨用户共享对话。运维场景更敏感，应默认按用户、渠道、集群或租户隔离 session。
- 不要依赖隐藏实现。Claude Code 的未公开内部机制只能作为产品行为参考，不能作为 KubeMin-Agent 的实现契约。

## 9. 来源与置信度说明

高置信度官方来源：

- [How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works)
- [How Claude remembers your project](https://code.claude.com/docs/en/memory)
- [Explore the context window](https://code.claude.com/docs/en/context-window)
- [Create custom subagents](https://code.claude.com/docs/en/sub-agents)
- [Claude Code settings](https://code.claude.com/docs/en/settings)
- [Connect Claude Code to tools via MCP](https://code.claude.com/docs/en/mcp)
- [Hooks reference](https://code.claude.com/docs/en/hooks)
- [Extend Claude with skills](https://code.claude.com/docs/en/skills)

置信度说明：

- “Claude Code 如何加载记忆、context 包含什么、session 如何存储、subagent 如何配置、settings/permissions 如何工作”来自官方文档，置信度高。
- “内部源码结构、具体去重算法、auto memory 评分策略”官方未公开，本文不做实现断言。
- 社区和新闻材料仅提示风险背景，未作为本文事实依据。
