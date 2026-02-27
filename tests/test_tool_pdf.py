"""Tests for PDFReaderTool."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kubemin_agent.agent.tools.pdf_reader import PDFReaderTool


@pytest.fixture
def workspace(tmp_path: Path):
    """Temporary workspace."""
    return tmp_path


@pytest.fixture
def valid_pdf(workspace):
    """Create a dummy file with .pdf extension."""
    pdf_path = workspace / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\ndummy content")
    return pdf_path


def test_pdf_tool_properties():
    """Test standard tool properties."""
    tool = PDFReaderTool()
    assert tool.name == "read_pdf"
    assert "file_path" in tool.parameters["properties"]
    assert "page_range" in tool.parameters["properties"]


@pytest.mark.asyncio
async def test_pdf_tool_file_not_found():
    """Test execution when file doesn't exist."""
    tool = PDFReaderTool()
    result = await tool.execute(file_path="/does/not/exist.pdf")
    assert "Error: File not found" in result


@pytest.mark.asyncio
async def test_pdf_tool_not_pdf(workspace):
    """Test execution when file is not a PDF."""
    txt_file = workspace / "test.txt"
    txt_file.write_text("hello")
    
    tool = PDFReaderTool()
    result = await tool.execute(file_path=str(txt_file))
    assert "Error: Not a PDF file" in result


@pytest.mark.asyncio
async def test_pdf_tool_success_all_pages(valid_pdf):
    """Test successful extraction of all pages."""
    mock_pymupdf = MagicMock()
    # Mock Document and Pages
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 2
    
    mock_page1 = MagicMock()
    mock_page1.get_text.return_value = "Content of page 1"
    
    mock_page2 = MagicMock()
    mock_page2.get_text.return_value = "Content of page 2"
    
    # Mock __getitem__ for pages
    mock_doc.__getitem__.side_effect = lambda idx: [mock_page1, mock_page2][idx]
    
    mock_pymupdf.open.return_value = mock_doc
    
    with patch.dict("sys.modules", {"pymupdf": mock_pymupdf}):
        tool = PDFReaderTool()
        result = await tool.execute(file_path=str(valid_pdf))
    
    mock_pymupdf.open.assert_called_once_with(str(valid_pdf))
    assert "[PDF: test.pdf | Pages: 2]" in result
    assert "Content of page 1" in result
    assert "Content of page 2" in result
    mock_doc.close.assert_called_once()


@pytest.mark.asyncio
async def test_pdf_tool_success_page_range(valid_pdf):
    """Test extraction with specific page range."""
    mock_pymupdf = MagicMock()
    mock_doc = MagicMock()
    mock_doc.__len__.return_value = 5
    
    mock_page = MagicMock()
    mock_page.get_text.return_value = "Target page content"
    mock_doc.__getitem__.return_value = mock_page
    
    mock_pymupdf.open.return_value = mock_doc
    
    with patch.dict("sys.modules", {"pymupdf": mock_pymupdf}):
        tool = PDFReaderTool()
        
        # Range test: "2-4"
        result1 = await tool.execute(file_path=str(valid_pdf), page_range="2-4")
        assert "Target page content" in result1
        # Check that it accessed indices 1, 2, 3 (which correspond to pages 2, 3, 4)
        # The __getitem__ should have been called 3 times
        assert mock_doc.__getitem__.call_count == 3
        
        # Single page test: "3"
        mock_doc.__getitem__.reset_mock()
        result2 = await tool.execute(file_path=str(valid_pdf), page_range="3")
        assert "Target page content" in result2
    assert mock_doc.__getitem__.call_count == 1
    mock_doc.__getitem__.assert_called_with(2)  # Index 2 is page 3


@pytest.mark.asyncio
async def test_pdf_tool_exception_handling(valid_pdf):
    """Test that runtime exceptions during parsing are caught."""
    mock_pymupdf = MagicMock()
    mock_pymupdf.open.side_effect = Exception("Corrupt PDF dictionary")
    
    with patch.dict("sys.modules", {"pymupdf": mock_pymupdf}):
        tool = PDFReaderTool()
        result = await tool.execute(file_path=str(valid_pdf))
    
    assert "Error reading PDF: Exception: Corrupt PDF dictionary" in result
