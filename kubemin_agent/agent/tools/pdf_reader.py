"""PDF reader tool for extracting text from gameplay guides."""

from pathlib import Path
from typing import Any

from kubemin_agent.agent.tools.base import Tool


class PDFReaderTool(Tool):
    """
    Reads and extracts text from PDF files.

    Used primarily for reading gameplay guides before testing.
    """

    @property
    def name(self) -> str:
        return "read_pdf"

    @property
    def description(self) -> str:
        return (
            "Read and extract text content from a PDF file. "
            "Use this to read gameplay guides or test documentation before testing a game."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the PDF file to read",
                },
                "page_range": {
                    "type": "string",
                    "description": "Optional page range, e.g. '1-5' or '3'. Reads all pages if omitted.",
                },
            },
            "required": ["file_path"],
        }

    async def execute(self, **kwargs: Any) -> str:
        file_path = kwargs["file_path"]
        page_range = kwargs.get("page_range", "")

        path = Path(file_path)
        if not path.exists():
            return f"Error: File not found: {file_path}"
        if not path.suffix.lower() == ".pdf":
            return f"Error: Not a PDF file: {file_path}"

        try:
            import pymupdf
        except ImportError:
            return "Error: pymupdf is not installed. Run: pip install pymupdf"

        try:
            doc = pymupdf.open(str(path))
            total_pages = len(doc)

            # Parse page range
            start_page, end_page = 0, total_pages
            if page_range:
                if "-" in page_range:
                    parts = page_range.split("-")
                    start_page = max(0, int(parts[0]) - 1)
                    end_page = min(total_pages, int(parts[1]))
                else:
                    page_num = int(page_range) - 1
                    start_page = max(0, page_num)
                    end_page = min(total_pages, page_num + 1)

            # Extract text
            text_parts: list[str] = []
            text_parts.append(f"[PDF: {path.name} | Pages: {total_pages}]")

            for page_idx in range(start_page, end_page):
                page = doc[page_idx]
                page_text = page.get_text()
                if page_text.strip():
                    text_parts.append(f"\n--- Page {page_idx + 1} ---\n{page_text.strip()}")

            doc.close()

            result = "\n".join(text_parts)

            # Truncate if too long
            if len(result) > 8000:
                result = result[:8000] + f"\n\n... [truncated, total {len(result)} chars]"

            return result

        except Exception as e:
            return f"Error reading PDF: {type(e).__name__}: {str(e)}"
