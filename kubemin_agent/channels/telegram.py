"""Telegram inbound identity mapping."""

from __future__ import annotations

from typing import Any, Sequence

from kubemin_agent.bus.events import InboundMessage
from kubemin_agent.bus.queue import MessageBus
from kubemin_agent.channels.base import BaseChannel


class TelegramChannel(BaseChannel):
    """Minimal Telegram channel adapter used by the new runtime baseline."""

    def __init__(
        self,
        bot_token: str,
        allowed_users: Sequence[int | str],
        bus: MessageBus,
        tenant_id: str = "default",
        team_id: str = "",
    ) -> None:
        super().__init__(bus=bus, tenant_id=tenant_id, team_id=team_id)
        self.bot_token = bot_token
        self.allowed_users = [str(user) for user in allowed_users]

    @property
    def name(self) -> str:
        return "telegram"

    async def send_message(self, chat_id: str, content: str) -> None:
        """Sending is intentionally left to a future HTTP adapter."""

    async def process_update(self, update: dict[str, Any]) -> None:
        """Convert a Telegram update into an InboundMessage."""
        message = update.get("message") or {}
        text = message.get("text") or ""
        if not text:
            return

        chat = message.get("chat") or {}
        from_user = message.get("from") or {}
        chat_id = str(chat.get("id") or "")
        user_id = str(from_user.get("id") or "")
        username = str(from_user.get("username") or "")

        if self.allowed_users and not self._is_allowed(user_id, username):
            return

        metadata = {"tenant_id": self.tenant_id, "username": username}
        if self.team_id:
            metadata["team_id"] = self.team_id

        await self.bus.publish_inbound(
            InboundMessage(
                channel=self.name,
                chat_id=chat_id,
                content=text,
                sender=user_id or username or "local",
                metadata=metadata,
            )
        )

    def _is_allowed(self, user_id: str, username: str) -> bool:
        return (
            user_id in self.allowed_users
            or username in self.allowed_users
            or (username and f"@{username}" in self.allowed_users)
        )
