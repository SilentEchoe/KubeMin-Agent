"""Screenshot tool for visual state capture during game testing."""

import base64
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from kubemin_agent.agent.tools.base import Tool
from kubemin_agent.agent.tools.browser import BrowserTool


class ScreenshotTool(Tool):
    """
    Captures screenshots from the browser for visual analysis.

    Saves screenshots to workspace and returns base64 data for LLM vision.
    """

    def __init__(self, browser_tool: BrowserTool, workspace: Path) -> None:
        self._browser_tool = browser_tool
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
            "Returns the screenshot file path and a base64-encoded image for analysis."
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
            },
            "required": ["name"],
        }

    async def execute(self, **kwargs: Any) -> str:
        label = kwargs["name"]
        full_page = kwargs.get("full_page", False)

        page = self._browser_tool.page
        if page is None:
            return "Error: No browser page is open. Use browser_action with 'navigate' first."

        try:
            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_label = "".join(c if c.isalnum() or c in "_-" else "_" for c in label)
            filename = f"{timestamp}_{safe_label}.png"
            filepath = self._screenshot_dir / filename

            # Take screenshot
            screenshot_bytes = await page.screenshot(
                path=str(filepath),
                full_page=full_page,
            )

            # Encode to base64
            b64_data = base64.b64encode(screenshot_bytes).decode("utf-8")

            # Truncate base64 for the response (LLM doesn't need the full thing in text)
            b64_preview = b64_data[:100] + "..." if len(b64_data) > 100 else b64_data

            logger.debug(f"Screenshot saved: {filepath}")

            return (
                f"Screenshot saved: {filepath}\n"
                f"Size: {len(screenshot_bytes)} bytes\n"
                f"Full page: {full_page}\n"
                f"Base64 preview: {b64_preview}\n"
                f"Page URL: {page.url}\n"
                f"Page title: {await page.title()}"
            )

        except Exception as e:
            return f"Screenshot error: {type(e).__name__}: {str(e)}"
