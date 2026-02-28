import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from kubemin_agent.bus.events import InboundMessage
from kubemin_agent.bus.queue import MessageBus
from kubemin_agent.channels.telegram import TelegramChannel


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def channel(bus):
    return TelegramChannel(
        bot_token="test_token",
        allowed_users=["12345", "@admin_user"],
        bus=bus,
    )


@pytest.mark.asyncio
async def test_telegram_channel_start_stop(channel):
    # Test valid start
    await channel.start()
    assert channel._running is True
    assert channel._client is not None
    assert channel._poll_task is not None

    # Test stop cleanly cancels task
    await channel.stop()
    assert channel._running is False
    assert channel._poll_task.cancelled() or channel._poll_task.done()


@pytest.mark.asyncio
async def test_telegram_disabled_on_empty_token(bus):
    empty_channel = TelegramChannel("", [], bus)
    await empty_channel.start()
    assert empty_channel._running is False
    assert empty_channel._client is None


@pytest.mark.asyncio
async def test_telegram_process_update_valid(channel):
    channel._running = True
    
    update = {
        "message": {
            "text": "Hello world",
            "from": {"id": 12345, "username": "someuser"},
            "chat": {"id": 67890}
        }
    }

    # Process payload
    await channel._process_update(update)

    # Verify message entered the bus
    assert not channel.bus.inbound.empty()
    msg: InboundMessage = await channel.bus.inbound.get()
    
    assert msg.channel == "telegram"
    assert msg.chat_id == "67890"
    assert msg.content == "Hello world"


@pytest.mark.asyncio
async def test_telegram_process_update_valid_by_username(channel):
    channel._running = True
    
    update = {
        "message": {
            "text": "Admin ping",
            "from": {"id": 99999, "username": "admin_user"},
            "chat": {"id": 11111}
        }
    }

    await channel._process_update(update)
    assert not channel.bus.inbound.empty()


@pytest.mark.asyncio
async def test_telegram_process_update_unauthorized(channel):
    channel._running = True
    
    update = {
        "message": {
            "text": "I am a hacker",
            "from": {"id": 666, "username": "evil_hacker"},
            "chat": {"id": 666}
        }
    }

    await channel._process_update(update)
    
    # Bus must be empty
    assert channel.bus.inbound.empty()


@pytest.mark.asyncio
async def test_telegram_send_message(channel):
    channel._running = True
    channel._client = AsyncMock()
    
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    channel._client.post.return_value = mock_response
    
    await channel.send_message("67890", "Reply text")
    
    channel._client.post.assert_called_once()
    args, kwargs = channel._client.post.call_args
    assert args[0] == "https://api.telegram.org/bottest_token/sendMessage"
    assert kwargs["json"] == {"chat_id": "67890", "text": "Reply text"}
