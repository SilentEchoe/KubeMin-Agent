"""Content audit tool via Chrome DevTools MCP."""

from __future__ import annotations

import re
from typing import Any

from kubemin_agent.agent.tools.base import Tool
from kubemin_agent.agent.tools.mcp_client import MCPClient

MAX_TEXT_PREVIEW_LENGTH = 1000
MAX_IMAGE_LIST = 20

# Basic sensitive patterns (expandable)
SENSITIVE_PATTERNS = [
    r"\b(fuck|shit|damn|ass|bitch)\b",
    r"\b(kill\s+yourself|suicide)\b",
    r"\b(gambling|bet\s+real\s+money)\b",
    r"\b(porn|xxx|nsfw)\b",
]


class ContentAuditTool(Tool):
    """
    Audits web page content for compliance via Chrome DevTools MCP.

    Uses take_snapshot for text extraction and evaluate_script
    for image extraction.
    """

    def __init__(self, mcp: MCPClient) -> None:
        self._mcp = mcp
        self._patterns = [re.compile(p, re.IGNORECASE) for p in SENSITIVE_PATTERNS]

    @property
    def name(self) -> str:
        return "audit_content"

    @property
    def description(self) -> str:
        return (
            "Audit the current page content for compliance issues. "
            "Checks for sensitive text, extracts image URLs, and reports findings. "
            "Use this to verify game content meets content policy requirements."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "check_type": {
                    "type": "string",
                    "enum": ["text", "images", "all"],
                    "description": "Type of content to audit: text only, images only, or all",
                },
            },
            "required": ["check_type"],
        }

    async def execute(self, **kwargs: Any) -> str:
        check_type = kwargs["check_type"]

        try:
            results: list[str] = ["Content Audit Report", "---"]

            if check_type in ("text", "all"):
                text_result = await self._audit_text()
                results.append(text_result)

            if check_type in ("images", "all"):
                image_result = await self._audit_images()
                results.append(image_result)

            # Also check console for errors
            if check_type == "all":
                console_result = await self._audit_console()
                results.append(console_result)

            return "\n\n".join(results)

        except Exception as e:
            return f"Audit error: {type(e).__name__}: {str(e)}"

    async def _audit_text(self) -> str:
        """Audit text content via page snapshot."""
        text = await self._mcp.call_tool("take_snapshot", {})

        lines: list[str] = ["[Text Audit]"]
        lines.append(f"Total snapshot length: {len(text)} chars")

        # Check for sensitive patterns
        issues: list[str] = []
        for pattern in self._patterns:
            matches = pattern.findall(text)
            if matches:
                issues.append(f"  - Pattern '{pattern.pattern}' matched: {matches[:5]}")

        if issues:
            lines.append(f"Sensitive content found ({len(issues)} patterns):")
            lines.extend(issues)
        else:
            lines.append("No sensitive content detected.")

        # Text preview
        preview = text[:MAX_TEXT_PREVIEW_LENGTH].strip()
        if len(text) > MAX_TEXT_PREVIEW_LENGTH:
            preview += f"\n... [truncated, total {len(text)} chars]"
        lines.append(f"\nText preview:\n{preview}")

        return "\n".join(lines)

    async def _audit_images(self) -> str:
        """Audit images via JavaScript evaluation."""
        js_code = """() => {
            const imgs = document.querySelectorAll('img');
            return JSON.stringify(Array.from(imgs).map(img => ({
                src: img.src,
                alt: img.alt || '',
                width: img.naturalWidth,
                height: img.naturalHeight,
            })));
        }"""
        raw = await self._mcp.call_tool("evaluate_script", {"function": js_code})

        lines: list[str] = ["[Image Audit]"]

        try:
            import json
            # The MCP response may contain "Result: ..." prefix
            json_str = raw
            if "Result:" in json_str:
                json_str = json_str.split("Result:", 1)[1].strip()
            images = json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            lines.append(f"Could not parse image data. Raw response:\n{raw[:500]}")
            return "\n".join(lines)

        lines.append(f"Total images found: {len(images)}")

        if not images:
            lines.append("No images on page.")
            return "\n".join(lines)

        missing_alt = [img for img in images if not img.get("alt")]
        if missing_alt:
            lines.append(f"Images missing alt text: {len(missing_alt)}")

        for i, img in enumerate(images[:MAX_IMAGE_LIST]):
            src = img.get("src", "")
            alt = img.get("alt", "")
            w, h = img.get("width", 0), img.get("height", 0)
            lines.append(f"  [{i+1}] {w}x{h} alt='{alt}' src={src[:100]}")

        if len(images) > MAX_IMAGE_LIST:
            lines.append(f"  ... and {len(images) - MAX_IMAGE_LIST} more")

        return "\n".join(lines)

    async def _audit_console(self) -> str:
        """Check console for errors and warnings."""
        raw = await self._mcp.call_tool("list_console_messages", {
            "types": ["error", "warning"],
        })

        lines: list[str] = ["[Console Audit]"]
        if raw.strip():
            lines.append(raw[:1000])
        else:
            lines.append("No console errors or warnings.")

        return "\n".join(lines)
