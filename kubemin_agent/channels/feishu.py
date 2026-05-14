"""Feishu inbound identity mapping."""

from __future__ import annotations

import json
from typing import Any, Sequence

from kubemin_agent.bus.events import InboundMessage
from kubemin_agent.bus.queue import MessageBus
from kubemin_agent.channels.base import BaseChannel


class FeishuChannel(BaseChannel):
    """Minimal Feishu channel adapter used by the new runtime baseline."""

    def __init__(
        self,
        allowed_users: Sequence[int | str],
        bus: MessageBus,
        tenant_id: str = "default",
        team_id: str = "",
    ) -> None:
        super().__init__(bus=bus, tenant_id=tenant_id, team_id=team_id)
        self.allowed_users = [str(user) for user in allowed_users]

    @property
    def name(self) -> str:
        return "feishu"

    async def send_message(self, chat_id: str, content: str) -> None:
        """Sending is intentionally left to a future HTTP adapter."""

    async def process_webhook(self, event_data: dict[str, Any]) -> None:
        """Convert a Feishu webhook event into an InboundMessage."""
        header = event_data.get("header") or {}
        if header.get("event_type") != "im.message.receive_v1":
            return
        event = event_data.get("event") or {}
        message = event.get("message") or {}
        sender = event.get("sender") or {}
        sender_id = str((sender.get("sender_id") or {}).get("open_id") or "")
        if self.allowed_users and sender_id not in self.allowed_users:
            return
        if message.get("message_type") != "text":
            return

        raw_content = message.get("content") or ""
        try:
            text = json.loads(raw_content).get("text", "")
        except json.JSONDecodeError:
            text = raw_content
        text = text.replace("@_user_1", "").strip()
        if not text:
            return

        metadata = {"tenant_id": self.tenant_id}
        if self.team_id:
            metadata["team_id"] = self.team_id

        await self.bus.publish_inbound(
            InboundMessage(
                channel=self.name,
                chat_id=sender_id,
                content=text,
                sender=sender_id or "local",
                metadata=metadata,
            )
        )
