"""Content audit tool for checking game content compliance."""

from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

from kubemin_agent.agent.tools.base import Tool
from kubemin_agent.agent.tools.browser import BrowserTool

if TYPE_CHECKING:
    from playwright.async_api import Page

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
    Audits web page content for compliance.

    Extracts text and images from the current page,
    checks for sensitive content, and reports findings.
    """

    def __init__(self, browser_tool: BrowserTool) -> None:
        self._browser_tool = browser_tool
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

        page = self._browser_tool.page
        if page is None:
            return "Error: No browser page is open. Use browser_action with 'navigate' first."

        try:
            results: list[str] = []
            results.append(f"Content Audit Report - {page.url}")
            results.append(f"Check type: {check_type}")
            results.append("---")

            if check_type in ("text", "all"):
                text_result = await self._audit_text(page)
                results.append(text_result)

            if check_type in ("images", "all"):
                image_result = await self._audit_images(page)
                results.append(image_result)

            return "\n\n".join(results)

        except Exception as e:
            return f"Audit error: {type(e).__name__}: {str(e)}"

    async def _audit_text(self, page: Page) -> str:
        """Audit text content on the page."""
        text = await page.inner_text("body")
        lines: list[str] = ["[Text Audit]"]
        lines.append(f"Total text length: {len(text)} chars")

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

    async def _audit_images(self, page: Page) -> str:
        """Audit images on the page."""
        images = await page.evaluate("""
            () => {
                const imgs = document.querySelectorAll('img');
                return Array.from(imgs).map(img => ({
                    src: img.src,
                    alt: img.alt || '',
                    width: img.naturalWidth,
                    height: img.naturalHeight,
                }));
            }
        """)

        lines: list[str] = ["[Image Audit]"]
        lines.append(f"Total images found: {len(images)}")

        if not images:
            lines.append("No images on page.")
            return "\n".join(lines)

        # Check for missing alt text
        missing_alt = [img for img in images if not img.get("alt")]
        if missing_alt:
            lines.append(f"Images missing alt text: {len(missing_alt)}")

        # List images
        for i, img in enumerate(images[:MAX_IMAGE_LIST]):  # Cap at MAX_IMAGE_LIST
            src = img.get("src", "")
            alt = img.get("alt", "")
            w, h = img.get("width", 0), img.get("height", 0)
            lines.append(f"  [{i+1}] {w}x{h} alt='{alt}' src={src[:100]}")

        if len(images) > MAX_IMAGE_LIST:
            lines.append(f"  ... and {len(images) - MAX_IMAGE_LIST} more")

        return "\n".join(lines)
