"""Agent loop: the core processing engine."""

import asyncio
import json
from pathlib import Path

from loguru import logger

from kubemin_agent.agent.context import ContextBuilder
from kubemin_agent.agent.subagent import SubagentManager
from kubemin_agent.agent.tools.registry import ToolRegistry
from kubemin_agent.bus.events import InboundMessage, OutboundMessage
from kubemin_agent.bus.queue import MessageBus
from kubemin_agent.providers.base import LLMProvider
from kubemin_agent.session.manager import SessionManager


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 20,
    ) -> None:
        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model
        self.max_iterations = max_iterations

        self.context = ContextBuilder(workspace)
        self.tools = ToolRegistry()
        self.sessions = SessionManager(workspace)
        self.subagents = SubagentManager()

        self._running = False

    async def run(self) -> None:
        """Run the agent loop, processing messages from the bus."""
        self._running = True
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
                response = await self._process_message(msg)
                if response:
                    await self.bus.publish_outbound(
                        OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content=response,
                        )
                    )
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing message: {e}")

    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopped")

    async def _process_message(self, msg: InboundMessage) -> str | None:
        """
        Process a single inbound message.

        Args:
            msg: The inbound message to process.

        Returns:
            The response message, or None if no response needed.
        """
        session_key = f"{msg.channel}:{msg.chat_id}"
        logger.info(f"Processing message from {session_key}")

        # Load session history
        history = self.sessions.get_history(session_key)

        # Build messages with context
        messages = self.context.build_messages(
            history=history,
            current_message=msg.content,
        )

        # Tool call loop
        for iteration in range(self.max_iterations):
            # Call LLM
            tool_definitions = self.tools.get_definitions() if len(self.tools) > 0 else None
            response = await self.provider.chat(
                messages=messages,
                tools=tool_definitions,
                model=self.model,
            )

            if not response.has_tool_calls:
                # No tool calls - save and return response
                result = response.content or ""
                self.sessions.save_turn(session_key, msg.content, result)
                return result

            # Execute tool calls
            self.context.add_assistant_message(
                messages,
                content=response.content,
                tool_calls=[
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in response.tool_calls
                ],
            )

            for tc in response.tool_calls:
                logger.debug(f"Executing tool: {tc.name}")
                result = await self.tools.execute(tc.name, tc.arguments)
                self.context.add_tool_result(messages, tc.id, tc.name, result)

        # Exceeded max iterations
        fallback = "I've reached the maximum number of tool iterations. Here's what I have so far."
        self.sessions.save_turn(session_key, msg.content, fallback)
        return fallback

    async def process_direct(self, content: str, session_key: str = "cli:direct") -> str:
        """
        Process a message directly (for CLI usage).

        Args:
            content: The message content.
            session_key: Session identifier.

        Returns:
            The agent's response.
        """
        msg = InboundMessage(
            channel="cli",
            chat_id="direct",
            content=content,
        )
        return await self._process_message(msg) or ""
