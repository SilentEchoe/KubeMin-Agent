"""Feishu (Lark) channel implementation using raw HTTP polling."""

import asyncio
from typing import Any

import httpx
from loguru import logger

from kubemin_agent.bus.events import InboundMessage
from kubemin_agent.bus.queue import MessageBus
from kubemin_agent.channels.base import BaseChannel


class FeishuChannel(BaseChannel):
    """
    Feishu (Lark) integration channel.
    
    Uses httpx for token acquisition and polling for simplicity.
    Only allows interactions from users specified in allowed_users.
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        verification_token: str,
        allowed_users: list[int | str],
        bus: MessageBus,
    ) -> None:
        super().__init__(bus)
        self.app_id = app_id
        self.app_secret = app_secret
        self.verification_token = verification_token
        self.allowed_users = [str(u) for u in allowed_users]
        self.api_url = "https://open.feishu.cn/open-apis"
        
        self._running = False
        self._client: httpx.AsyncClient | None = None
        self._tenant_access_token: str | None = None
        self._token_expire_time: float = 0.0

    @property
    def name(self) -> str:
        return "feishu"

    async def start(self) -> None:
        """Initialize the client and prepare to receive updates."""
        if not self.app_id or not self.app_secret:
            logger.warning("Feishu app_id or app_secret is empty. Channel disabled.")
            return

        self._running = True
        self._client = httpx.AsyncClient(timeout=30.0)
        
        # Verify token fetching works on startup
        try:
            await self._ensure_token()
            logger.info("Feishu channel started: successfully acquired tenant token.")
        except Exception as e:
            logger.error(f"Feishu channel failed to acquire initial token: {e}")
            self._running = False
            if self._client:
                await self._client.aclose()
            return

        # Note: In a production environment, Feishu generally pushes events via Webhooks (HTTP POST).
        # To avoid standing up an entire external web server dependency just for the agent channel,
        # users would typically expose a minimal FastAPI endpoint that calls `_process_webhook` 
        # or use Feishu's newer WebSocket protocol (which is beyond standard httpx polling).
        # We define the inbound schema logic below so external webhook routers evaluate into MessageBus.
        logger.info("Feishu channel ready for inbound webhook processing.")

    async def stop(self) -> None:
        """Stop processing and close the client."""
        self._running = False
        if self._client:
            await self._client.aclose()
            
        logger.info("Feishu channel stopped.")

    async def _ensure_token(self) -> None:
        """Fetch or refresh the tenant access token if necessary."""
        import time
        
        if self._tenant_access_token and time.time() < self._token_expire_time:
            return
            
        if not self._client:
            return

        url = f"{self.api_url}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": self.app_id,
            "app_secret": self.app_secret,
        }
        
        response = await self._client.post(url, json=payload, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") != 0:
            raise Exception(f"Failed to get Feishu token: {data.get('msg')}")
            
        self._tenant_access_token = data.get("tenant_access_token")
        expire = data.get("expire", 7200)
        self._token_expire_time = time.time() + expire - 300  # refresh 5 min early

    async def send_message(self, chat_id: str, content: str) -> None:
        """Send a message to a specific Feishu chat_id using the im/v1/messages API."""
        if not self._client or not self._running:
            logger.warning("Cannot send Feishu message: channel not running.")
            return

        try:
            await self._ensure_token()
        except Exception as e:
            logger.error(f"Feishu failed to refresh token for sending: {e}")
            return

        url = f"{self.api_url}/im/v1/messages"
        headers = {
            "Authorization": f"Bearer {self._tenant_access_token}",
            "Content-Type": "application/json"
        }
        params = {"receive_id_type": "open_id"}
        payload = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": f'{{"text":"{content}"}}'
        }
        
        try:
            response = await self._client.post(
                url, headers=headers, params=params, json=payload, timeout=10.0
            )
            response.raise_for_status()
            
            data = response.json()
            if data.get("code") != 0:
                logger.error(f"Feishu message send error: {data.get('msg')}")
        except Exception as e:
            logger.error(f"Failed to send Feishu message to {chat_id}: {e}")

    async def _process_webhook(self, event_data: dict[str, Any]) -> None:
        """
        Process a single incoming Feishu webhook event (im.message.receive_v1).
        This method is meant to be called by an HTTP server endpoint receiving Feishu POSTs.
        """
        header = event_data.get("header", {})
        event = event_data.get("event", {})
        
        if header.get("event_type") != "im.message.receive_v1":
            return
            
        message = event.get("message", {})
        sender = event.get("sender", {})
        
        chat_id = message.get("chat_id", "")
        msg_type = message.get("message_type")
        content_json = message.get("content", "")
        sender_id = sender.get("sender_id", {}).get("open_id", "")
        
        if msg_type != "text" or not content_json:
            return
            
        try:
            import json
            parsed_content = json.loads(content_json)
            text = parsed_content.get("text", "")
        except json.JSONDecodeError:
            text = content_json
            
        text = text.replace("@_user_1", "").strip() # Remove generic at-mentions from the bot
        
        if not text:
            return
            
        if self.allowed_users and sender_id not in self.allowed_users:
            logger.warning(f"Unauthorized Feishu user_id attempted contact: {sender_id}")
            return
            
        # Feishu standard is replying to open_id by default in 1v1 unless specific chat_id is mapped
        target_reply_id = sender_id
            
        inbound = InboundMessage(
            channel=self.name,
            chat_id=target_reply_id,
            content=text,
        )
        
        await self.bus.inbound.put(inbound)
        logger.debug(f"Received Feishu message from {sender_id}: {text[:50]}")
