"""Browser automation tool via Chrome DevTools MCP."""

from __future__ import annotations

from typing import Any

from kubemin_agent.agent.tools.base import Tool
from kubemin_agent.agent.tools.mcp_client import MCPClient


MAX_CONTENT_LENGTH = 4000


class BrowserTool(Tool):
    """
    Browser automation via Chrome DevTools MCP.

    Delegates all browser operations to the Chrome DevTools MCP server:
    navigate, click, fill, hover, drag, scroll, wait, evaluate, snapshot,
    console logs, and network requests.
    """

    def __init__(self, mcp: MCPClient) -> None:
        self._mcp = mcp

    @property
    def name(self) -> str:
        return "browser_action"

    @property
    def description(self) -> str:
        return (
            "Perform browser actions on a web page for game testing. "
            "Supports: navigate to URL, click/hover/drag elements (by uid from snapshot), "
            "fill text inputs, scroll, wait for elements, evaluate JavaScript, "
            "get page snapshot (structured text with uids), list console messages, "
            "and list network requests. "
            "IMPORTANT: Before clicking or filling, first use 'snapshot' to get element uids."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "navigate", "click", "fill", "hover", "drag",
                        "scroll", "wait", "evaluate", "snapshot",
                        "press_key", "console_logs", "network",
                    ],
                    "description": (
                        "Action to perform: "
                        "navigate (go to URL), "
                        "click (click element by uid), "
                        "fill (type into input by uid), "
                        "hover (hover element by uid), "
                        "drag (drag element to another by uid), "
                        "scroll (press Page_Down/Page_Up), "
                        "wait (wait for condition), "
                        "evaluate (run JavaScript), "
                        "snapshot (get page content with element uids), "
                        "press_key (press key combo), "
                        "console_logs (get browser console messages), "
                        "network (list network requests)"
                    ),
                },
                "url": {
                    "type": "string",
                    "description": "URL to navigate to (for 'navigate' action)",
                },
                "uid": {
                    "type": "string",
                    "description": "Element uid from page snapshot (for click/fill/hover)",
                },
                "value": {
                    "type": "string",
                    "description": (
                        "Text to fill (for 'fill'), JS code (for 'evaluate'), "
                        "key combo (for 'press_key', e.g. 'Enter', 'Control+A'), "
                        "or scroll direction (for 'scroll': 'up'/'down')"
                    ),
                },
                "to_uid": {
                    "type": "string",
                    "description": "Target element uid for 'drag' action",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds (for 'wait', default: 5000)",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]

        try:
            if action == "navigate":
                url = kwargs.get("url", "")
                if not url:
                    return "Error: 'url' is required for navigate action"
                return await self._mcp.call_tool("navigate_page", {"url": url})

            elif action == "click":
                uid = kwargs.get("uid", "")
                if not uid:
                    return "Error: 'uid' is required. Use 'snapshot' first to get element uids."
                return await self._mcp.call_tool("click", {"uid": uid, "includeSnapshot": True})

            elif action == "fill":
                uid = kwargs.get("uid", "")
                value = kwargs.get("value", "")
                if not uid:
                    return "Error: 'uid' is required. Use 'snapshot' first to get element uids."
                return await self._mcp.call_tool("fill", {"uid": uid, "value": value, "includeSnapshot": True})

            elif action == "hover":
                uid = kwargs.get("uid", "")
                if not uid:
                    return "Error: 'uid' is required."
                return await self._mcp.call_tool("hover", {"uid": uid, "includeSnapshot": True})

            elif action == "drag":
                from_uid = kwargs.get("uid", "")
                to_uid = kwargs.get("to_uid", "")
                if not from_uid or not to_uid:
                    return "Error: 'uid' and 'to_uid' are required for drag."
                return await self._mcp.call_tool("drag", {"from_uid": from_uid, "to_uid": to_uid})

            elif action == "scroll":
                direction = kwargs.get("value", "down").lower()
                key = "Page_Down" if direction != "up" else "Page_Up"
                return await self._mcp.call_tool("press_key", {"key": key})

            elif action == "wait":
                # wait_for expects a description of what to wait for
                value = kwargs.get("value", "page to load")
                timeout = kwargs.get("timeout", 5000)
                return await self._mcp.call_tool("wait_for", {
                    "event": value,
                    "timeout": timeout,
                })

            elif action == "evaluate":
                value = kwargs.get("value", "")
                if not value:
                    return "Error: 'value' (JavaScript code) is required."
                return await self._mcp.call_tool("evaluate_script", {"function": value})

            elif action == "snapshot":
                result = await self._mcp.call_tool("take_snapshot", {})
                if len(result) > MAX_CONTENT_LENGTH:
                    result = result[:MAX_CONTENT_LENGTH] + f"\n... [truncated, total {len(result)} chars]"
                return result

            elif action == "press_key":
                key = kwargs.get("value", "Enter")
                return await self._mcp.call_tool("press_key", {"key": key})

            elif action == "console_logs":
                return await self._mcp.call_tool("list_console_messages", {})

            elif action == "network":
                return await self._mcp.call_tool("list_network_requests", {})

            else:
                return f"Error: Unknown action '{action}'"

        except Exception as e:
            return f"Browser error ({action}): {type(e).__name__}: {str(e)}"
