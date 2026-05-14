import pytest

from kubemin_agent.bus.events import InboundMessage
from kubemin_agent.bus.queue import MessageBus
from kubemin_agent.channels.feishu import FeishuChannel
from kubemin_agent.channels.telegram import TelegramChannel


def test_inbound_message_defaults_to_local_default_scope() -> None:
    msg = InboundMessage(channel="cli", chat_id="direct", content="hello")

    assert msg.user_id == "local"
    assert msg.tenant_id == "default"
    assert msg.team_id == ""


@pytest.mark.asyncio
async def test_telegram_sets_sender_and_tenant() -> None:
    bus = MessageBus()
    channel = TelegramChannel("token", ["123"], bus, tenant_id="tenant-a")

    await channel.process_update(
        {
            "message": {
                "text": "hello",
                "chat": {"id": 456},
                "from": {"id": 123, "username": "alice"},
            }
        }
    )

    msg = await bus.inbound.get()
    assert msg.sender == "123"
    assert msg.user_id == "123"
    assert msg.tenant_id == "tenant-a"
    assert msg.team_id == ""


@pytest.mark.asyncio
async def test_telegram_passes_explicit_team_id_without_chat_fallback() -> None:
    bus = MessageBus()
    channel = TelegramChannel("token", ["123"], bus, tenant_id="tenant-a", team_id="platform")

    await channel.process_update(
        {
            "message": {
                "text": "hello",
                "chat": {"id": 456},
                "from": {"id": 123, "username": "alice"},
            }
        }
    )

    msg = await bus.inbound.get()
    assert msg.team_id == "platform"


@pytest.mark.asyncio
async def test_feishu_sets_sender_and_tenant() -> None:
    bus = MessageBus()
    channel = FeishuChannel(["open-1"], bus, tenant_id="tenant-b")

    await channel.process_webhook(
        {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "open-1"}},
                "message": {"message_type": "text", "content": '{"text":"hello"}'},
            },
        }
    )

    msg = await bus.inbound.get()
    assert msg.sender == "open-1"
    assert msg.user_id == "open-1"
    assert msg.tenant_id == "tenant-b"
    assert msg.team_id == ""


@pytest.mark.asyncio
async def test_feishu_passes_explicit_team_id_without_chat_fallback() -> None:
    bus = MessageBus()
    channel = FeishuChannel(["open-1"], bus, tenant_id="tenant-b", team_id="sre")

    await channel.process_webhook(
        {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "open-1"}},
                "message": {"message_type": "text", "content": '{"text":"hello"}'},
            },
        }
    )

    msg = await bus.inbound.get()
    assert msg.team_id == "sre"
