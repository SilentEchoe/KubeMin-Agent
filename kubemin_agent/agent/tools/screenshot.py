"""Screenshot tool via Chrome DevTools MCP."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from kubemin_agent.agent.tools.base import Tool
from kubemin_agent.agent.tools.mcp_client import MCPClient


class ScreenshotTool(Tool):
    """
    Captures screenshots via Chrome DevTools MCP.

    Saves screenshots to workspace directory.
    """

    def __init__(self, mcp: MCPClient, workspace: Path) -> None:
        self._mcp = mcp
        self._screenshot_dir = workspace / "screenshots"
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "take_screenshot"

    @property
    def description(self) -> str:
        return (
            "Take a screenshot of the current browser page. "
            "Use this to visually verify game state, UI elements, and visual correctness. "
            "Optionally capture a specific element by uid, or the full scrollable page."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Descriptive label for the screenshot, e.g. 'main_menu', 'game_board_after_move'",
                },
                "full_page": {
                    "type": "boolean",
                    "description": "Capture the full scrollable page (default: false, viewport only)",
                },
                "uid": {
                    "type": "string",
                    "description": "Optional element uid to screenshot a specific element",
                },
            },
            "required": ["name"],
        }

    async def execute(self, **kwargs: Any) -> str:
        label = kwargs["name"]
        full_page = kwargs.get("full_page", False)
        uid = kwargs.get("uid")

        try:
            # Generate filepath
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_label = "".join(c if c.isalnum() or c in "_-" else "_" for c in label)
            filename = f"{timestamp}_{safe_label}.png"
            filepath = self._screenshot_dir / filename

            # Build MCP args
            mcp_args: dict[str, Any] = {
                "filePath": str(filepath),
                "format": "png",
            }
            if full_page:
                mcp_args["fullPage"] = True
            if uid:
                mcp_args["uid"] = uid

            result = await self._mcp.call_tool("take_screenshot", mcp_args)

            logger.debug(f"Screenshot saved: {filepath}")
            return f"Screenshot saved: {filepath}\n{result}"

        except Exception as e:
            return f"Screenshot error: {type(e).__name__}: {str(e)}"
