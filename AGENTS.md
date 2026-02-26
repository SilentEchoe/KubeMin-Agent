# KubeMin-Agent

KubeMin-Agent is the **Agent Control Plane** of the KubeMin ecosystem. It manages, schedules, validates, and coordinates all sub-agents for cloud-native application management.

## Architecture

```
KubeMin-Agent (Control Plane)
├── control/         Scheduler, Validator, AgentRegistry, AuditLog
├── agents/          Sub-agents: K8sAgent, WorkflowAgent, GeneralAgent
├── agent/           Runtime infrastructure: AgentLoop, ContextBuilder, MemoryStore, Tools
├── providers/       LLM abstraction (LiteLLM gateway)
├── bus/             Async MessageBus (decouples channels from agents)
├── channels/        Channel adapters: CLI, Telegram, etc.
├── session/         JSONL session persistence
├── config/          Pydantic configuration models
├── cron/            Scheduled task service
├── heartbeat/       Proactive wake-up service
├── cli/             Typer CLI commands
└── utils/           Shared helpers
```

## Key Design Decisions

- **Control Plane pattern**: KubeMin-Agent is not an agent itself -- it is the management layer that dispatches tasks to sub-agents via a Scheduler, validates outputs via a Validator, and records all operations via AuditLog.
- **Sub-agent isolation**: Each sub-agent has its own ToolRegistry, system prompt, and security constraints. Tools are never shared across agents.
- **LLM-driven routing**: The Scheduler uses LLM intent analysis (not rule matching) to select the target sub-agent.
- **Shared context**: All sub-agents share one SessionManager and MemoryStore to maintain conversation coherence.
- **Docs-first**: All requirements and technical decisions must be documented in `.md` files before implementation. Agents use `docs/` 中的 markdown 文档作为协作信息源。

## Docs-First Development

本项目遵循 **文档优先 (Docs-First)** 原则。所有新增需求、架构变更、技术方案必须先通过文档拟定，审批后再进入开发。

### 规范

1. **需求先行**: 新功能/重大变更必须先在 `docs/` 中创建或更新对应的 `.md` 文档，明确：
   - 目标与背景
   - 技术方案（含架构图、接口定义）
   - 影响范围与风险评估
   - 验证计划

2. **文档驱动审批**: 技术方案文档是审批的唯一依据。文档未审批前不得开始编码实现。

3. **多 Agent 协作**: 多个 Agent 之间通过 `docs/` 下的 `.md` 文档交换信息：
   - 每个 Agent 拥有自己的文档（如 `docs/game-audit-agent.md`）
   - Agent 间的接口约定、数据格式、调度规则均以文档形式记录
   - Scheduler 调度决策参考 Agent 文档中的 `描述 (description)` 字段

4. **文档即真相**: 当代码行为与文档描述不一致时，以文档为准，代码需要修正。

5. **文档生命周期**: 文档随代码同步更新。功能变更时必须同步更新对应文档。

### 文档目录结构

```
docs/
  design-and-implementation-plan.md   -- 总体设计与实施计划
  game-audit-agent.md                 -- GameAuditAgent 使用文档
  <agent-name>.md                     -- 各 Agent 的使用/协作文档
```

## Tech Stack

- Python >= 3.11, async/await throughout
- `typer` (CLI), `litellm` (LLM gateway), `pydantic` + `pydantic-settings` (config)
- `httpx` (HTTP), `loguru` (logging), `croniter` (cron), `rich` (terminal output)
- `hatchling` (build system), `pytest` + `pytest-asyncio` (testing), `ruff` (linting)

## Code Standards

- PEP 8: `snake_case` for functions/variables/modules, `CamelCase` for classes
- Complete type annotations on all public interfaces
- `async/await` for all I/O operations, propagate cancellation properly
- Custom exceptions with traceable context
- Constants: single-package in nearest `constants.py`, cross-domain in `config/constants.py`
- No emoji in documentation or code comments

## Testing

- Framework: `pytest` with `pytest-asyncio`
- Extend existing `test_*.py` files when possible
- Use `conftest.py` for shared fixtures
- CI gates: `ruff` + `mypy` + `pytest` all passing, >= 70% coverage on core modules

## Communication

- Default language: Chinese
- Documentation: Chinese by default, English when requested
- No emoji in any project artifacts
