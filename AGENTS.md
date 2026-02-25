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
