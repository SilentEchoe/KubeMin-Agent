# Context Index (项目上下文索引)

KubeMin-Agent 的上下文入口，帮助快速定位关键信息。

---

## 核心概念

| 概念 | 说明 |
|------|------|
| **AgentLoop** | 核心引擎：从消息总线拉取消息 → 构建上下文 → 调用 LLM → 执行工具 → 回送响应 |
| **MessageBus** | 异步消息总线，解耦 Channel 与 Agent 核心 |
| **ToolRegistry** | 工具注册表，管理工具的注册、校验与执行 |
| **LLMProvider** | LLM 供应商抽象，统一不同模型的调用接口 |
| **ContextBuilder** | 上下文装配器，拼装 identity + bootstrap + memory + skills + history |
| **Session** | 会话管理，JSONL 持久化对话历史 |
| **Memory** | 持久记忆，长期记忆 + 每日记忆的文件存储 |
| **Skills** | 技能系统，支持 always 加载与延迟加载 |
| **Channel** | 通道接入，负责平台对接与消息格式转换 |

---

## 目录结构

| 目录 | 职责 |
|------|------|
| `agent/` | 核心 Agent 逻辑（loop、context、memory、skills、subagent） |
| `agent/tools/` | 工具系统（base、registry、filesystem、shell、web、message、spawn） |
| `providers/` | LLM Provider 抽象与实现 |
| `bus/` | 消息总线（events、queue） |
| `channels/` | 通道接入（base、manager、telegram、whatsapp） |
| `session/` | 会话管理 |
| `config/` | 配置模型（schema、loader） |
| `cron/` | 定时任务（service、types） |
| `heartbeat/` | 心跳服务 |
| `skills/` | 内置技能集 |
| `cli/` | CLI 命令入口 |
| `utils/` | 通用工具函数 |

---

## 关键接口（冻结优先）

| 接口 | 签名 |
|------|------|
| LLMProvider.chat | `chat(messages, tools, model, max_tokens, temperature) -> LLMResponse` |
| Tool.execute | `execute(**kwargs) -> str` |
| MessageBus | `publish_inbound / consume_inbound / publish_outbound / consume_outbound` |
| SessionManager | `get_or_create / save` |

---

## 常用命令

```bash
# 单测
pytest tests/

# 格式化与检查
ruff check .
ruff format .

# 类型检查
mypy .

# 运行 Agent（CLI 模式）
python -m kubemin_agent agent -m "Hello"

# 启动 Gateway
python -m kubemin_agent gateway
```

---

## 快速链接

- [SKILL 规范](../SKILL.md) - 开发规则与交付流程
- [Context Packet](./context-packet.md) - 提需求模板

---

## 术语

| 术语 | 含义 |
|------|------|
| user-facing behavior | 用户可见行为（CLI 输出、配置语义、日志契约） |
| error contract | 错误契约（异常类型/码及调用方依赖方式） |
| tool call loop | 工具调用循环（LLM 请求工具 → 执行 → 回填结果 → 再次调用 LLM） |
| bootstrap files | 启动文件（AGENTS.md、SOUL.md、USER.md 等系统提示词组件） |
| session key | 会话标识（格式：`channel:chat_id`） |
