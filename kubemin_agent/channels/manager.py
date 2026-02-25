"""Channel manager for multi-channel orchestration."""

from loguru import logger

from kubemin_agent.bus.events import OutboundMessage
from kubemin_agent.bus.queue import MessageBus
from kubemin_agent.channels.base import BaseChannel


class ChannelManager:
    """
    Manages multiple chat channels.

    Handles channel lifecycle and routes outbound messages to the correct channel.
    """

    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus
        self._channels: dict[str, BaseChannel] = {}

    def register(self, channel: BaseChannel) -> None:
        """Register a channel."""
        self._channels[channel.name] = channel
        self.bus.subscribe_outbound(channel.name, self._route_message(channel))
        logger.info(f"Channel registered: {channel.name}")

    def _route_message(self, channel: BaseChannel):
        """Create a callback to route outbound messages to a channel."""

        async def callback(msg: OutboundMessage) -> None:
            await channel.send_message(msg.chat_id, msg.content)

        return callback

    async def start_all(self) -> None:
        """Start all registered channels."""
        for name, channel in self._channels.items():
            try:
                await channel.start()
                logger.info(f"Channel started: {name}")
            except Exception as e:
                logger.error(f"Failed to start channel {name}: {e}")

    async def stop_all(self) -> None:
        """Stop all registered channels."""
        for name, channel in self._channels.items():
            try:
                await channel.stop()
                logger.info(f"Channel stopped: {name}")
            except Exception as e:
                logger.error(f"Failed to stop channel {name}: {e}")

    @property
    def channel_names(self) -> list[str]:
        """Get list of registered channel names."""
        return list(self._channels.keys())
