"""Tests for LiteLLM Provider."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kubemin_agent.providers.litellm_provider import LiteLLMProvider


@pytest.fixture
def provider():
    """Create a default provider."""
    return LiteLLMProvider(api_key="test-key", default_model="test/model")


@pytest.mark.asyncio
async def test_chat_basic(provider):
    """Test basic chat completion without tools."""
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Hello there!"
    mock_choice.message.tool_calls = None
    mock_choice.finish_reason = "stop"
    mock_response.choices = [mock_choice]
    
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 20
    mock_response.usage.total_tokens = 30

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.return_value = mock_response

        response = await provider.chat([{"role": "user", "content": "Hi"}])

        # Verify litellm call
        mock_acompletion.assert_called_once()
        kwargs = mock_acompletion.call_args.kwargs
        assert kwargs["model"] == "test/model"
        assert kwargs["api_key"] == "test-key"
        assert kwargs["messages"] == [{"role": "user", "content": "Hi"}]

        # Verify response parsing
        assert response.content == "Hello there!"
        assert not response.has_tool_calls
        assert response.finish_reason == "stop"
        assert response.usage == {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        }


@pytest.mark.asyncio
async def test_chat_with_tool_calls(provider):
    """Test chat completion that returns tool calls."""
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = None
    
    mock_tc1 = MagicMock()
    mock_tc1.id = "call_1"
    mock_tc1.function.name = "get_weather"
    mock_tc1.function.arguments = '{"location": "Tokyo"}'
    
    # Test fallback parsing when JSON is invalid
    mock_tc2 = MagicMock()
    mock_tc2.id = "call_2"
    mock_tc2.function.name = "bad_json_tool"
    mock_tc2.function.arguments = 'not valid json'

    mock_choice.message.tool_calls = [mock_tc1, mock_tc2]
    mock_choice.finish_reason = "tool_calls"
    mock_response.choices = [mock_choice]
    mock_response.usage = None

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.return_value = mock_response

        tools_schema = [{"type": "function", "function": {"name": "get_weather"}}]
        response = await provider.chat(
            [{"role": "user", "content": "Weather in Tokyo?"}],
            tools=tools_schema,
            model="specific/model"
        )

        mock_acompletion.assert_called_once()
        assert mock_acompletion.call_args.kwargs["model"] == "specific/model"
        assert mock_acompletion.call_args.kwargs["tools"] == tools_schema

        assert response.has_tool_calls
        assert len(response.tool_calls) == 2
        
        tc1 = response.tool_calls[0]
        assert tc1.name == "get_weather"
        assert tc1.arguments == {"location": "Tokyo"}
        
        tc2 = response.tool_calls[1]
        assert tc2.name == "bad_json_tool"
        assert tc2.arguments == {"raw": "not valid json"}


def test_get_default_model(provider):
    """Test getting default model."""
    assert provider.get_default_model() == "test/model"
