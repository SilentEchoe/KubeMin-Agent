"""Tests for AgentLoop."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from kubemin_agent.agent.loop import AgentLoop
from kubemin_agent.bus.events import InboundMessage
from kubemin_agent.bus.queue import MessageBus
from kubemin_agent.providers.base import LLMResponse, ToolCallRequest


@pytest.fixture
def workspace(tmp_path: Path):
    """Temporary workspace."""
    return tmp_path


@pytest.fixture
def agent_loop(workspace):
    """Create an AgentLoop instance with mocked dependencies."""
    bus = MessageBus()
    provider = AsyncMock()

    loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=workspace,
        max_iterations=3,
    )
    # Mock context builder to avoid complex system prompt generation
    loop.context = MagicMock()
    loop.context.build_messages.return_value = [{"role": "user", "content": "hello"}]
    loop.context.build_task_reminder.return_value = "reminder"
    loop.context.add_assistant_message = MagicMock()
    loop.context.add_tool_result = MagicMock()

    # Session manager stub
    loop.sessions = MagicMock()
    loop.sessions.get_history.return_value = []

    return loop


@pytest.mark.asyncio
async def test_agent_loop_direct_process_no_tools(agent_loop):
    """Test process_direct when LLM returns simple text without tool calls."""
    # Setup provider mock
    mock_response = LLMResponse(content="Hi!", finish_reason="stop", tool_calls=[])
    agent_loop.provider.chat.return_value = mock_response

    result = await agent_loop.process_direct("hello")

    assert result == "Hi!"
    agent_loop.provider.chat.assert_called_once()
    agent_loop.sessions.save_turn.assert_called_once_with("cli:direct", "hello", "Hi!")


@pytest.mark.asyncio
async def test_agent_loop_tool_calls(agent_loop):
    """Test the tool iteration loop."""
    # First LLM call: return a tool call
    tc_req = ToolCallRequest(id="call_1", name="dummy_tool", arguments={"a": 1})
    resp1 = LLMResponse(content=None, finish_reason="tool_calls", tool_calls=[tc_req])

    # Second LLM call: return final answer
    resp2 = LLMResponse(content="Final answer", finish_reason="stop", tool_calls=[])

    agent_loop.provider.chat.side_effect = [resp1, resp2]

    # Mock tool registry
    agent_loop.tools = AsyncMock()
    agent_loop.tools.__len__.return_value = 1
    agent_loop.tools.execute.return_value = "Tool result"

    result = await agent_loop.process_direct("hello")

    assert result == "Final answer"
    assert agent_loop.provider.chat.call_count == 2
    agent_loop.tools.execute.assert_called_once_with("dummy_tool", {"a": 1})


@pytest.mark.asyncio
async def test_agent_loop_max_iterations(agent_loop):
    """Test the loop breaking when max_iterations is reached."""
    # Always return a tool call
    tc_req = ToolCallRequest(id="call_1", name="dummy_tool", arguments={})
    resp = LLMResponse(content=None, finish_reason="tool_calls", tool_calls=[tc_req])
    agent_loop.provider.chat.return_value = resp

    # Mock tool registry
    agent_loop.tools = AsyncMock()
    agent_loop.tools.__len__.return_value = 1
    agent_loop.tools.execute.return_value = "Tool result"

    result = await agent_loop.process_direct("hello")

    assert "maximum number of tool iterations" in result
    assert agent_loop.provider.chat.call_count == agent_loop.max_iterations


@pytest.mark.asyncio
async def test_agent_loop_run_bus_listener(agent_loop):
    """Test the main run loop processing bus messages."""

    # Mock _process_message
    async def mock_process(msg):
        if msg.content == "STOP":
            agent_loop.stop()
            return None
        return f"Reply to {msg.content}"

    agent_loop._process_message = mock_process

    # Send messages
    await agent_loop.bus.publish_inbound(InboundMessage(channel="test", chat_id="1", content="Hi"))
    await agent_loop.bus.publish_inbound(InboundMessage(channel="test", chat_id="1", content="STOP"))

    # Run loop
    await agent_loop.run()

    # Check outbound
    outbound = []
    while not agent_loop.bus.outbound.empty():
        outbound.append(await agent_loop.bus.consume_outbound())

    assert len(outbound) == 1
    assert outbound[0].content == "Reply to Hi"


@pytest.mark.asyncio
async def test_agent_loop_circuit_breaker(agent_loop):
    """Test that the agent loop breaks early after consecutive tool errors."""
    
    # Always return a tool call
    tc_req = ToolCallRequest(id="call_error", name="fail_tool", arguments={})
    resp = LLMResponse(content=None, finish_reason="tool_calls", tool_calls=[tc_req])
    agent_loop.provider.chat.return_value = resp

    # Mock tool registry to ALWAYS RAISE an exception
    agent_loop.tools = AsyncMock()
    agent_loop.tools.__len__.return_value = 1
    agent_loop.tools.execute.side_effect = Exception("Simulated tool crash")

    result = await agent_loop.process_direct("break me")

    # The breaker is hardcoded to 3 in AgentLoop
    assert "too many consecutive tool execution errors" in result
    
    # Provider chat should have been called 3 times exactly
    assert agent_loop.provider.chat.call_count == 3
    assert agent_loop.tools.execute.call_count == 3
