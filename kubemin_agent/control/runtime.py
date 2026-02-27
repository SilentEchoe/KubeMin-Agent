"""Control plane runtime assembly and message processing."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from loguru import logger

from kubemin_agent.agents.general_agent import GeneralAgent
from kubemin_agent.agents.k8s_agent import K8sAgent
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
        evaluation_enabled: bool = True,
        evaluation_warn_threshold: int = 60,
        evaluation_llm_judge_enabled: bool = True,
        trace_capture: bool = True,
        max_trace_steps: int = 50,
        max_parallelism: int = 4,
        fail_fast: bool = False,
    ) -> None:
        self.provider = provider
        self.workspace = workspace
        self.model = model

        self.sessions = SessionManager(workspace)
        self.audit = AuditLog(workspace.parent)
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
        )

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
        return cls(
            provider=provider,
            workspace=workspace,
            model=config.agents.defaults.model,
            evaluation_enabled=config.evaluation.enabled,
            evaluation_warn_threshold=config.evaluation.warn_threshold,
            evaluation_llm_judge_enabled=config.evaluation.llm_judge_enabled,
            trace_capture=config.evaluation.trace_capture,
            max_trace_steps=config.evaluation.max_trace_steps,
            max_parallelism=config.control.max_parallelism,
            fail_fast=config.control.fail_fast,
        )

    def _register_default_agents(self) -> None:
        """Register built-in sub-agents."""
        self.registry.register(
            GeneralAgent(self.provider, self.sessions, audit=self.audit, workspace=self.workspace)
        )
        self.registry.register(
            K8sAgent(self.provider, self.sessions, audit=self.audit, workspace=self.workspace)
        )
        self.registry.register(
            WorkflowAgent(self.provider, self.sessions, audit=self.audit, workspace=self.workspace)
        )

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
