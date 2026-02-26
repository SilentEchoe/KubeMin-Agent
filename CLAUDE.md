# KubeMin-Agent

KubeMin-Agent is the **Agent Control Plane** of the KubeMin ecosystem -- a management layer that schedules, validates, and coordinates sub-agents for cloud-native operations.

## Project Structure

```
kubemin_agent/
  control/     - Control plane: Scheduler, Validator, AgentRegistry, AuditLog
  agents/      - Sub-agents: BaseAgent, K8sAgent, WorkflowAgent, GeneralAgent
  agent/       - Runtime: AgentLoop, ContextBuilder, MemoryStore, SkillsLoader, tools/
  providers/   - LLM provider abstraction + LiteLLM implementation
  bus/         - Async MessageBus with InboundMessage/OutboundMessage
  channels/    - BaseChannel, ChannelManager (CLI, Telegram)
  session/     - JSONL-persisted SessionManager
  config/      - Pydantic config schema + loader
  cron/        - CronService (cron/every/at schedules)
  heartbeat/   - HeartbeatService
  cli/         - Typer commands: onboard, agent, status, gateway
  utils/       - truncate_output, sanitize_session_key, format_error
```

## Architecture

The system follows a **Control Plane + Sub-Agent** pattern:

1. User message arrives via Channel -> MessageBus
2. **Scheduler** analyzes intent via LLM, creates a DispatchPlan
3. Scheduler dispatches to the appropriate **sub-agent** (K8sAgent / WorkflowAgent / GeneralAgent)
4. Sub-agent executes its LLM + tool call loop using its own ToolRegistry
5. **Validator** checks the output for safety and quality
6. **AuditLog** records the full trace
7. Result returns to user via MessageBus -> Channel

## Commands

```bash
pip install -e ".[dev]"          # Install with dev deps
python -m kubemin_agent agent -m "hello"  # Single message
python -m kubemin_agent agent    # Interactive mode
python -m kubemin_agent status   # Show config
python -m kubemin_agent onboard  # Initialize config
pytest                           # Run tests
ruff check .                     # Lint
```

## Code Conventions

- Python >= 3.11, fully async
- `snake_case` functions/variables, `CamelCase` classes
- Complete type hints on all public APIs
- `loguru` for logging, `pydantic` for config/validation
- Tests in `tests/` using `pytest` + `pytest-asyncio`
- No emoji in docs or comments
- Default communication language: Chinese
- **Docs-first**: new features/changes require a `.md` doc in `docs/` before implementation; agents coordinate via markdown documents

