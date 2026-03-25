"""Control plane runtime assembly and message processing."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from loguru import logger

from kubemin_agent.agent.tools.delegate import create_delegate_tools
from kubemin_agent.agents.game_audit_agent import GameAuditAgent
from kubemin_agent.agents.general_agent import GeneralAgent
from kubemin_agent.agents.guide_agent import GuideAgent
from kubemin_agent.agents.k8s_agent import K8sAgent
from kubemin_agent.agents.orchestrator_agent import OrchestratorAgent
from kubemin_agent.agents.patrol_agent import PatrolAgent
from kubemin_agent.agents.workflow_agent import WorkflowAgent
from kubemin_agent.bus.events import OutboundMessage
from kubemin_agent.bus.queue import MessageBus
from kubemin_agent.config.schema import Config
from kubemin_agent.control.audit import AuditLog
from kubemin_agent.control.evaluation import HybridEvaluator
from kubemin_agent.control.registry import AgentRegistry
from kubemin_agent.control.scheduler import Scheduler
from kubemin_agent.control.validator import Validator
from kubemin_agent.providers.base import LLMProvider
from kubemin_agent.session.manager import SessionManager


class ControlPlaneRuntime:
    """Build and run the default control plane execution pipeline."""

    def __init__(
        self,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_context_tokens: int = 6000,
        min_recent_history_messages: int = 4,
        task_anchor_max_chars: int = 600,
        history_message_max_chars: int = 1200,
        memory_backend: str = "file",
        memory_top_k: int = 5,
        memory_context_max_chars: int = 1400,
        max_tool_iterations: int = 20,
        evaluation_enabled: bool = True,
        evaluation_warn_threshold: int = 60,
        evaluation_llm_judge_enabled: bool = True,
        trace_capture: bool = True,
        max_trace_steps: int = 50,
        max_parallelism: int = 4,
        fail_fast: bool = False,
        kubemin_api_base: str = "",
        kubemin_namespace: str = "",
        orchestration_mode: str = "orchestrated",
        exec_timeout: int = 30,
        exec_restrict_to_workspace: bool = False,
        exec_sandbox_mode: str = "off",
        exec_sandbox_runtime: str = "auto",
        exec_sandbox_allow_network: bool = False,
        storage_retention_days: int = 30,
        audit_file_max_mb: int = 50,
        session_file_max_mb: int = 50,
        session_cache_messages: int = 200,
    ) -> None:
        self.provider = provider
        self.workspace = workspace
        self.model = model
        self.max_context_tokens = max_context_tokens
        self.min_recent_history_messages = min_recent_history_messages
        self.task_anchor_max_chars = task_anchor_max_chars
        self.history_message_max_chars = history_message_max_chars
        self.memory_backend = memory_backend
        self.memory_top_k = memory_top_k
        self.memory_context_max_chars = memory_context_max_chars
        self.max_tool_iterations = max(1, max_tool_iterations)

        self.sessions = SessionManager(
            workspace,
            cache_message_limit=session_cache_messages,
            file_max_mb=session_file_max_mb,
            retention_days=storage_retention_days,
        )
        self.audit = AuditLog(
            workspace.parent,
            retention_days=storage_retention_days,
            file_max_mb=audit_file_max_mb,
        )
        self.validator = Validator()
        self.evaluator = (
            HybridEvaluator(
                provider=provider,
                warn_threshold=evaluation_warn_threshold,
                llm_judge_enabled=evaluation_llm_judge_enabled,
            )
            if evaluation_enabled
            else None
        )
        self.registry = AgentRegistry()
        self.orchestration_mode = orchestration_mode
        self.scheduler = Scheduler(
            provider=provider,
            registry=self.registry,
            validator=self.validator,
            audit=self.audit,
            sessions=self.sessions,
            evaluator=self.evaluator,
            trace_capture=trace_capture,
            max_trace_steps=max_trace_steps,
            max_parallelism=max_parallelism,
            fail_fast=fail_fast,
            orchestration_mode=orchestration_mode,
        )
        self.kubemin_api_base = kubemin_api_base
        self.kubemin_namespace = kubemin_namespace
        self.exec_tool_config = {
            "default_timeout": exec_timeout,
            "restrict_to_workspace": exec_restrict_to_workspace,
            "sandbox_mode": exec_sandbox_mode,
            "sandbox_runtime": exec_sandbox_runtime,
            "sandbox_allow_network": exec_sandbox_allow_network,
        }

        self._running = False
        self._register_default_agents()

    @classmethod
    def from_config(
        cls,
        config: Config,
        provider: LLMProvider,
        workspace: Path,
    ) -> "ControlPlaneRuntime":
        """Create a runtime from the root config."""
        exec_sandbox_mode = config.tools.exec.sandbox_mode
        if exec_sandbox_mode == "off" and config.sandbox.mode == "strict":
            # In strict global mode, upgrade tool-level command execution to strict
            # so the process and tool layers share fail-closed semantics.
            exec_sandbox_mode = "strict"

        return cls(
            provider=provider,
            workspace=workspace,
            model=config.agents.defaults.model,
            max_context_tokens=config.agents.defaults.max_context_tokens,
            min_recent_history_messages=config.agents.defaults.min_recent_history_messages,
            task_anchor_max_chars=config.agents.defaults.task_anchor_max_chars,
            history_message_max_chars=config.agents.defaults.history_message_max_chars,
            memory_backend=config.agents.defaults.memory_backend,
            memory_top_k=config.agents.defaults.memory_top_k,
            memory_context_max_chars=config.agents.defaults.memory_context_max_chars,
            max_tool_iterations=config.agents.defaults.max_tool_iterations,
            evaluation_enabled=config.evaluation.enabled,
            evaluation_warn_threshold=config.evaluation.warn_threshold,
            evaluation_llm_judge_enabled=config.evaluation.llm_judge_enabled,
            trace_capture=config.evaluation.trace_capture,
            max_trace_steps=config.evaluation.max_trace_steps,
            max_parallelism=config.control.max_parallelism,
            fail_fast=config.control.fail_fast,
            kubemin_api_base=config.kubemin.api_base,
            kubemin_namespace=config.kubemin.default_namespace,
            orchestration_mode=config.control.orchestration_mode,
            exec_timeout=config.tools.exec.timeout,
            exec_restrict_to_workspace=config.tools.exec.restrict_to_workspace,
            exec_sandbox_mode=exec_sandbox_mode,
            exec_sandbox_runtime=config.tools.exec.sandbox_runtime,
            exec_sandbox_allow_network=config.tools.exec.sandbox_allow_network,
            storage_retention_days=config.storage.retention_days,
            audit_file_max_mb=config.storage.audit_file_max_mb,
            session_file_max_mb=config.storage.session_file_max_mb,
            session_cache_messages=config.storage.session_cache_messages,
        )

    def _register_default_agents(self) -> None:
        """Register built-in sub-agents."""
        agent_kwargs = {
            "audit": self.audit,
            "workspace": self.workspace,
            "max_context_tokens": self.max_context_tokens,
            "min_recent_history_messages": self.min_recent_history_messages,
            "task_anchor_max_chars": self.task_anchor_max_chars,
            "history_message_max_chars": self.history_message_max_chars,
            "memory_backend": self.memory_backend,
            "memory_top_k": self.memory_top_k,
            "memory_context_max_chars": self.memory_context_max_chars,
            "max_tool_iterations": self.max_tool_iterations,
            "exec_tool_config": self.exec_tool_config,
        }
        self.registry.register(
            GeneralAgent(self.provider, self.sessions, **agent_kwargs)
        )
        self.registry.register(
            K8sAgent(self.provider, self.sessions, **agent_kwargs)
        )
        self.registry.register(
            WorkflowAgent(self.provider, self.sessions, **agent_kwargs)
        )
        self.registry.register(
            PatrolAgent(
                self.provider,
                self.sessions,
                kubemin_api_base=self.kubemin_api_base,
                kubemin_namespace=self.kubemin_namespace,
                **agent_kwargs,
            )
        )
        self.registry.register(
            GuideAgent(self.provider, self.sessions, **agent_kwargs)
        )
        self.registry.register(
            GameAuditAgent(
                self.provider,
                self.sessions,
                audit=self.audit,
                workspace=self.workspace,
                headless=True,
            )
        )

        # --- Orchestrator setup (progressive context mode) ---
        if self.orchestration_mode == "orchestrated":
            delegate_tools = create_delegate_tools(
                registry=self.registry,
                exclude={"orchestrator"},
            )
            orchestrator = OrchestratorAgent(
                provider=self.provider,
                sessions=self.sessions,
                delegate_tools=delegate_tools,
                **agent_kwargs,
            )
            self.registry.register(orchestrator)
            self.scheduler.set_orchestrator(orchestrator)

    async def handle_message(
        self,
        channel: str,
        chat_id: str,
        content: str,
        request_id: str | None = None,
    ) -> str:
        """Handle one inbound message through control plane dispatch."""
        session_key = f"{channel}:{chat_id}"
        dispatch_id = request_id or uuid.uuid4().hex[:12]

        stripped = content.strip()
        if stripped.startswith("/plan "):
            return await self.scheduler.dispatch(
                message=stripped[6:].strip(),
                session_key=session_key,
                request_id=dispatch_id,
                plan_mode=True,
            )
        elif stripped == "/execute":
            return await self.scheduler.execute_saved_plan(
                session_key=session_key,
                request_id=dispatch_id,
            )

        return await self.scheduler.dispatch(
            message=content,
            session_key=session_key,
            request_id=dispatch_id,
        )

    async def run_bus_loop(self, bus: MessageBus) -> None:
        """Consume inbound queue and publish outbound responses."""
        self._running = True
        logger.info("Control plane runtime loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            try:
                request_id = uuid.uuid4().hex[:12]
                response = await self.handle_message(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=msg.content,
                    request_id=request_id,
                )
                await bus.publish_outbound(
                    OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=response)
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"Control plane runtime failed to process message: {e}")

    def stop(self) -> None:
        """Stop bus loop."""
        self._running = False
