"""Browser automation tool using Playwright for web game testing."""

from __future__ import annotations

import asyncio
from typing import Any, TYPE_CHECKING

from loguru import logger

from kubemin_agent.agent.tools.base import Tool

if TYPE_CHECKING:
    from playwright.async_api import Page


MAX_CONTENT_LENGTH = 4000
MAX_EVAL_RESULT_LENGTH = 2000
DEFAULT_TIMEOUT_MS = 5000
DEFAULT_VIEWPORT = {"width": 1280, "height": 720}
USER_AGENT = "KubeMin-Agent GameTestBot/1.0"


class BrowserTool(Tool):
    """
    Browser automation via Playwright.

    Provides actions to navigate, click, type, scroll, wait,
    and evaluate JavaScript on web pages.
    """

    def __init__(self) -> None:
        self._browser = None
        self._context = None
        self._page = None

    @property
    def name(self) -> str:
        return "browser_action"

    @property
    def description(self) -> str:
        return (
            "Perform browser actions on a web page for game testing. "
            "Supports: navigate to URL, click elements, type text, scroll, wait, "
            "evaluate JavaScript, and get page content. "
            "The browser persists across calls within the same session."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["navigate", "click", "type", "scroll", "wait", "evaluate", "content"],
                    "description": (
                        "Action to perform: "
                        "navigate (go to URL), "
                        "click (click element), "
                        "type (type into input), "
                        "scroll (scroll page), "
                        "wait (wait for selector/time), "
                        "evaluate (run JavaScript), "
                        "content (get page text content)"
                    ),
                },
                "url": {
                    "type": "string",
                    "description": "URL to navigate to (for 'navigate' action)",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector for the target element (for click/type/wait)",
                },
                "value": {
                    "type": "string",
                    "description": "Text to type (for 'type'), JS code (for 'evaluate'), or scroll direction (for 'scroll': up/down)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds (default: 5000)",
                },
            },
            "required": ["action"],
        }

    async def _ensure_browser(self) -> None:
        """Launch browser if not already running."""
        if self._page is not None:
            return

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError("playwright is not installed. Run: pip install playwright && playwright install chromium")

        pw = await async_playwright().start()
        self._browser = await pw.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            viewport=DEFAULT_VIEWPORT,
            user_agent=USER_AGENT,
        )
        self._page = await self._context.new_page()
        logger.info("Browser launched for game testing")

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]
        url = kwargs.get("url", "")
        selector = kwargs.get("selector", "")
        value = kwargs.get("value", "")
        timeout = kwargs.get("timeout", DEFAULT_TIMEOUT_MS)

        try:
            await self._ensure_browser()
        except RuntimeError as e:
            return f"Error: {str(e)}"

        try:
            if action == "navigate":
                if not url:
                    return "Error: 'url' is required for navigate action"
                await self._page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                title = await self._page.title()
                return f"Navigated to: {url}\nTitle: {title}\nURL: {self._page.url}"

            elif action == "click":
                if not selector:
                    return "Error: 'selector' is required for click action"
                await self._page.click(selector, timeout=timeout)
                await asyncio.sleep(0.3)
                return f"Clicked: {selector}"

            elif action == "type":
                if not selector:
                    return "Error: 'selector' is required for type action"
                await self._page.fill(selector, value, timeout=timeout)
                return f"Typed '{value}' into: {selector}"

            elif action == "scroll":
                direction = value.lower() if value else "down"
                delta = -500 if direction == "up" else 500
                await self._page.mouse.wheel(0, delta)
                await asyncio.sleep(0.3)
                return f"Scrolled {direction}"

            elif action == "wait":
                if selector:
                    await self._page.wait_for_selector(selector, timeout=timeout)
                    return f"Element found: {selector}"
                else:
                    wait_ms = timeout if timeout else 1000
                    await asyncio.sleep(wait_ms / 1000)
                    return f"Waited {wait_ms}ms"

            elif action == "evaluate":
                if not value:
                    return "Error: 'value' (JavaScript code) is required for evaluate action"
                result = await self._page.evaluate(value)
                return f"Result: {str(result)[:MAX_EVAL_RESULT_LENGTH]}"

            elif action == "content":
                text = await self._page.inner_text("body")
                if len(text) > MAX_CONTENT_LENGTH:
                    text = text[:MAX_CONTENT_LENGTH] + f"\n... [truncated, total {len(text)} chars]"
                return f"Page content:\n{text}"

            else:
                return f"Error: Unknown action '{action}'"

        except Exception as e:
            return f"Browser error ({action}): {type(e).__name__}: {str(e)}"

    async def close(self) -> None:
        """Close the browser."""
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._context = None
            self._page = None
            logger.info("Browser closed")

    @property
    def page(self) -> Page | None:
        """Access the current page (for screenshot tool)."""
        return self._page
