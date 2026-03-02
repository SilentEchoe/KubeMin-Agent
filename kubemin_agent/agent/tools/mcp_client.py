"""MCP client for Chrome DevTools MCP server connection."""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

from loguru import logger


class MCPClient:
    """
    Manages connection to Chrome DevTools MCP server via stdio transport.

    Spawns `npx chrome-devtools-mcp@latest --headless` as a subprocess
    and communicates via JSON-RPC over stdin/stdout.
    """

    def __init__(self, headless: bool = True, no_sandbox: bool | None = None) -> None:
        self._headless = headless
        self._no_sandbox = no_sandbox if no_sandbox is not None else self._detect_container()
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._initialized = False

    @staticmethod
    def _detect_container() -> bool:
        """Check if unsafe sandbox bypass is explicitly requested via environment variable."""
        return os.environ.get("UNSAFE_ALLOW_NO_SANDBOX") == "1"

    async def start(self) -> None:
        """Start the Chrome DevTools MCP server subprocess."""
        if self._process is not None:
            return

        npx_path = shutil.which("npx")
        if not npx_path:
            raise RuntimeError(
                "npx not found. Please install Node.js >= 20.19: https://nodejs.org/"
            )

        args = [npx_path, "-y", "chrome-devtools-mcp@latest"]
        if self._headless:
            args.append("--headless")
        if self._no_sandbox:
            args.append("--no-sandbox")

        logger.info(f"Starting Chrome DevTools MCP: {' '.join(args)}")

        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Start background reader
        self._reader_task = asyncio.create_task(self._read_responses())

        # Initialize MCP session
        await self._initialize()
        logger.info("Chrome DevTools MCP server started and initialized")

    async def _initialize(self) -> None:
        """Send MCP initialize handshake."""
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "kubemin-agent", "version": "0.1.0"},
        })
        logger.debug(f"MCP server info: {result.get('serverInfo', {})}")

        # Send initialized notification
        await self._send_notification("notifications/initialized", {})
        self._initialized = True

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        """
        Call a Chrome DevTools MCP tool.

        Args:
            name: Tool name (e.g., 'navigate_page', 'click', 'take_screenshot').
            arguments: Tool-specific arguments.

        Returns:
            Tool result as string.
        """
        if not self._initialized:
            await self.start()

        result = await self._send_request("tools/call", {
            "name": name,
            "arguments": arguments or {},
        })

        # Extract text content from MCP response
        content_parts = result.get("content", [])
        texts: list[str] = []
        for part in content_parts:
            if part.get("type") == "text":
                texts.append(part.get("text", ""))
            elif part.get("type") == "image":
                texts.append(f"[image: {part.get('mimeType', 'unknown')}]")

        return "\n".join(texts) if texts else str(result)

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools from the MCP server."""
        if not self._initialized:
            await self.start()

        result = await self._send_request("tools/list", {})
        return result.get("tools", [])

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for response."""
        import json

        if self._process is None or self._process.stdin is None:
            raise RuntimeError("MCP server not started")

        self._request_id += 1
        request_id = self._request_id

        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        line = json.dumps(message) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            raise RuntimeError(f"MCP request timed out: {method}")

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        import json

        if self._process is None or self._process.stdin is None:
            raise RuntimeError("MCP server not started")

        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        line = json.dumps(message) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

    async def _read_responses(self) -> None:
        """Background task to read JSON-RPC responses from stdout."""
        import json

        if self._process is None or self._process.stdout is None:
            return

        while True:
            try:
                line = await self._process.stdout.readline()
                if not line:
                    break

                data = json.loads(line.decode().strip())

                # Handle response
                if "id" in data and data["id"] in self._pending:
                    future = self._pending.pop(data["id"])
                    if "error" in data:
                        future.set_exception(
                            RuntimeError(f"MCP error: {data['error']}")
                        )
                    else:
                        future.set_result(data.get("result", {}))
                # Notifications are logged but not processed
                elif "method" in data and "id" not in data:
                    logger.debug(f"MCP notification: {data['method']}")

            except Exception as e:
                logger.warning(f"MCP reader error: {e}")
                break

    async def stop(self) -> None:
        """Stop the MCP server subprocess."""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
            self._process = None

        self._pending.clear()
        self._initialized = False
        logger.info("Chrome DevTools MCP server stopped")
