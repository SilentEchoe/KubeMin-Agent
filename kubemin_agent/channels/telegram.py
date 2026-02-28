"""Telegram channel implementation using raw HTTP polling."""

import asyncio
from typing import Any

import httpx
from loguru import logger

from kubemin_agent.bus.events import InboundMessage
from kubemin_agent.bus.queue import MessageBus
from kubemin_agent.channels.base import BaseChannel


class TelegramChannel(BaseChannel):
    """
    Telegram integration channel.
    
    Uses httpx for long-polling the getUpdates endpoint.
    Only allows interactions from users specified in allowed_users.
    """

    def __init__(
        self,
        bot_token: str,
        allowed_users: list[int | str],
        bus: MessageBus,
    ) -> None:
        super().__init__(bus)
        self.bot_token = bot_token
        self.allowed_users = [str(u) for u in allowed_users]
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        
        self._running = False
        self._offset = 0
        self._client: httpx.AsyncClient | None = None
        self._poll_task: asyncio.Task[None] | None = None

    @property
    def name(self) -> str:
        return "telegram"

    async def start(self) -> None:
        """Initialize the client and start the polling loop."""
        if not self.bot_token:
            logger.warning("Telegram bot_token is empty. Channel disabled.")
            return

        self._running = True
        self._client = httpx.AsyncClient(timeout=60.0)
        self._poll_task = asyncio.create_task(self._poll_updates())
        logger.info("Telegram channel started.")

    async def stop(self) -> None:
        """Stop polling and close the client."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            
        if self._client:
            await self._client.aclose()
            
        logger.info("Telegram channel stopped.")

    async def send_message(self, chat_id: str, content: str) -> None:
        """Send a message to a specific Telegram chat_id."""
        if not self._client or not self._running:
            logger.warning("Cannot send Telegram message: channel not running.")
            return

        url = f"{self.api_url}/sendMessage"
        payload = {"chat_id": chat_id, "text": content}
        
        try:
            response = await self._client.post(url, json=payload, timeout=10.0)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to send Telegram message to {chat_id}: {e}")

    async def _poll_updates(self) -> None:
        """Long-polling loop for receiving updates."""
        if not self._client:
            return

        url = f"{self.api_url}/getUpdates"
        
        while self._running:
            try:
                payload: dict[str, Any] = {"offset": self._offset, "timeout": 30}
                response = await self._client.get(url, params=payload, timeout=40.0)
                
                if response.status_code != 200:
                    logger.warning(f"Telegram polling returned HTTP {response.status_code}")
                    await asyncio.sleep(2)
                    continue

                data = response.json()
                if not data.get("ok"):
                    logger.error(f"Telegram API error: {data.get('description')}")
                    await asyncio.sleep(2)
                    continue
                    
                updates = data.get("result", [])
                for update in updates:
                    self._offset = max(self._offset, update["update_id"] + 1)
                    await self._process_update(update)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Telegram polling error: {e}")
                await asyncio.sleep(2)

    async def _process_update(self, update: dict[str, Any]) -> None:
        """Process a single incoming Telegram update."""
        message = update.get("message")
        if not message:
            return
            
        text = message.get("text", "")
        if not text:
            return
            
        chat = message.get("chat", {})
        from_user = message.get("from", {})
        
        chat_id = str(chat.get("id"))
        user_id = str(from_user.get("id"))
        username = from_user.get("username", "")
        
        auth_identifier = user_id
        if username and self.allowed_users:
            # allow fallback to @username matching
            if username in self.allowed_users or user_id in self.allowed_users:
                pass
            elif f"@{username}" in self.allowed_users:
                pass
            else:
                logger.warning(f"Unauthorized Telegram user attempted contact: @{username} ({user_id})")
                return
        elif self.allowed_users and user_id not in self.allowed_users:
            logger.warning(f"Unauthorized Telegram user_id attempted contact: {user_id}")
            return
            
        # Wrap into an inbound message and hand to Scheduler via MessageBus
        inbound = InboundMessage(
            channel=self.name,
            chat_id=chat_id,
            content=text,
        )
        
        await self.bus.inbound.put(inbound)
        logger.debug(f"Received Telegram message from {user_id}: {text[:50]}")
