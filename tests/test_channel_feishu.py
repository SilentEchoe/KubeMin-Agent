from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kubemin_agent.bus.events import InboundMessage
from kubemin_agent.bus.queue import MessageBus
from kubemin_agent.channels.feishu import FeishuChannel


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def channel(bus):
    with patch("time.time", return_value=1000.0):
        return FeishuChannel(
            app_id="cli_123",
            app_secret="sec_456",
            verification_token="vt_789",
            allowed_users=["ou_admin123"],
            bus=bus,
        )


@pytest.mark.asyncio
async def test_feishu_disabled_on_empty_token(bus):
    empty_channel = FeishuChannel("", "", "", [], bus)
    await empty_channel.start()
    assert empty_channel._running is False
    assert empty_channel._client is None


@pytest.mark.asyncio
async def test_feishu_token_acquisition(channel):
    channel._client = AsyncMock()

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "code": 0,
        "msg": "ok",
        "tenant_access_token": "t-mocked-token",
        "expire": 7200
    }
    channel._client.post.return_value = mock_response

    with patch("time.time", return_value=1000.0):
        await channel._ensure_token()

    assert channel._tenant_access_token == "t-mocked-token"
    # 1000 + 7200 - 300
    assert channel._token_expire_time == 7900.0

    # Subsequent calls should not hit the API if time has not passed
    with patch("time.time", return_value=2000.0):
        await channel._ensure_token()
        assert channel._client.post.call_count == 1


@pytest.mark.asyncio
async def test_feishu_process_webhook_valid(channel):
    channel._client = AsyncMock()
    channel._running = True

    payload = {
        "header": {
            "event_type": "im.message.receive_v1"
        },
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou_admin123"}
            },
            "message": {
                "chat_id": "oc_testgroup",
                "message_type": "text",
                "content": '{"text":"@_user_1 list namespaces"}'
            }
        }
    }

    await channel._process_webhook(payload)

    assert not channel.bus.inbound.empty()
    msg: InboundMessage = await channel.bus.inbound.get()

    assert msg.channel == "feishu"
    # By default Feishu logic replies to sender open_id directly (unless explicitly group configured)
    assert msg.chat_id == "ou_admin123"
    assert msg.content == "list namespaces"


@pytest.mark.asyncio
async def test_feishu_process_webhook_unauthorized(channel):
    channel._client = AsyncMock()
    channel._running = True

    payload = {
        "header": {
            "event_type": "im.message.receive_v1"
        },
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou_hacker999"}
            },
            "message": {
                "chat_id": "oc_testgroup",
                "message_type": "text",
                "content": '{"text":"drop tables"}'
            }
        }
    }

    await channel._process_webhook(payload)
    assert channel.bus.inbound.empty()


@pytest.mark.asyncio
async def test_feishu_send_message(channel):
    channel._client = AsyncMock()
    channel._running = True
    channel._tenant_access_token = "t-valid"

    # Mocking ensure token to pass immediately
    with patch.object(channel, "_ensure_token", new_callable=AsyncMock) as mock_ensure:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"code": 0}
        channel._client.post.return_value = mock_response

        await channel.send_message("ou_admin123", "Task done")

        mock_ensure.assert_called_once()
        channel._client.post.assert_called_once()
        args, kwargs = channel._client.post.call_args

        assert "im/v1/messages" in args[0]
        assert kwargs["headers"]["Authorization"] == "Bearer t-valid"
        assert kwargs["json"]["receive_id"] == "ou_admin123"
        assert "Task done" in kwargs["json"]["content"]


@pytest.mark.asyncio
async def test_feishu_start_and_stop_success(channel):
    with patch.object(channel, "_ensure_token", new_callable=AsyncMock):
        await channel.start()
    assert channel._running is True
    assert channel._client is not None
    await channel.stop()
    assert channel._running is False


@pytest.mark.asyncio
async def test_feishu_start_handles_token_failure(channel):
    with patch.object(
        channel,
        "_ensure_token",
        new_callable=AsyncMock,
        side_effect=RuntimeError("token error"),
    ):
        await channel.start()
    assert channel._running is False


@pytest.mark.asyncio
async def test_feishu_ensure_token_without_client(channel):
    channel._client = None
    channel._tenant_access_token = None
    await channel._ensure_token()


@pytest.mark.asyncio
async def test_feishu_ensure_token_raises_when_api_rejects(channel):
    channel._client = AsyncMock()
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"code": 999, "msg": "invalid app"}
    channel._client.post.return_value = mock_response

    with pytest.raises(Exception, match="Failed to get Feishu token"):
        await channel._ensure_token()


@pytest.mark.asyncio
async def test_feishu_send_message_not_running(channel):
    channel._running = False
    channel._client = None
    await channel.send_message("ou_admin123", "Task done")


@pytest.mark.asyncio
async def test_feishu_send_message_token_refresh_error(channel):
    channel._client = AsyncMock()
    channel._running = True
    with patch.object(
        channel,
        "_ensure_token",
        new_callable=AsyncMock,
        side_effect=RuntimeError("refresh failed"),
    ):
        await channel.send_message("ou_admin123", "Task done")


@pytest.mark.asyncio
async def test_feishu_send_message_logs_api_code_error(channel):
    channel._client = AsyncMock()
    channel._running = True
    channel._tenant_access_token = "t-valid"
    with patch.object(channel, "_ensure_token", new_callable=AsyncMock):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"code": 999, "msg": "send failed"}
        channel._client.post.return_value = mock_response
        await channel.send_message("ou_admin123", "Task done")


@pytest.mark.asyncio
async def test_feishu_process_webhook_ignores_non_message_event(channel):
    channel._running = True
    await channel._process_webhook({"header": {"event_type": "other"}, "event": {}})
    assert channel.bus.inbound.empty()


@pytest.mark.asyncio
async def test_feishu_process_webhook_ignores_non_text(channel):
    channel._running = True
    payload = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_admin123"}},
            "message": {"message_type": "image", "content": "{}"},
        },
    }
    await channel._process_webhook(payload)
    assert channel.bus.inbound.empty()


@pytest.mark.asyncio
async def test_feishu_process_webhook_handles_json_decode_and_empty_text(channel):
    channel._running = True
    payload = {
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_admin123"}},
            "message": {"message_type": "text", "content": "@_user_1"},
        },
    }
    await channel._process_webhook(payload)
    assert channel.bus.inbound.empty()
